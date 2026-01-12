# Darshan Signal Extraction Tool v2.0

## 概述

v2.0版本采用**三层层次化结构**提取Darshan I/O日志的性能指标和异常信号。

## 主要特性

✅ **三层层次化输出**
- Job Level: 整个作业的汇总
- Module Level: 各I/O模块（POSIX/STDIO/MPI-IO）的汇总
- Record Level: 每个文件的详细指标

✅ **NA值规则**
- 分母为0 → `NA`
- 未提取到的数据 → `NA`
- 不满足条件的信号 → `NA`

✅ **完整保留原始Header**
- Darshan版本、jobid、runtime
- 所有28个mount points
- 模块信息

✅ **性能主指标（必算）**
- 在Record/Module/Job三层都计算
- `read_bw`, `write_bw`, `read_iops`, `write_iops`
- `avg_read_size`, `avg_write_size`
- `seq_ratio`, `consec_ratio`

✅ **模块独立性**
- POSIX和STDIO不在事实层混合
- 每个模块独立计算和输出

✅ **Record元数据**
- 每个record显示file_name, mount_pt, fs_type

## 使用方法

### 基本用法

```bash
# 处理单个文件
python3 scripts/process_darshan_signals_v2.py input.txt

# 自定义输出
python3 scripts/process_darshan_signals_v2.py input.txt -o output.txt

# 处理文件夹
python3 scripts/process_darshan_signals_v2.py /path/to/logs/

# 自定义输出文件夹
python3 scripts/process_darshan_signals_v2.py /path/to/logs/ -o /output/
```

### 示例

```bash
cd /users/Minqiu/DarshanRAG/experiments

# 处理示例文件
python3 scripts/process_darshan_signals_v2.py \
    ../data/examples/Darshan_log_example.txt

# 输出: Darshan_log_example_signals_v2.txt
```

## 输出文件结构

```
[Header]
  ↓
[Job Level]
  ├─ total_bytes_read
  ├─ total_bytes_written
  ├─ total_reads
  └─ total_writes
  ↓
[POSIX Module]
  ├─ Module Aggregates
  ├─ Module Performance
  └─ Records
      ├─ Record 1
      │   ├─ file_name, mount_pt, fs_type
      │   ├─ Original Metrics
      │   └─ Derived Signals
      │       ├─ Performance Metrics
      │       ├─ Access Patterns
      │       ├─ Metadata
      │       ├─ Alignment
      │       ├─ Small I/O
      │       ├─ Data Reuse
      │       └─ Rank Imbalance
      └─ Record 2...
  ↓
[STDIO Module]
  └─ ...
```

## 提取的指标

### 原始Metrics（55+个）

从Darshan日志直接提取：
- 基础I/O: bytes, reads, writes, time
- 访问模式: seq, consec, switches
- 请求大小: 10个区间的分布
- 对齐: alignment, not_aligned
- 元数据: opens, stats, seeks, fsyncs
- 并行: rank bytes, variance

### 派生Signals（~20个）

#### 1. 性能指标（所有层级必算）
- `read_bw` (MB/s)
- `write_bw` (MB/s)
- `read_iops` (ops/s)
- `write_iops` (ops/s)
- `avg_read_size` (bytes)
- `avg_write_size` (bytes)
- `seq_ratio`
- `consec_ratio`

#### 2. 访问模式（POSIX）
- `seq_read_ratio`
- `seq_write_ratio`
- `consec_read_ratio`
- `consec_write_ratio`

#### 3. 元数据（POSIX）
- `meta_ops`
- `meta_intensity` ⭐ NEW (meta_ops per I/O)
- `meta_fraction`

#### 4. 对齐（POSIX）
- `unaligned_read_ratio`
- `unaligned_write_ratio`

#### 5. 小I/O（POSIX）
- `small_read_ratio` (<10KB)
- `small_write_ratio` (<10KB)

#### 6. 数据重用（POSIX）
- `reuse_proxy` ⭐ NEW (proxy from MAX_BYTE_READ+1)

#### 7. Rank不均（POSIX, 仅rank=-1）
- `rank_imbalance_ratio`
- `bw_variance_proxy`

#### 8. 共享标识
- `is_shared` (0或1)

## 重要规则

### NA值规则

1. **分母为0** → `NA`
   ```
   reads = 0 → avg_read_size = NA
   time = 0 → read_bw = NA
   ```

2. **RLIM只在特定条件下计算**
   ```
   条件: rank == -1 AND (bytes_read + bytes_written) > 0
   否则: rank_imbalance_ratio = NA
   ```

3. **模块特定信号**
   ```
   STDIO模块没有seq_reads → seq_read_ratio = NA
   ```

### 模块独立性

- ❌ 不要在事实层混合POSIX和STDIO数据
- ✅ 每个模块独立计算和输出
- ✅ Job Level可以汇总（统计意义）

## 公式速查

| Signal | 公式 |
|--------|------|
| `read_bw` | `bytes_read / 1024² / read_time` |
| `read_iops` | `reads / read_time` |
| `avg_read_size` | `bytes_read / reads` |
| `seq_read_ratio` | `seq_reads / reads` |
| `consec_read_ratio` | `consec_reads / reads` |
| `meta_intensity` | `meta_ops / (reads + writes)` |
| `small_read_ratio` | `(0-100B + 100B-1K + 1K-10K) / reads` |
| `reuse_proxy` | `bytes_read / (MAX_BYTE_READ + 1)` |
| `rank_imbalance_ratio` | `slowest_rank_bytes / fastest_rank_bytes` |

## 完整文档

详细的指标规格说明请参考：
- **[METRICS_SPECIFICATION_v2.md](METRICS_SPECIFICATION_v2.md)** - 完整的metrics定义和公式

## 与v1.0的区别

| 特性 | v1.0 | v2.0 |
|------|------|------|
| 结构 | 扁平 | 三层层次化 |
| NA规则 | 输出0 | 输出NA |
| 访问模式 | random_ratio | seq_ratio + consec_ratio |
| RLIM | 总是计算 | rank=-1时才计算 |
| 元数据 | meta_ops, meta_fraction | +meta_intensity |
| 数据重用 | read_reuse_ratio | reuse_proxy (标注proxy) |
| Record信息 | 无 | file_name, mount_pt, fs_type |
| 性能指标 | Record层 | Record + Module + Job |
| 模块独立 | 未强调 | 明确分离 |

## 输出后缀

- v1.0: `*_signals_v1.txt`
- v2.0: `*_signals_v2.txt`

## 测试

```bash
# 查看输出前100行
head -100 output_signals_v2.txt

# 查看Job Level汇总
grep "^JOB" output_signals_v2.txt

# 查看Module Level性能指标
grep "MODULE_PERF" output_signals_v2.txt

# 查看某个signal
grep "SIGNAL_READ_BW" output_signals_v2.txt

# 查看NA值
grep "SIGNAL.*NA$" output_signals_v2.txt

# 查看文件元数据
grep "# file_name:" output_signals_v2.txt
```

## 依赖

- Python 3.6+
- 标准库（无需额外安装）

## 文件位置

```
experiments/
├── scripts/
│   ├── process_darshan_signals_v2.py    # v2.0主程序
│   └── process_darshan_signals.py       # v1.0主程序（保留）
├── METRICS_SPECIFICATION_v2.md          # 完整规格说明
├── README_v2.md                         # 本文件
└── README_signals.md                    # v1.0文档
```

## 版本历史

- **v2.0** (2026-01-11)
  - 三层层次化结构
  - NA值规则
  - 改进的访问模式信号
  - 新增meta_intensity
  - RLIM条件判断
  - Record元数据显示
  - 模块独立性

- **v1.0** (2025-01-11)
  - 初始版本
  - 基本信号提取

---

**准备就绪！开始使用v2.0处理你的Darshan日志！** 🚀
