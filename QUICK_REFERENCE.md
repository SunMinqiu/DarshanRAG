# 🚀 DarshanRAG 快速参考

> **一页纸速查手册** - 最常用的命令和路径

---

## 📁 关键路径

```python
# 在Python代码中导入
from config_paths import PATHS, get_parsed_log_path, get_kg_path

# 常用路径
PATHS['parsed_logs']      # data/parsed/
PATHS['kg_root']          # knowledge_graphs/
PATHS['results']          # experiments/results/
PATHS['storage']          # experiments/storage/

# 辅助函数
get_parsed_log_path('2025-1-1')  # data/parsed/parsed-logs-2025-1-1/
get_kg_path('kg', '2025-1-1')    # knowledge_graphs/kg_2025-1-1.json
```

---

## ⚡ 常用命令

### 数据管理

```bash
# 检查磁盘使用
./scripts/organize_data.sh check

# 清理临时文件
./scripts/organize_data.sh clean

# 解析日志
./scripts/organize_data.sh parse 2025-1-1

# 压缩大文件
./scripts/organize_data.sh compress

# 列出所有实验
./scripts/organize_data.sh list
```

### 构建知识图谱

```bash
# 推荐方式 - 使用日期参数
python experiments/scripts/build_darshan_kg.py --date 2025-1-1

# 手动指定路径
python experiments/scripts/build_darshan_kg.py \
    --input_path data/parsed/parsed-logs-2025-1-1 \
    --output_path knowledge_graphs/kg_2025-1-1.json
```

### Git操作

```bash
# 查看状态（大文件会被自动忽略）
git status

# 添加代码更改（数据文件会被自动忽略）
git add .

# 检查.gitignore是否生效
git check-ignore -v knowledge_graphs/*.json
```

---

## 🔧 Notebook配置模板

```python
# Cell 1: 路径配置
import sys
from pathlib import Path

project_root = Path('/users/Minqiu/DarshanRAG')
sys.path.insert(0, str(project_root / 'experiments'))

from config_paths import PATHS, get_parsed_log_path, get_kg_path

# 配置实验
EXPERIMENT_DATE = '2025-1-1'
PARSED_LOGS = get_parsed_log_path(EXPERIMENT_DATE)
KG_FILE = get_kg_path('kg', EXPERIMENT_DATE)
RESULTS_DIR = PATHS['results'] / 'my_experiment'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

print(f"✅ 配置完成")
print(f"  📂 Parsed logs: {PARSED_LOGS}")
print(f"  🕸️  KG file: {KG_FILE}")
print(f"  📊 Results: {RESULTS_DIR}")

# Cell 2: API Key (使用环境变量)
import os
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  请设置 OPENAI_API_KEY 环境变量")
```

---

## 🗂️ 目录结构速览

```
DarshanRAG/
├── data/                    # 数据文件 (不提交git)
├── knowledge_graphs/        # KG文件 (不提交git)
├── experiments/
│   ├── notebooks/           # Jupyter notebooks
│   ├── scripts/             # 实验脚本
│   ├── results/             # 结果 (不提交git)
│   └── storage/             # 存储 (不提交git)
├── scripts/                 # 管理脚本
└── README_DATA.md           # 详细文档
```

---

## ⚠️ 重要提醒

### ✅ DO (推荐做的)

- ✅ 使用 `config_paths` 模块管理路径
- ✅ 使用环境变量存储API Key
- ✅ 定期运行 `./scripts/organize_data.sh check`
- ✅ 大文件压缩: `./scripts/organize_data.sh compress`

### ❌ DON'T (不要做的)

- ❌ 不要硬编码路径 (`/users/Minqiu/...`)
- ❌ 不要在代码中写API Key
- ❌ 不要手动提交 `data/` 或 `knowledge_graphs/`
- ❌ 不要删除 `.gitignore` 中的规则

---

## 🆘 快速故障排除

| 问题 | 解决方法 |
|------|----------|
| `ModuleNotFoundError: config_paths` | `sys.path.insert(0, '/users/Minqiu/DarshanRAG/experiments')` |
| 路径不存在 | `python experiments/config_paths.py` (自动创建) |
| 磁盘空间不足 | `./scripts/organize_data.sh clean` 和 `compress` |
| Git提示大文件 | 检查文件是否在 `data/` 或 `knowledge_graphs/` |
| API Key错误 | `export OPENAI_API_KEY='your-key'` |

---

## 📚 完整文档

- [README_DATA.md](README_DATA.md) - 数据管理完整指南
- [REORGANIZATION_SUMMARY.md](REORGANIZATION_SUMMARY.md) - 重组总结
- [experiments/config_paths.py](experiments/config_paths.py) - 路径配置源码

---

**提示**: 将此文件加入书签，随时查阅！ 📌
