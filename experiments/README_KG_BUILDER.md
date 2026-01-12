# Darshan Knowledge Graph Builder

This tool converts Darshan signal extraction output files into LightRAG's custom Knowledge Graph format for incident-level analysis and retrieval.

## Overview

The Darshan KG Builder processes Darshan log files (txt format) and constructs a knowledge graph with exactly 4 node types designed to support:
- **Incident-level retrieval**: Each I/O record becomes a queryable incident
- **Downstream computation**: All signal values preserved as node attributes
- **Explainable answers**: Graph connectivity based on comparability (same app, filesystem, module)

## Graph Schema

### Node Types (Exactly 4)

#### 1. Job
- **Entity Name**: `Job_{jobid}`
- **Attributes**:
  - `job_id`: Darshan job identifier
  - `nprocs`: Number of processes
  - `runtime`: Total execution time (seconds)
  - `exe`: Executable identifier
  - `start_time`: Job start timestamp
  - `end_time`: Job end timestamp
- **Example**: `Job_3122490`

#### 2. Incident
- **Entity Name**: `Incident_{module}_{record_id}_rank{rank}`
- **Attributes**:
  - `module`: HEATMAP | POSIX | STDIO | MPIIO
  - `rank`: MPI rank
  - `record_id`: Darshan record identifier
  - All `SIGNAL_*` values as attributes (e.g., `total_read_events`, `read_bandwidth_avg`)
  - Optional: `fs_type`, `mount_pt` (for POSIX/STDIO/MPIIO only)
- **Example**: `Incident_POSIX_12345_rank0`
- **Design Principle**: One incident = one Darshan record = minimum retrievable unit

#### 3. FileSystem
- **Entity Name**: `FS_{fs_type}_{mount_pt_safe}`
- **Attributes**:
  - `fs_type`: Filesystem type (e.g., lustre, nfs, ext4)
  - `mount_pt`: Mount point path
- **Example**: `FS_lustre__home`
- **Uniqueness**: Based on (fs_type, mount_pt) combination

#### 4. Application
- **Entity Name**: `App_{exe}`
- **Attributes**:
  - `exe`: Executable identifier
- **Example**: `App_4068766220`
- **Uniqueness**: One node per unique executable

### Edge Types

#### 1. HAS_INCIDENT (Job → Incident)
- **Keywords**: `job incident module`
- **Weight**: 1.0
- **Created for**: Every incident in the job

#### 2. ON_FS (Incident → FileSystem)
- **Keywords**: `incident filesystem io_pattern`
- **Weight**: 1.0
- **Created only when**:
  - Module is POSIX, STDIO, or MPIIO (NOT HEATMAP)
  - `fs_type` is present and not "UNKNOWN"
  - `mount_pt` is present and not "UNKNOWN"

#### 3. RUNS (Job → Application)
- **Keywords**: `job application executable`
- **Weight**: 1.0
- **Created for**: Every job-application pair

#### 4. BELONGS_TO (Incident → Application)
- **Keywords**: `incident application executable`
- **Weight**: 1.0
- **Created for**: Every incident in the job

## Usage

### Command Line

```bash
# Single file
python experiments/darshan_kg_builder.py \
  -i data/examples/Darshan_log_example_signals_v2.2.txt \
  -o output_kg.json

# Directory with txt files
python experiments/darshan_kg_builder.py \
  -i /path/to/logs_directory \
  -o output_kg.json

# Parent directory with subdirectories
python experiments/darshan_kg_builder.py \
  -i /path/to/parent_directory \
  -o output_kg.json
```

### Python API

```python
from darshan_kg_builder import DarshanKGBuilder

# Initialize builder
builder = DarshanKGBuilder()

# Parse single file
builder.parse_darshan_signal_file("path/to/log.txt")

# Or parse directory
builder.parse_darshan_directory("/path/to/logs")

# Build LightRAG custom KG
kg = builder.build_lightrag_kg(
    source_id="my-darshan-logs",
    file_path="/path/to/logs"
)

# Save to JSON
import json
with open("output_kg.json", "w") as f:
    json.dump(kg, f, indent=2)
```

### Integration with LightRAG

```python
import json
from lightrag import LightRAG

# Load the generated KG
with open("output_kg.json", "r") as f:
    custom_kg = json.load(f)

# Initialize LightRAG
rag = LightRAG(
    working_dir="./darshan_rag_storage",
    embedding_func=openai_embed,
    llm_model_func=gpt_4o_mini_complete,
)

# Insert the custom KG
await rag.ainsert_custom_kg(custom_kg)

# Query incidents
result = await rag.aquery(
    "Which incidents had high read bandwidth on Lustre filesystem?",
    param=QueryParam(mode="hybrid")
)
```

## Example Output Statistics

For `Darshan_log_example_signals_v2.2.txt`:
- **Entities**: 43 total
  - 1 Job node
  - 1 Application node
  - 1 FileSystem node
  - 40 Incident nodes (10 HEATMAP + 30 POSIX)
- **Relationships**: 113 total
  - 40 HAS_INCIDENT edges
  - 30 ON_FS edges (only POSIX incidents)
  - 1 RUNS edge
  - 40 BELONGS_TO edges
  - 2 Incident-Incident edges (same module/fs/app)

## Input Format

The tool expects Darshan signal extraction output format v2.2:

```
# jobid: 3122490
# nprocs: 4
# run time: 7451.1501
# exe: 4068766220
# start_time: 1735781151
# end_time: 1735788602

# mount point	fs type
# /home	lustre

# MODULE: HEATMAP
# RECORD: 16592106915301738621 (rank=0)
HEATMAP	0	16592106915301738621	SIGNAL_TOTAL_READ_EVENTS	1056203.0
HEATMAP	0	16592106915301738621	SIGNAL_TOTAL_WRITE_EVENTS	0.0
...

# MODULE: POSIX
# RECORD: 12345 (rank=0, mount=/home, fs=lustre)
POSIX	0	12345	SIGNAL_READ_BANDWIDTH_AVG	123.45
...
```

## Design Rationale

### Why These 4 Node Types?

1. **Job**: Represents the top-level execution context
2. **Incident**: Each record is independently retrievable for fine-grained analysis
3. **FileSystem**: Groups incidents by storage backend for performance comparison
4. **Application**: Groups incidents by executable for workload characterization

### Why Signals Are Attributes, Not Nodes?

- **Incident-level retrieval**: User queries focus on "incidents with high bandwidth", not "bandwidth nodes"
- **Downstream computation**: Raw signal values needed for aggregation (avg, max, percentile)
- **Explainability**: Graph edges show relationships (same app/fs), not signal similarity
- **Scalability**: Avoiding millions of signal nodes keeps the graph manageable

### Why Connectivity = Comparability?

Graph edges connect incidents that are **meaningfully comparable**:
- Same Application → Same workload characteristics
- Same FileSystem → Same storage performance context
- Same Module → Same I/O abstraction level

This enables queries like:
- "Compare read patterns across ranks for this job"
- "Find incidents with similar I/O characteristics on Lustre"
- "Analyze POSIX-level performance for this application"

## Query Examples

```python
# Find high-bandwidth incidents
"Which incidents had read bandwidth over 1000 MB/s?"

# Filesystem comparison
"Compare average write bandwidth between Lustre and NFS filesystems"

# Application analysis
"What are the common I/O patterns for application 4068766220?"

# Rank-level debugging
"Which rank had the highest write activity entropy in job 3122490?"

# Module-level insights
"Show all POSIX incidents with more than 1000 read operations"
```

## Troubleshooting

### No entities generated
- Check that input file follows Darshan signal extraction v2.2 format
- Verify job metadata header is present (`# jobid:`, `# nprocs:`, etc.)
- Ensure at least one MODULE section exists

### Missing filesystem relationships
- ON_FS edges only created for POSIX/STDIO/MPIIO modules
- HEATMAP incidents intentionally have no filesystem relationships
- Check that mount table is present and fs_type/mount_pt are not "UNKNOWN"

### Signal values are "NA"
- Some signals may be undefined (division by zero, no activity)
- These are preserved as string "NA(...)" to maintain data integrity
- Filter these in downstream queries if needed

## Implementation Notes

- **Regex-based parsing**: Robust to minor format variations
- **Type conversion**: Automatic detection of int/float/string values
- **Memory efficient**: Streams large log files without loading entire content
- **Batch processing**: Handles directories with hundreds of log files
- **LightRAG compatible**: Output format exactly matches expected schema
