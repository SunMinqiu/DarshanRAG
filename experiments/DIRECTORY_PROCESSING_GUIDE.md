# 目录处理指南 - v2.4

## 快速回答

**Q: 会保留原始的父子文件夹结构吗？**
**A: ✅ 是的，完全保留！**

**Q: 输出文件如何命名？**
**A: `原文件名_signals_v2.4.txt`**

---

## 工作原理

### 关键代码逻辑

```python
# 递归查找所有 .txt 文件
txt_files = list(input_path.rglob('*.txt'))

for txt_file in txt_files:
    # 计算相对路径
    rel_path = txt_file.relative_to(input_path)

    # 保持相对路径结构，只改文件名
    output_file = output_path / rel_path.parent / f"{rel_path.stem}_signals_v2.4.txt"

    # 自动创建必要的子目录
    output_file.parent.mkdir(parents=True, exist_ok=True)
```

### 路径映射示例

```
输入:  input_dir/exp1/subfolder/test.txt
       └────┬───┘ └──────┬──────┘ └──┬─┘
         根目录    相对路径      文件名

输出:  output_dir/exp1/subfolder/test_signals_v2.4.txt
       └────┬───┘ └──────┬──────┘ └────────┬───────────┘
      输出根目录   保留结构      新文件名 (原名_signals_v2.4.txt)
```

---

## 命令格式

### 格式1: 自动命名输出目录

```bash
python3 process_darshan_signals_v2.4.py <input_directory>
```

- 输出目录自动命名为: `<input_directory>_signals_v2.4/`
- 输出目录与输入目录位于同一父目录下

### 格式2: 指定输出目录

```bash
python3 process_darshan_signals_v2.4.py <input_directory> -o <output_directory>
```

- 输出目录使用你指定的路径
- 输出目录内部仍然保留相对路径结构

---

## 完整示例

### 示例 1: 简单的单层目录

**输入结构:**
```
/data/logs/
├── run1.txt
├── run2.txt
└── run3.txt
```

**命令:**
```bash
python3 scripts/process_darshan_signals_v2.4.py /data/logs/
```

**输出结构:**
```
/data/logs_signals_v2.4/
├── run1_signals_v2.4.txt
├── run2_signals_v2.4.txt
└── run3_signals_v2.4.txt
```

---

### 示例 2: 多层嵌套目录

**输入结构:**
```
/data/experiments/
├── exp1/
│   ├── config1.txt
│   └── results/
│       ├── run1.txt
│       └── run2.txt
├── exp2/
│   └── baseline.txt
└── raw_data/
    └── sample.txt
```

**命令 (自动命名):**
```bash
python3 scripts/process_darshan_signals_v2.4.py /data/experiments/
```

**输出结构:**
```
/data/experiments_signals_v2.4/    ← 自动创建，名字 = 输入目录名 + _signals_v2.4
├── exp1/                          ← 完全保留 exp1/ 子文件夹
│   ├── config1_signals_v2.4.txt
│   └── results/                   ← 保留 results/ 子文件夹
│       ├── run1_signals_v2.4.txt
│       └── run2_signals_v2.4.txt
├── exp2/                          ← 保留 exp2/ 子文件夹
│   └── baseline_signals_v2.4.txt
└── raw_data/                      ← 保留 raw_data/ 子文件夹
    └── sample_signals_v2.4.txt
```

**命令 (指定输出目录):**
```bash
python3 scripts/process_darshan_signals_v2.4.py /data/experiments/ -o /results/my_analysis/
```

**输出结构:**
```
/results/my_analysis/              ← 使用你指定的目录
├── exp1/
│   ├── config1_signals_v2.4.txt
│   └── results/
│       ├── run1_signals_v2.4.txt
│       └── run2_signals_v2.4.txt
├── exp2/
│   └── baseline_signals_v2.4.txt
└── raw_data/
    └── sample_signals_v2.4.txt
```

---

### 示例 3: 时间序列组织的目录

**输入结构:**
```
/data/project/
├── 2024/
│   ├── Q1/
│   │   ├── jan.txt
│   │   └── feb.txt
│   └── Q2/
│       ├── mar.txt
│       └── apr.txt
└── 2025/
    └── Q1/
        └── jan.txt
```

**命令:**
```bash
python3 scripts/process_darshan_signals_v2.4.py /data/project/ -o /results/
```

**输出结构:**
```
/results/
├── 2024/
│   ├── Q1/
│   │   ├── jan_signals_v2.4.txt
│   │   └── feb_signals_v2.4.txt
│   └── Q2/
│       ├── mar_signals_v2.4.txt
│       └── apr_signals_v2.4.txt
└── 2025/
    └── Q1/
        └── jan_signals_v2.4.txt    ← 虽然文件名和2024/Q1/jan.txt一样
                                     但在不同文件夹，所以不冲突
```

---

## 文件命名规则

### 命名公式

```
output_filename = original_stem + "_signals_v2.4.txt"
```

其中 `original_stem` = 原文件名去掉 `.txt` 扩展名

### 命名示例表

| 原文件名 | 输出文件名 |
|---------|-----------|
| `log.txt` | `log_signals_v2.4.txt` |
| `experiment_run1.txt` | `experiment_run1_signals_v2.4.txt` |
| `job_12345.txt` | `job_12345_signals_v2.4.txt` |
| `2024-01-15_data.txt` | `2024-01-15_data_signals_v2.4.txt` |
| `Darshan_log_example.txt` | `Darshan_log_example_signals_v2.4.txt` |

---

## 重要特性

### ✅ 完全保留目录结构
- 无论多少层嵌套都会保留
- 相对路径关系完全一致
- 子文件夹名称保持不变

### ✅ 递归处理所有 .txt 文件
- 使用 `rglob('*.txt')` 递归搜索
- 无论文件在多深的子目录都会被找到
- 自动跳过非 .txt 文件

### ✅ 自动创建必要的目录
- 使用 `mkdir(parents=True, exist_ok=True)`
- 会自动创建所有中间目录
- 如果目录已存在也不会报错

### ✅ 一致的命名规则
- 所有输出文件统一格式
- 容易识别哪个输出对应哪个输入
- 版本号 `v2.4` 包含在文件名中

### ✅ 错误处理
- 单个文件失败不影响其他文件
- 会打印错误信息但继续处理
- 最后显示处理完成的文件数

---

## 常见用例

### 用例 1: 批量处理实验数据

```bash
# 输入: 多个实验的darshan logs
/experiments/
├── baseline/
│   ├── run1.txt
│   ├── run2.txt
│   └── run3.txt
└── optimized/
    ├── run1.txt
    ├── run2.txt
    └── run3.txt

# 命令
python3 process_darshan_signals_v2.4.py /experiments/ -o /analysis/

# 结果: 保持实验分组结构
/analysis/
├── baseline/
│   ├── run1_signals_v2.4.txt
│   ├── run2_signals_v2.4.txt
│   └── run3_signals_v2.4.txt
└── optimized/
    ├── run1_signals_v2.4.txt
    ├── run2_signals_v2.4.txt
    └── run3_signals_v2.4.txt
```

### 用例 2: 处理时间序列数据

```bash
# 输入: 按日期组织的logs
/logs/
├── 2024-01/
│   ├── day01.txt
│   └── day02.txt
└── 2024-02/
    ├── day01.txt
    └── day02.txt

# 命令
python3 process_darshan_signals_v2.4.py /logs/

# 结果: 保持日期结构
/logs_signals_v2.4/
├── 2024-01/
│   ├── day01_signals_v2.4.txt
│   └── day02_signals_v2.4.txt
└── 2024-02/
    ├── day01_signals_v2.4.txt
    └── day02_signals_v2.4.txt
```

### 用例 3: 多用户/多系统数据

```bash
# 输入: 按用户和系统组织
/data/
├── user1/
│   ├── system_A/
│   │   └── job1.txt
│   └── system_B/
│       └── job1.txt
└── user2/
    └── system_A/
        └── job1.txt

# 命令
python3 process_darshan_signals_v2.4.py /data/ -o /processed/

# 结果: 完整保留层次结构
/processed/
├── user1/
│   ├── system_A/
│   │   └── job1_signals_v2.4.txt
│   └── system_B/
│       └── job1_signals_v2.4.txt
└── user2/
    └── system_A/
        └── job1_signals_v2.4.txt
```

---

## 注意事项

### ⚠️ 输出目录不能在输入目录内部

**错误示例:**
```bash
# 这会导致无限递归！
python3 process_darshan_signals_v2.4.py /data/ -o /data/output/
```

**原因:** 脚本会在 `/data/` 下递归查找 `.txt` 文件，包括 `/data/output/` 下的输出文件。

**正确做法:**
```bash
# 方法1: 输出到同级目录
python3 process_darshan_signals_v2.4.py /data/

# 方法2: 输出到完全独立的目录
python3 process_darshan_signals_v2.4.py /data/ -o /results/
```

### ⚠️ 重名文件处理

如果运行两次，第二次会**覆盖**第一次的输出文件（没有版本控制）。

**解决方案:** 使用不同的输出目录或手动备份
```bash
# 第一次运行
python3 process_darshan_signals_v2.4.py /data/ -o /results/run1/

# 第二次运行
python3 process_darshan_signals_v2.4.py /data/ -o /results/run2/
```

---

## 总结

| 特性 | 说明 |
|------|------|
| **目录结构** | ✅ 完全保留输入的父子文件夹结构 |
| **文件命名** | ✅ 统一格式: `原名_signals_v2.4.txt` |
| **递归处理** | ✅ 自动处理所有子文件夹中的 .txt 文件 |
| **自动创建目录** | ✅ 自动创建输出所需的所有子目录 |
| **错误处理** | ✅ 单个文件失败不影响其他文件 |
| **输出位置** | ✅ 可自动命名或手动指定 |

**结论:** 目录处理功能设计合理，完全保留原始组织结构，便于批量处理和结果对应！
