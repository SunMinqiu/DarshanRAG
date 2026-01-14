# 未使用Counters优先级列表

根据实用性和分析价值排序，以下是建议添加的counters。

---

## 🔴 高优先级 (强烈推荐)

### 1. STDIO Rank Bytes Imbalance (3个)
```python
STDIO_FASTEST_RANK_BYTES
STDIO_SLOWEST_RANK_BYTES
STDIO_F_VARIANCE_RANK_BYTES
```

**价值**: 补充STDIO的rank imbalance分析（目前只有time，没有bytes）
**用途**: 计算 `RANK_BYTES_IMB = slowest_bytes / fastest_bytes`
**实现难度**: ⭐ 简单（和POSIX的RANK_BYTES逻辑相同）

---

### 2. POSIX Max Write Position (1个)
```python
POSIX_MAX_BYTE_WRITTEN
```

**价值**: 估算写入的文件大小，补充MAX_BYTE_READ
**用途**: 计算 `write_reuse_proxy = bytes_written / (MAX_BYTE_WRITTEN + 1)`
**实现难度**: ⭐ 简单（和MAX_BYTE_READ逻辑相同）

---

## 🟡 中等优先级 (推荐)

### 3. Large I/O Size Histograms (14个)
```python
# READ bins (7个)
POSIX_SIZE_READ_10K_100K
POSIX_SIZE_READ_100K_1M
POSIX_SIZE_READ_1M_4M
POSIX_SIZE_READ_4M_10M
POSIX_SIZE_READ_10M_100M
POSIX_SIZE_READ_100M_1G
POSIX_SIZE_READ_1G_PLUS

# WRITE bins (7个)
POSIX_SIZE_WRITE_10K_100K
POSIX_SIZE_WRITE_100K_1M
POSIX_SIZE_WRITE_1M_4M
POSIX_SIZE_WRITE_4M_10M
POSIX_SIZE_WRITE_10M_100M
POSIX_SIZE_WRITE_100M_1G
POSIX_SIZE_WRITE_1G_PLUS
```

**价值**: 补充当前只有small I/O (<10KB) 的情况
**用途**:
- 计算 `large_read_ratio` = (sum of bins > 10KB) / total_reads
- 计算 `very_large_read_ratio` = (sum of bins > 1MB) / total_reads
- 识别bulk transfer patterns
**实现难度**: ⭐⭐ 中等（需要累加多个bins）

---

### 4. Memory Alignment Details (2个)
```python
POSIX_MEM_ALIGNMENT
POSIX_MEM_NOT_ALIGNED
```

**价值**: 补充alignment分析（当前只有FILE_NOT_ALIGNED）
**用途**:
- 计算 `mem_unaligned_ratio` = MEM_NOT_ALIGNED / (reads + writes)
- 对比 `file_unaligned_ratio` vs `mem_unaligned_ratio`
**实现难度**: ⭐ 简单

---

### 5. Access Pattern Top-4 (8个)
```python
POSIX_ACCESS1_ACCESS, POSIX_ACCESS1_COUNT
POSIX_ACCESS2_ACCESS, POSIX_ACCESS2_COUNT
POSIX_ACCESS3_ACCESS, POSIX_ACCESS3_COUNT
POSIX_ACCESS4_ACCESS, POSIX_ACCESS4_COUNT
```

**价值**: 识别最常见的access sizes
**用途**:
- 显示top-4 access sizes及其频率
- 用于buffer size优化建议
- 补充size histogram的统计
**实现难度**: ⭐ 简单（直接输出即可）

---

## 🟢 低优先级 (可选)

### 6. Stride Patterns (8个)
```python
POSIX_STRIDE1_STRIDE, POSIX_STRIDE1_COUNT
POSIX_STRIDE2_STRIDE, POSIX_STRIDE2_COUNT
POSIX_STRIDE3_STRIDE, POSIX_STRIDE3_COUNT
POSIX_STRIDE4_STRIDE, POSIX_STRIDE4_COUNT
```

**价值**: 识别strided access patterns（如array slicing, 矩阵转置）
**用途**:
- 显示top-4 stride patterns
- 检测非单元stride（表明复杂的data layout）
**实现难度**: ⭐ 简单（直接输出即可）

---

### 7. STDIO File Operations (4个)
```python
STDIO_OPENS
STDIO_FDOPENS
STDIO_SEEKS
STDIO_FLUSHES
```

**价值**: STDIO-specific操作统计
**用途**:
- 计算 `seek_intensity` = SEEKS / (reads + writes)
- 计算 `flush_rate` = FLUSHES / writes
**实现难度**: ⭐ 简单

---

### 8. STDIO Byte Positions (2个)
```python
STDIO_MAX_BYTE_READ
STDIO_MAX_BYTE_WRITTEN
```

**价值**: STDIO的文件访问范围
**用途**: 估算STDIO访问的文件大小
**实现难度**: ⭐ 简单

---

### 9. POSIX File Alignment Boundary (1个)
```python
POSIX_FILE_ALIGNMENT
```

**价值**: 文件系统的alignment boundary
**用途**: 显示expected alignment，用于解释FILE_NOT_ALIGNED
**实现难度**: ⭐ 简单（直接输出）

---

## ⚪ 非常低优先级 (特殊场景)

### 10. File Operations (7个)
```python
POSIX_FILENOS      # fileno() calls
POSIX_DUPS         # dup()/dup2() calls
POSIX_MMAPS        # mmap() calls
POSIX_MODE         # File open mode
POSIX_RENAME_SOURCES
POSIX_RENAME_TARGETS
POSIX_RENAMED_FROM
```

**价值**: 非常特殊的操作，大多数workload中=0
**用途**: 调试特定问题
**实现难度**: ⭐ 简单

---

### 11. Rank IDs (4个)
```python
POSIX_FASTEST_RANK
POSIX_SLOWEST_RANK
STDIO_FASTEST_RANK
STDIO_SLOWEST_RANK
```

**价值**: 识别具体哪个rank最快/慢
**用途**: 调试rank-specific问题
**实现难度**: ⭐ 简单
**注意**: 你已经有*_RANK_TIME和*_RANK_BYTES，rank ID用处不大

---

## 实现建议

### 最小可行方案 (MVP)
只添加**高优先级**的4个counters：
1. STDIO_*_RANK_BYTES (3个)
2. POSIX_MAX_BYTE_WRITTEN (1个)

**工作量**: ~30分钟
**价值**: 补全rank imbalance和reuse分析

---

### 推荐方案
添加**高优先级 + 部分中等优先级**：
1. STDIO_*_RANK_BYTES (3个)
2. POSIX_MAX_BYTE_WRITTEN (1个)
3. Large I/O bins (14个)
4. MEM_ALIGNMENT + MEM_NOT_ALIGNED (2个)

**工作量**: ~2小时
**价值**: 完善I/O size分析和alignment分析

---

### 完整方案
添加**高优先级 + 中等优先级**：
- 所有上述 + Access patterns + Stride patterns

**工作量**: ~3-4小时
**价值**: 全面的I/O pattern分析

---

## 代码模板

### 添加STDIO_RANK_BYTES (高优)

```python
# 在 compute_record_signals() 的 STDIO section:
if 'STDIO' in module:
    if rank == -1:
        fastest_bytes = get('STDIO_FASTEST_RANK_BYTES', None)
        slowest_bytes = get('STDIO_SLOWEST_RANK_BYTES', None)
        variance_bytes = get('STDIO_F_VARIANCE_RANK_BYTES', None)

        signals['fastest_rank_bytes'] = fastest_bytes if fastest_bytes is not None else self.na_with_reason('not_available')
        signals['slowest_rank_bytes'] = slowest_bytes if slowest_bytes is not None else self.na_with_reason('not_available')
        signals['var_rank_bytes'] = variance_bytes if variance_bytes is not None else self.na_with_reason('not_available')

        # Rank bytes imbalance
        if fastest_bytes and slowest_bytes and fastest_bytes > 0:
            signals['rank_bytes_imb'] = slowest_bytes / fastest_bytes
        else:
            signals['rank_bytes_imb'] = self.na_with_reason('dependency_missing')
```

### 添加Large I/O Bins (中优)

```python
# 在 compute_record_signals() 的 POSIX section:
if 'POSIX' in module:
    # Large I/O bins
    large_read_bins = ['POSIX_SIZE_READ_10K_100K', 'POSIX_SIZE_READ_100K_1M',
                       'POSIX_SIZE_READ_1M_4M', 'POSIX_SIZE_READ_4M_10M',
                       'POSIX_SIZE_READ_10M_100M', 'POSIX_SIZE_READ_100M_1G',
                       'POSIX_SIZE_READ_1G_PLUS']

    large_reads = sum(get(bin, 0) if not isinstance(get(bin, 0), str) else 0
                      for bin in large_read_bins)

    signals['large_read_ratio'] = div(large_reads, reads, 'no_reads')

    # Same for writes...
```

---

## 总结

| 优先级 | Counters数 | 工作量 | 价值 |
|--------|-----------|--------|------|
| 🔴 高  | 4         | 30分钟 | 补全核心分析 |
| 🟡 中  | 24        | 2小时  | 完善pattern分析 |
| 🟢 低  | 19        | 2小时  | 高级分析 |
| 总计   | 47        | 4.5小时| 全面覆盖 |

**建议**: 先实现**高优先级**的4个counters，然后根据实际需求决定是否添加中等优先级的。
