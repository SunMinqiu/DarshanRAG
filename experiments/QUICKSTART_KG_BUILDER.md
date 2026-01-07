# Darshan KG Builder - 快速开始指南

## 🚀 5分钟快速上手

### 步骤1: 安装依赖

```bash
cd /users/Minqiu/DarshanRAG/experiments

# 安装Python依赖
pip install -r requirements_kg_builder.txt

# 或者使用uv（推荐）
uv pip install -r requirements_kg_builder.txt
```

### 步骤2: 运行测试（可选）

```bash
# 验证安装是否成功
python test_kg_builder.py

# 预期输出:
# 🎉 ALL TESTS PASSED!
```

### 步骤3: 构建知识图谱

```bash
# 从Darshan日志构建KG
python build_darshan_kg.py \
    --input_path /users/Minqiu/parsed-logs-2025-1-1 \
    --output_path darshan_graph1_2025-1-1.json

# 预期输出:
# 🔍 Searching for Darshan logs in: /users/Minqiu/parsed-logs-2025-1-1
# ✅ Found 150 log file(s)
# 📄 [1/150] Parsing: ...
# ...
# 📊 Knowledge Graph Statistics:
#    - Chunks: 150
#    - Entities: 4523
#    - Relationships: 8946
# ✅ Knowledge graph saved successfully!
```

### 步骤4: 加载到LightRAG

```bash
# 设置OpenAI API密钥
export OPENAI_API_KEY='sk-your-api-key-here'

# 加载KG到LightRAG
python load_darshan_kg.py \
    --kg_path darshan_graph1_2025-1-1.json \
    --working_dir ./lightrag_storage_2025_1_1

# 预期输出:
# 📂 Loading KG from: darshan_graph1_2025-1-1.json
# 📊 KG Statistics:
#    - Chunks: 150
#    - Entities: 4523
#    - Relationships: 8946
# 🚀 Initializing LightRAG...
# ✅ LightRAG initialized
# 📥 Inserting KG into LightRAG...
# ⚠️  This will generate embeddings for all entities and relationships.
# ⏳ This may take a while...
# ✅ KG inserted successfully!
#
# 🔍 Running Example Queries
# --- Query 1/5 ---
# Q: What jobs are in the knowledge graph?
# ...
```

---

## 📖 详细说明

### 输入格式要求

**支持的输入类型**:
1. ✅ 单个`.txt`文件（darshan-parser输出）
2. ✅ 包含多个`.txt`文件的文件夹
3. ✅ 父文件夹（会递归搜索所有`.txt`文件）

**如何获取`.txt`格式的Darshan日志**:

```bash
# 使用darshan-parser转换.darshan文件
darshan-parser --all your_log.darshan > your_log.txt

# 批量转换
for log in *.darshan; do
    darshan-parser --all "$log" > "${log%.darshan}.txt"
done
```

---

## 🎯 常见使用场景

### 场景1: 单个作业分析

```bash
# 1. 转换单个darshan日志
darshan-parser --all job_12345.darshan > job_12345.txt

# 2. 构建KG
python build_darshan_kg.py \
    --input_path job_12345.txt \
    --output_path job_12345_kg.json

# 3. 加载并查询
python load_darshan_kg.py --kg_path job_12345_kg.json
```

### 场景2: 批量作业分析

```bash
# 1. 批量转换darshan日志
mkdir parsed_logs
for log in /path/to/darshan/logs/*.darshan; do
    darshan-parser --all "$log" > "parsed_logs/$(basename ${log%.darshan}).txt"
done

# 2. 构建大规模KG
python build_darshan_kg.py \
    --input_path parsed_logs/ \
    --output_path batch_analysis_kg.json

# 3. 加载到LightRAG
python load_darshan_kg.py \
    --kg_path batch_analysis_kg.json \
    --working_dir ./lightrag_batch_storage
```

### 场景3: 程序化查询

```python
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed

async def main():
    # 初始化LightRAG（指向已有的存储）
    rag = LightRAG(
        working_dir='./lightrag_storage_2025_1_1',
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete
    )

    await rag.initialize_storages()

    # 自定义查询
    questions = [
        "Which jobs have the highest I/O bandwidth?",
        "What files are frequently accessed as checkpoints?",
        "Show me jobs with imbalanced I/O across ranks",
        "Which filesystem (Lustre/GPFS/NFS) is used most?"
    ]

    for q in questions:
        print(f"\nQ: {q}")
        result = await rag.aquery(q, param=QueryParam(mode="hybrid"))
        print(f"A: {result}\n")
        print("-" * 70)

    await rag.finalize_storages()

asyncio.run(main())
```

---

## 🔍 生成的KG结构预览

构建的知识图谱包含以下节点和关系:

### 节点类型

1. **Job节点**: 作业元数据
   - 属性: job_id, start_time, end_time, runtime_sec, nprocs, exe等

2. **Module节点**: I/O模块（POSIX, STDIO, MPIIO等）
   - 属性: module_name, record_count等

3. **FileRecord节点**: 文件访问记录（**核心数据节点**）
   - 属性: file_path, rank, is_shared, file_role_hint
   - **counters_blob**: 包含所有原始counter数据（完整证据链）

4. **Phase节点**: 时间段（open/read/write/close/meta）
   - 属性: t_start, t_end, duration, bytes, iops_est, bw_est

5. **EventAnchor节点**: 时间点（first_open, last_read等）
   - 属性: kind, timestamp, confidence

6. **Counter节点**（可选）: 单个counter索引
   - 属性: counter_name, counter_type, value_json

### 关系类型

- `(Job)-[:HAS_MODULE]->(Module)`
- `(Module)-[:HAS_RECORD]->(FileRecord)`
- `(FileRecord)-[:HAS_PHASE]->(Phase)`
- `(Phase)-[:CONTAINS_ANCHOR]->(EventAnchor)`
- `(FileRecord)-[:HAS_COUNTER]->(Counter)`（可选）

### 示例查询用例

```python
# 1. 性能分析查询
"Which jobs have the lowest I/O bandwidth on shared files?"

# 2. 模式识别查询
"What are the common checkpoint file access patterns?"

# 3. 资源定位查询
"Which files are accessed by more than 10 jobs?"

# 4. 时间序列查询
"Show me the I/O timeline for job_12345"

# 5. 异常检测查询
"Find jobs with unusually long read phases"
```

---

## ⚠️ 常见问题

### Q1: 为什么插入KG很慢？

**A**: 这是正常现象。LightRAG需要为所有实体和关系生成embeddings（调用OpenAI API）。

**解决方案**:
- 使用更快的embedding模型：`text-embedding-3-small`
- 增加并发度（修改LightRAG配置）
- 考虑使用本地embedding模型

**时间估算**:
- 150个作业 → 约4500个实体 → 约10-20分钟（取决于API速度）

### Q2: 如何查看生成的KG内容？

```bash
# 查看KG JSON文件
jq . darshan_graph1_2025-1-1.json | less

# 查看统计信息
jq '{chunks: (.chunks | length), entities: (.entities | length), relationships: (.relationships | length)}' darshan_graph1_2025-1-1.json

# 查看实体类型分布
jq '[.entities[].entity_type] | group_by(.) | map({type: .[0], count: length})' darshan_graph1_2025-1-1.json
```

### Q3: 如何导出分析结果？

```python
import asyncio
from lightrag import LightRAG

async def export_data():
    rag = LightRAG(working_dir='./lightrag_storage_2025_1_1')
    await rag.initialize_storages()

    # 导出为Excel
    rag.export_data("darshan_analysis.xlsx", file_format="excel")

    # 导出为CSV
    rag.export_data("darshan_analysis.csv", file_format="csv")

    await rag.finalize_storages()

asyncio.run(export_data())
```

---

## 📊 性能优化建议

### 构建阶段优化

```bash
# 1. 并行处理多个文件（如果日志很多）
# 暂不支持，但可以分批处理后合并

# 2. 只处理最近的日志
find /path/to/logs -name "*.txt" -mtime -7 | \
    xargs python build_darshan_kg.py --input_path - --output_path recent_logs_kg.json
```

### 加载阶段优化

```python
from lightrag import LightRAG
from lightrag.llm.openai import openai_embed
from lightrag.utils import EmbeddingFunc

# 使用更小的embedding模型
async def faster_embed(texts):
    return await openai_embed(
        texts,
        model="text-embedding-3-small"  # 更快且更便宜
    )

rag = LightRAG(
    working_dir='./lightrag_storage',
    embedding_func=EmbeddingFunc(
        embedding_dim=1536,
        func=faster_embed
    ),
    embedding_func_max_async=32,  # 增加并发度
)
```

---

## 🎓 进阶用法

### 自定义Schema扩展

如果你需要添加自定义节点/属性，修改 [build_darshan_kg.py](build_darshan_kg.py) 中的相应方法。

### 批量查询脚本

```python
import asyncio
import json
from lightrag import LightRAG, QueryParam

async def batch_query():
    rag = LightRAG(working_dir='./lightrag_storage_2025_1_1')
    await rag.initialize_storages()

    # 从文件读取查询列表
    with open('queries.txt', 'r') as f:
        queries = [line.strip() for line in f if line.strip()]

    results = []
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query}")
        result = await rag.aquery(query, param=QueryParam(mode="hybrid"))
        results.append({'query': query, 'result': result})

    # 保存结果
    with open('query_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    await rag.finalize_storages()

asyncio.run(batch_query())
```

---

## 📞 获取帮助

如果遇到问题：

1. 查看详细文档: [README_KG_BUILDER.md](README_KG_BUILDER.md)
2. 运行测试验证环境: `python test_kg_builder.py`
3. 检查日志文件格式: `head -50 your_log.txt`

---

**Happy Querying! 🚀**
