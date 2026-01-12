# Darshan Signal Extraction Tool v2.0 - 项目总结

## ✅ 已完成的所有要求

### 1. NA值规则 ✅
- ✅ 分母为0输出`NA`，不是`0`
- ✅ 没有抽取到的数据用`NA`
- ✅ Darshan中`-1`值视为`NA`

### 2. 访问模式改进 ✅
- ✅ 移除了`random_ratio`
- ✅ 保留两个信号：
  - `seq_read_ratio = seq_reads / reads`
  - `consec_read_ratio = consec_reads / reads`
- ✅ 新增：`seq_ratio` 和 `consec_ratio`（整体比例）

### 3. RLIM条件判断 ✅
- ✅ 只有在 `rank == -1` 且 `bytes_total > 0` 时才计算
- ✅ 否则输出`NA`

### 4. 新增meta_intensity ✅
- ✅ 公式：`meta_intensity = meta_ops / (reads + writes)`
- ✅ 含义：每次I/O操作的元数据操作数

### 5. RDA改名和标注 ✅
- ✅ `read_reuse_ratio` 改名为 `reuse_proxy`
- ✅ 标注为"proxy from MAX_BYTE_READ+1"
- ✅ 文件大小估算来自 `MAX_BYTE_READ + 1`

### 6. Record元数据 ✅
- ✅ 每个record显示：
  - `file_name`: 文件路径
  - `mount_pt`: 挂载点
  - `fs_type`: 文件系统类型

### 7. 性能主指标（必算）✅
- ✅ Record-level必算
- ✅ Module-level必算
- ✅ Job-level必算
- ✅ 包括：`read_bw`, `write_bw`, `read_iops`, `write_iops`, `avg_read_size`, `avg_write_size`, `seq_ratio`, `consec_ratio`

### 8. 分母为0规则 ✅
- ✅ 所有除法操作，分母为0输出`NA`
- ✅ rank != -1 时不计算RLIM

### 9. 模块独立性 ✅
- ✅ POSIX和STDIO不在事实层相加
- ✅ 每个模块独立计算和输出

### 10. 三层结构 ✅
- ✅ Job Level（作业级汇总）
- ✅ Module Level（模块级汇总和性能）
- ✅ Record Level（文件级详细指标）

### 11. 规格说明文档 ✅
- ✅ 创建了 `METRICS_SPECIFICATION_v2.md`
- ✅ 详细说明了：
  - 提取的原始metrics（55+个）
  - 计算的派生signals（~20个）
  - 每个指标的公式
  - NA值规则
  - 层次化结构

---

## 📁 创建的文件

### 程序文件
1. **process_darshan_signals_v2.py** - v2.0主程序（约650行）
   - 三层层次化结构
   - NA值处理
   - 条件判断（RLIM）
   - 模块独立性

### 文档文件
1. **METRICS_SPECIFICATION_v2.md** - 完整的指标规格说明
   - 所有提取的metrics
   - 所有计算的signals
   - 详细公式
   - 层次化结构说明

2. **README_v2.md** - 使用指南
   - 快速入门
   - 输出结构
   - 公式速查
   - 与v1.0对比

3. **QUICK_REFERENCE_v2.txt** - 快速参考卡片
   - 命令速查
   - 公式速查
   - 规则提醒

4. **SUMMARY_v2.md** - 本文件，项目总结

---

## 📊 输出示例

### Job Level
```
JOB	total_bytes_read	7489771.0
JOB	total_bytes_written	11201335.0
JOB	total_reads	910.0
JOB	total_writes	89257.0
```

### Module Level
```
POSIX	MODULE_AGG	total_bytes_read	4204115.0
POSIX	MODULE_PERF	read_bw	131.23
POSIX	MODULE_PERF	avg_read_size	7932.29
```

### Record Level
```
# RECORD: 10166465462036786034 (rank=0)
# file_name: /home/user/data.dat
# mount_pt: /home
# fs_type: lustre

POSIX	0	10166...	POSIX_BYTES_READ	1198.0
POSIX	0	10166...	SIGNAL_READ_BW	1.81
POSIX	0	10166...	SIGNAL_AVG_READ_SIZE	599.0
POSIX	0	10166...	SIGNAL_SEQ_READ_RATIO	0.5
POSIX	0	10166...	SIGNAL_META_INTENSITY	1.0
POSIX	0	10166...	SIGNAL_REUSE_PROXY	1.0
```

---

## 🎯 提取和计算的指标总览

### 原始Metrics（55+个）

**POSIX模块**：
- 基础I/O（6个）: bytes_read/written, reads/writes, read/write_time
- 访问模式（5个）: seq_reads/writes, consec_reads/writes, rw_switches
- 请求大小（20个）: 10个读区间 + 10个写区间
- 对齐（4个）: file/mem alignment, file/mem not_aligned
- 元数据（6个）: opens, stats, seeks, fsyncs, fdsyncs, meta_time
- 并行（6个）: fastest/slowest rank bytes, variance_rank_bytes/time
- 其他（2个）: max_byte_read/written

**STDIO模块**（6个）：
- bytes_read/written, reads/writes, read/write_time

### 派生Signals（~20个）

| 类别 | Signal | 公式 | 层级 | 模块 |
|------|--------|------|------|------|
| **性能** | read_bw | bytes_read/1024²/time | R,M,J | All |
| | write_bw | bytes_written/1024²/time | R,M,J | All |
| | read_iops | reads/time | R,M,J | All |
| | write_iops | writes/time | R,M,J | All |
| | avg_read_size | bytes_read/reads | R,M,J | All |
| | avg_write_size | bytes_written/writes | R,M,J | All |
| | seq_ratio | (seq_r+seq_w)/(r+w) | R,M,J | POSIX |
| | consec_ratio | (consec_r+consec_w)/(r+w) | R,M,J | POSIX |
| **访问** | seq_read_ratio | seq_reads/reads | R | POSIX |
| | seq_write_ratio | seq_writes/writes | R | POSIX |
| | consec_read_ratio | consec_reads/reads | R | POSIX |
| | consec_write_ratio | consec_writes/writes | R | POSIX |
| **元数据** | meta_ops | opens+stats+seeks+fsyncs+fdsyncs | R | POSIX |
| | meta_intensity | meta_ops/(reads+writes) | R | POSIX |
| | meta_fraction | meta_time/total_time | R | POSIX |
| **对齐** | unaligned_read_ratio | not_aligned/reads | R | POSIX |
| | unaligned_write_ratio | not_aligned/writes | R | POSIX |
| **小I/O** | small_read_ratio | small_reads/reads | R | POSIX |
| | small_write_ratio | small_writes/writes | R | POSIX |
| **重用** | reuse_proxy | bytes_read/(max_byte+1) | R | POSIX |
| **不均** | rank_imbalance_ratio | slowest/fastest | R* | POSIX |
| | bw_variance_proxy | variance_rank_bytes | R* | POSIX |
| **共享** | is_shared | 1 if rank=-1 else 0 | R | All |

**层级**：R=Record, M=Module, J=Job
**R***: 仅当rank=-1且bytes>0时

---

## 🚀 使用方法

### 基本命令
```bash
# 单文件
python3 scripts/process_darshan_signals_v2.py input.txt

# 文件夹
python3 scripts/process_darshan_signals_v2.py /path/to/logs/

# 自定义输出
python3 scripts/process_darshan_signals_v2.py input.txt -o output.txt
```

### 示例
```bash
cd /users/Minqiu/DarshanRAG/experiments

python3 scripts/process_darshan_signals_v2.py \
    ../data/examples/Darshan_log_example.txt

# 输出: ../data/examples/Darshan_log_example_signals_v2.txt
```

### 查看输出
```bash
# Job级
grep "^JOB" output_signals_v2.txt

# Module级性能
grep "MODULE_PERF" output_signals_v2.txt

# 特定signal
grep "SIGNAL_READ_BW" output_signals_v2.txt

# NA值
grep "SIGNAL.*NA" output_signals_v2.txt
```

---

## 📈 测试结果

**测试文件**: Darshan_log_example.txt (332.8KB)
**输出文件**: Darshan_log_example_signals_v2.txt (3166行)

**验证项**：
- ✅ Header完整保留（28个mount entries）
- ✅ 三层结构正确
- ✅ NA值正确输出
- ✅ 性能指标在所有层级都计算
- ✅ RLIM条件判断正确
- ✅ Record元数据正确显示
- ✅ 模块独立性正确
- ✅ 所有公式计算正确

---

## 📚 文档完整性

| 文档 | 内容 | 状态 |
|------|------|------|
| METRICS_SPECIFICATION_v2.md | 完整的指标规格说明 | ✅ |
| README_v2.md | 使用指南 | ✅ |
| QUICK_REFERENCE_v2.txt | 快速参考 | ✅ |
| SUMMARY_v2.md | 项目总结 | ✅ |

---

## 🎉 项目完成状态

**所有11项要求全部完成！** ✅

1. ✅ NA值规则
2. ✅ 访问模式改用seq_ratio和consec_ratio
3. ✅ RLIM条件判断
4. ✅ 新增meta_intensity
5. ✅ RDA改名为reuse_proxy并标注
6. ✅ Record元数据显示
7. ✅ 性能指标三层必算
8. ✅ 分母为0→NA
9. ✅ 模块独立性
10. ✅ 三层结构
11. ✅ 详细规格文档

---

## 📍 文件位置

```
/users/Minqiu/DarshanRAG/experiments/
├── scripts/
│   ├── process_darshan_signals_v2.py    # v2.0主程序 ⭐
│   └── process_darshan_signals.py       # v1.0（保留）
├── METRICS_SPECIFICATION_v2.md          # 完整规格 ⭐
├── README_v2.md                         # 使用指南 ⭐
├── QUICK_REFERENCE_v2.txt               # 快速参考 ⭐
└── SUMMARY_v2.md                        # 本文件 ⭐
```

---

## 🔄 版本对比

| 特性 | v1.0 | v2.0 |
|------|------|------|
| 结构 | 扁平 | 三层层次化 ✅ |
| NA处理 | 输出0 | 输出NA ✅ |
| 访问模式 | random_ratio | seq/consec_ratio ✅ |
| RLIM | 总是计算 | 条件判断 ✅ |
| 元数据 | 2指标 | 3指标(+intensity) ✅ |
| 重用指标 | read_reuse_ratio | reuse_proxy ✅ |
| Record信息 | 无 | file/mount/fs ✅ |
| 性能指标 | Record层 | 三层都有 ✅ |
| 模块独立 | 未强调 | 明确规定 ✅ |
| 文档 | 基础 | 完整规格 ✅ |

---

**v2.0版本已完全就绪，可以投入使用！** 🚀

---

**End of Summary**
