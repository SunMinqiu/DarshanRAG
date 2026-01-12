# 更新日志 - Header Preservation Feature

## 版本：v1.1 (2026-01-11)

### 新增功能：完整保留原始Darshan日志Header

#### 📋 功能描述
现在工具会完整保留原始Darshan日志文件的所有header信息，从文件开头一直到 `# description of columns:` 之前的所有内容。

#### ✨ 保留的Header内容包括：

1. **基本信息**
   - darshan log version
   - compression method
   - exe, uid, jobid
   - start_time, end_time (及可读格式)
   - nprocs, run time
   - metadata

2. **日志文件区域信息**
   ```
   # log file regions
   # -------------------------------------------------------
   # header: 1328 bytes (uncompressed)
   # job data: 516 bytes (compressed)
   # record table: 616 bytes (compressed)
   # POSIX module: 1036 bytes (compressed), ver=4
   # STDIO module: 1632 bytes (compressed), ver=2
   # APMPI module: 581 bytes (compressed), ver=1
   # HEATMAP module: 533 bytes (compressed), ver=1
   ```

3. **挂载文件系统信息**（完整保留所有28个mount entries）
   ```
   # mounted file systems (mount point and fs type)
   # -------------------------------------------------------
   # mount entry:	/run/credentials/systemd-sysusers.service	ramfs
   # mount entry:	/var/opt/cray/pe/pe_images/nvidia-23.12	squashfs
   ...
   # mount entry:	/	overlay
   ```

#### 📄 输出文件格式

新的输出文件结构：

```
# ============================================================
# ORIGINAL DARSHAN LOG HEADER (Preserved)
# ============================================================
[所有原始header内容，完整保留格式和缩进]

# ============================================================
# SIGNAL EXTRACTION OUTPUT - Darshan Signal Extraction v1
# ============================================================
#
# Format: <rank> <record_id> <metric_name> <value>
#
# Section 1: Original Metrics (Required Minimal Sufficient Set)
# -----------------------------------------------------------
[原始metrics数据...]

# Section 2: Derived Anomaly Signals
# -----------------------------------
[派生信号数据...]
```

#### 🔧 代码修改

**修改的文件：** `scripts/process_darshan_signals.py`

**主要变更：**

1. **添加header存储**
   ```python
   def __init__(self):
       # ... existing code ...
       self.header_lines = []  # Store all header lines
   ```

2. **解析时保留header**
   ```python
   def parse_log_file(self, input_path):
       in_header = True  # Track if we're in header section

       for line in f:
           if '# description of columns:' in line:
               in_header = False

           if in_header and line:
               self.header_lines.append(original_line.rstrip('\n'))
   ```

3. **输出时写入header**
   ```python
   def write_signals_output(self, output_path):
       # Write preserved original header
       f.write("# ORIGINAL DARSHAN LOG HEADER (Preserved)\n")
       for header_line in self.header_lines:
           f.write(header_line + "\n")
   ```

#### ✅ 测试验证

创建了专门的测试脚本验证header保留功能：

```bash
bash test_header_preservation.sh
```

**测试结果：**
- ✅ darshan log version 保留
- ✅ jobid, nprocs, runtime 保留
- ✅ 所有28个mount entries 完整保留
- ✅ module信息保留
- ✅ 格式和缩进保持一致

#### 📊 文件大小对比

- 原始输出文件大小（v1.0）：~66KB
- 新版输出文件大小（v1.1）：~68KB
- 增加的header信息：~2KB

#### 💡 使用方式

使用方式完全不变，header会自动保留：

```bash
# 单文件处理
python3 scripts/process_darshan_signals.py input.txt

# 文件夹处理
python3 scripts/process_darshan_signals.py /path/to/logs/ -o /output/

# 所有原始header信息都会自动保留在输出文件中
```

#### 🎯 优势

1. **完整性**：保留所有原始日志的上下文信息
2. **可追溯性**：可以追溯到原始作业的所有元信息
3. **便于分析**：mount points等信息对性能分析很重要
4. **无额外操作**：自动保留，无需额外参数

#### 📝 注意事项

- Header保留不影响原有的metrics和signals提取功能
- 输出文件略有增大（约2KB），但信息更完整
- 所有原有功能保持不变，完全向后兼容

#### 🔄 向后兼容性

✅ 完全向后兼容
- 所有现有脚本和命令无需修改
- 输出格式保持结构化，易于解析
- 新增的header部分有明确的分隔标记

---

## 相关文件

- 主程序：`scripts/process_darshan_signals.py`
- 测试脚本：`test_header_preservation.sh`
- 使用示例：`USAGE_EXAMPLES.md`

## 测试覆盖

✅ 单文件处理
✅ 文件夹批量处理
✅ Header完整性验证
✅ Mount entries计数验证
✅ 所有原有功能正常

---

**版本历史：**

- **v1.1** (2026-01-11) - 添加完整header保留功能
- **v1.0** (2025-01-11) - 初始版本，基本信号提取功能
