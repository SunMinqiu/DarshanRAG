# Darshan I/O GraphRAG Workflow

A comprehensive workflow for analyzing HPC I/O performance using Darshan logs with Graph-based Retrieval Augmented Generation (GraphRAG).

## Overview

This project provides tools to:
1. Parse Darshan I/O profiling logs
2. Build a knowledge graph from parsed logs
3. Query the graph using natural language with LLM integration
4. Analyze I/O patterns, efficiency issues, and performance bottlenecks

## Prerequisites

- Python 3.12+
- Darshan tools (`darshan-parser`)
- OpenAI API key
- Required Python packages: `openai`, `networkx`, `asyncio`

## Workflow

### Step 1: Setup

```python
%cd pocket-rag

import os
os.environ["OPENAI_API_KEY"] = "your-api-key-here"
```

### Step 2: Parse Darshan Logs

Unpack and parse raw Darshan log files (`.darshan`) into human-readable text format:

```bash
# Unpack compressed logs
./unpack-darshan-logs.sh /path/to/darshan/logs

# Parse logs using darshan-parser
mkdir -p ~/parsed-logs
ls /path/to/logs/*.darshan* | parallel 'darshan-parser {} > ~/parsed-logs/{/.}.txt'
```

### Step 3: Build Knowledge Graph

Create a knowledge graph from parsed Darshan logs:

```bash
python cookbook/07_darshan_graph_rag.py --input_path /path/to/parsed-logs -o graph_output.json
```

This generates a JSON file containing:
- **Nodes**: Jobs, Ranks, Files, MountPoints, FileSystems, JobIOSummaries
- **Edges**: HAS_RANK, USES_FILE, HAS_SUMMARY, IO_POSIX, MOUNTED_ON, ON_FS

### Step 4: Initialize GraphRAG

```python
from openai import AsyncOpenAI
from cookbook.neo4j_graph_rag import (
    create_graph_backend,
    DarshanGraphDB,
    DarshanGraphRAG
)

# Setup OpenAI LLM
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

async def openai_llm(messages, model="gpt-4o-mini"):
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7
    )
    return response.choices[0].message.content

# Create backend and load graph
backend = create_graph_backend('networkx', persist_path='darshan_graph_nx.json')
await backend.connect()

graph_db = DarshanGraphDB(backend)
await graph_db.load_from_json('graph_output.json')

# Create GraphRAG with LLM
rag = DarshanGraphRAG(backend, llm_func=openai_llm, model="gpt-4o-mini")
```

### Step 5: Query the Graph

#### Natural Language Queries

```python
# Ask questions about I/O patterns
question = "Which file systems did Job 3122490 use? How much data did it read and write?"
result = await rag.query(question, context_depth=2)
print(result['answer'])

# Analyze I/O efficiency
question = "Which jobs have low I/O efficiency? Why?"
result = await rag.query(question, context_depth=2)
print(result['answer'])
```

#### Job Summary Queries

```python
job_summary = await rag.query_job_summary("3122490")
print(f"Files accessed: {len(job_summary['files'])}")
print(f"Ranks used: {len(job_summary['ranks'])}")
print(f"I/O Summary: {job_summary['summary']}")
```

#### File Access Pattern Analysis

```python
file_analysis = await rag.query_file_access_pattern("File:/lus/grand/1649248601")
print(f"Jobs accessed: {file_analysis['accessed_by_jobs']}")
print(f"Filesystem: {file_analysis['filesystem']}")
```

## Direct Analysis Tools

### Analyze Darshan Reports

Sum up I/O bytes from parsed logs:

```python
import os
import glob
from collections import defaultdict

POSIX_READ = "POSIX_BYTES_READ"
POSIX_WRITE = "POSIX_BYTES_WRITTEN"

def analyze_darshan_reports(report_dir):
    """Analyze multiple darshan reports from a directory."""
    if os.path.isdir(report_dir):
        paths = sorted(glob.glob(os.path.join(report_dir, "*")))
        paths = [p for p in paths if os.path.isfile(p)]
    else:
        paths = sorted(glob.glob(report_dir))
    
    global_read = 0
    global_write = 0
    global_file_io = defaultdict(int)

    for path in paths:
        # Parse each file for POSIX_BYTES_READ/WRITTEN
        ...
    
    return {
        "total_read_bytes": global_read,
        "total_write_bytes": global_write,
        "max_io_file": max_file,
        "max_io_bytes": max_io
    }

# Usage
result = analyze_darshan_reports("/path/to/parsed-logs")
print(f"Total Reads: {result['total_read_bytes']:,} bytes")
print(f"Total Writes: {result['total_write_bytes']:,} bytes")
print(f"Largest I/O File: {result['max_io_file']}")
```

### Sum Total Bytes Across Reports

```python
def sum_total_bytes(folder_or_pattern):
    """Sum total_bytes across multiple darshan reports."""
    # Supports both:
    # 1. Summary format: '# total_bytes: value'
    # 2. Parsed darshan format: POSIX_BYTES_READ/WRITTEN entries
    ...
    return total, per_report, max_file, max_bytes

# Usage
total, per_report, max_file, max_bytes = sum_total_bytes("/path/to/parsed-logs")
print(f"Global Total I/O: {total:,} bytes")
print(f"Max I/O File: {max_file}")
print(f"Max I/O Bytes: {max_bytes:,} bytes")
```

## Graph Structure

### Node Types

| Type | Description |
|------|-------------|
| Job | HPC job with ID and number of processes |
| Rank | MPI rank within a job |
| File | File accessed during job execution |
| MountPoint | File system mount point |
| FileSystem | File system type (lustre, ext4, etc.) |
| JobIOSummary | Aggregated I/O statistics for a job |

### Edge Types

| Type | Description |
|------|-------------|
| HAS_RANK | Job -> Rank relationship |
| USES_FILE | Job/Rank -> File relationship |
| HAS_SUMMARY | Job -> JobIOSummary relationship |
| IO_POSIX | Rank -> File I/O operations |
| MOUNTED_ON | File -> MountPoint relationship |
| ON_FS | MountPoint -> FileSystem relationship |

## Example Queries

### I/O Efficiency Analysis

```python
questions = [
    "Which job has the largest I/O? What are its characteristics?",
    "Are there any jobs with small I/O problems?",
    "What file systems did all jobs use?",
    "Which files have the largest I/O? What are their characteristics?",
    "Group jobs into clusters with similar I/O characteristics"
]

for q in questions:
    result = await rag.query(q, context_depth=2)
    print(f"Q: {q}")
    print(f"A: {result['answer']}\n")
```

### I/O Efficiency Indicators

The system analyzes these key indicators:

1. **Small I/O Operations** (<4KB average) - Indicates inefficient access patterns
2. **High Seek Ratios** - Random access causing performance degradation
3. **Imbalanced I/O Across Ranks** - Synchronization bottlenecks
4. **Many Files Accessed** - Potential metadata overhead

## Output Example

```
===== Darshan I/O Summary =====
Total Reads : 2,785,328,751,890 bytes
Total Writes: 13,919,745,410,209 bytes
Largest I/O File:
  File : /lus/grand/2431195864
  I/O  : 2,783,344,493,776 bytes

Graph Statistics:
  Total nodes: 3565
  Total edges: 35438
  Node types: {'Job': 67, 'Rank': 302, 'File': 3087, 'MountPoint': 26, 'FileSystem': 16, 'JobIOSummary': 67}
```

## File Structure

```
.
├── pocket-rag/
│   └── cookbook/
│       ├── 07_darshan_graph_rag.py    # Build graph from logs
│       ├── 08_real_graph_rag_example.py  # GraphRAG demo
│       ├── neo4j_graph_rag.py         # Core GraphRAG implementation
│       ├── query_darshan_graph.py     # Interactive query tool
│       └── index_darshan_logs.py      # Vector DB indexing
├── parsed-logs-2025-1-1/              # Parsed Darshan log files
├── graph_2025-1-1.json                # Generated knowledge graph
├── darshan_graph_nx.json              # NetworkX persisted graph
├── IORAG.ipynb                        # Main analysis notebook
└── README.md                          # This file
```

## Tips

1. **Large Datasets**: For large log collections, increase `context_depth` for more comprehensive answers
2. **Specific Queries**: Include job IDs or file paths in queries for targeted analysis
3. **Performance**: Use the direct analysis tools for simple aggregations instead of LLM queries
4. **Caching**: The NetworkX backend persists to JSON for faster subsequent loads

## License

MIT License



