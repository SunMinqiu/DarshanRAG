# Description Generator V3 - 快速开始

## 一行命令

```bash
# 处理单个文件
python experiments/scripts/generate_descriptions_v3.py input.json output.json

# 处理整个目录（保留文件夹结构）
python experiments/scripts/generate_descriptions_v3.py input_dir/ output_dir/
```

## 它做什么？

为 Darshan 知识图谱的**实体**和**关系**自动生成描述文本。

### 输入

```json
{
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
      ...
    }
  ]
}
```

### 输出

```json
{
  "entities": [
    {
      "entity_name": "Job_3122490",
      "entity_type": "JOB",
      "description": "This JOB is a single HPC job, describing when it ran...",
      "source_id": "...",
      "file_path": "..."
    }
  ],
  "relationships": [
    {
      "src_id": "App_4068766220",
      "tgt_id": "Job_3122490",
      "description": "This relationship indicates that job Job_3122490 runs...",
      "keywords": "...",
      "weight": 1.0,
      "source_id": "...",
      "file_path": "..."
    }
  ]
}
```

## 支持的类型

### 实体 (6种)
- APPLICATION
- JOB
- MODULE
- RECORD
- FILE
- FILESYSTEM

### 关系 (8种)
- Application → Job
- Job → Module
- Job → FileSystem
- Module → Record
- Record → File
- Record → Module
- File → FileSystem
- Job → File

## 输出说明

脚本会：
1. ✅ 为每个实体生成 `description` 字段
2. ✅ 为每个关系生成 `description` 字段
3. ✅ 移除不需要的额外属性
4. ✅ 输出使用统计报告

## 统计报告

运行后会看到：

```
【1】实体模板中永远没有匹配到的属性（总是 N/A）
【2】关系模板中永远没有匹配到的属性（总是 N/A）
【3】实体 JSON 中永远没有用到的属性
【4】关系 JSON 中永远没有用到的属性
【5】总体统计
```

这些统计帮助你：
- 发现缺失的数据字段
- 识别不需要的模板占位符
- 了解数据完整性

## 完整示例

### 单个文件处理

```bash
# 处理 Darshan KG 输出
python experiments/scripts/generate_descriptions_v3.py \
  experiments/output_kg_v2.json \
  experiments/output_kg_with_desc.json

# 输出
# Reading experiments/output_kg_v2.json...
# Processing 68 entities and 99 relationships...
# Writing to experiments/output_kg_with_desc.json...
# Done!
#
# [统计报告...]
```

### 目录批量处理

```bash
# 处理整个目录，保留文件夹结构
python experiments/scripts/generate_descriptions_v3.py \
  experiments/kg_outputs/ \
  experiments/kg_outputs_with_descriptions/

# 输出
# Found 15 JSON files to process
# [1/15] Processing: experiment1/job_123.json
#   → Output: experiment1/job_123_with_descriptions.json
# [2/15] Processing: experiment1/job_456.json
#   → Output: experiment1/job_456_with_descriptions.json
# ...
# Done processing 15 files!
```

**目录模式说明**:
- 所有子文件夹结构会原样保留在输出目录中
- 每个 JSON 文件输出为 `{原文件名}_with_descriptions.json`
- 非 JSON 文件会被自动忽略

## 验证结果

```bash
# 检查是否所有实体和关系都有描述
python -c "
import json
with open('output.json') as f:
    kg = json.load(f)

entities_with_desc = sum(1 for e in kg['entities'] if e.get('description'))
rels_with_desc = sum(1 for r in kg['relationships'] if r.get('description'))

print(f'实体: {entities_with_desc}/{len(kg[\"entities\"])}')
print(f'关系: {rels_with_desc}/{len(kg[\"relationships\"])}')
"
```

## 常见问题

**Q: 为什么某些描述中有 "N/A"？**

A: 模板中引用的属性在数据中缺失。查看统计报告【1】和【2】了解哪些属性缺失。

**Q: 如何修改描述模板？**

A: 编辑 `generate_descriptions_v3.py` 中的：
- `ENTITY_TEMPLATES` (实体模板)
- `RELATIONSHIP_TEMPLATES` (关系模板)

**Q: 如何保留更多属性？**

A: 修改：
- `KEEP_ENTITY_ATTRIBUTES` (实体保留字段)
- `KEEP_RELATIONSHIP_ATTRIBUTES` (关系保留字段)

## 更多信息

- 详细文档: [README_v3.md](README_v3.md)
- 功能总结: [SUMMARY_v3.md](SUMMARY_v3.md)
- 完成状态: [COMPLETION_V3.md](COMPLETION_V3.md)
