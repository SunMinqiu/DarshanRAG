# Description Generator V3 - 完成总结

## ✅ 新增功能

### 1. 关系描述生成

添加了 7 种关系类型的描述模板：

| 关系类型 | 模板 | 示例 |
|---------|------|------|
| Application → Job | 表示 job 运行该 application | `job Job_3122490 runs the application App_4068766220` |
| Job → File | job 对文件的 I/O 操作 | `performs file I/O operations on file {tgt_id}` |
| Job → FileSystem | job 访问的存储资源 | `interaction between job and storage resource` |
| Job → Module | job 使用的 I/O 模块 | `uses the I/O module {tgt_id} during execution` |
| Module → Record | 模块产生的 I/O 记录 | `links the I/O module to a specific I/O record` |
| Record → File | record 对应的文件访问 | `corresponds to I/O operations performed on file` |
| Record → Module | record 的执行上下文 | `is executed under the I/O module {tgt_id}` |

### 2. 关系属性访问

关系描述模板可以访问：
- 关系自身属性（`src_id`, `tgt_id`, `keywords`, `weight`）
- 源实体的所有属性
- 目标实体的所有属性

示例：在 Job→File 关系模板中可以引用 `{bytes_read}` 和 `{bytes_written}`

### 3. 扩展的使用统计

新增两个统计类别：
- **【2】关系模板中永远没有匹配到的属性**
- **【4】关系 JSON 中永远没有用到的属性**

### 4. 关系属性清理

关系只保留标准字段：
- `src_id`, `tgt_id`, `description`
- `keywords`, `weight`
- `source_id`, `file_path`

## 📊 测试结果

使用 `test_v2.1_output.json` 测试：

```
输入:
  - 68 个实体
  - 99 个关系

输出:
  - 所有实体都生成了描述
  - 所有关系都生成了描述
  - 清理后只保留必要字段
```

### 发现的未匹配属性

#### 实体模板缺失

- **APPLICATION**: `nprocs` (可能需要添加到数据中)
- **FILE**: `rank`, `is_shared` (模板中引用但数据中没有)
- **JOB**: `nnodes`, `exe` (需要检查数据源)
- **RECORD**: `io_start_ts`, `seq_write_ratio`, `consec_write_ratio`

#### 关系模板缺失

- **MODULE→RECORD**: `operation_types` (需要从 record 推断操作类型)

## 📁 交付文件

1. **[generate_descriptions_v3.py](generate_descriptions_v3.py)** - 主脚本（485行）
2. **[README_v3.md](README_v3.md)** - 详细使用文档
3. **[SUMMARY_v3.md](SUMMARY_v3.md)** - 本文件
4. **test_with_descriptions.json** - 测试输出示例

## 🎯 关键改进

### 相比 V2 的改进

| 特性 | V2 | V3 |
|------|----|----|
| 实体描述 | ✅ | ✅ |
| 关系描述 | ❌ | ✅ |
| 关系属性访问 | ❌ | ✅ |
| 关系统计报告 | ❌ | ✅ |
| 关系属性清理 | ❌ | ✅ |

### 代码结构

```python
# 实体模板（6种）
ENTITY_TEMPLATES = {
    "JOB": "...",
    "APPLICATION": "...",
    ...
}

# 关系模板（7种）
RELATIONSHIP_TEMPLATES = {
    ("APPLICATION", "JOB"): "...",
    ("JOB", "FILE"): "...",
    ...
}

# 生成流程
1. generate_entity_description()      # 实体描述
2. generate_relationship_description() # 关系描述（可访问实体属性）
3. clean_entity()                      # 清理实体
4. clean_relationship()                # 清理关系
```

## 🚀 使用示例

### 命令行

```bash
# 基本用法
python experiments/scripts/generate_descriptions_v3.py \
  input.json output.json

# 使用默认输出路径
python experiments/scripts/generate_descriptions_v3.py input.json
# 输出: input_with_descriptions.json
```

### 输出示例

```json
{
  "entities": [
    {
      "entity_name": "Job_3122490",
      "entity_type": "JOB",
      "description": "This JOB is a single HPC job...",
      "source_id": "darshan-logs",
      "file_path": "..."
    }
  ],
  "relationships": [
    {
      "src_id": "App_4068766220",
      "tgt_id": "Job_3122490",
      "description": "This relationship indicates that job Job_3122490 runs the application...",
      "keywords": "application job executable",
      "weight": 1.0,
      "source_id": "darshan-logs",
      "file_path": "..."
    }
  ]
}
```

## 📝 待改进

### 1. 缺失的数据字段

需要在 KG builder 中添加：
- `nnodes` (Job)
- `operation_types` (关系，可从 record 推断)
- `io_start_time`, `io_end_time` (关系，从 record 获取)

### 2. 模板优化

- 为 `is_shared=N/A` 的情况提供更好的描述
- 为没有写操作的 record 优化描述（避免过多 N/A）

### 3. 关系类型扩展

如果有新的边类型（如 File→FileSystem），需要添加对应模板

## ✨ 特色功能

### 自动属性合并

关系描述生成时自动合并：
```python
merged = dict(relationship)  # 关系属性
merged.update(src_entity)    # 源实体属性
merged.update(tgt_entity)    # 目标实体属性
```

这允许模板引用任何相关属性！

### 智能统计报告

5 个统计类别全面分析：
1. 实体模板占位符使用情况
2. 关系模板占位符使用情况
3. 实体 JSON 未使用属性
4. 关系 JSON 未使用属性
5. 总体统计汇总

### 类型安全的模板匹配

关系模板基于 `(src_type, tgt_type)` 元组匹配，确保类型安全：

```python
template_key = (src_type, tgt_type)  # 如 ("JOB", "MODULE")
if template_key in RELATIONSHIP_TEMPLATES:
    template = RELATIONSHIP_TEMPLATES[template_key]
```

## 🎓 学到的经验

1. **先生成后清理**: 必须先生成描述，再清理属性，否则模板无法访问原始数据
2. **实体查找表**: 使用 `entities_by_name` 字典加速关系处理
3. **属性合并顺序**: relationship → src_entity → tgt_entity，确保关系属性优先
4. **NA 值处理**: 统一的 `get_value_or_na()` 函数处理所有缺失值

## 🔧 维护指南

### 添加新实体类型

1. 在 `ENTITY_TEMPLATES` 中添加模板
2. 在 `KEEP_ENTITY_ATTRIBUTES` 中定义保留字段
3. 运行测试查看统计报告

### 添加新关系类型

1. 识别 `(src_type, tgt_type)` 组合
2. 在 `RELATIONSHIP_TEMPLATES` 中添加模板
3. 测试并检查未匹配属性

### 调试技巧

- 使用统计报告识别缺失属性
- 检查 `track_usage["placeholders"]` 了解使用情况
- 对比输入输出 JSON 验证清理逻辑
