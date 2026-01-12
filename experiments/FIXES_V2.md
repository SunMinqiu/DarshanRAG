# Darshan KG Builder V2 - 修复总结

## 修复的4个问题

### 1. ✅ NA 值处理优化

**问题**: 数值字段混合存储字符串（如 "NA(no_time)"），导致后续数值计算困难。

**解决方案**:
- 数值字段: 缺失值统一用 `null` 表示
- 原因字段: 添加并行字段 `{field_name}_na_reason` 说明缺失原因

**示例**:
```json
{
  "read_bw": null,
  "read_bw_na_reason": "no_time",
  "avg_write_lat": null,
  "avg_write_lat_na_reason": "no_writes"
}
```

**代码变更**:
- `_convert_value()` 返回 `(value, na_reason)` 元组
- 所有解析函数同时设置值和 NA 原因字段

**优势**:
- JSON 类型一致性：数值字段永远是 number 或 null
- 保留原因信息：方便调试和数据质量分析
- 便于下游计算：可直接过滤 `!= null` 进行数值操作

---

### 2. ✅ Mount Table 作为 Job 属性

**问题**: 原设计将 mount table 中的所有 filesystem 都创建为节点和边，导致 Job 连接大量未实际使用的 filesystem。

**解决方案**:
- Mount table 存储为 Job 实体的 `mount_table` 属性
- 格式: `{mount_pt: fs_type}` 字典
- 不为 mount table 中的 filesystem 创建节点或边

**示例**:
```json
{
  "entity_name": "Job_3122490",
  "entity_type": "JOB",
  "mount_table": {
    "/home": "lustre",
    "/lus/grand": "lustre",
    "/lus/eagle": "lustre",
    "/local/scratch": "ext4",
    ...
  }
}
```

**代码变更**:
- `_parse_mount_table()`: 仅存储到 `self.mount_table`，不注册 filesystem
- `build_lightrag_kg()`: 将 `mount_table` 添加为 Job 实体属性

**优势**:
- 保留系统配置信息：mount table 作为 Job 的静态属性
- 避免无意义边：Job 不会连接到未实际访问的 filesystem
- 图更简洁：减少大量不必要的节点和边

---

### 3. ✅ Job → FileSystem 边优化

**问题**: Job 连接所有 mount table 中的 filesystem，而非实际访问的。

**解决方案**:
- 边名称: `TOUCH_FILESYSTEM`（明确语义）
- 创建条件: 仅连接 records 中**实际访问过**的 filesystem
- 新数据结构: `self.filesystems_touched` 跟踪被 records 触及的 filesystem

**示例**:
```
输入文件有 26 个 mount points
但只有 1 个被 records 实际访问 (/home on lustre)

结果:
- FileSystem 节点: 1 个（而非 26 个）
- Job → FileSystem 边: 1 条
```

**代码变更**:
- `_parse_module_records()`: 在解析 record 时注册 `filesystems_touched`
- `build_lightrag_kg()`: 仅为 `filesystems_touched` 创建节点和 TOUCH_FILESYSTEM 边

**优势**:
- 反映真实行为：边表示实际 I/O 活动，而非系统配置
- 图更准确：易于查询 "这个 job 访问了哪些 filesystem"
- 性能优化：减少无关节点和边

---

### 4. ✅ 删除 Job 中的 exe 字段

**问题**: Job 实体包含 `exe` 字段，与 Application 实体重复。

**解决方案**:
- `exe` 字段**仅**保留在 Application 实体中
- Job 实体通过 `Application → Job (HAS_JOB)` 边关联到 Application

**示例**:
```json
// Application 实体
{
  "entity_name": "App_4068766220",
  "entity_type": "APPLICATION",
  "exe": "4068766220"
}

// Job 实体（无 exe 字段）
{
  "entity_name": "Job_3122490",
  "entity_type": "JOB",
  "job_id": 3122490,
  "uid": 1449515727,
  ...
}
```

**代码变更**:
- `build_lightrag_kg()`: 过滤掉 `exe` 字段 `if key not in ['job_id', 'exe']`

**优势**:
- 避免冗余：信息只存储一次
- 关系清晰：通过图边查询 Job 对应的 Application
- 符合规范化：实体属性不重复

---

### 5. ✅ Signal 命名空间隔离

**问题**: 同一 record_id 在多个 module 中出现（如 HEATMAP 和 POSIX 共享同一 record_id），导致 POSIX records 错误地包含 HEATMAP signals。

**根本原因**: `_parse_module_records()` 在整个文件中搜索 record headers，没有限定在当前 module section 内。

**解决方案**:
- 提取每个 module section 的内容范围
- 只在该 module section 内解析 records
- 确保每个 Record 实体只包含对应 module 的 signals

**代码变更**:
```python
def _parse_module_section(self, content: str, module_name: str) -> None:
    # 1. 找到当前 module section 的起始位置
    module_match = re.search(module_pattern, content)

    # 2. 找到下一个 module section 的起始位置（或 EOF）
    next_module_match = ...

    # 3. 提取当前 module section 的内容
    module_content = content[module_start:module_end]

    # 4. 只在 module_content 中解析 records
    self._parse_module_records(module_content, module_name)
```

**验证结果**:
```
Before fix:
- POSIX records 包含: active_bins, total_read_events (HEATMAP signals) ❌

After fix:
- HEATMAP records 只包含: active_bins, total_read_events, ... ✅
- POSIX records 只包含: avg_read_lat, meta_ops, ... ✅
```

**优势**:
- Signal 正确性：每个 Record 只包含对应 module 的 signals
- 查询准确性：可靠区分不同 I/O 层级的性能特征
- 避免混淆：HEATMAP（时间分布）vs POSIX（系统调用级）

---

## 输出对比

### 修复前
```
Total entities: 175
Total relationships: 270

Entity breakdown:
  APPLICATION: 1
  JOB: 1
  MODULE: 3
  RECORD: 120 (重复计数!)
  FILE: 22
  FILESYSTEM: 28 (所有 mount points)
```

### 修复后
```
Total entities: 68
Total relationships: 99

Entity breakdown:
  APPLICATION: 1
  JOB: 1
  MODULE: 3
  RECORD: 40 (8 HEATMAP + 10 POSIX + 22 STDIO)
  FILE: 22
  FILESYSTEM: 1 (仅实际访问的)
```

## 影响评估

### 数据质量
- ✅ NA 值统一处理，类型一致
- ✅ Signal 命名空间隔离，无跨模块污染
- ✅ Filesystem 节点准确反映实际访问

### 图结构
- ✅ 更简洁：从 175 实体 → 68 实体
- ✅ 更准确：边表示真实行为
- ✅ 更可查：通过边查询关联信息

### 计算友好
- ✅ 数值字段可直接过滤和计算
- ✅ NA 原因可用于数据质量分析
- ✅ 减少冗余信息

## 测试验证

所有修复已通过以下测试：

1. **NA 值验证**:
   ```python
   assert record['avg_write_lat'] is None
   assert record['avg_write_lat_na_reason'] == 'no_writes'
   ```

2. **Job 属性验证**:
   ```python
   assert 'exe' not in job_entity
   assert 'mount_table' in job_entity
   assert len(job_entity['mount_table']) == 26
   ```

3. **FileSystem 节点验证**:
   ```python
   assert len(filesystems) == 1  # 仅实际访问的
   assert filesystems[0]['mount_pt'] == '/home'
   ```

4. **Signal 隔离验证**:
   ```python
   heatmap_signals = ['active_bins', 'total_read_events', ...]
   posix_signals = ['avg_read_lat', 'meta_ops', ...]

   assert all(s not in posix_record for s in heatmap_signals)
   assert all(s not in heatmap_record for s in posix_signals)
   ```

## 向后兼容性

这些修复**破坏了向后兼容性**，因为：

1. JSON 结构变化：NA 值从字符串变为 `null` + 原因字段
2. 实体数量减少：Filesystem 和 Record 数量显著减少
3. 属性变化：Job 实体新增 `mount_table`，删除 `exe`

**迁移建议**: 使用新版本 `darshan_kg_builder_v2.py` 重新生成 KG。
