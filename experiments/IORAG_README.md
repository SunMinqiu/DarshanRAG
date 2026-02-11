# IORAG：基于 LightRAG 的 Darshan 日志知识图谱系统

> **IO + RAG = IORAG**: 将 Darshan I/O 日志转换为图谱+向量混合的数据库，用于智能查询和异常检测

## 📋 目录

- [项目概述](#项目概述)
- [完整 Workflow](#完整-workflow)
- [核心脚本详解](#核心脚本详解)
- [Signal 计算规格](#signal-计算规格)
- [设计思路](#设计思路)
- [使用示例](#使用示例)
- [故障排查](#故障排查)

---

## 项目概述

### 🎯 目标

使用 LightRAG 框架，将 Darshan I/O 日志转换为 **图谱（Graph）+ 向量（Vector）** 结合的知识库，实现：

1. **智能检索**：通过自然语言查询 I/O 行为（"哪些文件的带宽超过 1GB/s？"）
2. **异常检测**：识别 I/O 性能异常模式（随机访问、元数据密集、负载不均等）
3. **关系推理**：理解 Application → Job → Module → Record → File → FileSystem 的层次关系
4. **可解释性**：为每个实体生成自然语言描述，便于人类理解

### 🏗️ 架构

```
Raw Darshan Log (.darshan)
         ↓
   [darshan-parser]
         ↓
  Parsed Log (.txt)
         ↓
[process_darshan_signals_v2.4.py]  ← 计算 signals
         ↓
  Signal File (*_signals_v2.4.txt)
         ↓
[darshan_kg_builder_v2.1.py]  ← 构建 KG
         ↓
  KG JSON (*_kg.json)
         ↓
[generate_descriptions_v3.py]  ← 添加描述
         ↓
  KG with Descriptions (*_kg_with_desc.json)
         ↓
[parse_darshan_chunks.py]  ← 添加 chunks
         ↓
  KG with Chunks (*_kg_with_chunks.json)
         ↓
[embed_kg_local.py]  ← 生成 embeddings
         ↓
  Embeddings (entity & relation vectors)
         ↓
[load_custom_kg_to_lightrag.py]  ← 加载到 LightRAG
         ↓
   LightRAG Instance
         ↓
  [Query with Natural Language] 🎯
```

---

## 完整 Workflow

### 阶段 0: 准备原始日志

```bash
# 解压 Darshan 日志
chmod +x scripts/unpack-darshan-logs.sh
./scripts/unpack-darshan-logs.sh /path/to/darshan-logs-tarball/
```

**输入**: `logs.tar.gz`（包含多个 `.darshan` 文件）
**输出**: 解压后的 `.darshan` 文件

### 阶段 1: 解析日志为文本

```bash
# 使用 darshan-parser 解析二进制日志
darshan-parser input.darshan > output.txt
```

**输入**: `.darshan` 二进制文件
**输出**: 文本格式的 counter 数据

### 阶段 2: 计算 Signals

```bash
python3 scripts/process_darshan_signals_v2.4.py \
    input.txt \
    -o output_signals_v2.4.txt
```

**输入**:
- Darshan 解析后的文本日志
- 包含所有原始 counters（POSIX_OPENS, POSIX_READS, etc.）

**输出**:
- Header: 完整保留原始日志 header（job metadata, mount points）
- Job 级别: 4 个聚合指标（total_bytes_read/written, total_reads/writes）
- Module 级别: 每个模块（POSIX, STDIO, HEATMAP）的 6 个性能指标
- Record 级别: 每个文件访问记录的 **100+ 派生信号**

**实现**:
1. 使用 `(module, rank, record_id)` 三元组作为唯一键，避免多 rank 记录覆盖
2. 三层层次化计算：Job → Module → Record
3. NA 值处理：数值字段用 `NA(reason)` 标注缺失原因
4. Signal 命名空间隔离：每个 module section 只解析该 section 的 records

**关键 Signals**（见 [Signal 计算规格](#signal-计算规格)）:
- 时间指标：`read_start_ts`, `read_end_ts`, `read_span`, `read_time`, `read_busy_frac`
- 性能指标：`read_bw`, `write_bw`, `read_iops`, `write_iops`
- 访问模式：`seq_ratio`, `consec_ratio`, `rw_switches`
- HEATMAP 专用：`active_bins`, `peak_activity_bin`, `entropy_norm`, `top1_share`

### 阶段 3: 构建知识图谱

```bash
python experiments/darshan_kg_builder_v2.1.py \
    -i output_signals_v2.4.txt \
    -o output_kg.json
```

**输入**:
- Signal 文件（v2.4+ 格式）
- 包含 Job/Module/Record 三层数据

**输出**:
- LightRAG 格式的 JSON 文件
- 包含 `entities` 和 `relationships` 两个数组
- 每个实体包含所有 signal 值作为属性

**实现**:
1. **6 种实体类型**:
   - `APPLICATION`: 可执行文件标识（`App_{exe}`）
   - `JOB`: 单次作业实例（`Job_{job_id}`）
   - `MODULE`: I/O 模块（`{job_id}::{module_name}`）
   - `RECORD`: 文件访问记录（`{job_id}::{module}::{record_id}::rank{rank}`）
   - `FILE`: 文件实体（`File_{file_path_norm}`）
   - `FILESYSTEM`: 文件系统（`FS_{fs_type}_{mount_pt}`）

2. **边类型**:
   - `APPLICATION → JOB (HAS_JOB)`: 应用产生的作业
   - `JOB → MODULE (HAS_MODULE)`: 作业使用的 I/O 模块
   - `MODULE → RECORD (HAS_RECORD)`: 模块下的访问记录
   - `RECORD → FILE (ON_FILE)`: 记录访问的文件
   - `FILE → FILESYSTEM (ON_FILESYSTEM)`: 文件所在的文件系统
   - `JOB → FILESYSTEM (TOUCH_FILESYSTEM)`: 作业访问的文件系统

3. **关键设计**:
   - Record = Incident = 最小可检索单元
   - Signal 值存储为实体属性（而非独立节点）
   - NA 值用 `null` 表示，原因存储在 `{field}_na_reason` 字段
   - Mount table 存储为 Job 属性（而非边）

### 阶段 4: 生成自然语言描述

```bash
python3 scripts/generate_descriptions_v3.py \
    output_kg.json \
    output_kg_with_desc.json
```

**输入**:
- KG JSON（实体和关系）
- 每个实体包含原始 signal 属性

**输出**:
- 更新后的 KG JSON
- 每个实体的 `description` 字段填充自然语言文本
- 每个关系的 `description` 字段填充连接语义

**实现**:
1. 使用预定义的模板（针对每种实体类型）
2. 填充模板占位符（如 `{job_id}`, `{read_bw}`）
3. 处理 NA 值：显示原因而非"N/A"
4. 统计模板使用情况：
   - 哪些占位符总是有值
   - 哪些占位符从不有值
   - 哪些 JSON 属性未被使用

**模板示例**（RECORD）:
```
This FILE I/O RECORD describes how {file_name} was accessed...
I/O activity begins at {io_start_ts} and spans {io_span} seconds...
Performance shows read bandwidth {read_bw} MB/s...
Access pattern: sequential ratio {seq_ratio}, consecutive ratio {consec_ratio}...
```

### 阶段 5: 添加 Counter Chunks

```bash
python3 scripts/parse_darshan_chunks.py \
    --log raw_log.txt \
    --kg output_kg_with_desc.json \
    --output output_kg_with_chunks.json
```

**输入**:
- Raw Darshan log（解析后的文本）
- KG with descriptions

**输出**:
- 更新后的 KG JSON
- 新增 `chunks` 数组
- 每个 chunk 包含对应实体的原始 counter 文本

**实现**:
1. 解析 raw log 中的所有 counter 行
2. 按实体名称分组（MODULE, RECORD, FILE, FILESYSTEM）
3. 为每个实体生成 `chunk_text`（原始 counter 数据）
4. 示例 chunk:
   ```
   POSIX  -1  11610284057069735693  POSIX_OPENS  24  /home/file  /home  lustre
   POSIX  -1  11610284057069735693  POSIX_READS  100  /home/file  /home  lustre
   ...
   ```

### 阶段 6: 生成 Embeddings

```bash
# 使用 Gemma 模型（推荐）
python3 scripts/embed_kg_local.py \
    --kg output_kg_with_chunks.json \
    --output ./embeddings_gemma \
    --model google/embeddinggemma-300m \
    --batch-size 4 \
    --max-length 2048

# 或使用轻量级模型（CPU 友好）
./scripts/embed_kg_cpu_optimized.sh
```

**输入**:
- KG with chunks
- 每个实体有 `description` 和 `chunk_text`

**输出**:
- `entity_embeddings.pkl`: 实体向量（entity_name + description）
- `relationship_embeddings.pkl`: 关系向量（src_id→tgt_id + description）
- `embedding_metadata.json`: 元数据（模型名称、维度、数量）

**实现**:
1. 加载本地 Transformer 模型（无需 API）
2. 实体文本 = `entity_name` + `description`
3. 关系文本 = `src_id → tgt_id` + `description`
4. Batch 处理，支持 CPU/GPU
5. Mean pooling + L2 normalization
6. 保存为 pickle 和 numpy 格式

**推荐模型**:
- `google/embeddinggemma-300m`: 768 维，高精度（默认）
- `sentence-transformers/all-MiniLM-L6-v2`: 384 维，快速
- `BAAI/bge-small-en-v1.5`: 384 维，英文优化

### 阶段 7: 加载到 LightRAG

```bash
python3 scripts/load_custom_kg_to_lightrag.py \
    --kg output_kg_with_chunks.json \
    --embeddings ./embeddings_gemma \
    --embedding-model google/embeddinggemma-300m
```

**输入**:
- KG with chunks
- Embeddings 目录

**输出**:
- LightRAG working directory
- 包含向量数据库、图存储、KV存储
- 准备好接受查询

**实现**:
1. 创建本地 embedding 函数（与预计算的模型一致）
2. 配置 OpenAI API 作为 LLM
3. 初始化 LightRAG 实例
4. 插入自定义 KG（保留图结构）
5. 生成 notebook 示例代码

### 阶段 8: 查询与可视化

在 Jupyter Notebook 中：

```python
import asyncio
from lightrag import LightRAG, QueryParam

# 初始化 RAG
rag = LightRAG(
    working_dir="./lightrag_storage",
    embedding_func=embedding_func,
    llm_model_func=llm_func,
)

await rag.initialize_storages()

# 查询示例
result = await rag.aquery(
    "What are the POSIX I/O operations?",
    param=QueryParam(mode="hybrid", top_k=5)
)
print(result)
```

**查询模式**:
- `naive`: 简单向量搜索
- `local`: 基于实体的局部搜索（适合具体细节）
- `global`: 基于关系的全局搜索（适合整体概况）
- `hybrid`: local + global 结合（推荐）
- `mix`: 混合图谱和向量检索

---

## 核心脚本详解

### 1. `scripts/unpack-darshan-logs.sh`

**功能**: 解压 Darshan 日志 tar.gz 文件

**输入参数**:
- `$1`: 父目录路径（包含多个子目录，每个子目录有 `logs.tar.gz`）

**输出**:
- 解压后的 `.darshan` 文件（在原地）

**实现**:
```bash
# 遍历所有子目录
find "$PARENT_DIR" -name "logs.tar.gz" | while read tarfile; do
    echo "Extracting: $tarfile"
    tar -xzf "$tarfile" -C "$(dirname "$tarfile")"
    echo "Done: $tarfile"
done
```

**使用**:
```bash
chmod +x scripts/unpack-darshan-logs.sh
./scripts/unpack-darshan-logs.sh /path/to/polaris-darshan-logs-25-1/
```

---

### 2. `scripts/process_darshan_signals_v2.4.py`

**功能**: 从 Darshan 文本日志计算派生 signals

**输入参数**:
- `input_file`: Darshan 解析后的文本日志（必需）
- `-o, --output`: 输出文件路径（可选，默认为 `{input}_signals_v2.4.txt`）

**输出格式**:
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

**实现**:
1. 解析 header（jobid, uid, nprocs, mount table）
2. 提取原始 counters（POSIX_OPENS, POSIX_READS, etc.）
3. 计算三层 signals:
   - Job 级别: 汇总所有模块的字节数和操作数
   - Module 级别: 每个模块的性能指标（BW, IOPS, avg size）
   - Record 级别: 100+ 派生指标（见下文）
4. 使用 `(module, rank, record_id)` 三元组作为唯一键
5. NA 值标注原因：`NA(no_reads)`, `NA(no_write_time)`, etc.

**关键函数**:
- `parse_log_file()`: 解析日志文件
- `compute_job_level_signals()`: 计算 Job 级别汇总
- `compute_module_level_signals()`: 计算 Module 级别性能
- `compute_posix_signals()`: 计算 POSIX 专用 signals
- `compute_heatmap_signals()`: 计算 HEATMAP 专用 signals

---

### 3. `experiments/darshan_kg_builder_v2.1.py`

**功能**: 将 signal 文件转换为 LightRAG 知识图谱

**输入参数**:
- `-i, --input`: Signal 文件或目录（必需）
- `-o, --output`: 输出 KG JSON 文件（必需）

**输出格式**:
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

**实现**:
1. 解析 signal 文件的三层结构
2. 创建 6 种实体类型（APPLICATION, JOB, MODULE, RECORD, FILE, FILESYSTEM）
3. 创建 6 种关系类型
4. Signal 值直接存储为实体属性
5. NA 值转换：`NA(reason)` → `null` + `{field}_na_reason` 字段
6. 图结构特性:
   - Record = Incident（最小可检索单元）
   - Signal 是属性（非节点）
   - Mount table 存储为 Job 属性
   - FileSystem 仅连接实际访问的文件系统

**关键类**:
- `DarshanKGBuilderV2`: 主构建器
- `_parse_job_metadata()`: 解析 job 信息
- `_parse_module_section()`: 解析模块 section
- `_parse_record_signals()`: 解析 record signals
- `build_lightrag_kg()`: 构建最终 KG

---

### 4. `scripts/generate_descriptions_v3.py`

**功能**: 为 KG 实体和关系生成自然语言描述

**输入参数**:
- `input_kg.json`: 输入 KG 文件（必需）
- `output_kg.json`: 输出文件（必需）

**输出**:
- 更新后的 KG（每个实体/关系的 `description` 字段已填充）

**实现**:
1. 定义实体模板（APPLICATION, JOB, MODULE, RECORD, FILE, FILESYSTEM）
2. 定义关系模板（APPLICATION→JOB, JOB→MODULE, etc.）
3. 填充模板占位符（如 `{job_id}`, `{read_bw}`）
4. NA 值处理:
   - 如果 `read_bw == null` 且 `read_bw_na_reason` 存在
   - 填充为：`"read bandwidth is unavailable due to {read_bw_na_reason}"`
5. 统计报告:
   - 模板中永远没有匹配到的属性
   - JSON 中永远没有用到的属性
   - 总体使用情况

**模板示例**（JOB）:
```python
ENTITY_TEMPLATES["JOB"] = """
This JOB is a single HPC job, describing when it ran, how large it was, and what application it executed.

The job is identified by job_id {job_id} and was submitted by user {uid}.
It ran on {nprocs} processes across {nnodes} compute nodes...
"""
```

---

### 5. `scripts/parse_darshan_chunks.py`

**功能**: 从 raw log 提取 counter chunks 并添加到 KG

**输入参数**:
- `--log`: Raw Darshan log 文件或目录（必需）
- `--kg`: 现有 KG JSON（必需）
- `--output`: 输出 KG JSON（可选，默认覆盖原文件）

**输出**:
- 更新后的 KG（包含 `chunks` 数组）

**实现**:
1. 解析 raw log 的所有 counter 行
2. 按实体名称分组:
   - MODULE: `{job_id}::{module_name}`
   - RECORD: `{job_id}::{module}::{record_id}::rank{rank}`
   - FILE: `File_{file_path_norm}`
   - FILESYSTEM: `FS_{fs_type}_{mount_pt}`
3. 为每个实体生成 `chunk_text`（原始 counter 文本）
4. 示例输出:
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

**关键函数**:
- `parse_darshan_log()`: 解析 log 文件
- `group_by_entity()`: 按实体分组
- `normalize_entity_name()`: 标准化实体名称

---

### 6. `scripts/embed_kg_local.py`

**功能**: 使用本地 Transformer 模型生成 KG embeddings

**输入参数**:
- `--kg`: KG JSON 文件（必需）
- `--output`: 输出目录（必需）
- `--model`: Hugging Face 模型名称（默认 `google/embeddinggemma-300m`）
- `--batch-size`: Batch 大小（默认 32）
- `--max-length`: 最大序列长度（默认 512）
- `--device`: 设备（`cpu` 或 `cuda`，自动检测）

**输出**:
- `entity_embeddings.pkl`: 实体向量字典
- `relationship_embeddings.pkl`: 关系向量字典
- `entity_embeddings.npy`: NumPy 数组格式
- `relationship_embeddings.npy`: NumPy 数组格式
- `embedding_metadata.json`: 元数据

**实现**:
1. 加载 Hugging Face Transformer 模型
2. 实体文本 = `"{entity_name}: {description}"`
3. 关系文本 = `"{src_id} -> {tgt_id}: {description}"`
4. Tokenize + Encode
5. Mean pooling（使用 attention mask）
6. L2 normalization
7. Batch 处理（避免 OOM）
8. 保存为 pickle 和 numpy

**关键函数**:
- `embed_texts()`: Batch embedding
- `mean_pooling()`: 平均池化
- `prepare_entity_texts()`: 准备实体文本
- `prepare_relationship_texts()`: 准备关系文本

**推荐模型对比**:

| 模型 | 维度 | 大小 | 速度 | 精度 | 推荐场景 |
|------|------|------|------|------|----------|
| google/embeddinggemma-300m | 768 | 1.2GB | 中 | 高 | 默认推荐 ✅ |
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 80MB | 快 | 中 | 快速测试 |
| BAAI/bge-small-en-v1.5 | 384 | 130MB | 快 | 高 | 英文任务 |
| BAAI/bge-m3 | 1024 | 2.5GB | 慢 | 很高 | 多语言高精度 |

---

### 7. `scripts/embed_kg_cpu_optimized.sh`

**功能**: CPU 优化的快速 embedding 脚本

**输入**:
- 硬编码 KG 路径（可修改脚本）

**输出**:
- `./embeddings_cpu/` 目录
- 使用轻量级模型（`all-MiniLM-L6-v2`）

**实现**:
```bash
python3 embed_kg_local.py \
  --kg "$KG_FILE" \
  --output "$OUTPUT_DIR" \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --batch-size 4 \
  --max-length 2048
```

**优化**:
- Batch size = 4（CPU 友好）
- 使用轻量级模型（80MB）
- Max length = 2048（支持长文本）

---

### 8. `scripts/load_custom_kg_to_lightrag.py`

**功能**: 将 KG 和 embeddings 加载到 LightRAG

**输入参数**:
- `--kg`: KG JSON 文件（必需）
- `--embeddings`: Embeddings 目录（可选）
- `--embedding-model`: Embedding 模型名称（默认 `sentence-transformers/all-MiniLM-L6-v2`）
- `--working-dir`: LightRAG working directory（默认 `./lightrag_darshan_storage`）
- `--openai-key`: OpenAI API key（可选，或使用环境变量 `OPENAI_API_KEY`）
- `--openai-model`: OpenAI 模型（默认 `gpt-4o-mini`）

**输出**:
- LightRAG working directory（包含向量数据库、图存储）
- Notebook 示例代码（打印到控制台）

**实现**:
1. 创建本地 embedding 函数（与预计算模型一致）
2. 配置 OpenAI API
3. 初始化 LightRAG 实例
4. 插入自定义 KG：
   - 实体 → 向量数据库
   - 关系 → 图存储
   - Chunks → 文本索引
5. 生成 notebook 代码示例

**关键类**:
- `LocalEmbeddingFunction`: 本地 embedding wrapper
- `llm_model_func`: OpenAI LLM wrapper
- LightRAG 配置

---

## Signal 计算规格

### 概述

Signals 分为三层：
1. **Job Level**: 作业级别汇总（4 个）
2. **Module Level**: 模块级别性能（6 个/模块）
3. **Record Level**: 记录级别详细指标（100+/记录）

### NA 值原因标注

所有 NA 值格式：`NA(reason)`

| 原因代码 | 含义 | 示例 |
|---------|------|------|
| `no_reads` | 读操作数为0 | `avg_read_size = NA(no_reads)` |
| `no_writes` | 写操作数为0 | `avg_write_size = NA(no_writes)` |
| `no_io` | 无I/O操作 | `seq_ratio = NA(no_io)` |
| `no_read_time` | 读时间为0 | `read_bw = NA(no_read_time)` |
| `no_write_time` | 写时间为0 | `write_bw = NA(no_write_time)` |
| `no_time` | 总时间为0 | `read_iops = NA(no_time)` |
| `no_bytes` | 字节数为0 | `rank_imbalance_ratio = NA(no_bytes)` |
| `not_shared_file` | rank != -1，非共享文件 | `rank_imbalance_ratio = NA(not_shared_file)` |
| `no_bin_width` | HEATMAP 缺少 bin width | HEATMAP signal = `NA(no_bin_width)` |

---

### 1. Job Level Signals

| Signal | 公式 | 说明 |
|--------|------|------|
| `total_bytes_read` | Σ(所有模块的 bytes_read) | 作业总读字节数 |
| `total_bytes_written` | Σ(所有模块的 bytes_written) | 作业总写字节数 |
| `total_reads` | Σ(所有模块的 reads) | 作业总读操作数 |
| `total_writes` | Σ(所有模块的 writes) | 作业总写操作数 |

---

### 2. Module Level Signals

每个模块（POSIX, STDIO, MPIIO）计算以下指标：

| Signal | 公式 | NA 原因 |
|--------|------|--------|
| `total_bytes_read` | Σ(该模块所有 records 的 bytes_read) | - |
| `total_bytes_written` | Σ(该模块所有 records 的 bytes_written) | - |
| `total_reads` | Σ(该模块所有 records 的 reads) | - |
| `total_writes` | Σ(该模块所有 records 的 writes) | - |
| `read_bw` | total_bytes_read / 1024² / total_time | `NA(no_time)` |
| `write_bw` | total_bytes_written / 1024² / total_time | `NA(no_time)` |
| `read_iops` | total_reads / total_time | `NA(no_time)` |
| `write_iops` | total_writes / total_time | `NA(no_time)` |
| `avg_read_size` | total_bytes_read / total_reads | `NA(no_reads)` |
| `avg_write_size` | total_bytes_written / total_writes | `NA(no_writes)` |

**注意**: HEATMAP 模块不计算 MODULE_AGG 和 MODULE_PERF（无意义）

---

### 3. Record Level Signals

#### 3.1 通用 Signals（所有模块）

##### 时间指标

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `read_start_ts` | `F_READ_START_TIMESTAMP` | 第一次读操作的时间戳 | `NA(not_monitored)` |
| `read_end_ts` | `F_READ_END_TIMESTAMP` | 最后一次读操作的时间戳 | `NA(not_monitored)` |
| `write_start_ts` | `F_WRITE_START_TIMESTAMP` | 第一次写操作的时间戳 | `NA(not_monitored)` |
| `write_end_ts` | `F_WRITE_END_TIMESTAMP` | 最后一次写操作的时间戳 | `NA(not_monitored)` |
| `meta_start_ts` | `F_META_START_TIMESTAMP` | 第一次元数据操作时间戳 | `NA(not_monitored)` |
| `meta_end_ts` | `F_META_END_TIMESTAMP` | 最后一次元数据操作时间戳 | `NA(not_monitored)` |
| `read_time` | `F_READ_TIME` | 累计读时间（秒） | - |
| `write_time` | `F_WRITE_TIME` | 累计写时间（秒） | - |
| `meta_time` | `F_META_TIME` | 累计元数据操作时间（秒） | - |
| `io_time` | read_time + write_time | 总 I/O 时间 | - |
| `read_span` | read_end_ts - read_start_ts | 读操作时间跨度 | - |
| `write_span` | write_end_ts - write_start_ts | 写操作时间跨度 | - |
| `meta_span` | meta_end_ts - meta_start_ts | 元数据操作时间跨度 | - |
| `io_span` | max(read_end_ts, write_end_ts, meta_end_ts) - min(...) | 总 I/O 时间跨度 | - |
| `read_busy_frac` | read_time / read_span | 读操作忙碌比例 | `NA(no_read_time)` |
| `write_busy_frac` | write_time / write_span | 写操作忙碌比例 | `NA(no_write_time)` |
| `meta_busy_frac` | meta_time / meta_span | 元数据操作忙碌比例 | `NA(no_meta_time)` |
| `busy_frac` | io_time / io_span | 总 I/O 忙碌比例 | - |

##### 性能指标

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `read_bw` | bytes_read / 1024² / read_time | 读带宽（MB/s） | `NA(no_read_time)` |
| `write_bw` | bytes_written / 1024² / write_time | 写带宽（MB/s） | `NA(no_write_time)` |
| `read_iops` | reads / read_time | 读 IOPS（操作/秒） | `NA(no_read_time)` |
| `write_iops` | writes / write_time | 写 IOPS（操作/秒） | `NA(no_write_time)` |
| `avg_read_size` | bytes_read / reads | 平均读大小（字节） | `NA(no_reads)` |
| `avg_write_size` | bytes_written / writes | 平均写大小（字节） | `NA(no_writes)` |
| `avg_read_lat` | read_time / reads | 平均读延迟（秒） | `NA(no_reads)` |
| `avg_write_lat` | write_time / writes | 平均写延迟（秒） | `NA(no_writes)` |
| `max_read_time` | `F_MAX_READ_TIME` | 最大单次读时间 | - |
| `max_write_time` | `F_MAX_WRITE_TIME` | 最大单次写时间 | - |
| `max_read_time_size` | `F_MAX_READ_TIME_SIZE` | 最大读时间对应的大小 | - |
| `max_write_time_size` | `F_MAX_WRITE_TIME_SIZE` | 最大写时间对应的大小 | - |

##### 数据量指标

| Signal | 公式 | 说明 |
|--------|------|------|
| `bytes_read` | `BYTES_READ` | 读取字节数 |
| `bytes_written` | `BYTES_WRITTEN` | 写入字节数 |
| `reads` | `READS` | 读操作数 |
| `writes` | `WRITES` | 写操作数 |

---

#### 3.2 POSIX 专用 Signals

##### 访问模式

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `seq_read_ratio` | `SEQ_READS` / reads | 顺序读比例 | `NA(no_reads)` |
| `seq_write_ratio` | `SEQ_WRITES` / writes | 顺序写比例 | `NA(no_writes)` |
| `consec_read_ratio` | `CONSEC_READS` / reads | 连续读比例 | `NA(no_reads)` |
| `consec_write_ratio` | `CONSEC_WRITES` / writes | 连续写比例 | `NA(no_writes)` |
| `seq_ratio` | (SEQ_READS + SEQ_WRITES) / (reads + writes) | 总顺序访问比例 | `NA(no_io)` |
| `consec_ratio` | (CONSEC_READS + CONSEC_WRITES) / (reads + writes) | 总连续访问比例 | `NA(no_io)` |
| `rw_switches` | `RW_SWITCHES` | 读写切换次数 | - |

##### 元数据操作

| Signal | 公式 | 说明 |
|--------|------|------|
| `meta_ops` | OPENS + STATS + SEEKS + FSYNCS + FDSYNCS | 元数据操作总数 |
| `meta_intensity` | meta_ops / (reads + writes) | 元数据强度 |
| `meta_fraction` | meta_time / io_time | 元数据时间占比 |

##### 对齐和大小

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `unaligned_read_ratio` | `MEM_NOT_ALIGNED` / reads | 未对齐读比例 | `NA(no_reads)` |
| `unaligned_write_ratio` | `MEM_NOT_ALIGNED` / writes | 未对齐写比例 | `NA(no_writes)` |
| `small_read_ratio` | `SIZE_READ_0_100` / reads | 小读（<100B）比例 | `NA(no_reads)` |
| `small_write_ratio` | `SIZE_WRITE_0_100` / writes | 小写（<100B）比例 | `NA(no_writes)` |
| `tail_read_ratio` | 最大的 SIZE_READ_bin / reads | 大读比例 | `NA(no_reads)` |
| `tail_write_ratio` | 最大的 SIZE_WRITE_bin / writes | 大写比例 | `NA(no_writes)` |

##### 数据重用

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `reuse_proxy` | bytes_read / (MAX_BYTE_READ + 1) | 数据重用代理 | `NA(no_file_size)` |

##### Rank 不均衡（仅共享文件，rank=-1）

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `rank_imbalance_ratio` | `F_SLOWEST_RANK_BYTES` / `F_FASTEST_RANK_BYTES` | Rank 字节不均衡比例 | `NA(not_shared_file)` 或 `NA(no_fastest_bytes)` |
| `rank_time_imb` | (`F_SLOWEST_RANK_TIME` - `F_FASTEST_RANK_TIME`) / `F_FASTEST_RANK_TIME` | Rank 时间不均衡 | `NA(not_shared_file)` |
| `fastest_rank_time` | `F_FASTEST_RANK_TIME` | 最快 rank 的时间 | `NA(not_shared_file)` |
| `slowest_rank_time` | `F_SLOWEST_RANK_TIME` | 最慢 rank 的时间 | `NA(not_shared_file)` |
| `var_rank_time` | `F_VARIANCE_RANK_TIME` | Rank 时间方差 | `NA(not_shared_file)` |
| `var_rank_bytes` | `F_VARIANCE_RANK_BYTES` | Rank 字节方差 | `NA(not_shared_file)` |
| `bw_variance_proxy` | var_rank_bytes | 带宽方差代理 | `NA(not_shared_file)` |

##### 其他

| Signal | 说明 |
|--------|------|
| `is_shared` | 1 if rank=-1 else 0（是否为共享文件） |

---

#### 3.3 HEATMAP 专用 Signals

HEATMAP 模块记录 I/O 活动的时间分布，使用 bins 统计不同时间段的 I/O 事件。

##### 输入数据

- `HEATMAP_F_BIN_WIDTH_SECONDS`: 每个 bin 的时间宽度（Δt）
- `HEATMAP_READ_BIN_k`: 第 k 个 bin 的读事件数（R[k]）
- `HEATMAP_WRITE_BIN_k`: 第 k 个 bin 的写事件数（W[k]）
- k = 0, 1, 2, ..., N-1（N 为 bin 总数）

##### 定义

设：
- Δt = `HEATMAP_F_BIN_WIDTH_SECONDS`
- R[k] = `HEATMAP_READ_BIN_k`
- W[k] = `HEATMAP_WRITE_BIN_k`
- A[k] = R[k] + W[k]（总活动）
- N = bin 总数

##### 计算的 Signals

| Signal | 公式 | 说明 | NA 原因 |
|--------|------|------|--------|
| `total_read_events` | Σ R[k] | 所有 bin 的读事件总数 | - |
| `total_write_events` | Σ W[k] | 所有 bin 的写事件总数 | - |
| `active_bins` | \|{k \| A[k]>0}\| | 有活动的 bin 数量 | - |
| `active_time` | active_bins × Δt | 有 I/O 活动的总时间（秒） | `NA(no_bin_width)` |
| `activity_span` | (k_last - k_first + 1) × Δt | 从第一个到最后一个活动 bin 的时间跨度 | `NA(no_bin_width)` |
| `peak_activity_bin` | argmax_k A[k] | 活动最密集的 bin 的**索引**（0-N） | - |
| `peak_activity_value` | max A[k] | 活动最密集的 bin 的**事件数** | - |
| `read_activity_entropy_norm` | H_r^{norm} | 读活动分布的归一化熵 [0,1] | - |
| `write_activity_entropy_norm` | H_w^{norm} | 写活动分布的归一化熵 [0,1] | - |
| `top1_share` | max A[k] / Σ A[k] | 最大 bin 占总活动的比例 | - |

##### 详细公式

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
返回活动最密集的 bin 的**索引**（0-N）：
```
peak_idx = argmax_{k} A[k]
```

**7. peak_activity_value**
返回活动最密集的 bin 的**事件数**：
```
A_peak = max_{k} A[k]
```

**8. read_activity_entropy_norm**
读分布的归一化熵：
```
若 TR > 0:
  p_k = R[k] / TR  (对所有 k)
  H_r = -Σ_{k: p_k>0} p_k × log(p_k)
  H_r^{norm} = H_r / log(N)
否则:
  H_r^{norm} = 0
```

**解释**：
- 熵值越高，读活动在时间上分布越均匀
- 熵值越低，读活动越集中在少数时间段
- 归一化到 [0,1]，便于比较

**9. write_activity_entropy_norm**
写分布的归一化熵（公式同上，使用 W[k]）

**10. top1_share**
最大 bin 占比（反映 I/O 突发性）：
```
TA = Σ_{k} A[k]
若 TA > 0:
  S_1 = max_{k} A[k] / TA
否则:
  S_1 = 0
```

**解释**：
- 接近 1：I/O 高度集中在某个时间段（突发性强）
- 接近 0：I/O 均匀分布在多个时间段

##### HEATMAP Signals 的意义

| Signal | 用途 | 异常指示 |
|--------|------|----------|
| `active_time` | 实际 I/O 活跃时间 | 与 runtime 对比，识别 I/O 稀疏性 |
| `activity_span` | I/O 时间跨度 | 识别 I/O 是否分散在整个作业周期 |
| `entropy_norm` | 时间分布均匀性 | 低熵 → I/O 集中（可能是检查点） |
| `top1_share` | 突发性 | 高值 → 短时间大量 I/O（突发） |
| `peak_activity_bin` | 峰值 I/O 强度 | 识别 I/O 瓶颈时刻 |

---

### 4. Signal 总结表（按类别）

#### 时间类（21 个）

| 类别 | Signals |
|------|---------|
| 时间戳 | `read_start_ts`, `read_end_ts`, `write_start_ts`, `write_end_ts`, `meta_start_ts`, `meta_end_ts` |
| 累计时间 | `read_time`, `write_time`, `meta_time`, `io_time` |
| 时间跨度 | `read_span`, `write_span`, `meta_span`, `io_span` |
| 忙碌比例 | `read_busy_frac`, `write_busy_frac`, `meta_busy_frac`, `busy_frac` |
| 延迟 | `avg_read_lat`, `avg_write_lat`, `max_read_time`, `max_write_time` |

#### 性能类（12 个）

| 类别 | Signals |
|------|---------|
| 带宽 | `read_bw`, `write_bw` |
| IOPS | `read_iops`, `write_iops` |
| 操作大小 | `avg_read_size`, `avg_write_size`, `max_read_time_size`, `max_write_time_size` |
| 数据量 | `bytes_read`, `bytes_written`, `reads`, `writes` |

#### 访问模式类（15 个）

| 类别 | Signals |
|------|---------|
| 顺序性 | `seq_read_ratio`, `seq_write_ratio`, `seq_ratio` |
| 连续性 | `consec_read_ratio`, `consec_write_ratio`, `consec_ratio` |
| 读写切换 | `rw_switches` |
| 对齐 | `unaligned_read_ratio`, `unaligned_write_ratio` |
| 大小分布 | `small_read_ratio`, `small_write_ratio`, `tail_read_ratio`, `tail_write_ratio` |
| 数据重用 | `reuse_proxy` |
| 共享性 | `is_shared` |

#### 元数据类（3 个）

| Signals |
|---------|
| `meta_ops`, `meta_intensity`, `meta_fraction` |

#### Rank 不均衡类（7 个）

| Signals |
|---------|
| `rank_imbalance_ratio`, `rank_time_imb`, `fastest_rank_time`, `slowest_rank_time`, `var_rank_time`, `var_rank_bytes`, `bw_variance_proxy` |

#### HEATMAP 时间分布类（10 个）

| Signals |
|---------|
| `total_read_events`, `total_write_events`, `active_bins`, `active_time`, `activity_span`, `peak_activity_bin`, `peak_activity_value`, `read_activity_entropy_norm`, `write_activity_entropy_norm`, `top1_share` |

---

## 设计思路

### 核心原则

1. **Record = Incident = 最小可检索单元**
   - 每个 Darshan record 对应一个 incident 实体
   - 所有 signal 值作为该实体的属性存储（而非独立节点）
   - 支持 incident 级检索：用户查询聚焦于"哪些 incident 的带宽高于 X"

2. **支持下游计算**
   - 保留原始 signal 值用于聚合计算（平均、最大值、百分位等）
   - 不损失数据精度

3. **可解释性**
   - 图边连接表示可比性（相同应用/文件系统/模块）
   - 而非信号相似度
   - 每个实体有自然语言描述

4. **可扩展性**
   - 避免产生数百万个 signal 节点
   - 保持图规模可控（实体数 = 应用数 + 作业数 + 模块数 + 记录数 + 文件数 + 文件系统数）

### 关键设计决策

#### 1. NA 值处理

- **数值字段**: 缺失值统一用 `null` 表示（而非字符串 "NA(...)"）
- **原因字段**: 添加并行字段 `{field_name}_na_reason` 说明缺失原因
- **示例**:
  ```json
  {
    "read_bw": null,
    "read_bw_na_reason": "no_time"
  }
  ```
- **优势**: 便于下游数值计算和过滤

#### 2. Mount Table 作为 Job 属性

- **设计**: mount table 存储为 Job 实体的 `mount_table` 属性
- **格式**: `{mount_pt: fs_type}` 字典
- **不创建边**: 避免 Job 连接所有系统中存在的 filesystem
- **Rationale**: mount table 是系统配置，不是 I/O 行为

#### 3. Job → FileSystem 边

- **边名称**: `TOUCH_FILESYSTEM`
- **创建条件**: 仅连接 records 中**实际访问过**的 filesystem
- **Rationale**: 反映真实 I/O 行为，而非系统配置

#### 4. Signal 命名空间隔离

- **问题**: 同一 record_id 可能在多个 module 中出现（如 HEATMAP 和 POSIX）
- **解决**: 严格限制每个 module section 只解析该 section 内的 records
- **结果**: HEATMAP records 只包含 HEATMAP signals，POSIX records 只包含 POSIX signals

#### 5. 三层层次化结构

- **Job Level**: 作业级别汇总（全局视图）
- **Module Level**: 模块级别性能（接口层视图）
- **Record Level**: 记录级别详细指标（文件级视图）

**优势**:
- 支持多粒度查询
- 便于聚合计算
- 保持数据层次性

#### 6. Description 模板系统

- **实体模板**: 针对每种实体类型定义自然语言模板
- **关系模板**: 针对每种关系类型定义连接语义
- **占位符填充**: 自动填充实体属性到模板
- **NA 处理**: 显示缺失原因而非"N/A"

**优势**:
- 提高可解释性
- 便于 LLM 理解
- 支持自然语言查询

#### 7. Chunk 作为原始数据快照

- **设计**: 每个实体的 chunk_text 包含原始 counter 数据
- **格式**: 保留原始 Darshan log 格式
- **用途**:
  - LLM 可以访问原始数据
  - 支持精确数值查询
  - 验证 signal 计算

#### 8. 本地 Embedding

- **设计**: 使用本地 Transformer 模型而非 OpenAI API
- **优势**:
  - 无 API 成本
  - 无网络依赖
  - 完全可控
  - 支持离线环境

---

## 使用示例

### 示例 1: 从头到尾的完整流程

```bash
# 0. 解压日志
./scripts/unpack-darshan-logs.sh /path/to/darshan-logs/

# 1. 解析日志（使用 darshan-parser）
darshan-parser /path/to/log.darshan > /path/to/log.txt

# 2. 计算 signals
python3 scripts/process_darshan_signals_v2.4.py \
    /path/to/log.txt \
    -o /path/to/log_signals_v2.4.txt

# 3. 构建 KG
python experiments/darshan_kg_builder_v2.1.py \
    -i /path/to/log_signals_v2.4.txt \
    -o /path/to/kg.json

# 4. 生成描述
python3 scripts/generate_descriptions_v3.py \
    /path/to/kg.json \
    /path/to/kg_with_desc.json

# 5. 添加 chunks
python3 scripts/parse_darshan_chunks.py \
    --log /path/to/log.txt \
    --kg /path/to/kg_with_desc.json \
    --output /path/to/kg_with_chunks.json

# 6. 生成 embeddings
python3 scripts/embed_kg_local.py \
    --kg /path/to/kg_with_chunks.json \
    --output ./embeddings \
    --model google/embeddinggemma-300m \
    --batch-size 32

# 7. 加载到 LightRAG
python3 scripts/load_custom_kg_to_lightrag.py \
    --kg /path/to/kg_with_chunks.json \
    --embeddings ./embeddings \
    --embedding-model google/embeddinggemma-300m
```

### 示例 2: 批量处理多个日志

```bash
# 批量解析（在 Jupyter notebook 中）
import os
import subprocess
from pathlib import Path
from tqdm import tqdm

parent_dir = '/path/to/darshan-logs/'
parsed_root = Path('~/parsed-logs/').expanduser()
parsed_root.mkdir(parents=True, exist_ok=True)

# 收集所有 .darshan 文件
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

# 批量解析
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

print(f"\n✅ 解析完成: 成功 {success_count} 个, 失败 {fail_count} 个")
```

### 示例 3: 在 Notebook 中查询

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
    print("⚠️  请设置 OPENAI_API_KEY 环境变量")
else:
    print("✅ OPENAI_API_KEY 已加载")

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
    """查询 Darshan KG"""
    result = await rag.aquery(
        question,
        param=QueryParam(mode=mode, top_k=top_k)
    )
    return result

print("✓ Query helper ready!")

# Cell 7: Example Queries
# 基本查询
result = await query("What are the POSIX I/O operations?")
print(result)

# 查询文件访问
result = await query("Which files were accessed and where?")
print(result)

# 分析 I/O 性能
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

### 示例 4: 自定义查询

```python
# 基于时间的查询
result = await query("Which records spent the most time in read operations?")

# 基于性能的查询
result = await query("Which records achieved read bandwidth over 1000 MB/s?")

# 基于访问模式的查询
result = await query("Find records with high sequential access ratios on Lustre")

# 跨层级聚合查询
result = await query("What are the average I/O characteristics for this application?")

# 元数据密集型负载
result = await query("Show records with high metadata intensity on NFS")

# Rank 不均衡
result = await query("Which shared files have the highest rank imbalance in I/O time?")
```

---

## 故障排查

### 问题 1: `process_darshan_signals_v2.4.py` 输出为空

**可能原因**:
- 输入文件格式不正确（不是 darshan-parser 的输出）
- 文件编码问题

**解决**:
```bash
# 检查文件头
head -20 input.txt

# 应该看到类似这样的 header:
# darshan log version: 3.41
# compression method: BZIP2
# exe: 4068766220
# ...

# 重新解析
darshan-parser input.darshan > output.txt
```

### 问题 2: `darshan_kg_builder_v2.1.py` 报错 "No records found"

**可能原因**:
- Signal 文件不是 v2.4+ 格式
- Record section 格式不正确

**解决**:
```bash
# 检查 signal 文件格式
grep "# Record:" signal_file.txt

# 应该看到类似:
# Record: 11610284057069735693, rank=-1, file=/home/file, mount=/home, fs=lustre
```

### 问题 3: `embed_kg_local.py` 报错 "CUDA out of memory"

**可能原因**:
- Batch size 太大
- 模型太大

**解决**:
```bash
# 减小 batch size
python3 scripts/embed_kg_local.py \
    --kg kg.json \
    --output ./embeddings \
    --batch-size 4  # 从 32 减到 4

# 或使用 CPU
python3 scripts/embed_kg_local.py \
    --kg kg.json \
    --output ./embeddings \
    --device cpu
```

### 问题 4: `load_custom_kg_to_lightrag.py` 报错 "OpenAI API key not provided"

**解决**:
```bash
# 方法 1: 环境变量
export OPENAI_API_KEY=sk-your-key-here
python3 scripts/load_custom_kg_to_lightrag.py --kg kg.json

# 方法 2: 命令行参数
python3 scripts/load_custom_kg_to_lightrag.py \
    --kg kg.json \
    --openai-key sk-your-key-here
```

### 问题 5: LightRAG 查询结果不准确

**可能原因**:
- Embedding 模型不一致
- Top-k 太小
- 查询模式不合适

**解决**:
```python
# 1. 增加 top_k
result = await query("question", mode="hybrid", top_k=20)

# 2. 尝试不同的查询模式
result = await query("question", mode="local")  # 局部搜索
result = await query("question", mode="global")  # 全局搜索
result = await query("question", mode="mix")  # 混合搜索

# 3. 启用 rerank（需要配置 rerank 模型）
result = await rag.aquery(
    "question",
    param=QueryParam(mode="hybrid", enable_rerank=True)
)
```

---

## 文件结构

```
/users/Minqiu/DarshanRAG/experiments/
├── config_paths.py                      # 路径配置模块
├── darshan_kg_builder_v2.1.py           # KG 构建脚本
├── notebooks/
│   └── IORAG.ipynb                      # 主 notebook
├── scripts/
│   ├── unpack-darshan-logs.sh           # 解压日志
│   ├── process_darshan_signals_v2.4.py  # 信号提取
│   ├── generate_descriptions_v3.py      # 生成描述
│   ├── parse_darshan_chunks.py          # 解析 chunks
│   ├── embed_kg_local.py                # 本地嵌入
│   ├── embed_kg_cpu_optimized.sh        # CPU 优化嵌入
│   └── load_custom_kg_to_lightrag.py    # 加载 KG
├── results/                             # 结果输出
├── storage/                             # RAG 存储
├── ground_truth/                        # 真值数据
└── IORAG_README.md                      # 本文档
```

---

## 参考资料

- [LightRAG GitHub](https://github.com/HKUDS/LightRAG)
- [Darshan Documentation](https://www.mcs.anl.gov/research/projects/darshan/)
- [Hugging Face Transformers](https://huggingface.co/docs/transformers)
- [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m)
- [Sentence Transformers](https://www.sbert.net/)

---

## 版本历史

- **v1.0** (2026-02-10): 初始版本
  - 完整 workflow 文档
  - 所有脚本详解
  - Signal 计算规格
  - 设计思路说明

---

**Author**: Claude
**Date**: 2026-02-10
**Version**: 1.0
