# IORAG: LightRAG-based Knowledge Graph System for Darshan Logs

> **IO + RAG = IORAG**: Transform Darshan I/O logs into a hybrid Graph+Vector database for intelligent querying and anomaly detection

## 📋 Table of Contents

- [Project Overview](#project-overview)
- [Complete Workflow](#complete-workflow)
- [Core Scripts](#core-scripts)
- [Signal Computation Specifications](#signal-computation-specifications)
- [Design Philosophy](#design-philosophy)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)

---

## Project Overview

### 🎯 Objectives

Using the LightRAG framework, transform Darshan I/O logs into a **Graph + Vector** hybrid knowledge base to enable:

1. **Intelligent Retrieval**: Query I/O behavior using natural language ("Which files have bandwidth over 1GB/s?")
2. **Anomaly Detection**: Identify I/O performance anomaly patterns (random access, metadata-intensive, load imbalance, etc.)
3. **Relationship Reasoning**: Understand the hierarchical relationships: Application → Job → Module → Record → File → FileSystem
4. **Explainability**: Generate natural language descriptions for each entity for human understanding

### 🏗️ Architecture

```
Raw Darshan Log (.darshan)
         ↓
   [darshan-parser]
         ↓
  Parsed Log (.txt)
         ↓
[process_darshan_signals_v2.4.py]  ← Compute signals
         ↓
  Signal File (*_signals_v2.4.txt)
         ↓
[darshan_kg_builder_v2.1.py]  ← Build KG
         ↓
  KG JSON (*_kg.json)
         ↓
[generate_descriptions_v3.py]  ← Add descriptions
         ↓
  KG with Descriptions (*_kg_with_desc.json)
         ↓
[parse_darshan_chunks.py]  ← Add chunks
         ↓
  KG with Chunks (*_kg_with_chunks.json)
         ↓
[embed_kg_local.py]  ← Generate embeddings
         ↓
  Embeddings (entity & relation vectors)
         ↓
[load_custom_kg_to_lightrag.py]  ← Load to LightRAG
         ↓
   LightRAG Instance
         ↓
  [Query with Natural Language] 🎯
```

---

## Complete Workflow

### Stage 0: Prepare Raw Logs

```bash
# Unpack Darshan logs
chmod +x scripts/unpack-darshan-logs.sh
./scripts/unpack-darshan-logs.sh /path/to/darshan-logs-tarball/
```

**Input**: `logs.tar.gz` (containing multiple `.darshan` files)
**Output**: Extracted `.darshan` files

### Stage 1: Parse Logs to Text

```bash
# Parse binary logs using darshan-parser
darshan-parser input.darshan > output.txt
```

**Input**: `.darshan` binary file
**Output**: Text format counter data

### Stage 2: Compute Signals

```bash
python3 scripts/process_darshan_signals_v2.4.py \
    input.txt \
    -o output_signals_v2.4.txt
```

**Input**:
- Darshan parsed text log
- Contains all raw counters (POSIX_OPENS, POSIX_READS, etc.)

**Output**:
- Header: Complete preservation of original log header (job metadata, mount points)
- Job Level: 4 aggregate metrics (total_bytes_read/written, total_reads/writes)
- Module Level: 6 performance metrics per module (POSIX, STDIO, HEATMAP)
- Record Level: **100+ derived signals** per file access record

**Implementation**:
1. Use `(module, rank, record_id)` triplet as unique key to avoid multi-rank record overwriting
2. Three-tier hierarchical computation: Job → Module → Record
3. NA value handling: Annotate missing values with `NA(reason)`
4. Signal namespace isolation: Each module section only parses records from that section

**Key Signals** (see [Signal Computation Specifications](#signal-computation-specifications)):
- Time metrics: `read_start_ts`, `read_end_ts`, `read_span`, `read_time`, `read_busy_frac`
- Performance metrics: `read_bw`, `write_bw`, `read_iops`, `write_iops`
- Access patterns: `seq_ratio`, `consec_ratio`, `rw_switches`
- HEATMAP specific: `active_bins`, `peak_activity_bin`, `entropy_norm`, `top1_share`

### Stage 3: Build Knowledge Graph

```bash
python experiments/darshan_kg_builder_v2.1.py \
    -i output_signals_v2.4.txt \
    -o output_kg.json
```

**Input**:
- Signal file (v2.4+ format)
- Contains Job/Module/Record three-tier data

**Output**:
- LightRAG format JSON file
- Contains `entities` and `relationships` arrays
- Each entity includes all signal values as attributes

**Implementation**:
1. **6 Entity Types**:
   - `APPLICATION`: Executable identifier (`App_{exe}`)
   - `JOB`: Single job instance (`Job_{job_id}`)
   - `MODULE`: I/O module (`{job_id}::{module_name}`)
   - `RECORD`: File access record (`{job_id}::{module}::{record_id}::rank{rank}`)
   - `FILE`: File entity (`File_{file_path_norm}`)
   - `FILESYSTEM`: File system (`FS_{fs_type}_{mount_pt}`)

2. **Edge Types**:
   - `APPLICATION → JOB (HAS_JOB)`: Jobs produced by application
   - `JOB → MODULE (HAS_MODULE)`: I/O modules used by job
   - `MODULE → RECORD (HAS_RECORD)`: Access records under module
   - `RECORD → FILE (ON_FILE)`: File accessed by record
   - `FILE → FILESYSTEM (ON_FILESYSTEM)`: File system containing file
   - `JOB → FILESYSTEM (TOUCH_FILESYSTEM)`: File systems accessed by job

3. **Key Design**:
   - Record = Incident = Minimum retrievable unit
   - Signal values stored as entity attributes (not separate nodes)
   - NA values represented as `null`, reasons stored in `{field}_na_reason` field
   - Mount table stored as Job attribute (not edges)

### Stage 4: Generate Natural Language Descriptions

```bash
python3 scripts/generate_descriptions_v3.py \
    output_kg.json \
    output_kg_with_desc.json
```

**Input**:
- KG JSON (entities and relationships)
- Each entity contains raw signal attributes

**Output**:
- Updated KG JSON
- Each entity's `description` field filled with natural language text
- Each relationship's `description` field filled with connection semantics

**Implementation**:
1. Use predefined templates (for each entity type)
2. Fill template placeholders (e.g., `{job_id}`, `{read_bw}`)
3. Handle NA values: Display reason instead of "N/A"
4. Track template usage statistics:
   - Which placeholders always have values
   - Which placeholders never have values
   - Which JSON attributes are never used

**Template Example** (RECORD):
```
This FILE I/O RECORD describes how {file_name} was accessed...
I/O activity begins at {io_start_ts} and spans {io_span} seconds...
Performance shows read bandwidth {read_bw} MB/s...
Access pattern: sequential ratio {seq_ratio}, consecutive ratio {consec_ratio}...
```

### Stage 5: Add Counter Chunks

```bash
python3 scripts/parse_darshan_chunks.py \
    --log raw_log.txt \
    --kg output_kg_with_desc.json \
    --output output_kg_with_chunks.json
```

**Input**:
- Raw Darshan log (parsed text)
- KG with descriptions

**Output**:
- Updated KG JSON
- New `chunks` array added
- Each chunk contains raw counter text for corresponding entity

**Implementation**:
1. Parse all counter lines from raw log
2. Group by entity name (MODULE, RECORD, FILE, FILESYSTEM)
3. Generate `chunk_text` for each entity (raw counter data)
4. Example chunk:
   ```
   POSIX  -1  11610284057069735693  POSIX_OPENS  24  /home/file  /home  lustre
   POSIX  -1  11610284057069735693  POSIX_READS  100  /home/file  /home  lustre
   ...
   ```

### Stage 6: Generate Embeddings

```bash
# Using Gemma model (recommended)
python3 scripts/embed_kg_local.py \
    --kg output_kg_with_chunks.json \
    --output ./embeddings_gemma \
    --model google/embeddinggemma-300m \
    --batch-size 4 \
    --max-length 2048

# Or using lightweight model (CPU friendly)
./scripts/embed_kg_cpu_optimized.sh
```

**Input**:
- KG with chunks
- Each entity has `description` and `chunk_text`

**Output**:
- `entity_embeddings.pkl`: Entity vectors (entity_name + description)
- `relationship_embeddings.pkl`: Relationship vectors (src_id→tgt_id + description)
- `embedding_metadata.json`: Metadata (model name, dimensions, counts)

**Implementation**:
1. Load local Transformer model (no API required)
2. Entity text = `entity_name` + `description`
3. Relationship text = `src_id → tgt_id` + `description`
4. Batch processing, supports CPU/GPU
5. Mean pooling + L2 normalization
6. Save as pickle and numpy formats

**Recommended Models**:
- `google/embeddinggemma-300m`: 768 dim, high accuracy (default)
- `sentence-transformers/all-MiniLM-L6-v2`: 384 dim, fast
- `BAAI/bge-small-en-v1.5`: 384 dim, English optimized

### Stage 7: Load to LightRAG

```bash
python3 scripts/load_custom_kg_to_lightrag.py \
    --kg output_kg_with_chunks.json \
    --embeddings ./embeddings_gemma \
    --embedding-model google/embeddinggemma-300m
```

**Input**:
- KG with chunks
- Embeddings directory

**Output**:
- LightRAG working directory
- Contains vector database, graph storage, KV storage
- Ready to accept queries

**Implementation**:
1. Create local embedding function (consistent with precomputed model)
2. Configure OpenAI API as LLM
3. Initialize LightRAG instance
4. Insert custom KG (preserve graph structure)
5. Generate notebook example code

### Stage 8: Query and Visualization

In Jupyter Notebook:

```python
import asyncio
from lightrag import LightRAG, QueryParam

# Initialize RAG
rag = LightRAG(
    working_dir="./lightrag_storage",
    embedding_func=embedding_func,
    llm_model_func=llm_func,
)

await rag.initialize_storages()

# Query example
result = await rag.aquery(
    "What are the POSIX I/O operations?",
    param=QueryParam(mode="hybrid", top_k=5)
)
print(result)
```

**Query Modes**:
- `naive`: Simple vector search
- `local`: Entity-based local search (suitable for specific details)
- `global`: Relationship-based global search (suitable for overview)
- `hybrid`: local + global combined (recommended)
- `mix`: Mixed graph and vector retrieval

---

## Core Scripts

### 1. `scripts/unpack-darshan-logs.sh`

**Function**: Unpack Darshan log tar.gz files

**Input Parameters**:
- `$1`: Parent directory path (containing multiple subdirectories, each with `logs.tar.gz`)

**Output**:
- Extracted `.darshan` files (in place)

**Implementation**:
```bash
# Traverse all subdirectories
find "$PARENT_DIR" -name "logs.tar.gz" | while read tarfile; do
    echo "Extracting: $tarfile"
    tar -xzf "$tarfile" -C "$(dirname "$tarfile")"
    echo "Done: $tarfile"
done
```

**Usage**:
```bash
chmod +x scripts/unpack-darshan-logs.sh
./scripts/unpack-darshan-logs.sh /path/to/polaris-darshan-logs-25-1/
```

---

### 2. `scripts/process_darshan_signals_v2.4.py`

**Function**: Compute derived signals from Darshan text logs

**Input Parameters**:
- `input_file`: Darshan parsed text log (required)
- `-o, --output`: Output file path (optional, default: `{input}_signals_v2.4.txt`)

**Output Format**:
```
# ============================================================
# ORIGINAL DARSHAN LOG HEADER
# ============================================================
# darshan log version: 3.41
# jobid: 3122490
# uid: 1449515727
# nprocs: 4
# mount entry: /home lustre
...

# *******************************************************
# JOB LEVEL - Derived Signals
# *******************************************************
JOB	total_bytes_read	7489771.0
JOB	total_bytes_written	11201335.0
JOB	total_reads	910.0
JOB	total_writes	89257.0

# *******************************************************
# POSIX module - Derived Signals
# *******************************************************
POSIX	MODULE_AGG	total_bytes_read	4204115.0
POSIX	MODULE_PERF	read_bw	131.12732077836188

# Record: 11610284057069735693, rank=-1, file=/home/3079452805, mount=/home, fs=lustre
POSIX	-1	11610284057069735693	SIGNAL_READ_START_TS	23.047361
POSIX	-1	11610284057069735693	SIGNAL_READ_END_TS	23.049321
POSIX	-1	11610284057069735693	SIGNAL_READ_BW	131.12732077836188
POSIX	-1	11610284057069735693	SIGNAL_WRITE_BW	NA(no_write_time)
...
```

**Implementation**:
1. Parse header (jobid, uid, nprocs, mount table)
2. Extract raw counters (POSIX_OPENS, POSIX_READS, etc.)
3. Compute three-tier signals:
   - Job level: Aggregate bytes and operations across all modules
   - Module level: Performance metrics per module (BW, IOPS, avg size)
   - Record level: 100+ derived metrics (see below)
4. Use `(module, rank, record_id)` triplet as unique key
5. Annotate NA values with reasons: `NA(no_reads)`, `NA(no_write_time)`, etc.

**Key Functions**:
- `parse_log_file()`: Parse log file
- `compute_job_level_signals()`: Compute job-level aggregates
- `compute_module_level_signals()`: Compute module-level performance
- `compute_posix_signals()`: Compute POSIX-specific signals
- `compute_heatmap_signals()`: Compute HEATMAP-specific signals

---

### 3. `experiments/darshan_kg_builder_v2.1.py`

**Function**: Convert signal file to LightRAG knowledge graph

**Input Parameters**:
- `-i, --input`: Signal file or directory (required)
- `-o, --output`: Output KG JSON file (required)

**Output Format**:
```json
{
  "entities": [
    {
      "entity_name": "Job_3122490",
      "entity_type": "JOB",
      "description": "",
      "source_id": "darshan-logs",
      "job_id": 3122490,
      "uid": 1449515727,
      "nprocs": 4,
      "runtime": 7451.1501,
      "total_bytes_read": 7489771.0,
      "mount_table": {"/home": "lustre", ...}
    },
    {
      "entity_name": "3122490::POSIX::11610284057069735693::rank-1",
      "entity_type": "RECORD",
      "description": "",
      "record_id": "11610284057069735693",
      "rank": -1,
      "file_name": "/home/3079452805",
      "read_bw": 131.12732077836188,
      "write_bw": null,
      "write_bw_na_reason": "no_write_time",
      ...
    }
  ],
  "relationships": [
    {
      "src_id": "App_4068766220",
      "tgt_id": "Job_3122490",
      "description": "",
      "keywords": "application job executable",
      "weight": 1.0
    }
  ]
}
```

**Implementation**:
1. Parse three-tier structure from signal file
2. Create 6 entity types (APPLICATION, JOB, MODULE, RECORD, FILE, FILESYSTEM)
3. Create 6 relationship types
4. Store signal values directly as entity attributes
5. NA value conversion: `NA(reason)` → `null` + `{field}_na_reason` field
6. Graph structure features:
   - Record = Incident (minimum retrievable unit)
   - Signals are attributes (not nodes)
   - Mount table stored as Job attribute
   - FileSystem only connects to actually accessed filesystems

**Key Classes**:
- `DarshanKGBuilderV2`: Main builder
- `_parse_job_metadata()`: Parse job information
- `_parse_module_section()`: Parse module section
- `_parse_record_signals()`: Parse record signals
- `build_lightrag_kg()`: Build final KG

---

### 4. `scripts/generate_descriptions_v3.py`

**Function**: Generate natural language descriptions for KG entities and relationships

**Input Parameters**:
- `input_kg.json`: Input KG file (required)
- `output_kg.json`: Output file (required)

**Output**:
- Updated KG (each entity/relationship's `description` field filled)

**Implementation**:
1. Define entity templates (APPLICATION, JOB, MODULE, RECORD, FILE, FILESYSTEM)
2. Define relationship templates (APPLICATION→JOB, JOB→MODULE, etc.)
3. Fill template placeholders (e.g., `{job_id}`, `{read_bw}`)
4. NA value handling:
   - If `read_bw == null` and `read_bw_na_reason` exists
   - Fill as: `"read bandwidth is unavailable due to {read_bw_na_reason}"`
5. Statistics report:
   - Template placeholders never matched
   - JSON attributes never used
   - Overall usage statistics

**Template Example** (JOB):
```python
ENTITY_TEMPLATES["JOB"] = """
This JOB is a single HPC job, describing when it ran, how large it was, and what application it executed.

The job is identified by job_id {job_id} and was submitted by user {uid}.
It ran on {nprocs} processes across {nnodes} compute nodes...
"""
```

---

### 5. `scripts/parse_darshan_chunks.py`

**Function**: Extract counter chunks from raw log and add to KG

**Input Parameters**:
- `--log`: Raw Darshan log file or directory (required)
- `--kg`: Existing KG JSON (required)
- `--output`: Output KG JSON (optional, default: overwrite original)

**Output**:
- Updated KG (contains `chunks` array)

**Implementation**:
1. Parse all counter lines from raw log
2. Group by entity name:
   - MODULE: `{job_id}::{module_name}`
   - RECORD: `{job_id}::{module}::{record_id}::rank{rank}`
   - FILE: `File_{file_path_norm}`
   - FILESYSTEM: `FS_{fs_type}_{mount_pt}`
3. Generate `chunk_text` for each entity (raw counter text)
4. Example output:
   ```json
   {
     "chunks": [
       {
         "entity_name": "3122490::POSIX",
         "chunk_text": "POSIX\t-1\t123...\tPOSIX_OPENS\t24\t/home/file\t/home\tlustre\nPOSIX\t-1\t123...\tPOSIX_READS\t100\t..."
       }
     ]
   }
   ```

**Key Functions**:
- `parse_darshan_log()`: Parse log file
- `group_by_entity()`: Group by entity
- `normalize_entity_name()`: Normalize entity name

---

### 6. `scripts/embed_kg_local.py`

**Function**: Generate KG embeddings using local Transformer models

**Input Parameters**:
- `--kg`: KG JSON file (required)
- `--output`: Output directory (required)
- `--model`: Hugging Face model name (default: `google/embeddinggemma-300m`)
- `--batch-size`: Batch size (default: 32)
- `--max-length`: Max sequence length (default: 512)
- `--device`: Device (`cpu` or `cuda`, auto-detect)

**Output**:
- `entity_embeddings.pkl`: Entity vector dictionary
- `relationship_embeddings.pkl`: Relationship vector dictionary
- `entity_embeddings.npy`: NumPy array format
- `relationship_embeddings.npy`: NumPy array format
- `embedding_metadata.json`: Metadata

**Implementation**:
1. Load Hugging Face Transformer model
2. Entity text = `"{entity_name}: {description}"`
3. Relationship text = `"{src_id} -> {tgt_id}: {description}"`
4. Tokenize + Encode
5. Mean pooling (using attention mask)
6. L2 normalization
7. Batch processing (avoid OOM)
8. Save as pickle and numpy

**Key Functions**:
- `embed_texts()`: Batch embedding
- `mean_pooling()`: Mean pooling
- `prepare_entity_texts()`: Prepare entity texts
- `prepare_relationship_texts()`: Prepare relationship texts

**Model Comparison**:

| Model | Dim | Size | Speed | Accuracy | Use Case |
|-------|-----|------|-------|----------|----------|
| google/embeddinggemma-300m | 768 | 1.2GB | Medium | High | Default recommended ✅ |
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 80MB | Fast | Medium | Quick testing |
| BAAI/bge-small-en-v1.5 | 384 | 130MB | Fast | High | English tasks |
| BAAI/bge-m3 | 1024 | 2.5GB | Slow | Very High | Multilingual high accuracy |

---

### 7. `scripts/embed_kg_cpu_optimized.sh`

**Function**: CPU-optimized fast embedding script

**Input**:
- Hardcoded KG path (can modify script)

**Output**:
- `./embeddings_cpu/` directory
- Uses lightweight model (`all-MiniLM-L6-v2`)

**Implementation**:
```bash
python3 embed_kg_local.py \
  --kg "$KG_FILE" \
  --output "$OUTPUT_DIR" \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --batch-size 4 \
  --max-length 2048
```

**Optimizations**:
- Batch size = 4 (CPU friendly)
- Use lightweight model (80MB)
- Max length = 2048 (supports long texts)

---

### 8. `scripts/load_custom_kg_to_lightrag.py`

**Function**: Load KG and embeddings to LightRAG

**Input Parameters**:
- `--kg`: KG JSON file (required)
- `--embeddings`: Embeddings directory (optional)
- `--embedding-model`: Embedding model name (default: `sentence-transformers/all-MiniLM-L6-v2`)
- `--working-dir`: LightRAG working directory (default: `./lightrag_darshan_storage`)
- `--openai-key`: OpenAI API key (optional, or use `OPENAI_API_KEY` env var)
- `--openai-model`: OpenAI model (default: `gpt-4o-mini`)

**Output**:
- LightRAG working directory (contains vector database, graph storage)
- Notebook example code (printed to console)

**Implementation**:
1. Create local embedding function (consistent with precomputed model)
2. Configure OpenAI API
3. Initialize LightRAG instance
4. Insert custom KG:
   - Entities → Vector database
   - Relationships → Graph storage
   - Chunks → Text index
5. Generate notebook code example

**Key Classes**:
- `LocalEmbeddingFunction`: Local embedding wrapper
- `llm_model_func`: OpenAI LLM wrapper
- LightRAG configuration

---

## Signal Computation Specifications

### Overview

Signals are organized in three tiers:
1. **Job Level**: Job-level aggregates (4)
2. **Module Level**: Module-level performance (6 per module)
3. **Record Level**: Record-level detailed metrics (100+ per record)

### NA Value Reason Annotation

All NA values follow format: `NA(reason)`

| Reason Code | Meaning | Example |
|------------|---------|---------|
| `no_reads` | Read count is 0 | `avg_read_size = NA(no_reads)` |
| `no_writes` | Write count is 0 | `avg_write_size = NA(no_writes)` |
| `no_io` | No I/O operations | `seq_ratio = NA(no_io)` |
| `no_read_time` | Read time is 0 | `read_bw = NA(no_read_time)` |
| `no_write_time` | Write time is 0 | `write_bw = NA(no_write_time)` |
| `no_time` | Total time is 0 | `read_iops = NA(no_time)` |
| `no_bytes` | Byte count is 0 | `rank_imbalance_ratio = NA(no_bytes)` |
| `not_shared_file` | rank != -1, not shared | `rank_imbalance_ratio = NA(not_shared_file)` |
| `no_bin_width` | HEATMAP missing bin width | HEATMAP signal = `NA(no_bin_width)` |

---

### 1. Job Level Signals

| Signal | Formula | Description |
|--------|---------|-------------|
| `total_bytes_read` | Σ(all modules' bytes_read) | Total job read bytes |
| `total_bytes_written` | Σ(all modules' bytes_written) | Total job write bytes |
| `total_reads` | Σ(all modules' reads) | Total job read operations |
| `total_writes` | Σ(all modules' writes) | Total job write operations |

---

### 2. Module Level Signals

Each module (POSIX, STDIO, MPIIO) computes:

| Signal | Formula | NA Reason |
|--------|---------|-----------|
| `total_bytes_read` | Σ(all records' bytes_read for this module) | - |
| `total_bytes_written` | Σ(all records' bytes_written for this module) | - |
| `total_reads` | Σ(all records' reads for this module) | - |
| `total_writes` | Σ(all records' writes for this module) | - |
| `read_bw` | total_bytes_read / 1024² / total_time | `NA(no_time)` |
| `write_bw` | total_bytes_written / 1024² / total_time | `NA(no_time)` |
| `read_iops` | total_reads / total_time | `NA(no_time)` |
| `write_iops` | total_writes / total_time | `NA(no_time)` |
| `avg_read_size` | total_bytes_read / total_reads | `NA(no_reads)` |
| `avg_write_size` | total_bytes_written / total_writes | `NA(no_writes)` |

**Note**: HEATMAP module does not compute MODULE_AGG and MODULE_PERF (meaningless)

---

### 3. Record Level Signals

#### 3.1 Common Signals (All Modules)

##### Time Metrics

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `read_start_ts` | `F_READ_START_TIMESTAMP` | First read operation timestamp | `NA(not_monitored)` |
| `read_end_ts` | `F_READ_END_TIMESTAMP` | Last read operation timestamp | `NA(not_monitored)` |
| `write_start_ts` | `F_WRITE_START_TIMESTAMP` | First write operation timestamp | `NA(not_monitored)` |
| `write_end_ts` | `F_WRITE_END_TIMESTAMP` | Last write operation timestamp | `NA(not_monitored)` |
| `meta_start_ts` | `F_META_START_TIMESTAMP` | First metadata operation timestamp | `NA(not_monitored)` |
| `meta_end_ts` | `F_META_END_TIMESTAMP` | Last metadata operation timestamp | `NA(not_monitored)` |
| `read_time` | `F_READ_TIME` | Cumulative read time (seconds) | - |
| `write_time` | `F_WRITE_TIME` | Cumulative write time (seconds) | - |
| `meta_time` | `F_META_TIME` | Cumulative metadata time (seconds) | - |
| `io_time` | read_time + write_time | Total I/O time | - |
| `read_span` | read_end_ts - read_start_ts | Read operation time span | - |
| `write_span` | write_end_ts - write_start_ts | Write operation time span | - |
| `meta_span` | meta_end_ts - meta_start_ts | Metadata operation time span | - |
| `io_span` | max(...) - min(...) | Total I/O time span | - |
| `read_busy_frac` | read_time / read_span | Read busy fraction | `NA(no_read_time)` |
| `write_busy_frac` | write_time / write_span | Write busy fraction | `NA(no_write_time)` |
| `meta_busy_frac` | meta_time / meta_span | Metadata busy fraction | `NA(no_meta_time)` |
| `busy_frac` | io_time / io_span | Total I/O busy fraction | - |

##### Performance Metrics

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `read_bw` | bytes_read / 1024² / read_time | Read bandwidth (MB/s) | `NA(no_read_time)` |
| `write_bw` | bytes_written / 1024² / write_time | Write bandwidth (MB/s) | `NA(no_write_time)` |
| `read_iops` | reads / read_time | Read IOPS (ops/s) | `NA(no_read_time)` |
| `write_iops` | writes / write_time | Write IOPS (ops/s) | `NA(no_write_time)` |
| `avg_read_size` | bytes_read / reads | Average read size (bytes) | `NA(no_reads)` |
| `avg_write_size` | bytes_written / writes | Average write size (bytes) | `NA(no_writes)` |
| `avg_read_lat` | read_time / reads | Average read latency (seconds) | `NA(no_reads)` |
| `avg_write_lat` | write_time / writes | Average write latency (seconds) | `NA(no_writes)` |
| `max_read_time` | `F_MAX_READ_TIME` | Maximum single read time | - |
| `max_write_time` | `F_MAX_WRITE_TIME` | Maximum single write time | - |
| `max_read_time_size` | `F_MAX_READ_TIME_SIZE` | Size of max read time | - |
| `max_write_time_size` | `F_MAX_WRITE_TIME_SIZE` | Size of max write time | - |

##### Data Volume Metrics

| Signal | Formula | Description |
|--------|---------|-------------|
| `bytes_read` | `BYTES_READ` | Bytes read |
| `bytes_written` | `BYTES_WRITTEN` | Bytes written |
| `reads` | `READS` | Read operations |
| `writes` | `WRITES` | Write operations |

---

#### 3.2 POSIX-Specific Signals

##### Access Patterns

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `seq_read_ratio` | `SEQ_READS` / reads | Sequential read ratio | `NA(no_reads)` |
| `seq_write_ratio` | `SEQ_WRITES` / writes | Sequential write ratio | `NA(no_writes)` |
| `consec_read_ratio` | `CONSEC_READS` / reads | Consecutive read ratio | `NA(no_reads)` |
| `consec_write_ratio` | `CONSEC_WRITES` / writes | Consecutive write ratio | `NA(no_writes)` |
| `seq_ratio` | (SEQ_READS + SEQ_WRITES) / (reads + writes) | Total sequential ratio | `NA(no_io)` |
| `consec_ratio` | (CONSEC_READS + CONSEC_WRITES) / (reads + writes) | Total consecutive ratio | `NA(no_io)` |
| `rw_switches` | `RW_SWITCHES` | Read-write switch count | - |

##### Metadata Operations

| Signal | Formula | Description |
|--------|---------|-------------|
| `meta_ops` | OPENS + STATS + SEEKS + FSYNCS + FDSYNCS | Total metadata operations |
| `meta_intensity` | meta_ops / (reads + writes) | Metadata intensity |
| `meta_fraction` | meta_time / io_time | Metadata time fraction |

##### Alignment and Size

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `unaligned_read_ratio` | `MEM_NOT_ALIGNED` / reads | Unaligned read ratio | `NA(no_reads)` |
| `unaligned_write_ratio` | `MEM_NOT_ALIGNED` / writes | Unaligned write ratio | `NA(no_writes)` |
| `small_read_ratio` | `SIZE_READ_0_100` / reads | Small read (<100B) ratio | `NA(no_reads)` |
| `small_write_ratio` | `SIZE_WRITE_0_100` / writes | Small write (<100B) ratio | `NA(no_writes)` |
| `tail_read_ratio` | max SIZE_READ_bin / reads | Large read ratio | `NA(no_reads)` |
| `tail_write_ratio` | max SIZE_WRITE_bin / writes | Large write ratio | `NA(no_writes)` |

##### Data Reuse

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `reuse_proxy` | bytes_read / (MAX_BYTE_READ + 1) | Data reuse proxy | `NA(no_file_size)` |

##### Rank Imbalance (Shared Files Only, rank=-1)

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `rank_imbalance_ratio` | `F_SLOWEST_RANK_BYTES` / `F_FASTEST_RANK_BYTES` | Rank byte imbalance | `NA(not_shared_file)` or `NA(no_fastest_bytes)` |
| `rank_time_imb` | (`F_SLOWEST_RANK_TIME` - `F_FASTEST_RANK_TIME`) / `F_FASTEST_RANK_TIME` | Rank time imbalance | `NA(not_shared_file)` |
| `fastest_rank_time` | `F_FASTEST_RANK_TIME` | Fastest rank time | `NA(not_shared_file)` |
| `slowest_rank_time` | `F_SLOWEST_RANK_TIME` | Slowest rank time | `NA(not_shared_file)` |
| `var_rank_time` | `F_VARIANCE_RANK_TIME` | Rank time variance | `NA(not_shared_file)` |
| `var_rank_bytes` | `F_VARIANCE_RANK_BYTES` | Rank byte variance | `NA(not_shared_file)` |
| `bw_variance_proxy` | var_rank_bytes | Bandwidth variance proxy | `NA(not_shared_file)` |

##### Other

| Signal | Description |
|--------|-------------|
| `is_shared` | 1 if rank=-1 else 0 (is shared file) |

---

#### 3.3 HEATMAP-Specific Signals

HEATMAP module records I/O activity time distribution using bins to track I/O events in different time periods.

##### Input Data

- `HEATMAP_F_BIN_WIDTH_SECONDS`: Time width of each bin (Δt)
- `HEATMAP_READ_BIN_k`: Read event count in k-th bin (R[k])
- `HEATMAP_WRITE_BIN_k`: Write event count in k-th bin (W[k])
- k = 0, 1, 2, ..., N-1 (N is total bin count)

##### Definitions

Let:
- Δt = `HEATMAP_F_BIN_WIDTH_SECONDS`
- R[k] = `HEATMAP_READ_BIN_k`
- W[k] = `HEATMAP_WRITE_BIN_k`
- A[k] = R[k] + W[k] (total activity)
- N = total bin count

##### Computed Signals

| Signal | Formula | Description | NA Reason |
|--------|---------|-------------|-----------|
| `total_read_events` | Σ R[k] | Total read events across all bins | - |
| `total_write_events` | Σ W[k] | Total write events across all bins | - |
| `active_bins` | \|{k \| A[k]>0}\| | Number of bins with activity | - |
| `active_time` | active_bins × Δt | Total time with I/O activity (seconds) | `NA(no_bin_width)` |
| `activity_span` | (k_last - k_first + 1) × Δt | Time span from first to last active bin | `NA(no_bin_width)` |
| `peak_activity_bin` | argmax_k A[k] | **Index** of bin with highest activity (0-N) | - |
| `peak_activity_value` | max A[k] | **Event count** of bin with highest activity | - |
| `read_activity_entropy_norm` | H_r^{norm} | Normalized entropy of read distribution [0,1] | - |
| `write_activity_entropy_norm` | H_w^{norm} | Normalized entropy of write distribution [0,1] | - |
| `top1_share` | max A[k] / Σ A[k] | Fraction of total activity in peak bin | - |

##### Detailed Formulas

**1. total_read_events**
```
TR = Σ_{k=0}^{N-1} R[k]
```

**2. total_write_events**
```
TW = Σ_{k=0}^{N-1} W[k]
```

**3. active_bins**
```
N_active = |{k | A[k] > 0}|
```

**4. active_time**
```
T_active = N_active × Δt
```

**5. activity_span**
```
k_first = min{k | A[k] > 0}
k_last = max{k | A[k] > 0}
T_span = (k_last - k_first + 1) × Δt
```

**6. peak_activity_bin**
Returns **index** (0-N) of bin with highest activity:
```
peak_idx = argmax_{k} A[k]
```

**7. peak_activity_value**
Returns **event count** of bin with highest activity:
```
A_peak = max_{k} A[k]
```

**8. read_activity_entropy_norm**
Normalized entropy of read distribution:
```
If TR > 0:
  p_k = R[k] / TR  (for all k)
  H_r = -Σ_{k: p_k>0} p_k × log(p_k)
  H_r^{norm} = H_r / log(N)
Else:
  H_r^{norm} = 0
```

**Interpretation**:
- Higher entropy: Read activity distributed uniformly over time
- Lower entropy: Read activity concentrated in few time periods
- Normalized to [0,1] for easy comparison

**9. write_activity_entropy_norm**
Normalized entropy of write distribution (same formula as above, using W[k])

**10. top1_share**
Fraction of total activity in peak bin (reflects I/O burstiness):
```
TA = Σ_{k} A[k]
If TA > 0:
  S_1 = max_{k} A[k] / TA
Else:
  S_1 = 0
```

**Interpretation**:
- Close to 1: I/O highly concentrated in one time period (bursty)
- Close to 0: I/O evenly distributed across many time periods

##### Significance of HEATMAP Signals

| Signal | Purpose | Anomaly Indication |
|--------|---------|-------------------|
| `active_time` | Actual I/O active time | Compare with runtime to identify I/O sparsity |
| `activity_span` | I/O time span | Identify if I/O is scattered across job duration |
| `entropy_norm` | Time distribution uniformity | Low entropy → I/O concentrated (possible checkpoint) |
| `top1_share` | Burstiness | High value → Large I/O in short time (burst) |
| `peak_activity_bin` | Peak I/O intensity | Identify I/O bottleneck moments |

---

### 4. Signal Summary Table (by Category)

#### Time Metrics (21)

| Category | Signals |
|----------|---------|
| Timestamps | `read_start_ts`, `read_end_ts`, `write_start_ts`, `write_end_ts`, `meta_start_ts`, `meta_end_ts` |
| Cumulative Time | `read_time`, `write_time`, `meta_time`, `io_time` |
| Time Spans | `read_span`, `write_span`, `meta_span`, `io_span` |
| Busy Fractions | `read_busy_frac`, `write_busy_frac`, `meta_busy_frac`, `busy_frac` |
| Latency | `avg_read_lat`, `avg_write_lat`, `max_read_time`, `max_write_time` |

#### Performance Metrics (12)

| Category | Signals |
|----------|---------|
| Bandwidth | `read_bw`, `write_bw` |
| IOPS | `read_iops`, `write_iops` |
| Operation Size | `avg_read_size`, `avg_write_size`, `max_read_time_size`, `max_write_time_size` |
| Data Volume | `bytes_read`, `bytes_written`, `reads`, `writes` |

#### Access Pattern Metrics (15)

| Category | Signals |
|----------|---------|
| Sequentiality | `seq_read_ratio`, `seq_write_ratio`, `seq_ratio` |
| Consecutiveness | `consec_read_ratio`, `consec_write_ratio`, `consec_ratio` |
| Read-Write Switching | `rw_switches` |
| Alignment | `unaligned_read_ratio`, `unaligned_write_ratio` |
| Size Distribution | `small_read_ratio`, `small_write_ratio`, `tail_read_ratio`, `tail_write_ratio` |
| Data Reuse | `reuse_proxy` |
| Sharing | `is_shared` |

#### Metadata Metrics (3)

| Signals |
|---------|
| `meta_ops`, `meta_intensity`, `meta_fraction` |

#### Rank Imbalance Metrics (7)

| Signals |
|---------|
| `rank_imbalance_ratio`, `rank_time_imb`, `fastest_rank_time`, `slowest_rank_time`, `var_rank_time`, `var_rank_bytes`, `bw_variance_proxy` |

#### HEATMAP Time Distribution Metrics (10)

| Signals |
|---------|
| `total_read_events`, `total_write_events`, `active_bins`, `active_time`, `activity_span`, `peak_activity_bin`, `peak_activity_value`, `read_activity_entropy_norm`, `write_activity_entropy_norm`, `top1_share` |

---

## Design Philosophy

### Core Principles

1. **Record = Incident = Minimum Retrievable Unit**
   - Each Darshan record corresponds to an incident entity
   - All signal values stored as entity attributes (not separate nodes)
   - Supports incident-level retrieval: User queries focus on "which incidents have bandwidth above X"

2. **Support Downstream Computation**
   - Preserve original signal values for aggregate calculations (average, max, percentile, etc.)
   - No loss of data precision

3. **Explainability**
   - Graph edges represent comparability (same application/filesystem/module)
   - Not signal similarity
   - Each entity has natural language description

4. **Scalability**
   - Avoid creating millions of signal nodes
   - Keep graph size manageable (entity count = apps + jobs + modules + records + files + filesystems)

### Key Design Decisions

#### 1. NA Value Handling

- **Numeric Fields**: Missing values uniformly represented as `null` (not string "NA(...)")
- **Reason Fields**: Add parallel field `{field_name}_na_reason` to explain missing reason
- **Example**:
  ```json
  {
    "read_bw": null,
    "read_bw_na_reason": "no_time"
  }
  ```
- **Advantage**: Facilitates downstream numeric computation and filtering

#### 2. Mount Table as Job Attribute

- **Design**: Mount table stored as Job entity's `mount_table` attribute
- **Format**: `{mount_pt: fs_type}` dictionary
- **No Edges**: Avoid connecting Job to all filesystems existing in system
- **Rationale**: Mount table is system configuration, not I/O behavior

#### 3. Job → FileSystem Edge

- **Edge Name**: `TOUCH_FILESYSTEM`
- **Creation Condition**: Only connect to filesystems **actually accessed** in records
- **Rationale**: Reflect actual I/O behavior, not system configuration

#### 4. Signal Namespace Isolation

- **Problem**: Same record_id may appear in multiple modules (e.g., HEATMAP and POSIX)
- **Solution**: Strictly limit each module section to parse only records from that section
- **Result**: HEATMAP records contain only HEATMAP signals, POSIX records contain only POSIX signals

#### 5. Three-Tier Hierarchical Structure

- **Job Level**: Job-level aggregates (global view)
- **Module Level**: Module-level performance (interface layer view)
- **Record Level**: Record-level detailed metrics (file-level view)

**Advantages**:
- Support multi-granularity queries
- Facilitate aggregate computation
- Maintain data hierarchy

#### 6. Description Template System

- **Entity Templates**: Define natural language templates for each entity type
- **Relationship Templates**: Define connection semantics for each relationship type
- **Placeholder Filling**: Automatically fill entity attributes into templates
- **NA Handling**: Display missing reason instead of "N/A"

**Advantages**:
- Improve explainability
- Facilitate LLM understanding
- Support natural language queries

#### 7. Chunks as Raw Data Snapshot

- **Design**: Each entity's chunk_text contains raw counter data
- **Format**: Preserve original Darshan log format
- **Purpose**:
  - LLM can access raw data
  - Support precise numeric queries
  - Verify signal computation

#### 8. Local Embedding

- **Design**: Use local Transformer models instead of OpenAI API
- **Advantages**:
  - No API cost
  - No network dependency
  - Fully controllable
  - Supports offline environments

---

## Usage Examples

### Example 1: Complete End-to-End Workflow

```bash
# 0. Unpack logs
./scripts/unpack-darshan-logs.sh /path/to/darshan-logs/

# 1. Parse logs (using darshan-parser)
darshan-parser /path/to/log.darshan > /path/to/log.txt

# 2. Compute signals
python3 scripts/process_darshan_signals_v2.4.py \
    /path/to/log.txt \
    -o /path/to/log_signals_v2.4.txt

# 3. Build KG
python experiments/darshan_kg_builder_v2.1.py \
    -i /path/to/log_signals_v2.4.txt \
    -o /path/to/kg.json

# 4. Generate descriptions
python3 scripts/generate_descriptions_v3.py \
    /path/to/kg.json \
    /path/to/kg_with_desc.json

# 5. Add chunks
python3 scripts/parse_darshan_chunks.py \
    --log /path/to/log.txt \
    --kg /path/to/kg_with_desc.json \
    --output /path/to/kg_with_chunks.json

# 6. Generate embeddings
python3 scripts/embed_kg_local.py \
    --kg /path/to/kg_with_chunks.json \
    --output ./embeddings \
    --model google/embeddinggemma-300m \
    --batch-size 32

# 7. Load to LightRAG
python3 scripts/load_custom_kg_to_lightrag.py \
    --kg /path/to/kg_with_chunks.json \
    --embeddings ./embeddings \
    --embedding-model google/embeddinggemma-300m
```

### Example 2: Batch Processing Multiple Logs

```bash
# Batch parsing (in Jupyter notebook)
import os
import subprocess
from pathlib import Path
from tqdm import tqdm

parent_dir = '/path/to/darshan-logs/'
parsed_root = Path('~/parsed-logs/').expanduser()
parsed_root.mkdir(parents=True, exist_ok=True)

# Collect all .darshan files
darshan_logs = []
for root, dirs, files in os.walk(parent_dir):
    for file in files:
        if file.endswith('.darshan'):
            fullpath = os.path.join(root, file)
            rel = os.path.relpath(fullpath, parent_dir)
            output_dir = parsed_root / Path(rel).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            out_txt = output_dir / (Path(file).stem + '.txt')
            darshan_logs.append((fullpath, out_txt))

# Batch parse
success_count = 0
fail_count = 0

for in_log, out_txt in tqdm(darshan_logs, desc="Parsing darshan logs"):
    result = subprocess.run(
        ['darshan-parser', in_log],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        with open(out_txt, 'w') as f:
            f.write(result.stdout)
        success_count += 1
    else:
        fail_count += 1

print(f"\n✅ Parsing complete: {success_count} succeeded, {fail_count} failed")
```

### Example 3: Query in Notebook

```python
# Cell 1: Setup
import os
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.utils import EmbeddingFunc
from transformers import AutoTokenizer, AutoModel
import torch
import numpy as np

# Cell 2: API Key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  Please set OPENAI_API_KEY environment variable")
else:
    print("✅ OPENAI_API_KEY loaded")

# Cell 3: Local Embedding Function
class LocalEmbeddingFunction:
    def __init__(self, model_name="google/embeddinggemma-300m", device=None, batch_size=4):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(self.device).eval()
        self.embedding_dim = self.model.config.hidden_size
        self.batch_size = batch_size
        print(f"✓ Model loaded: {model_name} ({self.embedding_dim}D)")

    async def __call__(self, texts):
        embeddings = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                encoded = self.tokenizer(batch, padding=True, truncation=True,
                                        max_length=512, return_tensors="pt").to(self.device)
                outputs = self.model(**encoded)
                attention_mask = encoded['attention_mask']
                token_embeddings = outputs.last_hidden_state
                input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
                batch_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1) / \
                                  torch.clamp(input_mask_expanded.sum(1), min=1e-9)
                batch_embeddings = torch.nn.functional.normalize(batch_embeddings, p=2, dim=1)
                embeddings.append(batch_embeddings.cpu().numpy())
        return np.vstack(embeddings)

local_embed = LocalEmbeddingFunction()
embedding_func = EmbeddingFunc(
    embedding_dim=local_embed.embedding_dim,
    max_token_size=2048,
    func=lambda texts: local_embed(texts)
)

# Cell 4: LLM Function
async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await openai_complete_if_cache(
        "gpt-4o-mini",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=OPENAI_API_KEY,
        **kwargs
    )

print("✓ LLM function configured")

# Cell 5: Load RAG
WORKING_DIR = "./lightrag_darshan_storage"

rag = LightRAG(
    working_dir=WORKING_DIR,
    embedding_func=embedding_func,
    llm_model_func=llm_model_func,
)

await rag.initialize_storages()
print("✓ LightRAG loaded successfully!")

# Cell 6: Query Helper
async def query(question, mode="hybrid", top_k=5):
    """Query Darshan KG"""
    result = await rag.aquery(
        question,
        param=QueryParam(mode=mode, top_k=top_k)
    )
    return result

print("✓ Query helper ready!")

# Cell 7: Example Queries
# Basic query
result = await query("What are the POSIX I/O operations?")
print(result)

# Query file access
result = await query("Which files were accessed and where?")
print(result)

# Analyze I/O performance
result = await rag.aquery(
    "Analyze the I/O performance",
    param=QueryParam(
        mode="hybrid",
        top_k=10,
        only_need_context=False
    )
)
print(result)
```

### Example 4: Custom Queries

```python
# Time-based queries
result = await query("Which records spent the most time in read operations?")

# Performance-based queries
result = await query("Which records achieved read bandwidth over 1000 MB/s?")

# Access pattern queries
result = await query("Find records with high sequential access ratios on Lustre")

# Cross-level aggregate queries
result = await query("What are the average I/O characteristics for this application?")

# Metadata-intensive workloads
result = await query("Show records with high metadata intensity on NFS")

# Rank imbalance
result = await query("Which shared files have the highest rank imbalance in I/O time?")
```

---

## Troubleshooting

### Issue 1: `process_darshan_signals_v2.4.py` outputs nothing

**Possible Causes**:
- Input file format incorrect (not darshan-parser output)
- File encoding issues

**Solution**:
```bash
# Check file header
head -20 input.txt

# Should see header like:
# darshan log version: 3.41
# compression method: BZIP2
# exe: 4068766220
# ...

# Re-parse
darshan-parser input.darshan > output.txt
```

### Issue 2: `darshan_kg_builder_v2.1.py` error "No records found"

**Possible Causes**:
- Signal file not v2.4+ format
- Record section format incorrect

**Solution**:
```bash
# Check signal file format
grep "# Record:" signal_file.txt

# Should see:
# Record: 11610284057069735693, rank=-1, file=/home/file, mount=/home, fs=lustre
```

### Issue 3: `embed_kg_local.py` error "CUDA out of memory"

**Possible Causes**:
- Batch size too large
- Model too large

**Solution**:
```bash
# Reduce batch size
python3 scripts/embed_kg_local.py \
    --kg kg.json \
    --output ./embeddings \
    --batch-size 4  # Reduce from 32 to 4

# Or use CPU
python3 scripts/embed_kg_local.py \
    --kg kg.json \
    --output ./embeddings \
    --device cpu
```

### Issue 4: `load_custom_kg_to_lightrag.py` error "OpenAI API key not provided"

**Solution**:
```bash
# Method 1: Environment variable
export OPENAI_API_KEY=sk-your-key-here
python3 scripts/load_custom_kg_to_lightrag.py --kg kg.json

# Method 2: Command line parameter
python3 scripts/load_custom_kg_to_lightrag.py \
    --kg kg.json \
    --openai-key sk-your-key-here
```

### Issue 5: LightRAG query results inaccurate

**Possible Causes**:
- Embedding model inconsistent
- Top-k too small
- Query mode inappropriate

**Solution**:
```python
# 1. Increase top_k
result = await query("question", mode="hybrid", top_k=20)

# 2. Try different query modes
result = await query("question", mode="local")  # Local search
result = await query("question", mode="global")  # Global search
result = await query("question", mode="mix")  # Mixed search

# 3. Enable rerank (requires rerank model configuration)
result = await rag.aquery(
    "question",
    param=QueryParam(mode="hybrid", enable_rerank=True)
)
```

---

## File Structure

```
/users/Minqiu/DarshanRAG/experiments/
├── config_paths.py                      # Path configuration module
├── darshan_kg_builder_v2.1.py           # KG builder script
├── notebooks/
│   └── IORAG.ipynb                      # Main notebook
├── scripts/
│   ├── unpack-darshan-logs.sh           # Unpack logs
│   ├── process_darshan_signals_v2.4.py  # Signal extraction
│   ├── generate_descriptions_v3.py      # Generate descriptions
│   ├── parse_darshan_chunks.py          # Parse chunks
│   ├── embed_kg_local.py                # Local embedding
│   ├── embed_kg_cpu_optimized.sh        # CPU optimized embedding
│   └── load_custom_kg_to_lightrag.py    # Load KG
├── results/                             # Results output
├── storage/                             # RAG storage
├── ground_truth/                        # Ground truth data
├── IORAG_README.md                      # Chinese documentation
└── IORAG_README_EN.md                   # This document
```

---

## References

- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [Darshan Documentation](https://www.mcs.anl.gov/research/projects/darshan/)
- [Hugging Face Transformers](https://huggingface.co/docs/transformers)
- [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m)
- [Sentence Transformers](https://www.sbert.net/)

---

## Version History

- **v1.0** (2026-02-10): Initial version
  - Complete workflow documentation
  - All scripts detailed explanation
  - Signal computation specifications
  - Design philosophy explanation

---

**Author**: Claude
**Date**: 2026-02-10
**Version**: 1.0
