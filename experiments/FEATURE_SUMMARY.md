# Darshan信号提取工具 - 功能总结

## ✅ 已完成的功能

### 1. 核心功能

#### ✨ **完整Header保留** (v1.1 新增)
- ✅ 保留从文件开头到 `# description of columns:` 之前的所有内容
- ✅ 包括darshan版本、jobid、时间戳等元信息
- ✅ 完整保留所有28个mount entries（文件系统信息）
- ✅ 保留POSIX/STDIO/APMPI/HEATMAP模块信息
- ✅ 维持原始格式和缩进

#### 📊 **Metrics提取**
提取的原始Metrics（最小充分集）：

**基础I/O（6个）**
- POSIX_BYTES_READ
- POSIX_BYTES_WRITTEN
- POSIX_READS
- POSIX_WRITES
- POSIX_F_READ_TIME
- POSIX_F_WRITE_TIME

**访问模式（5个）**
- POSIX_SEQ_READS
- POSIX_SEQ_WRITES
- POSIX_CONSEC_READS
- POSIX_CONSEC_WRITES
- POSIX_RW_SWITCHES

**请求大小分布（20个）**
- POSIX_SIZE_READ_* (10个区间)
- POSIX_SIZE_WRITE_* (10个区间)

**对齐信息（4个）**
- POSIX_FILE_NOT_ALIGNED
- POSIX_MEM_NOT_ALIGNED
- POSIX_FILE_ALIGNMENT
- POSIX_MEM_ALIGNMENT

**元数据操作（6个）**
- POSIX_OPENS
- POSIX_STATS
- POSIX_SEEKS
- POSIX_FSYNCS
- POSIX_FDSYNCS
- POSIX_F_META_TIME

**并行与共享（6个）**
- POSIX_FASTEST_RANK
- POSIX_FASTEST_RANK_BYTES
- POSIX_SLOWEST_RANK
- POSIX_SLOWEST_RANK_BYTES
- POSIX_F_VARIANCE_RANK_BYTES
- POSIX_F_VARIANCE_RANK_TIME

**STDIO指标（6个）**
- STDIO_BYTES_READ
- STDIO_BYTES_WRITTEN
- STDIO_READS
- STDIO_WRITES
- STDIO_F_READ_TIME
- STDIO_F_WRITE_TIME

**其他（2个）**
- POSIX_MAX_BYTE_READ
- POSIX_MAX_BYTE_WRITTEN

**总计：55+ 原始metrics**

#### 🎯 **派生信号计算**

工具自动计算12种I/O异常信号：

| # | 信号 | 派生指标数 | 说明 |
|---|------|-----------|------|
| 1 | **HMD** | 3 | High Metadata Load - 元数据操作总数、时间占比、速率 |
| 2 | **MSL-R/W** | 2 | Misaligned I/O - 读写未对齐比率 |
| 3 | **RMA-R/W** | 3 | Random Access - 随机读写比率、切换率 |
| 4 | **SHF** | 1 | Shared File Access - 是否共享文件 |
| 5 | **SML-R/W** | 2 | Small I/O - 小I/O读写比率 |
| 6 | **RDA-R** | 2 | Repetitive Data Access - 数据重用比率、低偏移信号 |
| 7 | **RLIM** | 1 | Rank Load Imbalance - Rank负载不均比率 |
| 8 | **SLIM** | 2 | Server Load Imbalance - 带宽方差、突发度 |
| 9 | **MPNM** | 1 | Multi-Process w/o MPI - 无MPI多进程标志 |
| 10 | **NC-R/W** | 2 | No Collective I/O - 集合I/O读写比率 |
| 11 | **LLL-R/W** | 2 | Low-Level Library - STDIO使用比率 |
| 12 | **NOL** | - | No Issue - 通过其他信号判断 |

**总计：21个派生信号指标**

#### 🔧 **处理能力**

**输入支持：**
- ✅ 单个txt文件
- ✅ 包含txt文件的文件夹
- ✅ 多层嵌套的父目录
- ✅ 自动递归查找所有.txt文件

**输出控制：**
- ✅ 自动生成输出名称（添加_signals_v1后缀）
- ✅ 自定义输出文件路径（`-o` 参数）
- ✅ 自定义输出文件夹路径
- ✅ 保持原有目录结构

**错误处理：**
- ✅ UTF-8编码，容错处理
- ✅ 安全除法（避免除零错误）
- ✅ 处理缺失的module（APMPI, HEATMAP）
- ✅ 处理不完整的数据

### 2. 文件和文档

#### 程序文件
- ✅ `scripts/process_darshan_signals.py` - 主程序（约550行）
- ✅ `test_signal_extraction.sh` - 自动化测试脚本
- ✅ `test_header_preservation.sh` - Header保留功能测试

#### 文档文件
- ✅ `README_signals.md` - 完整功能说明
- ✅ `USAGE_EXAMPLES.md` - 详细使用示例
- ✅ `SUMMARY.md` - 项目总结
- ✅ `QUICK_START.txt` - 快速参考卡片
- ✅ `CHANGELOG_header_preservation.md` - Header功能更新日志
- ✅ `FEATURE_SUMMARY.md` - 本文件，功能总结

### 3. 测试验证

#### 功能测试
- ✅ 单文件处理测试
- ✅ 文件夹批量处理测试
- ✅ Header完整性验证
- ✅ Metrics提取验证
- ✅ 信号计算验证
- ✅ Mount entries计数验证（28个全部保留）

#### 示例文件处理
- **输入：** Darshan_log_example.txt (332.8KB)
- **输出：** Darshan_log_example_signals_v1.txt (68.5KB, 1526行)
- **处理时间：** < 1秒
- **提取记录数：** 多个rank和file记录

## 📋 使用方式速查

### 基础命令

```bash
# 单文件
python3 scripts/process_darshan_signals.py input.txt

# 文件夹
python3 scripts/process_darshan_signals.py /path/to/logs/

# 自定义输出
python3 scripts/process_darshan_signals.py input.txt -o output.txt
python3 scripts/process_darshan_signals.py /logs/ -o /output/

# 帮助
python3 scripts/process_darshan_signals.py --help
```

### 测试命令

```bash
# 完整测试
bash test_signal_extraction.sh

# Header保留测试
bash test_header_preservation.sh
```

## 📊 输出文件结构

```
[输出文件 *_signals_v1.txt]
│
├─ 第0部分：原始Header（完整保留）
│   ├─ darshan版本和配置
│   ├─ 作业信息（jobid, uid, exe）
│   ├─ 时间戳和运行时间
│   ├─ 模块信息
│   └─ 所有mount points
│
├─ 第1部分：原始Metrics（55+ 指标）
│   ├─ 基础I/O量和次数
│   ├─ 访问模式
│   ├─ 请求大小分布
│   ├─ 对齐信息
│   ├─ 元数据操作
│   ├─ 并行与共享
│   └─ STDIO指标
│
└─ 第2部分：派生信号（21个指标）
    ├─ HMD（3个指标）
    ├─ MSL（2个指标）
    ├─ RMA（3个指标）
    ├─ SHF（1个指标）
    ├─ SML（2个指标）
    ├─ RDA（2个指标）
    ├─ RLIM（1个指标）
    ├─ SLIM（2个指标）
    ├─ MPNM（1个指标）
    ├─ NC（2个指标）
    └─ LLL（2个指标）
```

## 🎯 适用场景

1. **I/O性能分析** - 识别应用程序的I/O瓶颈
2. **异常检测** - 自动检测12种常见I/O异常模式
3. **性能优化** - 为优化提供量化指标
4. **作业监控** - 批量分析大规模作业的I/O行为
5. **系统调优** - 基于mount points和文件系统信息优化配置
6. **研究分析** - 保留完整元信息用于深度研究

## 💡 优势特点

1. **完整性** ⭐
   - 保留所有原始header信息
   - 提取最小充分的metrics集合
   - 计算全面的派生信号

2. **易用性**
   - 简单的命令行接口
   - 自动化处理
   - 清晰的输出格式

3. **可扩展性**
   - 批量处理能力
   - 保持目录结构
   - 支持大规模日志分析

4. **可靠性**
   - 错误容忍处理
   - 完整的测试覆盖
   - 向后兼容

5. **无依赖**
   - 仅使用Python标准库
   - Python 3.6+即可运行
   - 无需额外安装

## 🔄 版本历史

- **v1.1** (2026-01-11)
  - ✅ 添加完整header保留功能
  - ✅ 保留所有mount points
  - ✅ 更新文档和测试

- **v1.0** (2025-01-11)
  - ✅ 初始版本
  - ✅ 基本信号提取功能
  - ✅ 批量处理支持

## 📍 文件位置

```
/users/Minqiu/DarshanRAG/experiments/
├── scripts/
│   └── process_darshan_signals.py    # 主程序
├── test_signal_extraction.sh         # 完整测试
├── test_header_preservation.sh       # Header测试
├── README_signals.md                 # 使用文档
├── USAGE_EXAMPLES.md                 # 示例文档
├── SUMMARY.md                        # 项目总结
├── QUICK_START.txt                   # 快速参考
├── CHANGELOG_header_preservation.md  # 更新日志
└── FEATURE_SUMMARY.md                # 本文件
```

## ✅ 完成状态

所有核心功能已完成并通过测试，工具可以投入使用！

---

**准备就绪！开始处理你的Darshan日志吧！** 🚀
