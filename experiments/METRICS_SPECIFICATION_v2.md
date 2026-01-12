# Darshan信号提取工具 v2.0 - Metrics规格说明

## 概述

本工具从Darshan I/O日志中提取性能指标和异常信号，采用**三层层次化结构**：
- **Job Level**: 整个作业的汇总指标
- **Module Level**: 各I/O模块（POSIX, STDIO, MPI-IO等）的汇总指标
- **Record Level**: 每个文件（record_id）的详细指标

## 输出结构

```
[Header: 原始Darshan日志头部信息]
  ↓
[Job Level: 作业级汇总]
  ↓
[Module Level: 模块级汇总]
  ├─ POSIX模块
  │   ├─ Module aggregates
  │   └─ Records (各文件)
  │       ├─ Original metrics
  │       └─ Derived signals
  ├─ STDIO模块
  └─ MPI-IO模块
```

---

## 第一层：Job Level（作业级）

### 汇总指标

| 指标名 | 说明 | 来源 |
|-------|------|-----|
| `total_bytes_read` | 总读取字节数 | 所有模块所有record汇总 |
| `total_bytes_written` | 总写入字节数 | 所有模块所有record汇总 |
| `total_reads` | 总读操作数 | 所有模块所有record汇总 |
| `total_writes` | 总写操作数 | 所有模块所有record汇总 |

**注意**：Job级别的汇总**不混合**不同模块的事实层数据，但会累加所有record的I/O量。

---

## 第二层：Module Level（模块级）

每个模块（POSIX, STDIO, MPI-IO等）独立计算。

### Module Aggregates（模块汇总）

| 指标名 | 说明 |
|-------|------|
| `total_bytes_read` | 该模块所有record的总读取字节数 |
| `total_bytes_written` | 该模块所有record的总写入字节数 |
| `total_reads` | 该模块所有record的总读操作数 |
| `total_writes` | 该模块所有record的总写操作数 |
| `total_read_time` | 该模块总读时间 |
| `total_write_time` | 该模块总写时间 |

### Module Performance Metrics（模块性能指标）

| 指标名 | 计算公式 | 说明 |
|-------|---------|------|
| `read_bw` | `total_bytes_read / (1024²) / total_read_time` | 读带宽 (MB/s) |
| `write_bw` | `total_bytes_written / (1024²) / total_write_time` | 写带宽 (MB/s) |
| `read_iops` | `total_reads / total_read_time` | 读IOPS |
| `write_iops` | `total_writes / total_write_time` | 写IOPS |
| `avg_read_size` | `total_bytes_read / total_reads` | 平均读请求大小 (bytes) |
| `avg_write_size` | `total_bytes_written / total_writes` | 平均写请求大小 (bytes) |

**分母为0时**：输出 `NA`

---

## 第三层：Record Level（记录级 / 文件级）

每个record代表一个文件的I/O行为。

### Record Header信息

每个record包含文件元数据（从原始日志提取）：
- `file_name`: 文件路径
- `mount_pt`: 挂载点
- `fs_type`: 文件系统类型（如lustre, nfs等）
- `rank`: MPI rank编号（-1表示共享文件）

---

## 提取的原始Metrics

以下metrics从Darshan日志中直接提取（按模块分类）：

### POSIX模块

#### 基础I/O量与次数
- `POSIX_BYTES_READ`: 读取总字节数
- `POSIX_BYTES_WRITTEN`: 写入总字节数
- `POSIX_READS`: 读操作次数
- `POSIX_WRITES`: 写操作次数
- `POSIX_F_READ_TIME`: 读操作总时间
- `POSIX_F_WRITE_TIME`: 写操作总时间

#### 访问模式
- `POSIX_SEQ_READS`: 顺序读次数
- `POSIX_SEQ_WRITES`: 顺序写次数
- `POSIX_CONSEC_READS`: 连续读次数
- `POSIX_CONSEC_WRITES`: 连续写次数
- `POSIX_RW_SWITCHES`: 读写切换次数

#### 请求大小分布（10个区间）
- `POSIX_SIZE_READ_0_100`: 0-100字节的读次数
- `POSIX_SIZE_READ_100_1K`: 100B-1KB的读次数
- `POSIX_SIZE_READ_1K_10K`: 1KB-10KB的读次数
- `POSIX_SIZE_READ_10K_100K`: 10KB-100KB的读次数
- `POSIX_SIZE_READ_100K_1M`: 100KB-1MB的读次数
- `POSIX_SIZE_READ_1M_4M`: 1MB-4MB的读次数
- `POSIX_SIZE_READ_4M_10M`: 4MB-10MB的读次数
- `POSIX_SIZE_READ_10M_100M`: 10MB-100MB的读次数
- `POSIX_SIZE_READ_100M_1G`: 100MB-1GB的读次数
- `POSIX_SIZE_READ_1G_PLUS`: >1GB的读次数
- （对应的WRITE版本）

#### 对齐信息
- `POSIX_FILE_NOT_ALIGNED`: 文件未对齐次数
- `POSIX_MEM_NOT_ALIGNED`: 内存未对齐次数
- `POSIX_FILE_ALIGNMENT`: 文件对齐大小
- `POSIX_MEM_ALIGNMENT`: 内存对齐大小

#### 元数据操作
- `POSIX_OPENS`: open调用次数
- `POSIX_STATS`: stat调用次数
- `POSIX_SEEKS`: seek调用次数
- `POSIX_FSYNCS`: fsync调用次数
- `POSIX_FDSYNCS`: fdatasync调用次数
- `POSIX_F_META_TIME`: 元数据操作总时间

#### 并行与共享（仅当rank=-1时有意义）
- `POSIX_FASTEST_RANK`: 最快rank编号
- `POSIX_FASTEST_RANK_BYTES`: 最快rank传输字节数
- `POSIX_SLOWEST_RANK`: 最慢rank编号
- `POSIX_SLOWEST_RANK_BYTES`: 最慢rank传输字节数
- `POSIX_F_VARIANCE_RANK_BYTES`: rank间字节数方差
- `POSIX_F_VARIANCE_RANK_TIME`: rank间时间方差

#### 其他
- `POSIX_MAX_BYTE_READ`: 读取的最大偏移量
- `POSIX_MAX_BYTE_WRITTEN`: 写入的最大偏移量

### STDIO模块

- `STDIO_BYTES_READ`
- `STDIO_BYTES_WRITTEN`
- `STDIO_READS`
- `STDIO_WRITES`
- `STDIO_F_READ_TIME`
- `STDIO_F_WRITE_TIME`

---

## 计算的派生Signals

### 1. 性能主指标（Performance Metrics）✨ 必算

**适用层级**：Record, Module, Job
**适用模块**：所有（POSIX, STDIO, MPI-IO等）

| Signal | 公式 | 单位 | 说明 |
|--------|------|------|------|
| `read_bw` | `bytes_read / (1024²) / read_time` | MB/s | 读带宽 |
| `write_bw` | `bytes_written / (1024²) / write_time` | MB/s | 写带宽 |
| `read_iops` | `reads / read_time` | ops/s | 读IOPS |
| `write_iops` | `writes / write_time` | ops/s | 写IOPS |
| `avg_read_size` | `bytes_read / reads` | bytes | 平均读请求大小 |
| `avg_write_size` | `bytes_written / writes` | bytes | 平均写请求大小 |
| `seq_ratio` | `(seq_reads + seq_writes) / (reads + writes)` | 比例 | 整体顺序访问比例 |
| `consec_ratio` | `(consec_reads + consec_writes) / (reads + writes)` | 比例 | 整体连续访问比例 |

**分母为0规则**：输出 `NA`

---

### 2. 访问模式信号（Access Patterns）

**仅POSIX模块**

| Signal | 公式 | 说明 |
|--------|------|------|
| `seq_read_ratio` | `seq_reads / reads` | 顺序读比例 |
| `seq_write_ratio` | `seq_writes / writes` | 顺序写比例 |
| `consec_read_ratio` | `consec_reads / reads` | 连续读比例 |
| `consec_write_ratio` | `consec_writes / writes` | 连续写比例 |

**注意**：不再使用 `random_ratio`（已移除）

---

### 3. 元数据信号（Metadata）

**仅POSIX模块**

| Signal | 公式 | 说明 |
|--------|------|------|
| `meta_ops` | `opens + stats + seeks + fsyncs + fdsyncs` | 元数据操作总数 |
| `meta_intensity` ⭐ NEW | `meta_ops / (reads + writes)` | 每次I/O操作的元数据操作数 |
| `meta_fraction` | `meta_time / (meta_time + read_time + write_time)` | 元数据时间占比 |

---

### 4. 对齐信号（Alignment）- MSL

**仅POSIX模块**

| Signal | 公式 | 说明 |
|--------|------|------|
| `unaligned_read_ratio` | `file_not_aligned / reads` | 未对齐读比例 |
| `unaligned_write_ratio` | `file_not_aligned / writes` | 未对齐写比例 |

---

### 5. 小I/O信号（Small I/O）- SML

**仅POSIX模块**

| Signal | 公式 | 说明 |
|--------|------|------|
| `small_read_ratio` | `(size_0_100 + size_100_1K + size_1K_10K) / reads` | <10KB读操作比例 |
| `small_write_ratio` | `(size_0_100 + size_100_1K + size_1K_10K) / writes` | <10KB写操作比例 |

---

### 6. 数据重用信号（Data Reuse）- RDA ⭐ 更新

**仅POSIX模块**

| Signal | 公式 | 说明 |
|--------|------|------|
| `reuse_proxy` | `bytes_read / (MAX_BYTE_READ + 1)` | 数据重用代理指标（proxy） |

**注意**：
- 改名：`read_reuse_ratio` → `reuse_proxy`
- 文件大小估算来自 `MAX_BYTE_READ + 1`（proxy估算）
- 输出时标注为 "proxy from MAX_BYTE_READ+1"

---

### 7. Rank负载不均信号（Rank Imbalance）- RLIM ⭐ 重要规则

**仅POSIX模块，且仅当满足以下条件时计算**：
1. `rank == -1`（共享文件）
2. `bytes_read + bytes_written > 0`（有实际I/O）

**否则输出 `NA`**

| Signal | 公式 | 说明 |
|--------|------|------|
| `rank_imbalance_ratio` | `slowest_rank_bytes / fastest_rank_bytes` | Rank间字节数不均比 |
| `bw_variance_proxy` | `POSIX_F_VARIANCE_RANK_BYTES` | Rank间字节方差 |

---

### 8. 共享文件标识

| Signal | 值 | 说明 |
|--------|---|------|
| `is_shared` | `1` if `rank == -1` else `0` | 是否共享文件 |

---

## NA值规则 ⭐ 重要

### 什么时候输出NA？

1. **分母为0**：所有除法运算，分母为0时输出 `NA`
   - 例如：`reads = 0` 时，`avg_read_size = NA`

2. **没有提取到的数据**：使用 `NA` 而不是 `0`
   - 例如：STDIO模块没有 `seq_reads`，则相关ratio为 `NA`

3. **条件不满足的信号**：
   - RLIM相关信号：当 `rank != -1` 或无I/O时，输出 `NA`

4. **值为-1的metric**：Darshan中 `-1` 表示未监控，应视为 `NA`

### 不输出NA的情况

- 确实为0的计数值（如 `reads = 0`）
- 确实为0的字节数（如 `bytes_written = 0`）

---

## 模块独立性原则 ⭐ 重要

**POSIX和STDIO模块的数据不在事实层相加**

- ❌ 错误：`total_bytes = POSIX_BYTES_READ + STDIO_BYTES_READ`
- ✅ 正确：POSIX模块和STDIO模块分别独立计算和输出

**但在Job Level可以汇总**（因为是统计意义上的总I/O量）

---

## 层次化输出格式

### 示例输出结构

```
# ============================================================
# JOB LEVEL METRICS
# ============================================================
JOB	total_bytes_read	7489771.0
JOB	total_bytes_written	11201335.0
...

# ============================================================
# MODULE: POSIX
# ============================================================
#
## Module-Level Aggregates:
POSIX	MODULE_AGG	total_bytes_read	4204115.0
...

## Module-Level Performance Metrics:
POSIX	MODULE_PERF	read_bw	1523.45
POSIX	MODULE_PERF	avg_read_size	7932.29
...

# ------------------------------------------------------------
# RECORD: 10166465462036786034 (rank=0)
# file_name: /home/user/data.dat
# mount_pt: /home
# fs_type: lustre
# ------------------------------------------------------------
#
### Original Metrics:
POSIX	0	10166465462036786034	POSIX_BYTES_READ	1198.0
POSIX	0	10166465462036786034	POSIX_READS	2.0
...

### Derived Signals:
# Performance Metrics
POSIX	0	10166465462036786034	SIGNAL_READ_BW	1.898
POSIX	0	10166465462036786034	SIGNAL_AVG_READ_SIZE	599.0
...

# Access Patterns
POSIX	0	10166465462036786034	SIGNAL_SEQ_READ_RATIO	0.5
POSIX	0	10166465462036786034	SIGNAL_CONSEC_READ_RATIO	0.5
...

# Metadata
POSIX	0	10166465462036786034	SIGNAL_META_OPS	2.0
POSIX	0	10166465462036786034	SIGNAL_META_INTENSITY	1.0
...

# Data Reuse (proxy from MAX_BYTE_READ+1)
POSIX	0	10166465462036786034	SIGNAL_REUSE_PROXY	1.0
...

```

---

## 公式速查表

| 类别 | Signal | 公式 | NA条件 |
|------|--------|------|--------|
| 性能 | read_bw | bytes_read / 1024² / time | time = 0 |
| 性能 | write_bw | bytes_written / 1024² / time | time = 0 |
| 性能 | read_iops | reads / time | time = 0 |
| 性能 | write_iops | writes / time | time = 0 |
| 性能 | avg_read_size | bytes_read / reads | reads = 0 |
| 性能 | avg_write_size | bytes_written / writes | writes = 0 |
| 访问 | seq_read_ratio | seq_reads / reads | reads = 0 |
| 访问 | consec_read_ratio | consec_reads / reads | reads = 0 |
| 访问 | seq_ratio | (seq_reads+seq_writes) / (reads+writes) | total = 0 |
| 访问 | consec_ratio | (consec_reads+consec_writes) / (reads+writes) | total = 0 |
| 元数据 | meta_intensity | meta_ops / (reads+writes) | total = 0 |
| 元数据 | meta_fraction | meta_time / total_time | total_time = 0 |
| 对齐 | unaligned_read_ratio | not_aligned / reads | reads = 0 |
| 小I/O | small_read_ratio | small_count / reads | reads = 0 |
| 重用 | reuse_proxy | bytes_read / (max_byte+1) | max_byte+1 ≤ 1 |
| 不均 | rank_imbalance_ratio | slowest / fastest | rank≠-1 or bytes=0 or fastest=0 |

---

## 版本信息

- **工具版本**: v2.0
- **输出后缀**: `_signals_v2.txt`
- **日期**: 2026-01-11

---

## 变更记录（相对v1.0）

1. ✅ 采用三层层次化结构（Job → Module → Record）
2. ✅ NA规则：分母为0输出NA，不是0
3. ✅ 访问模式改用 `seq_ratio` 和 `consec_ratio`，移除 `random_ratio`
4. ✅ RLIM只在 `rank == -1` 且有I/O时计算
5. ✅ 新增 `meta_intensity` 指标
6. ✅ RDA改名为 `reuse_proxy` 并标注proxy
7. ✅ Record header包含file_name, mount_pt, fs_type
8. ✅ 性能主指标在所有层级必算
9. ✅ POSIX/STDIO模块独立，不在事实层混合
10. ✅ 完整保留原始Darshan header

---

**End of Specification**
