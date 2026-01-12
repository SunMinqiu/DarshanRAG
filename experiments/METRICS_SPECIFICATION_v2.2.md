# Darshan信号提取工具 v2.2 - Metrics规格说明

## 更新说明（v2.2）

相对v2.1的改进：
1. ✅ 修复多rank记录覆盖bug：使用(module, rank, record_id)三元组作为唯一键
2. ✅ PEAK_ACTIVITY_BIN改为返回bin索引（0-N），新增PEAK_ACTIVITY_VALUE返回bin值
3. ✅ 移除HEATMAP模块的MODULE_AGG和MODULE_PERF（无意义）
4. ✅ 移除输出中的"### Original Metrics"部分

## 更新说明（v2.1）

相对v2.0的改进：
1. ✅ 移除输出中的"(Preserved)"文本
2. ✅ 修复parsing，确保所有metrics（包括HEATMAP）都正确提取
3. ✅ **NA值带原因标注**：`NA(reason)` 格式
4. ✅ **HEATMAP专用signals**：9个时间分布统计指标

---

## NA值原因标注 ⭐ NEW

所有NA值现在都附带原因说明，格式为 `NA(reason)`

### NA原因类型

| 原因代码 | 含义 | 示例场景 |
|---------|------|---------|
| `no_reads` | 读操作数为0 | `avg_read_size = NA(no_reads)` |
| `no_writes` | 写操作数为0 | `avg_write_size = NA(no_writes)` |
| `no_io` | 无I/O操作 | `seq_ratio = NA(no_io)` |
| `no_read_time` | 读时间为0 | `read_bw = NA(no_read_time)` |
| `no_write_time` | 写时间为0 | `write_bw = NA(no_write_time)` |
| `no_time` | 总时间为0 | `read_iops = NA(no_time)` |
| `no_bytes` | 字节数为0 | `rank_imbalance_ratio = NA(no_bytes)` |
| `no_file_size` | 文件大小估算失败 | `reuse_proxy = NA(no_file_size)` |
| `no_fastest_bytes` | 最快rank字节数为0 | `rank_imbalance_ratio = NA(no_fastest_bytes)` |
| `not_shared_file` | rank != -1，非共享文件 | `rank_imbalance_ratio = NA(not_shared_file)` |
| `not_monitored` | Darshan记录为-1 | metric = `NA(not_monitored)` |
| `not_available` | metric不存在 | metric = `NA(not_available)` |
| `no_bin_width` | HEATMAP缺少bin width | HEATMAP signal = `NA(no_bin_width)` |

---

## HEATMAP模块专用Signals ⭐ NEW

HEATMAP模块记录I/O活动的时间分布，使用bins来统计不同时间段的I/O事件。

### 输入数据

- `HEATMAP_F_BIN_WIDTH_SECONDS`: 每个bin的时间宽度（Δt）
- `HEATMAP_READ_BIN_k`: 第k个bin的读事件数（R[k]）
- `HEATMAP_WRITE_BIN_k`: 第k个bin的写事件数（W[k]）
- k = 0, 1, 2, ..., N-1（N为bin总数）

### 定义

设：
- Δt = `HEATMAP_F_BIN_WIDTH_SECONDS`
- R[k] = `HEATMAP_READ_BIN_k`
- W[k] = `HEATMAP_WRITE_BIN_k`
- A[k] = R[k] + W[k]（总活动）
- N = bin总数

### 计算的Signals

| Signal | 公式 | 说明 |
|--------|------|------|
| `total_read_events` | Σ R[k] | 所有bin的读事件总数 |
| `total_write_events` | Σ W[k] | 所有bin的写事件总数 |
| `active_bins` | \|{k \| A[k]>0}\| | 有活动的bin数量 |
| `active_time` | active_bins × Δt | 有I/O活动的总时间 |
| `activity_span` | (k_last - k_first + 1) × Δt | 从第一个到最后一个活动bin的时间跨度 |
| `peak_activity_bin` | argmax_k A[k] | 活动最密集的bin的**索引** (0-N) ⭐ v2.2更新 |
| `peak_activity_value` | max A[k] | 活动最密集的bin的**事件数** ⭐ v2.2新增 |
| `read_activity_entropy_norm` | H_r^{norm} | 读活动分布的归一化熵 [0,1] |
| `write_activity_entropy_norm` | H_w^{norm} | 写活动分布的归一化熵 [0,1] |
| `top1_share` | max A[k] / Σ A[k] | 最大bin占总活动的比例 |

### 详细公式

#### 1. total_read_events
```
TR = Σ_{k=0}^{N-1} R[k]
```

#### 2. total_write_events
```
TW = Σ_{k=0}^{N-1} W[k]
```

#### 3. active_bins
```
N_active = |{k | A[k] > 0}|
```

#### 4. active_time
```
T_active = N_active × Δt
```

#### 5. activity_span
```
k_first = min{k | A[k] > 0}
k_last = max{k | A[k] > 0}
T_span = (k_last - k_first + 1) × Δt
```

#### 6. peak_activity_bin ⭐ v2.2更新
返回活动最密集的bin的**索引**（不是值）：
```
peak_idx = argmax_{k} A[k]
```

#### 7. peak_activity_value ⭐ v2.2新增
返回活动最密集的bin的**事件数**：
```
A_peak = max_{k} A[k]
```

#### 8. read_activity_entropy_norm
读分布的归一化熵：
```
若 TR > 0:
  p_k = R[k] / TR  (对所有 k)
  H_r = -Σ_{k: p_k>0} p_k × log(p_k)
  H_r^{norm} = H_r / log(N)
否则:
  H_r^{norm} = 0
```

**解释**：
- 熵值越高，读活动在时间上分布越均匀
- 熵值越低，读活动越集中在少数时间段
- 归一化到[0,1]，便于比较

#### 9. write_activity_entropy_norm
写分布的归一化熵：
```
若 TW > 0:
  q_k = W[k] / TW  (对所有 k)
  H_w = -Σ_{k: q_k>0} q_k × log(q_k)
  H_w^{norm} = H_w / log(N)
否则:
  H_w^{norm} = 0
```

#### 10. top1_share
最大bin占比（反映I/O突发性）：
```
TA = Σ_{k} A[k]
若 TA > 0:
  S_1 = max_{k} A[k] / TA
否则:
  S_1 = 0
```

**解释**：
- 接近1：I/O高度集中在某个时间段（突发性强）
- 接近0：I/O均匀分布在多个时间段

### HEATMAP Signals的意义

| Signal | 用途 | 异常指示 |
|--------|------|----------|
| active_time | 实际I/O活跃时间 | 与runtime对比，识别I/O稀疏性 |
| activity_span | I/O时间跨度 | 识别I/O是否分散在整个作业周期 |
| entropy_norm | 时间分布均匀性 | 低熵 → I/O集中（可能是检查点） |
| top1_share | 突发性 | 高值 → 短时间大量I/O（突发） |
| peak_activity_bin | 峰值I/O强度 | 识别I/O瓶颈时刻 |

---

## 完整指标列表

### 第一层：Job Level

| 指标 | 说明 |
|------|------|
| total_bytes_read | 总读字节数 |
| total_bytes_written | 总写字节数 |
| total_reads | 总读操作数 |
| total_writes | 总写操作数 |

### 第二层：Module Level

每个模块（POSIX, STDIO, HEATMAP等）：

| 指标 | 公式 | NA原因 |
|------|------|--------|
| read_bw | bytes_read/1024²/time | `NA(no_time)` |
| write_bw | bytes_written/1024²/time | `NA(no_time)` |
| read_iops | reads/time | `NA(no_time)` |
| write_iops | writes/time | `NA(no_time)` |
| avg_read_size | bytes_read/reads | `NA(no_reads)` |
| avg_write_size | bytes_written/writes | `NA(no_writes)` |

### 第三层：Record Level

#### 所有模块通用

| Signal | 公式 | NA原因 |
|--------|------|--------|
| read_bw | bytes/1024²/time | `NA(no_read_time)` |
| write_bw | bytes/1024²/time | `NA(no_write_time)` |
| read_iops | reads/time | `NA(no_read_time)` |
| write_iops | writes/time | `NA(no_write_time)` |
| avg_read_size | bytes/reads | `NA(no_reads)` |
| avg_write_size | bytes/writes | `NA(no_writes)` |

#### POSIX模块特有

| Signal | 公式 | NA原因 |
|--------|------|--------|
| seq_read_ratio | seq_reads/reads | `NA(no_reads)` |
| seq_write_ratio | seq_writes/writes | `NA(no_writes)` |
| consec_read_ratio | consec_reads/reads | `NA(no_reads)` |
| consec_write_ratio | consec_writes/writes | `NA(no_writes)` |
| seq_ratio | (seq_r+seq_w)/(r+w) | `NA(no_io)` |
| consec_ratio | (consec_r+consec_w)/(r+w) | `NA(no_io)` |
| meta_ops | opens+stats+seeks+fsyncs+fdsyncs | - |
| meta_intensity | meta_ops/(reads+writes) | `NA(no_io)` |
| meta_fraction | meta_time/total_time | `NA(no_time)` |
| unaligned_read_ratio | not_aligned/reads | `NA(no_reads)` |
| unaligned_write_ratio | not_aligned/writes | `NA(no_writes)` |
| small_read_ratio | small_count/reads | `NA(no_reads)` |
| small_write_ratio | small_count/writes | `NA(no_writes)` |
| reuse_proxy | bytes_read/(max_byte+1) | `NA(no_file_size)` |
| rank_imbalance_ratio* | slowest/fastest | `NA(not_shared_file)` or `NA(no_bytes)` |
| bw_variance_proxy* | variance_rank_bytes | `NA(not_shared_file)` or `NA(no_bytes)` |
| is_shared | 1 if rank=-1 else 0 | - |

\* 仅当rank=-1且bytes>0时计算

#### HEATMAP模块特有

见上文HEATMAP专用Signals部分（9个指标）

---

## 输出格式示例

### Header（已移除"Preserved"）
```
# ============================================================
# ORIGINAL DARSHAN LOG HEADER
# ============================================================
```

### NA with Reason
```
POSIX	0	123...	SIGNAL_WRITE_BW	NA(no_write_time)
POSIX	0	123...	SIGNAL_AVG_WRITE_SIZE	NA(no_writes)
POSIX	0	456...	SIGNAL_RANK_IMBALANCE_RATIO	NA(not_shared_file)
```

### HEATMAP Signals (v2.2)
```
HEATMAP	0	789...	SIGNAL_TOTAL_READ_EVENTS	1049304.0
HEATMAP	0	789...	SIGNAL_ACTIVE_BINS	5
HEATMAP	0	789...	SIGNAL_ACTIVE_TIME	256.0
HEATMAP	0	789...	SIGNAL_PEAK_ACTIVITY_BIN	0
HEATMAP	0	789...	SIGNAL_PEAK_ACTIVITY_VALUE	1049304.0
HEATMAP	0	789...	SIGNAL_READ_ACTIVITY_ENTROPY_NORM	0.723
HEATMAP	0	789...	SIGNAL_TOP1_SHARE	0.45
```

---

## 变更历史

### v2.2 (2026-01-12)
- ✅ **修复关键bug**：使用(module, rank, record_id)三元组作为唯一键，防止多rank记录覆盖
- ✅ PEAK_ACTIVITY_BIN改为返回bin索引（0-N）
- ✅ 新增PEAK_ACTIVITY_VALUE返回bin事件数
- ✅ 移除HEATMAP模块的MODULE_AGG和MODULE_PERF（无意义）
- ✅ 移除输出中的"### Original Metrics"部分

### v2.1 (2026-01-11)
- ✅ 移除"(Preserved)"文本
- ✅ 修复parsing确保所有数据都提取
- ✅ NA值带原因标注：`NA(reason)`
- ✅ 新增HEATMAP专用signals（9个，v2.2更新为10个）

### v2.0 (2026-01-11)
- 三层层次化结构
- NA规则
- 模块独立性
- 性能指标三层必算

---

## 快速参考

### NA原因速查
- `no_reads/writes/io`: 操作数为0
- `no_read_time/write_time/time`: 时间为0
- `not_shared_file`: rank != -1
- `no_bytes`: 字节数为0
- `not_monitored`: Darshan值为-1

### HEATMAP公式速查
- `active_bins`: 有活动的bin数
- `peak_activity_bin`: 最大bin的索引（0-N）⭐ v2.2
- `peak_activity_value`: 最大bin的事件数 ⭐ v2.2
- `entropy_norm`: 分布均匀性 [0,1]
- `top1_share`: 最大bin占比（突发性）

---

**End of Specification v2.2**
