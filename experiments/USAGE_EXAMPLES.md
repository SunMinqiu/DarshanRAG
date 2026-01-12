# Darshan Signal Extraction - 使用示例

## 快速开始

### 1. 处理单个文件

```bash
# 最简单的用法 - 自动生成输出文件名
cd /users/Minqiu/DarshanRAG/experiments
python3 process_darshan_signals.py ../data/examples/Darshan_log_example.txt

# 输出文件将自动命名为：
# ../data/examples/Darshan_log_example_signals_v1.txt
```

### 2. 自定义输出文件名

```bash
python3 process_darshan_signals.py input.txt -o custom_output.txt
```

### 3. 处理文件夹中的所有txt文件

```bash
# 假设你的日志文件在这个目录
python3 process_darshan_signals.py /path/to/darshan_logs/

# 输出文件夹自动命名为：
# /path/to/darshan_logs_signals_v1/
```

### 4. 处理文件夹并指定输出目录

```bash
python3 process_darshan_signals.py /path/to/darshan_logs/ -o /path/to/output/
```

## 完整命令示例

### 示例1：处理单个示例文件

```bash
cd /users/Minqiu/DarshanRAG/experiments

# 处理示例文件
python3 process_darshan_signals.py ../data/examples/Darshan_log_example.txt

# 查看输出
head -100 ../data/examples/Darshan_log_example_signals_v1.txt
```

### 示例2：处理整个examples目录

```bash
cd /users/Minqiu/DarshanRAG/experiments

# 处理整个目录
python3 process_darshan_signals.py ../data/examples/

# 输出将保存在: ../data/examples_signals_v1/
```

### 示例3：处理嵌套目录结构

假设你有这样的目录结构：
```
/data/
  ├── 2024/
  │   ├── january/
  │   │   ├── job1.txt
  │   │   └── job2.txt
  │   └── february/
  │       └── job3.txt
  └── 2025/
      └── january/
          └── job4.txt
```

执行命令：
```bash
python3 process_darshan_signals.py /data/
```

输出结构（保持原有目录结构）：
```
/data_signals_v1/
  ├── 2024/
  │   ├── january/
  │   │   ├── job1_signals_v1.txt
  │   │   └── job2_signals_v1.txt
  │   └── february/
  │       └── job3_signals_v1.txt
  └── 2025/
      └── january/
          └── job4_signals_v1.txt
```

### 示例4：批量处理多个不同路径的文件

创建一个shell脚本：
```bash
#!/bin/bash
# batch_process.sh

PROCESSOR="/users/Minqiu/DarshanRAG/experiments/process_darshan_signals.py"

# 处理多个不同位置的文件
python3 $PROCESSOR /path1/logs/
python3 $PROCESSOR /path2/logs/
python3 $PROCESSOR /path3/special_log.txt -o /output/special_log_signals_v1.txt

echo "All processing complete!"
```

## 测试工具

运行自动化测试：
```bash
cd /users/Minqiu/DarshanRAG/experiments
bash test_signal_extraction.sh
```

## 查看帮助信息

```bash
python3 process_darshan_signals.py --help
```

## 输出文件内容说明

生成的 `*_signals_v1.txt` 文件包含两部分：

### 第一部分：原始Metrics（最小充分集）
包含从Darshan日志中提取的所有必需原始指标，例如：
- POSIX_BYTES_READ
- POSIX_BYTES_WRITTEN
- POSIX_READS
- POSIX_WRITES
- 访问模式计数器
- 对齐信息
- 元数据操作计数
- 等等...

### 第二部分：派生异常信号
自动计算的12种I/O异常检测信号：

1. **HMD** - 高元数据负载
   - meta_ops（元数据操作总数）
   - meta_fraction（元数据时间占比）
   - meta_ops_rate（元数据操作速率）

2. **MSL** - 未对齐I/O
   - unaligned_read_ratio
   - unaligned_write_ratio

3. **RMA** - 随机访问
   - random_read_ratio
   - random_write_ratio
   - rw_switch_rate

4. **SHF** - 共享文件访问
   - is_shared

5. **SML** - 小I/O
   - small_read_ratio
   - small_write_ratio

6. **RDA** - 重复数据访问
   - read_reuse_ratio
   - low_unique_offset_signal

7. **RLIM** - Rank负载不均
   - rank_imbalance_ratio

8. **SLIM** - 服务器负载不均
   - bw_variance_proxy
   - burstiness

9. **MPNM** - 无MPI多进程
   - mpnm (0或1)

10. **NC** - 无集合I/O
    - collective_read_ratio
    - collective_write_ratio

11. **LLL** - 低级库使用
    - stdio_read_fraction
    - stdio_write_fraction

12. **NOL** - 无问题（通过其他信号判断）

## 常见问题

### Q1: 输出文件在哪里？
- 单个文件：在输入文件同目录，文件名加 `_signals_v1` 后缀
- 文件夹：在输入文件夹同级，文件夹名加 `_signals_v1` 后缀

### Q2: 可以覆盖原文件吗？
不会。输出文件总是使用不同的名称（添加 `_signals_v1` 后缀）。

### Q3: 支持哪些文件格式？
只支持 `.txt` 格式的Darshan日志（通过 darshan-parser 生成的文本格式）。

### Q4: 如何只处理特定rank的数据？
当前版本处理所有rank的数据。如需过滤，可以在后处理中使用grep：
```bash
grep "^0\t" output_signals_v1.txt  # 只查看rank 0的数据
```

### Q5: 性能如何？
- 单个文件：通常几秒钟
- 大量文件：取决于文件数量和大小
- 工具会显示处理进度

## 故障排查

### 错误：找不到输入文件
确保路径正确，支持绝对路径和相对路径。

### 错误：权限拒绝
确保有读取输入文件和写入输出目录的权限。

### 输出文件为空或数据不完整
检查输入文件是否是有效的Darshan日志文本格式。

## 进阶用法

### 与其他工具结合

```bash
# 处理后立即分析
python3 process_darshan_signals.py input.txt && \
  grep "SIGNAL_HMD" input_signals_v1.txt

# 处理多个文件并统计
python3 process_darshan_signals.py logs/ && \
  find logs_signals_v1/ -name "*_signals_v1.txt" -exec wc -l {} \;

# 提取特定信号
python3 process_darshan_signals.py input.txt && \
  grep "SIGNAL_SML_small_read_ratio" input_signals_v1.txt
```

## 联系与反馈

如有问题或建议，请查看项目文档或联系维护者。
