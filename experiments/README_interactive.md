# LightRAG 交互式使用指南

简单的交互式使用方式，适合快速测试和查询知识图谱。

## 快速开始

### 1. 加载知识图谱

```bash
# 基本用法
python experiments/load_kg.py your_kg.json

# 自定义工作目录和模型
python experiments/load_kg.py your_kg.json \
  --working-dir ./my_rag_storage \
  --gen-model gpt-4o-mini \
  --embed-model text-embedding-3-large \
  --temperature 0.1
```

**参数说明：**
- `kg_path`: 知识图谱JSON文件路径（必需）
- `--working-dir`: LightRAG存储目录（默认: ./experiments/rag_storage）
- `--workspace`: 工作空间名称，用于数据隔离（默认: 空）
- `--gen-model`: 生成模型，如 gpt-4o, gpt-4o-mini（默认: gpt-4o）
- `--embed-model`: 嵌入模型，如 text-embedding-3-large（默认: text-embedding-3-large）
- `--temperature`: 生成温度（默认: 0.1）
- `--synthetic-chunks`: 如果没有chunks，创建合成chunks（通常不需要）

### 2. 查询方式

#### 方式1: 使用 Web UI（推荐）

加载KG后，启动LightRAG Server：

```bash
# 进入工作目录
cd experiments/rag_storage  # 或你指定的working-dir

# 启动服务器（如果使用了workspace，需要指定）
lightrag-server --working-dir . --workspace "" --port 9621

# 如果使用了自定义workspace
lightrag-server --working-dir . --workspace "your_workspace" --port 9621
```

然后在浏览器打开 `http://localhost:9621`，就可以：
- 在Web界面查询
- 可视化知识图谱
- 查看实体和关系

#### 方式2: 交互式命令行

```bash
# 基本用法（使用默认配置）
python experiments/interactive_query.py

# 指定工作目录和模型
python experiments/interactive_query.py \
  --working-dir ./experiments/rag_storage \
  --gen-model gpt-4o-mini \
  --mode hybrid

# 使用自定义workspace
python experiments/interactive_query.py \
  --working-dir ./experiments/rag_storage \
  --workspace "your_workspace"
```

**交互命令：**
- 直接输入问题查询
- `mode <模式名>` 切换查询模式（hybrid, mix, local, global, naive）
- `quit` 或 `exit` 退出

**查询模式说明：**
- `hybrid`: 混合模式（推荐）
- `mix`: 知识图谱+向量检索混合
- `local`: 基于实体的局部上下文
- `global`: 基于知识图谱的全局知识
- `naive`: 简单向量检索
- `bypass`: 直接使用LLM，不使用检索

### 3. 在代码中查询

```python
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_embed, openai_complete_if_cache
from lightrag.utils import EmbeddingFunc
import numpy as np
import os

async def query_example():
    # 配置
    working_dir = "./experiments/rag_storage"
    workspace = ""
    gen_model = "gpt-4o"
    embed_model = "text-embedding-3-large"
    api_key = os.environ.get("OPENAI_API_KEY")
    
    # 设置embedding函数
    async def embedding_func_impl(texts):
        return await openai_embed.func(texts, model=embed_model, api_key=api_key)
    
    embedding_func = EmbeddingFunc(
        embedding_dim=3072 if "3-large" in embed_model else 1536,
        max_token_size=8192,
        func=embedding_func_impl
    )
    
    # 设置LLM函数
    async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        return await openai_complete_if_cache(
            model=gen_model,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=api_key,
            temperature=0.1,
            **kwargs
        )
    
    # 初始化LightRAG
    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=embedding_func,
        llm_model_func=llm_model_func,
        workspace=workspace,
    )
    
    await rag.initialize_storages()
    
    # 查询
    query = "What I/O pattern does job 12345 use?"
    result = await rag.aquery(query, param=QueryParam(mode="hybrid"))
    
    print(result)
    
    await rag.finalize_storages()

# 运行
asyncio.run(query_example())
```

## 知识图谱格式

你的 `custom_kg.json` 文件应该遵循以下格式：

```json
{
  "entities": [
    {
      "entity_name": "Job_12345",
      "entity_type": "job",
      "description": "HPC job with ID 12345...",
      "source_id": "optional_source_id",
      "file_path": "optional_file_path"
    }
  ],
  "relationships": [
    {
      "src_id": "Job_12345",
      "tgt_id": "MPI-IO",
      "description": "Job 12345 uses MPI-IO pattern",
      "keywords": "uses, io_pattern",
      "weight": 1.0,
      "source_id": "optional_source_id"
    }
  ],
  "chunks": []  // 可选，可以为空
}
```

## 配置说明

所有参数都可以通过命令行设置，常用参数：

### 模型配置
- `--gen-model`: gpt-4o, gpt-4o-mini, gpt-4-turbo 等
- `--embed-model`: text-embedding-3-large, text-embedding-3-small 等
- `--temperature`: 0.0-2.0，越低越确定性（默认0.1）

### 存储配置
- `--working-dir`: LightRAG数据存储目录
- `--workspace`: 工作空间名称，用于隔离不同项目的数据

### 查询配置（interactive_query.py）
- `--mode`: 默认查询模式（hybrid, mix, local, global, naive）

## 环境变量

可以通过环境变量设置：

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_API_BASE="https://api.openai.com/v1"  # 可选，默认值
```

## 常见问题

### 1. API Key 错误

```bash
export OPENAI_API_KEY="sk-..."
```

### 2. 找不到已加载的KG

确保 `--working-dir` 和 `--workspace` 与加载时使用的一致。

### 3. 想重新加载KG

直接运行 `load_kg.py`，它会覆盖同一 working_dir/workspace 的数据。

### 4. 想查看知识图谱结构

使用Web UI的可视化功能，或者查看 `working_dir` 下的 `graph_chunk_entity_relation.graphml` 文件。

## 完整工作流程示例

```bash
# 1. 设置API key
export OPENAI_API_KEY="sk-..."

# 2. 加载知识图谱
python experiments/load_kg.py ./my_kg.json \
  --working-dir ./my_rag \
  --gen-model gpt-4o-mini

# 3a. 使用Web UI（推荐）
cd my_rag
lightrag-server --working-dir . --port 9621
# 然后浏览器打开 http://localhost:9621

# 3b. 或使用命令行交互
python experiments/interactive_query.py \
  --working-dir ./my_rag \
  --gen-model gpt-4o-mini \
  --mode hybrid
```

## 与完整实验框架的区别

- **交互式版本**（本指南）：简单快速，适合日常查询和测试
- **实验框架**（experiment_harness.py）：完整评估框架，适合系统化实验和参数扫描

根据需求选择合适的工具！
