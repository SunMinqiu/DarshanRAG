# Darshan KG Builder V2 - 完成总结

## ✅ 已完成功能

### 1. 核心架构（V2）

**6种节点类型**：
- Application: 可执行文件
- Job: 作业实例
- Module: I/O 模块 (HEATMAP, POSIX, STDIO, MPIIO)
- Record: I/O 记录（**= incident，最小可检索单元**）
- File: 文件
- FileSystem: 文件系统

**6种边关系**：
- Application → Job (HAS_JOB)
- Job → Module (HAS_MODULE)
- Module → Record (HAS_RECORD)
- Record → File (ON_FILE)
- File → FileSystem (ON_FILESYSTEM)
- Job → FileSystem (TOUCH_FILESYSTEM)

### 2. 完整支持 v2.4 格式

✓ 解析 JOB 级聚合指标
✓ 解析 MODULE 级聚合和性能指标
✓ 解析所有 SIGNAL_* 派生指标（70+ 个）
✓ 完整支持所有新增时间相关 signals：
  - 时间戳: `*_start_ts`, `*_end_ts` (6个)
  - 时长: `*_time` (13个)
  - 跨度: `*_span` (5个)
  - 忙碌比例: `*_busy_frac`, `*_fraction` (5个)

### 3. LightRAG 格式兼容

✓ 标准 JSON 结构: `{chunks, entities, relationships}`
✓ 实体必需字段: `entity_name, entity_type, description, source_id, file_path`
✓ 关系必需字段: `src_id, tgt_id, description, keywords, weight, source_id, file_path`
✓ Description 和 chunks 按要求留空（待模板抽取）
✓ 所有自定义属性作为额外字段添加

### 4. 测试结果

**输入**: `Darshan_log_example_signals_v2.4.txt`

**输出统计**:
- 175 个实体
  - 1 Application
  - 1 Job
  - 3 Modules (HEATMAP, POSIX, STDIO)
  - 120 Records
  - 22 Files
  - 28 FileSystems
- 270 条关系

**验证**: ✅ 所有格式验证通过

## 📋 使用方法

```bash
python experiments/darshan_kg_builder_v2.py \
  -i data/examples/Darshan_log_example_signals_v2.4.txt \
  -o experiments/output_kg_v2.json
```

## 📚 文档

- **代码**: `/users/Minqiu/DarshanRAG/experiments/darshan_kg_builder_v2.py`
- **输出示例**: `/users/Minqiu/DarshanRAG/experiments/output_kg_v2.json`
- **README**: `/users/Minqiu/DarshanRAG/experiments/README_KG_BUILDER_V2.md`

## 🎯 设计要点

1. **Record = Incident**：每个 Darshan record 是一个独立的 incident 实体
2. **Signals = Attributes**：所有 SIGNAL_* 值作为 Record 实体的属性，不创建独立节点
3. **Graph = Comparability**：图边连接表示可比性（相同 app/fs/module），而非语义相似度
4. **Explainable**：支持 incident 级检索、下游计算和可解释分析

## ⏭️ 后续开发

- [ ] 模板抽取：自动生成 description 和 chunks
- [ ] Job I/O Summary：基于 signals 生成自然语言摘要
- [ ] Incident 聚类：基于访问模式相似性连接 records
