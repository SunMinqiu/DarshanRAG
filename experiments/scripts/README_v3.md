# Description Generator V3

自动为 Darshan KG 的实体和关系生成描述，基于预定义模板填充属性。

## 功能

1. **实体描述生成**: 为 6 种实体类型生成描述
   - APPLICATION
   - JOB
   - MODULE
   - RECORD
   - FILE
   - FILESYSTEM

2. **关系描述生成**: 为 7 种关系类型生成描述
   - Application → Job (HAS_JOB)
   - Job → File (ON_FILE)
   - Job → FileSystem (TOUCH_FILESYSTEM)
   - Job → Module (HAS_MODULE)
   - Module → Record (HAS_RECORD)
   - Record → File (ON_FILE)
   - Record → Module (执行上下文)

3. **属性清理**: 移除不需要的属性，只保留标准字段

4. **使用统计**: 报告哪些模板占位符永远没有匹配到值

## 使用方法

### 基本用法

```bash
python generate_descriptions_v3.py input.json output.json
```

### 示例

```bash
# 为 Darshan KG 生成描述
python experiments/scripts/generate_descriptions_v3.py \
  experiments/test_v2.1_output.json \
  experiments/test_with_descriptions.json
```

### 默认输出路径

如果不指定输出路径，将自动生成：

```bash
python generate_descriptions_v3.py input.json
# 输出: input_with_descriptions.json
```

### 目录处理

脚本支持处理整个目录树中的所有 JSON 文件，同时保留原始目录结构：

```bash
# 处理目录（保留目录结构）
python generate_descriptions_v3.py input_dir/ output_dir/

# 或者让脚本自动生成输出目录名
python generate_descriptions_v3.py input_dir/
# 输出目录: input_dir_with_descriptions/
```

**目录处理特性**:
- ✅ 递归查找所有 `.json` 文件
- ✅ 保留父子文件夹结构
- ✅ 每个 JSON 文件命名为 `{原文件名}_with_descriptions.json`
- ✅ 自动创建必要的子目录
- ✅ 显示处理进度（如 `[3/10] Processing: subfolder/file.json`）

**示例**:
```
输入目录结构:
kg_outputs/
├── experiment1/
│   ├── job_123.json
│   └── job_456.json
└── experiment2/
    └── job_789.json

输出目录结构:
kg_outputs_with_descriptions/
├── experiment1/
│   ├── job_123_with_descriptions.json
│   └── job_456_with_descriptions.json
└── experiment2/
    └── job_789_with_descriptions.json
```

## 输入格式

JSON 文件必须包含 `entities` 和 `relationships` 数组：

```json
{
  "chunks": [],
  "entities": [
    {
      "entity_name": "Job_3122490",
      "entity_type": "JOB",
      "job_id": 3122490,
      "uid": 1449515727,
      ...
    }
  ],
  "relationships": [
    {
      "src_id": "App_4068766220",
      "tgt_id": "Job_3122490",
      "keywords": "application job executable",
      "weight": 1.0,
      ...
    }
  ]
}
```

## 输出格式

生成的 JSON 保持相同结构，但：

1. **实体**: 添加 `description` 字段，移除额外属性
2. **关系**: 添加 `description` 字段，移除额外属性

### 实体输出示例

```json
{
  "entity_name": "Job_3122490",
  "entity_type": "JOB",
  "description": "This JOB is a single HPC job, describing when it ran...",
  "source_id": "darshan-logs",
  "file_path": "..."
}
```

### 关系输出示例

```json
{
  "src_id": "App_4068766220",
  "tgt_id": "Job_3122490",
  "description": "This relationship indicates that job Job_3122490 runs the application...",
  "keywords": "application job executable",
  "weight": 1.0,
  "source_id": "darshan-logs",
  "file_path": "..."
}
```

## 使用统计报告

脚本会输出详细的统计报告：

### 【1】实体模板中永远没有匹配到的属性

显示哪些模板占位符总是为 N/A（可能需要从 JSON 中删除这些字段，或添加到模板中）

```
APPLICATION:
  - nprocs (缺失1次)

JOB:
  - nnodes (缺失1次)
```

### 【2】关系模板中永远没有匹配到的属性

显示关系模板中总是为 N/A 的占位符

```
MODULE→RECORD:
  - operation_types (缺失40次)
```

### 【3】实体 JSON 中永远没有用到的属性

显示 JSON 中有但模板中没用到的属性（这些属性在清理后会被移除）

```
RECORD (73个未使用属性):
  - active_bins
  - heatmap_bin_width
  - meta_ops
  ...
```

### 【4】关系 JSON 中永远没有用到的属性

显示关系 JSON 中未使用的属性

### 【5】总体统计

汇总每种实体/关系类型的占位符使用情况

```
JOB:
  模板占位符总数: 7
  - 总是有值: 5
  - 有时有值: 0
  - 从不有值: 2
```

## 模板定义

### 实体模板位置

在 `ENTITY_TEMPLATES` 字典中定义（脚本第 13-93 行）

### 关系模板位置

在 `RELATIONSHIP_TEMPLATES` 字典中定义（脚本第 96-109 行）

### 添加新模板

1. 在 `ENTITY_TEMPLATES` 或 `RELATIONSHIP_TEMPLATES` 中添加新模板
2. 使用 `{placeholder}` 语法引用属性
3. 脚本会自动替换占位符并跟踪使用情况

### 模板占位符规则

- 占位符格式: `{attribute_name}`
- 自动从实体/关系属性中获取值
- 如果属性不存在或为 `null`，替换为 "N/A"
- 对于关系模板，可以访问 src 和 tgt 实体的属性

## 关系模板特殊处理

关系描述生成时，模板可以访问：

1. **关系自身属性**: `src_id`, `tgt_id`, `keywords`, `weight` 等
2. **源实体属性**: src 实体的所有属性
3. **目标实体属性**: tgt 实体的所有属性

这允许模板引用如 `{bytes_read}` 等实体属性来丰富关系描述。

## 属性保留规则

### 实体保留字段

所有实体类型只保留：
- `entity_name`
- `entity_type`
- `description`
- `source_id`
- `file_path`

### 关系保留字段

所有关系只保留：
- `src_id`
- `tgt_id`
- `description`
- `keywords`
- `weight`
- `source_id`
- `file_path`

## 注意事项

1. **处理顺序**: 先生成描述，再清理属性（确保模板可以访问所有原始属性）

2. **NA 值处理**: 模板中引用的属性如果为 `null` 或缺失，会被替换为 "N/A"

3. **关系类型匹配**: 关系模板基于 `(src_type, tgt_type)` 匹配，如果没有对应模板，描述留空

4. **统计输出**: 使用统计帮助识别：
   - 需要从数据中添加的字段
   - 需要从模板中移除的占位符
   - 未使用但保留在 JSON 中的属性

## 扩展

### 添加新的实体类型

1. 在 `ENTITY_TEMPLATES` 中添加模板
2. 在 `KEEP_ENTITY_ATTRIBUTES` 中定义保留字段

### 添加新的关系类型

1. 在 `RELATIONSHIP_TEMPLATES` 中添加 `(src_type, tgt_type)` 键值对
2. 关系保留字段全局定义，无需修改

### 自定义 NA 默认值

修改 `get_value_or_na()` 函数的 `default` 参数

## 示例输出

### 完整处理流程

```bash
$ python generate_descriptions_v3.py input.json output.json

Reading input.json...
Processing 68 entities and 99 relationships...
  Processed 68 entities...
  Processed 99 relationships...
Writing to output.json...
Done!

======================================================================
使用统计报告
======================================================================

【1】实体模板中永远没有匹配到的属性（总是 N/A）:
----------------------------------------------------------------------
  JOB:
    - nnodes (缺失1次)

【2】关系模板中永远没有匹配到的属性（总是 N/A）:
----------------------------------------------------------------------
  MODULE→RECORD:
    - operation_types (缺失40次)

...
```

## 故障排除

### 错误: JSON file must contain 'entities' and 'relationships' keys

输入文件格式不正确，确保包含 `entities` 和 `relationships` 数组。

### 某些关系没有描述

检查 `RELATIONSHIP_TEMPLATES` 是否定义了对应的 `(src_type, tgt_type)` 模板。

### 模板占位符总是显示 N/A

检查 JSON 数据中是否真的包含该属性，或属性名是否拼写正确。
