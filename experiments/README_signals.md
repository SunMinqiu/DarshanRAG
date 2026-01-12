# Darshan Signal Extraction Tool

这个工具用于从Darshan日志文件中提取I/O性能异常检测所需的信号指标。

## 功能特性

1. **完整保留原始Header**：保留Darshan日志的所有header信息（版本、jobid、mount points等）⭐ NEW!
2. **提取原始Metrics**：从Darshan日志中提取最小充分集的原始指标
3. **计算派生信号**：自动计算12种I/O异常信号
4. **批量处理**：支持单文件或文件夹批量处理
5. **保持目录结构**：处理文件夹时保持原有的目录结构
6. **自定义输出路径**：支持自定义输出文件或文件夹路径

## 提取的异常信号

工具会计算以下派生信号：

1. **HMD** - High Metadata Load (高元数据负载)
2. **MSL** - Misaligned I/O (未对齐I/O)
3. **RMA** - Random Access (随机访问)
4. **SHF** - Shared File Access (共享文件访问)
5. **SML** - Small I/O (小I/O)
6. **RDA** - Repetitive Data Access (重复数据访问)
7. **RLIM** - Rank Load Imbalance (Rank负载不均)
8. **SLIM** - Server Load Imbalance (服务器负载不均)
9. **MPNM** - Multi-Process without MPI (无MPI多进程)
10. **NC** - No Collective I/O (无集合I/O)
11. **LLL** - Low-Level Library (低级库使用)
12. **NOL** - No Issue (无问题)

## 使用方法

### 1. 处理单个文件

```bash
# 自动生成输出文件名 (input_signals_v1.txt)
python process_darshan_signals.py input.txt

# 指定输出文件名
python process_darshan_signals.py input.txt -o output_signals_v1.txt
```

### 2. 处理文件夹

```bash
# 处理文件夹中所有.txt文件，自动创建输出文件夹
python process_darshan_signals.py /path/to/logs/

# 指定输出文件夹
python process_darshan_signals.py /path/to/logs/ -o /path/to/output/
```

### 3. 处理示例文件

```bash
# 处理示例Darshan日志
python process_darshan_signals.py ../data/examples/Darshan_log_example.txt

# 处理整个examples目录
python process_darshan_signals.py ../data/examples/
```

## 输出格式

输出文件分为三个部分：

### 第0部分：原始Darshan日志Header（完整保留）⭐ NEW!
```
# ============================================================
# ORIGINAL DARSHAN LOG HEADER (Preserved)
# ============================================================
# darshan log version: 3.41
# compression method: BZIP2
# exe: 4068766220
# uid: 1449515727
# jobid: 3122490
# start_time: 1735781151
# nprocs: 4
# run time: 7451.1501
# metadata: lib_ver = 3.4.4
# log file regions...
# mounted file systems...
# mount entry: /lus/grand lustre
# mount entry: /home lustre
...
```

保留内容包括：
- Darshan版本、压缩方法
- 作业信息（jobid, uid, exe）
- 时间信息（start_time, end_time）
- 进程数和运行时间
- 模块信息（POSIX, STDIO, APMPI, HEATMAP）
- **所有mount points（文件系统挂载信息）**

### 第一部分：原始Metrics（最小充分集）
保留从Darshan日志中提取的所有必需原始指标：
- POSIX I/O操作计数和字节数
- 访问模式指标
- 请求大小分布
- 对齐信息
- 元数据操作
- 并行访问指标
- STDIO指标

### 第二部分：派生信号
计算得到的异常检测信号，每个信号包含一个或多个数值指标。

格式：
```
<rank> <record_id> <signal_name> <value>
```

## 命令示例

```bash
# 给脚本添加执行权限
chmod +x process_darshan_signals.py

# 示例1：处理单个文件
./process_darshan_signals.py Darshan_log_example.txt

# 示例2：处理文件夹
./process_darshan_signals.py /users/Minqiu/DarshanRAG/data/logs/

# 示例3：处理父文件夹（包含多个子文件夹）
./process_darshan_signals.py /users/Minqiu/DarshanRAG/data/

# 示例4：使用Python直接运行
python3 process_darshan_signals.py input.txt -o custom_output.txt
```

## 目录结构示例

处理前：
```
logs/
  ├── 2024/
  │   ├── job1.txt
  │   └── job2.txt
  └── 2025/
      └── job3.txt
```

处理后：
```
logs_signals_v1/
  ├── 2024/
  │   ├── job1_signals_v1.txt
  │   └── job2_signals_v1.txt
  └── 2025/
      └── job3_signals_v1.txt
```

## 依赖要求

- Python 3.6+
- 标准库（无需额外安装依赖）

## 注意事项

1. 输入文件必须是Darshan日志的文本格式（通过darshan-parser生成）
2. 文件编码使用UTF-8，对无法解码的字符会自动忽略
3. 如果APMPI或HEATMAP模块不存在，相关信号会使用默认值
4. 处理大量文件时会在控制台显示进度
