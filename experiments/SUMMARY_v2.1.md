# Darshan Signal Extraction Tool v2.1 - 更新总结

## ✅ v2.1完成的改进

### 1. 移除"(Preserved)"文本 ✅
- 输出Header改为：`# ORIGINAL DARSHAN LOG HEADER`
- 更简洁清晰

### 2. 修复Parsing ✅
- 确保所有模块的metrics都正确提取
- 包括HEATMAP的所有bins
- 文件元数据正确关联

### 3. NA值原因标注 ✅⭐
**格式**：`NA(reason)`

**原因类型**：
- `no_reads`, `no_writes`, `no_io` - 操作数为0
- `no_read_time`, `no_write_time`, `no_time` - 时间为0
- `no_bytes` - 字节数为0
- `not_shared_file` - rank != -1（非共享文件）
- `no_file_size` - 文件大小估算失败
- `not_monitored` - Darshan记录值为-1
- `not_available` - metric不存在

**示例**：
```
POSIX	0	123...	SIGNAL_WRITE_BW	NA(no_write_time)
POSIX	0	123...	SIGNAL_RANK_IMBALANCE_RATIO	NA(not_shared_file)
```

### 4. HEATMAP专用Signals ✅⭐

新增**9个HEATMAP时间分布统计指标**：

| # | Signal | 说明 | 公式 |
|---|--------|------|------|
| 1 | `total_read_events` | 读事件总数 | Σ R[k] |
| 2 | `total_write_events` | 写事件总数 | Σ W[k] |
| 3 | `active_bins` | 有活动的bin数 | \|{k\|A[k]>0}\| |
| 4 | `active_time` | 活跃时间 | active_bins × Δt |
| 5 | `activity_span` | 时间跨度 | (k_last-k_first+1)×Δt |
| 6 | `peak_activity_bin` | 峰值活动 | max A[k] |
| 7 | `read_activity_entropy_norm` | 读分布熵 | H_r / log(N) |
| 8 | `write_activity_entropy_norm` | 写分布熵 | H_w / log(N) |
| 9 | `top1_share` | 最大bin占比 | max A[k] / Σ A[k] |

**其中**：
- Δt = `HEATMAP_F_BIN_WIDTH_SECONDS`
- R[k] = `HEATMAP_READ_BIN_k`
- W[k] = `HEATMAP_WRITE_BIN_k`
- A[k] = R[k] + W[k]

**熵计算**（归一化到[0,1]）：
```
若 TR > 0:
  p_k = R[k] / TR
  H_r = -Σ p_k log(p_k)  (仅 p_k > 0)
  H_r^{norm} = H_r / log(N)
否则:
  H_r^{norm} = 0
```

---

## 测试验证

### 测试文件
- 输入：Darshan_log_example.txt
- 输出：test_v2.1.txt

### 验证项
✅ Header无"(Preserved)"  
✅ NA值带原因标注  
✅ HEATMAP signals正确计算  
✅ 所有modules正确解析  

### 示例输出

**NA with Reason**：
```bash
$ grep "NA(" test_v2.1.txt | head -5
HEATMAP	MODULE_PERF	read_bw	NA(no_time)
POSIX	0	10166...	SIGNAL_WRITE_BW	NA(no_write_time)
POSIX	0	10166...	SIGNAL_AVG_WRITE_SIZE	NA(no_writes)
```

**HEATMAP Signals**：
```bash
$ grep "HEATMAP.*SIGNAL_" test_v2.1.txt | head -9
HEATMAP	0	16592...	SIGNAL_TOTAL_READ_EVENTS	1049304.0
HEATMAP	0	16592...	SIGNAL_TOTAL_WRITE_EVENTS	0.0
HEATMAP	0	16592...	SIGNAL_ACTIVE_BINS	1
HEATMAP	0	16592...	SIGNAL_ACTIVE_TIME	51.2
HEATMAP	0	16592...	SIGNAL_ACTIVITY_SPAN	51.2
HEATMAP	0	16592...	SIGNAL_PEAK_ACTIVITY_BIN	1049304.0
HEATMAP	0	16592...	SIGNAL_READ_ACTIVITY_ENTROPY_NORM	0.0
HEATMAP	0	16592...	SIGNAL_WRITE_ACTIVITY_ENTROPY_NORM	0
HEATMAP	0	16592...	SIGNAL_TOP1_SHARE	1.0
```

---

## 使用方法

```bash
# 单文件
python3 scripts/process_darshan_signals_v2.1.py input.txt

# 文件夹
python3 scripts/process_darshan_signals_v2.1.py /path/to/logs/

# 自定义输出
python3 scripts/process_darshan_signals_v2.1.py input.txt -o output.txt
```

---

## 文档

- **[METRICS_SPECIFICATION_v2.1.md](METRICS_SPECIFICATION_v2.1.md)** - 完整规格说明
  - NA原因类型详解
  - HEATMAP signals详细公式
  - 所有指标速查表

---

## 版本对比

| 特性 | v2.0 | v2.1 |
|------|------|------|
| Header文本 | "ORIGINAL DARSHAN LOG HEADER (Preserved)" | "ORIGINAL DARSHAN LOG HEADER" |
| NA格式 | `NA` | `NA(reason)` ⭐ |
| HEATMAP signals | 无 | 9个统计指标 ⭐ |
| Parsing | 基础 | 完整验证 |

---

## 新增指标总数

**v2.1新增**：
- NA原因类型：12种
- HEATMAP signals：9个

**总计指标**（所有版本）：
- 原始metrics：55+
- POSIX/STDIO signals：~20
- HEATMAP signals：9
- **总计：~84个指标**

---

## 快速参考

### NA原因
```
NA(no_reads)          - 读操作为0
NA(no_writes)         - 写操作为0
NA(no_read_time)      - 读时间为0
NA(no_write_time)     - 写时间为0
NA(not_shared_file)   - 非共享文件（rank != -1）
NA(no_bytes)          - 字节数为0
```

### HEATMAP关键指标
```
active_time          - 有I/O的时间
entropy_norm         - 分布均匀性 [0,1]
top1_share           - 最大bin占比（突发性指示）
```

---

## 文件位置

```
experiments/
├── scripts/
│   ├── process_darshan_signals_v2.1.py  ⭐ 最新版本
│   ├── process_darshan_signals_v2.py
│   └── process_darshan_signals.py
├── METRICS_SPECIFICATION_v2.1.md        ⭐ 最新规格
├── SUMMARY_v2.1.md                      ⭐ 本文件
└── (v2.0文档...)
```

---

**v2.1已就绪，所有要求已完成！** ✅

- ✅ 移除"(Preserved)"
- ✅ 修复parsing
- ✅ NA原因标注
- ✅ HEATMAP signals

---

**End of Summary v2.1**
