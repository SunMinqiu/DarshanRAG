# Darshan Knowledge Graph Builder

构建符合LightRAG custom_kg格式的Darshan日志知识图谱。

## 📋 目录

- [快速开始](#快速开始)
- [功能特性](#功能特性)
- [知识图谱Schema](#知识图谱schema)
- [使用方法](#使用方法)
- [示例](#示例)
- [故障排除](#故障排除)

---

## 🚀 快速开始

### 1. 构建知识图谱

```bash
# 从单个log文件构建KG
python build_darshan_kg.py --input_path /path/to/log.txt --output_path darshan_kg.json

# 从文件夹构建KG（递归遍历所有.txt文件）
python build_darshan_kg.py --input_path /path/to/logs/ --output_path darshan_kg.json

# 从父文件夹构建KG
python build_darshan_kg.py --input_path /users/Minqiu/parsed-logs-2025-1-1/ --output_path darshan_graph1_2025-1-1.json
```

### 2. 加载到LightRAG

```bash
# 设置OpenAI API密钥
export OPENAI_API_KEY='sk-...'

# 加载KG并运行示例查询
python load_darshan_kg.py --kg_path darshan_kg.json

# 仅加载KG，不运行查询
python load_darshan_kg.py --kg_path darshan_kg.json --no-queries
```

---

## ✨ 功能特性

### 输入灵活性
- ✅ **单个文件**: 处理单个`.txt`格式的Darshan日志
- ✅ **文件夹**: 遍历指定文件夹中的所有日志
- ✅ **递归遍历**: 自动递归搜索子文件夹中的所有`.txt`文件
- ✅ **自定义输出路径**: 指定KG输出位置

### KG构建特性
- ✅ 符合LightRAG `custom_kg`格式
- ✅ 完整的Schema支持（Job、Module、FileRecord、Phase、EventAnchor、Counter）
- ✅ 保留所有counter数据（不丢失任何信息）
- ✅ 自动推导Phase和EventAnchor
- ✅ 智能文件角色识别（checkpoint/log/temp/data）
- ✅ 时间锚点提取和对齐

---

## 📊 知识图谱Schema

### A. Job节点（作业层）

**Primary Key**: `job_id`

**MUST字段**:
- `job_id`: 作业ID
- `start_time`: 开始时间戳
- `end_time`: 结束时间戳
- `runtime_sec`: 运行时长（秒）
- `nprocs`: 进程数
- `log_version`: Darshan版本

**SHOULD字段**:
- `exe`: 可执行文件原始路径
- `exe_norm`: 归一化可执行文件名
- `uid`: 用户ID
- `mount_table_digest`: 挂载表摘要

**边关系**:
- `(Job)-[:HAS_MODULE]->(Module)`

---

### B. Module节点（模块层）

**Primary Key**: `job_id + module_name`

**MUST字段**:
- `module_name`: 模块名称（POSIX/STDIO/MPIIO/H5F等）
- `job_id`: 所属作业ID

**SHOULD字段**:
- `module_present`: 模块是否存在
- `record_count`: 记录数量

**边关系**:
- `(Job)-[:HAS_MODULE]->(Module)`
- `(Module)-[:HAS_RECORD]->(FileRecord)`

---

### C. FileRecord节点（文件记录层）

**Primary Key**: `job_id + module_name + record_id`

**MUST字段**:
- `job_id`, `module_name`, `record_id`
- `file_path`: 文件路径
- `rank`: 进程rank（-1表示共享文件）
- `mount_pt`: 挂载点
- `fs_type`: 文件系统类型

**SHOULD字段**:
- `is_shared`: 是否为共享文件（rank == -1）
- `path_tokens`: 路径分词（便于检索）
- `path_depth`: 路径深度
- `file_role_hint`: 文件角色提示（data/checkpoint/temp/log/unknown）
- `time_anchors`: 时间锚点

**关键字段**:
- ✅ **`counters_blob`**: JSON格式，保存该record的所有counter（细粒度数据）

**边关系**:
- `(Module)-[:HAS_RECORD]->(FileRecord)`
- `(FileRecord)-[:HAS_PHASE]->(Phase)`
- `(FileRecord)-[:HAS_COUNTER]->(Counter)` (可选)

---

### D. Phase节点（时间段层，诊断核心）

**Primary Key**: `job_id + module_name + record_id + phase_type`

**MUST字段**:
- `phase_type`: 阶段类型（open/read/write/close/meta）
- `t_start`: 开始时间戳
- `t_end`: 结束时间戳
- `duration`: 持续时间
- `bytes`: 字节数

**SHOULD字段**:
- `iops_est`: 估算IOPS
- `bw_est`: 估算带宽
- `is_sparse_time`: 时间戳是否稀疏

**边关系**:
- `(FileRecord)-[:HAS_PHASE]->(Phase)`
- `(Phase)-[:CONTAINS_ANCHOR]->(EventAnchor)`

---

### E. EventAnchor节点（时间点层，对齐/证据链）

**Primary Key**: `job_id + module_name + record_id + kind`

**MUST字段**:
- `kind`: 事件类型（first_open/last_read等）
- `timestamp`: 时间戳

**SHOULD字段**:
- `source_counter_name`: 来源counter名称
- `confidence`: 置信度（1.0=原始提供；0.5=推导）

**边关系**:
- `(Phase)-[:CONTAINS_ANCHOR]->(EventAnchor)`

---

### F. Counter节点（可选，用于结构化索引）

**Primary Key**: `job_id + module_name + record_id + counter_name`

**MUST字段**:
- `counter_name`: Counter名称
- `counter_type`: 类型（scalar/hist/topk/timestamp/rank_stat）
- `value_json`: JSON格式的值

**边关系**:
- `(FileRecord)-[:HAS_COUNTER]->(Counter)`

---

## 🔧 使用方法

### 命令行参数

#### `build_darshan_kg.py`

```bash
python build_darshan_kg.py [OPTIONS]

必需参数:
  --input_path PATH     Darshan日志路径（文件/文件夹/父文件夹）

可选参数:
  --output_path PATH    输出KG JSON文件路径（默认: darshan_kg.json）
```

#### `load_darshan_kg.py`

```bash
python load_darshan_kg.py [OPTIONS]

必需参数:
  --kg_path PATH        KG JSON文件路径

可选参数:
  --working_dir PATH    LightRAG工作目录（默认: ./lightrag_darshan_storage）
  --no-queries          跳过示例查询
```

---

## 📝 示例

### 示例1: 处理单个log文件

```bash
# 1. 构建KG
python build_darshan_kg.py \
    --input_path /path/to/single_log.txt \
    --output_path single_job_kg.json

# 2. 加载到LightRAG
export OPENAI_API_KEY='sk-...'
python load_darshan_kg.py --kg_path single_job_kg.json
```

### 示例2: 处理整个文件夹

```bash
# 1. 构建KG（递归遍历所有.txt文件）
python build_darshan_kg.py \
    --input_path /users/Minqiu/parsed-logs-2025-1-1/ \
    --output_path darshan_graph1_2025-1-1.json

# 输出示例:
# 🔍 Searching for Darshan logs in: /users/Minqiu/parsed-logs-2025-1-1/
# ✅ Found 150 log file(s)
# 📄 [1/150] Parsing: /users/Minqiu/parsed-logs-2025-1-1/job1.txt
#    ✓ Extracted 3 modules
# ...
# 📊 Knowledge Graph Statistics:
#    - Chunks: 150
#    - Entities: 4523
#    - Relationships: 8946

# 2. 加载到LightRAG
python load_darshan_kg.py \
    --kg_path darshan_graph1_2025-1-1.json \
    --working_dir ./rag_storage_2025_1_1
```

### 示例3: 程序化查询

```python
import asyncio
import json
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

async def query_kg():
    # 初始化LightRAG
    rag = LightRAG(
        working_dir='./lightrag_darshan_storage',
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete
    )

    await rag.initialize_storages()

    # 查询示例
    queries = [
        "Which jobs accessed checkpoint files?",
        "What is the I/O performance pattern for shared files?",
        "Show me jobs with high read bandwidth on Lustre filesystem"
    ]

    for query in queries:
        result = await rag.aquery(
            query,
            param=QueryParam(mode="hybrid")
        )
        print(f"Q: {query}")
        print(f"A: {result}\n")

    await rag.finalize_storages()

asyncio.run(query_kg())
```

---

## 🛠️ 故障排除

### 问题1: "No log files found!"

**原因**: 输入路径不存在或没有`.txt`文件

**解决**:
```bash
# 检查路径是否正确
ls -la /path/to/logs/

# 确保日志文件是.txt格式（darshan-parser输出）
darshan-parser your_log.darshan > your_log.txt
```

### 问题2: 插入KG很慢

**原因**: 需要为所有实体和关系生成embeddings（调用OpenAI API）

**解决**:
- ✅ 这是正常现象（参考之前的讨论）
- ✅ 使用更快的embedding模型：`text-embedding-3-small`
- ✅ 增加并发度（修改`embedding_func_max_async`参数）
- ✅ 使用本地embedding模型（Sentence-Transformers）

### 问题3: "OPENAI_API_KEY not set"

**解决**:
```bash
export OPENAI_API_KEY='sk-your-api-key-here'
```

### 问题4: 解析失败

**原因**: Darshan log格式不符合预期

**解决**:
```bash
# 确保使用darshan-parser转换
darshan-parser --all your_log.darshan > your_log.txt

# 检查log格式
head -50 your_log.txt
```

---

## 📖 抽取规则（内置规则，确保数据一致性）

脚本遵循以下硬约束规则：

1. ✅ **永远不丢counter**: 所有`POSIX_*`, `STDIO_*`等字段原样进入`FileRecord.counters_blob`

2. ✅ **时间戳处理**:
   - 如果存在`*_START_TIMESTAMP`/`*_END_TIMESTAMP`，必须生成`EventAnchor`
   - 自动生成/更新对应`Phase`的`t_start`/`t_end`

3. ✅ **Phase推导**:
   - 优先从标量counter推导bytes/time/ops
   - 其次才使用`t_end - t_start`

4. ✅ **共享文件标识**:
   - `rank == -1`的record标为`is_shared=true`
   - 这是并行不均衡诊断的关键

5. ✅ **缺失字段处理**:
   - 不猜测数值
   - 使用`null` + `confidence`标注
   - 对Phase允许标注"unknown time range"

---

## 📚 输出格式

### KG JSON结构

```json
{
  "chunks": [
    {
      "content": "Job job123 Summary: ...",
      "source_id": "doc-job123",
      "chunk_order_index": 1,
      "file_path": "log.txt"
    }
  ],
  "entities": [
    {
      "entity_name": "Job_job123",
      "entity_type": "Job",
      "description": "Job job123 executed app.exe with 256 processes for 3600 seconds",
      "source_id": "doc-job123",
      "file_path": "log.txt",
      "properties": {
        "job_id": "job123",
        "start_time": 1704067200,
        "end_time": 1704070800,
        "runtime_sec": 3600,
        "nprocs": 256,
        "exe": "/path/to/app.exe",
        "exe_norm": "app.exe"
      }
    },
    {
      "entity_name": "FileRecord_job123_POSIX_abc123",
      "entity_type": "FileRecord",
      "description": "File record abc123 for file /scratch/data.h5 (rank=0, shared=False)",
      "source_id": "doc-job123",
      "file_path": "log.txt",
      "properties": {
        "job_id": "job123",
        "module_name": "POSIX",
        "record_id": "abc123",
        "file_path": "/scratch/data.h5",
        "rank": 0,
        "is_shared": false,
        "file_role_hint": "data",
        "counters_blob": {
          "POSIX_BYTES_READ": 1048576000,
          "POSIX_BYTES_WRITTEN": 524288000,
          "POSIX_READ_START_TIMESTAMP": 1704067300,
          "POSIX_READ_END_TIMESTAMP": 1704067600,
          ...
        }
      }
    }
  ],
  "relationships": [
    {
      "src_id": "Job_job123",
      "tgt_id": "Module_job123_POSIX",
      "description": "Job job123 uses module POSIX",
      "keywords": "has_module uses",
      "source_id": "doc-job123",
      "file_path": "log.txt",
      "weight": 1.0
    }
  ]
}
```

---

## 🎯 下一步

构建并加载KG后，你可以：

1. **诊断I/O性能问题**:
   ```python
   result = await rag.aquery(
       "Which jobs have low I/O bandwidth on shared files?",
       param=QueryParam(mode="hybrid")
   )
   ```

2. **分析checkpoint模式**:
   ```python
   result = await rag.aquery(
       "What are the checkpoint file access patterns across jobs?",
       param=QueryParam(mode="global")
   )
   ```

3. **识别热点文件**:
   ```python
   result = await rag.aquery(
       "Which files are accessed by the most jobs?",
       param=QueryParam(mode="mix")
   )
   ```

4. **导出分析**:
   ```python
   # 导出KG为CSV/Excel用于进一步分析
   rag.export_data("darshan_kg_analysis.xlsx", file_format="excel")
   ```

---

## 📞 联系与反馈

如有问题或建议，请提交Issue或PR。

**Happy Querying! 🚀**
