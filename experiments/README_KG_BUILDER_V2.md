# Darshan Knowledge Graph Builder V2

将 Darshan signal extraction output (v2.4+) 转换为 LightRAG custom KG 格式，用于 incident 级检索、下游计算和可解释分析。

## 设计思路

### 核心原则

**Record = Incident = 最小可检索单元**

每个 Darshan record 对应一个 incident 实体，所有 SIGNAL_* 值作为该实体的属性存储，而非独立节点。

### 为什么这样设计？

1. **支持 incident 级检索**：用户查询聚焦于 "哪些 incident 的带宽高于 X"，而非 "带宽节点"
2. **支持下游计算**：保留原始 signal 值用于聚合计算（平均、最大值、百分位等）
3. **可解释性**：图边连接表示可比性（相同应用/文件系统/模块），而非信号相似度
4. **可扩展性**：避免产生数百万个 signal 节点，保持图规模可控

## 关键设计决策（V2改进）

### 1. NA 值处理
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

### 2. Mount Table 作为 Job 属性
- **设计**: mount table 存储为 Job 实体的 `mount_table` 属性
- **格式**: `{mount_pt: fs_type}` 字典
- **不创建边**: 避免 Job 连接所有系统中存在的 filesystem

### 3. Job → FileSystem 边
- **边名称**: `TOUCH_FILESYSTEM`
- **创建条件**: 仅连接 records 中**实际访问过**的 filesystem
- **rationale**: 反映真实 I/O 行为，而非系统配置

### 4. Signal 命名空间隔离
- **问题**: 同一 record_id 可能在多个 module 中出现（如 HEATMAP 和 POSIX）
- **解决**: 严格限制每个 module section 只解析该 section 内的 records
- **结果**: HEATMAP records 只包含 HEATMAP signals，POSIX records 只包含 POSIX signals

## 图结构（V2架构）

### 节点类型（6种）

#### A) Application
- **ID**: `App_{exe}`
- **属性**: `exe`
- **示例**: `App_4068766220`

#### B) Job
- **ID**: `Job_{job_id}`
- **属性**:
  - `job_id`: Job 标识
  - `uid`: 用户ID
  - `nprocs`: 进程数
  - `start_time`: 起始时间戳
  - `end_time`: 结束时间戳
  - `runtime`: 运行时长（秒）
  - `total_bytes_read`: Job 级读取字节数
  - `total_bytes_written`: Job 级写入字节数
  - `total_reads`: 总读操作数
  - `total_writes`: 总写操作数
  - `job_io_summary`: Job 级 I/O 摘要（目前留空，后续用模板抽取）
- **示例**: `Job_3122490`

#### C) Module
- **ID**: `{job_id}::{module_name}`
- **属性**:
  - `module_name`: HEATMAP | POSIX | STDIO | MPIIO
  - Module 级聚合指标（`total_bytes_read`, `total_bytes_written`, 等）
  - Module 级性能指标（`read_bw`, `write_bw`, `avg_read_size`, 等）
- **示例**: `3122490::POSIX`

#### D) Record
- **ID**: `{job_id}::{module_name}::{record_id}::rank{rank}`
- **属性**:
  - `record_id`: Darshan record 标识
  - `rank`: MPI rank
  - `file_name`: 访问的文件名
  - `mount_pt`: 挂载点
  - `fs_type`: 文件系统类型
  - 所有 SIGNAL_* 派生指标作为属性，包括：
    - **时间指标**: `read_start_ts`, `read_end_ts`, `write_start_ts`, `write_end_ts`, `meta_start_ts`, `meta_end_ts`
    - **时长指标**: `read_time`, `write_time`, `meta_time`, `io_time`
    - **时间跨度**: `read_span`, `write_span`, `meta_span`, `io_span`
    - **忙碌比例**: `read_busy_frac`, `write_busy_frac`, `meta_busy_frac`, `busy_frac`
    - **性能指标**: `read_bw`, `write_bw`, `read_iops`, `write_iops`
    - **操作大小**: `avg_read_size`, `avg_write_size`
    - **访问模式**: `seq_ratio`, `consec_ratio`, `seq_read_ratio`, `seq_write_ratio`
    - **延迟指标**: `avg_read_lat`, `avg_write_lat`, `max_read_time`, `max_write_time`
    - **Rank 不均衡**: `rank_imbalance_ratio`, `rank_time_imb`, `fastest_rank_time`, `slowest_rank_time`
    - **HEATMAP 特有**: `active_bins`, `active_time`, `activity_span`, `peak_activity_bin`, `read_activity_entropy_norm`
- **示例**: `3122490::POSIX::11610284057069735693::rank0`

#### E) File
- **ID**: `File_{file_path_norm}`
- **属性**:
  - `file_path_raw`: 原始文件路径
  - `file_path_norm`: 标准化文件路径（用于唯一标识）
  - `mount_pt`: 挂载点
  - `fs_type`: 文件系统类型
- **示例**: `File__home_3079452805`
- **注意**: heatmap:POSIX 等虚拟文件不创建 File 节点

#### F) FileSystem
- **ID**: `FS_{fs_type}_{mount_pt_norm}`
- **属性**:
  - `mount_pt`: 挂载点路径
  - `fs_type`: 文件系统类型（lustre, nfs, ext4, 等）
- **示例**: `FS_lustre__home`
- **唯一性**: 基于 (mount_pt, fs_type) 组合

### 边类型

#### Application → Job (HAS_JOB)
- **Keywords**: `application job executable`
- **含义**: 同一可执行文件产生的 jobs

#### Job → Module (HAS_MODULE)
- **Keywords**: `job module io_layer`
- **含义**: Job 使用的 I/O 模块

#### Module → Record (HAS_RECORD)
- **Keywords**: `module record incident`
- **含义**: 模块下的记录（incidents）

#### Record → File (ON_FILE)
- **Keywords**: `record file io_access`
- **含义**: Record 访问的文件
- **创建条件**: 仅当 file_name 不以 "heatmap:" 开头时

#### File → FileSystem (ON_FILESYSTEM)
- **Keywords**: `file filesystem storage`
- **含义**: 文件所在的文件系统
- **创建条件**: fs_type 和 mount_pt 都不为 "UNKNOWN"

#### Job → FileSystem (TOUCH_FILESYSTEM)
- **Keywords**: `job filesystem storage`
- **含义**: Job 访问的文件系统

## 使用方法

### 命令行

```bash
# 单个文件
python experiments/darshan_kg_builder_v2.py \
  -i data/examples/Darshan_log_example_signals_v2.4.txt \
  -o output_kg_v2.json

# 包含 txt 文件的目录
python experiments/darshan_kg_builder_v2.py \
  -i /path/to/logs_directory \
  -o output_kg_v2.json

# 包含子目录的父目录
python experiments/darshan_kg_builder_v2.py \
  -i /path/to/parent_directory \
  -o output_kg_v2.json
```

### Python API

```python
from darshan_kg_builder_v2 import DarshanKGBuilderV2

# 初始化 builder
builder = DarshanKGBuilderV2()

# 解析单个文件
builder.parse_darshan_signal_file("path/to/log.txt")

# 或解析目录
builder.parse_darshan_directory("/path/to/logs")

# 构建 LightRAG custom KG
kg = builder.build_lightrag_kg(
    source_id="darshan-logs-v2.4",
    file_path="/path/to/logs"
)

# 保存为 JSON
import json
with open("output_kg_v2.json", "w") as f:
    json.dump(kg, f, indent=2)
```

### 与 LightRAG 集成

```python
import json
from lightrag import LightRAG
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

# 加载生成的 KG
with open("output_kg_v2.json", "r") as f:
    custom_kg = json.load(f)

# 初始化 LightRAG
rag = LightRAG(
    working_dir="./darshan_rag_storage",
    embedding_func=openai_embed,
    llm_model_func=gpt_4o_mini_complete,
)

# 插入 custom KG
await rag.ainsert_custom_kg(custom_kg)

# 查询示例
result = await rag.aquery(
    "Which records had high read bandwidth on Lustre filesystem?",
    param=QueryParam(mode="hybrid")
)
```

## 查询思路

### 基于时间的查询

```python
# 查找读取时间最长的 records
"Which records spent the most time in read operations?"

# 查找 I/O 时间跨度最大的 records
"Show records with the largest I/O span between first and last operations"

# 查找读写交替频繁的 records
"Find records with high read-write switch rates"
```

### 基于性能的查询

```python
# 高带宽 incidents
"Which records achieved read bandwidth over 1000 MB/s?"

# 低效 I/O 模式
"Find records with high small write ratios on Lustre"

# Rank 不均衡
"Which shared files have the highest rank imbalance in I/O time?"
```

### 基于访问模式的查询

```python
# 顺序访问 vs 随机访问
"Compare sequential access ratios across different file systems"

# 元数据密集型负载
"Show records with high metadata intensity on NFS"

# 数据重用
"Find records with high data reuse on the same file"
```

### 跨层级聚合查询

```python
# Application 级分析
"What are the average I/O characteristics for application 4068766220?"

# Module 级比较
"Compare POSIX vs STDIO performance for this job"

# FileSystem 级聚合
"Show average bandwidth for all Lustre filesystems"
```

## 输出示例

对于 `Darshan_log_example_signals_v2.4.txt`:

```
Total entities: 68
Total relationships: 99

Entity breakdown:
  APPLICATION: 1
  JOB: 1
  MODULE: 3 (HEATMAP, POSIX, STDIO)
  RECORD: 40 (8 HEATMAP + 10 POSIX + 22 STDIO)
  FILE: 22
  FILESYSTEM: 1 (only touched filesystems)
```

**注意**: 同一 record_id 可能在多个 module 中出现（如 HEATMAP 和 POSIX 共享同一 record_id），但它们被正确分离为独立的 Record 实体，各自包含对应 module 的 signals。

### Job 实体示例

```json
{
  "entity_name": "Job_3122490",
  "entity_type": "JOB",
  "description": "",
  "source_id": "darshan-logs",
  "file_path": "...",
  "job_id": 3122490,
  "uid": 1449515727,
  "nprocs": 4,
  "runtime": 7451.1501,
  "start_time": 1735781151,
  "end_time": 1735788602,
  "total_bytes_read": 7489771.0,
  "total_bytes_written": 11201335.0,
  "total_reads": 910.0,
  "total_writes": 89257.0,
  "mount_table": {
    "/home": "lustre",
    "/lus/grand": "lustre",
    "/lus/eagle": "lustre",
    ...
  },
  "job_io_summary": ""
}
```

**注意**: Job 实体不再包含 `exe` 字段（exe 只在 Application 实体中）。

### Record 实体示例（含时间 signals 和 NA 处理）

```json
{
  "entity_name": "3122490::POSIX::11610284057069735693::rank-1",
  "entity_type": "RECORD",
  "description": "",
  "source_id": "darshan-logs",
  "file_path": "...",
  "record_id": "11610284057069735693",
  "rank": -1,
  "file_name": "/home/3079452805",
  "mount_pt": "/home",
  "fs_type": "lustre",
  "read_start_ts": 23.047361,
  "read_end_ts": 23.049321,
  "read_time": 0.005924,
  "read_span": 0.001960000000000406,
  "read_busy_frac": 3.0224489795912106,
  "read_bw": 131.12732077836188,
  "read_iops": 16880.486158001353,
  "avg_read_size": 8145.32,
  "avg_read_lat": 5.9239999999999995e-05,
  "max_read_time": 0.001155,
  "io_span": 23.049321,
  "io_time": 0.008766,
  "busy_frac": 0.00038031489083778215,
  "seq_ratio": 0.96,
  "consec_ratio": 0.96,
  "meta_ops": 112.0,
  "meta_intensity": 1.12,
  "rank_imbalance_ratio": 1.0,
  "rank_time_imb": 0.3467799009200283,
  "is_shared": 1,
  "avg_write_lat": null,
  "avg_write_lat_na_reason": "no_writes",
  "write_bw": null,
  "write_bw_na_reason": "no_write_time"
}
```

**NA 值处理示例**: 数值字段用 `null` 表示缺失，原因存储在 `*_na_reason` 字段中。

## 输入格式

工具支持 Darshan signal extraction output v2.4+ 格式：

```
# darshan log version: 3.41
# exe: 4068766220
# uid: 1449515727
# jobid: 3122490
# start_time: 1735781151
# end_time: 1735788602
# nprocs: 4
# run time: 7451.1501

# mount entry:	/home	lustre
# mount entry:	/lus/grand	lustre

# *******************************************************
# JOB LEVEL - Derived Signals
# *******************************************************
JOB	total_bytes_read	7489771.0
JOB	total_bytes_written	11201335.0

# *******************************************************
# POSIX module - Derived Signals
# *******************************************************
POSIX	MODULE_AGG	total_bytes_read	4204115.0
POSIX	MODULE_PERF	read_bw	NA(no_time)

# Record: 11610284057069735693, rank=-1, file=/home/3079452805, mount=/home, fs=lustre
SIGNAL_READ_START_TS	23.047361
SIGNAL_READ_END_TS	23.049321
SIGNAL_READ_BW	131.12732077836188
...
```

## 待开发功能

1. **Description 和 Chunk 生成**：使用模板抽取技术自动生成实体描述和文本 chunks
2. **Job I/O Summary**：基于 signals 自动生成自然语言摘要
3. **Incident 聚类**：基于访问模式相似性连接 records

## 实现细节

- **正则表达式解析**：对格式变化具有鲁棒性
- **类型自动转换**：自动识别 int/float/string 值
- **NA 值保留**：保留 "NA(...)" 以维护数据完整性
- **批处理**：支持处理数百个日志文件的目录
- **LightRAG 兼容**：输出格式完全符合 LightRAG custom KG schema
