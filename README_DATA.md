# 📊 DarshanRAG 数据管理指南

> **重要提示**: 本项目采用标准化的目录结构来管理实验数据。所有脚本和notebook应使用 `config_paths` 模块来访问路径，避免硬编码。

---

## 📁 目录结构说明

```
DarshanRAG/
├── data/                           # 所有数据文件（⚠️ 不提交到git）
│   ├── raw/                        # 原始 Darshan 日志文件
│   ├── parsed/                     # 解析后的日志（darshan-parser输出）
│   │   └── parsed-logs-YYYY-M-D/   # 按日期组织
│   ├── archives/                   # 源码包等归档文件
│   │   └── darshan-3.5.0.tar.gz
│   └── examples/                   # 示例日志文件
│       └── Darshan_log_example.txt
│
├── knowledge_graphs/               # 知识图谱文件（⚠️ 不提交）
│   ├── kg_2025-1-1.json           # 大型KG文件
│   ├── darshan_graph_nx.json      # NetworkX格式
│   └── test_kg_single.json        # 测试用小型KG
│
├── experiments/                    # 实验代码和结果
│   ├── notebooks/                  # Jupyter notebooks
│   │   ├── IORAG.ipynb
│   │   └── Ground_truth.ipynb
│   ├── scripts/                    # 实验脚本
│   │   ├── build_darshan_kg.py
│   │   ├── load_darshan_kg.py
│   │   ├── Q1-1.py, Q1-2.py, Q1-3.py
│   │   └── ...
│   ├── results/                    # 实验结果输出（⚠️ 不提交）
│   ├── storage/                    # RAG系统存储（⚠️ 不提交）
│   │   └── lightrag_storage_*/
│   ├── config_paths.py             # 路径配置模块
│   └── config.yaml                 # 实验配置
│
├── lightrag/                       # LightRAG核心代码
├── docs/                           # 文档
└── README.md                       # 项目主文档
```

---

## 🚀 快速开始

### 1. 设置环境

```bash
cd /users/Minqiu/DarshanRAG

# 可选：设置环境变量指定项目根目录
export DARSHAN_RAG_ROOT=$(pwd)

# 查看路径配置
python experiments/config_paths.py
```

### 2. 准备数据

```bash
# 将原始日志放到 data/raw/
cp /path/to/darshan/logs/*.darshan data/raw/

# 解析日志到 data/parsed/
./scripts/organize_data.sh parse 2025-1-1
```

### 3. 构建知识图谱

```python
# 方式1: 使用日期参数（推荐）
python experiments/scripts/build_darshan_kg.py --date 2025-1-1

# 方式2: 手动指定路径
python experiments/scripts/build_darshan_kg.py \
    --input_path data/parsed/parsed-logs-2025-1-1 \
    --output_path knowledge_graphs/kg_2025-1-1.json
```

---

## 💻 在代码中使用路径

### Python脚本

```python
import sys
from pathlib import Path

# 添加experiments目录到路径（如果脚本在scripts/子目录）
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_paths import PATHS, get_parsed_log_path, get_kg_path

# 使用预定义路径
parsed_logs = PATHS['parsed_logs']
kg_root = PATHS['kg_root']

# 使用辅助函数
input_path = get_parsed_log_path('2025-1-1')
output_path = get_kg_path('kg', '2025-1-1')

print(f"Input: {input_path}")
print(f"Output: {output_path}")
```

### Jupyter Notebook

在notebook的第一个代码单元格中：

```python
import sys
from pathlib import Path

# 添加experiments目录到路径
project_root = Path('/users/Minqiu/DarshanRAG')
sys.path.insert(0, str(project_root / 'experiments'))

from config_paths import PATHS, get_parsed_log_path, get_kg_path, get_storage_dir

# 配置路径
PARSED_LOGS = get_parsed_log_path('2025-1-1')
KG_FILE = get_kg_path('kg', '2025-1-1')
STORAGE_DIR = get_storage_dir('lightrag_2025_1_1')

# 确保输出目录存在
RESULTS_DIR = PATHS['results'] / 'experiment_2025_1_1'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

print(f"✅ Paths configured:")
print(f"  📂 Parsed logs: {PARSED_LOGS}")
print(f"  🕸️  KG file: {KG_FILE}")
print(f"  💾 Storage: {STORAGE_DIR}")
print(f"  📊 Results: {RESULTS_DIR}")
```

---

## 🔧 数据管理脚本

使用 `scripts/organize_data.sh` 脚本来管理数据：

```bash
# 查看帮助
./scripts/organize_data.sh help

# 解析日志
./scripts/organize_data.sh parse <date>

# 清理旧数据
./scripts/organize_data.sh clean

# 检查磁盘使用
./scripts/organize_data.sh check
```

---

## ⚠️ 重要提示

### 不要提交到Git的内容

以下目录和文件已在 `.gitignore` 中配置，**不会被提交**：

- ✅ `data/` - 所有原始和解析后的日志
- ✅ `knowledge_graphs/` - 所有知识图谱文件
- ✅ `experiments/results/` - 实验结果
- ✅ `experiments/storage/` - RAG系统存储
- ✅ `*.tar.gz` - 大型归档文件

### API Key安全

**绝对不要**将API Key硬编码在代码中或提交到git！

```python
# ❌ 错误做法
api_key = "sk-proj-xxxxx"

# ✅ 正确做法
import os
api_key = os.environ.get("OPENAI_API_KEY")

# 或使用 .env 文件（确保 .env 在 .gitignore 中）
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
```

### 大文件管理

- **KG文件**: 知识图谱JSON文件可能非常大（数百MB）。建议：
  - 使用gzip压缩存储：`gzip kg_2025-1-1.json`
  - 按需生成，不保留中间文件
  - 使用数据库（Neo4j/MongoDB）代替JSON文件

- **存储目录**: LightRAG的存储目录会随着数据增长而膨胀：
  - 定期清理不需要的存储
  - 为不同实验使用不同的存储目录
  - 使用 `get_storage_dir()` 函数创建命名规范的存储

---

## 📝 常见任务

### 任务1: 运行新实验

```bash
# 1. 准备数据
cp /new/logs/*.darshan data/raw/
./scripts/organize_data.sh parse 2025-1-15

# 2. 构建KG
python experiments/scripts/build_darshan_kg.py --date 2025-1-15

# 3. 运行实验
python experiments/scripts/load_darshan_kg.py \
    --kg_path $(python -c "from config_paths import get_kg_path; print(get_kg_path('kg', '2025-1-15'))")
```

### 任务2: 在notebook中运行查询

打开 `experiments/notebooks/IORAG.ipynb`，确保第一个单元格配置了路径：

```python
# Cell 1: 配置路径
import sys
sys.path.insert(0, '/users/Minqiu/DarshanRAG/experiments')
from config_paths import *

# Cell 2: 加载数据
kg_file = get_kg_path('kg', '2025-1-1')
# ... 继续你的分析
```

### 任务3: 清理磁盘空间

```bash
# 检查空间使用
./scripts/organize_data.sh check

# 清理旧的临时文件
./scripts/organize_data.sh clean

# 手动压缩大型KG文件
cd knowledge_graphs
gzip kg_2025-1-1.json  # 压缩后变成 kg_2025-1-1.json.gz
```

---

## 🆘 故障排除

### 问题1: 导入 config_paths 失败

```python
ModuleNotFoundError: No module named 'config_paths'
```

**解决方法**:
```python
import sys
from pathlib import Path
sys.path.insert(0, '/users/Minqiu/DarshanRAG/experiments')
from config_paths import PATHS
```

### 问题2: 路径不存在

```python
FileNotFoundError: [Errno 2] No such file or directory: '.../parsed-logs-2025-1-1'
```

**解决方法**:
```bash
# 确保目录已创建
python experiments/config_paths.py  # 会自动创建所有目录

# 检查文件是否在正确位置
ls -la data/parsed/
```

### 问题3: 磁盘空间不足

**解决方法**:
```bash
# 查看大文件
du -sh data/* knowledge_graphs/* experiments/storage/*

# 删除不需要的文件
rm -rf experiments/storage/old_storage/
gzip knowledge_graphs/*.json
```

---

## 📚 相关文档

- [experiments/README_KG_BUILDER.md](experiments/README_KG_BUILDER.md) - 知识图谱构建详细说明
- [experiments/README_experiment.md](experiments/README_experiment.md) - 实验框架使用指南
- [experiments/README_interactive.md](experiments/README_interactive.md) - 交互式查询使用说明

---

## 🤝 贡献指南

如果你修改了目录结构或路径配置：

1. 更新 `config_paths.py` 中的路径定义
2. 更新本文档
3. 更新 `.gitignore`（如果新增不应提交的目录）
4. 通知其他项目成员

---

**最后更新**: 2026-01-11
**维护者**: DarshanRAG Team
