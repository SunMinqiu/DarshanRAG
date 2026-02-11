#!/bin/bash
# CPU 优化版本的 embedding 脚本
# 适用于没有 GPU 的环境

set -e

echo "=========================================="
echo "CPU-Optimized Embedding"
echo "=========================================="
echo ""

# 配置
KG_PATH="${1:-/users/Minqiu/DarshanRAG/data/examples/Darshan_log_example_kg_with_chunks.json}"
OUTPUT_DIR="${2:-./embeddings_cpu}"
MODEL="${3:-sentence-transformers/all-MiniLM-L6-v2}"  # 默认使用轻量模型

echo "Configuration:"
echo "  KG: $KG_PATH"
echo "  Output: $OUTPUT_DIR"
echo "  Model: $MODEL"
echo ""

# 检查 KG 文件
if [ ! -f "$KG_PATH" ]; then
    echo "Error: KG file not found at $KG_PATH"
    exit 1
fi

# 清理旧输出
rm -rf "$OUTPUT_DIR"

# CPU 优化参数
BATCH_SIZE=4          # 小 batch size 避免内存问题
MAX_LENGTH=256        # BERT 模型最大支持 512，使用 256 加速处理

echo "CPU Optimization Settings:"
echo "  - Batch size: $BATCH_SIZE"
echo "  - Max length: $MAX_LENGTH"
echo "  - Using lightweight model for faster processing"
echo ""

# 运行 embedding
echo "Starting embedding process..."
echo ""

python3 /users/Minqiu/DarshanRAG/experiments/scripts/embed_kg_local.py \
    --kg "$KG_PATH" \
    --output "$OUTPUT_DIR" \
    --model "$MODEL" \
    --batch-size $BATCH_SIZE \
    --max-length $MAX_LENGTH

echo ""
echo "=========================================="
echo "✓ Embedding completed!"
echo "=========================================="
echo ""
echo "Output saved to: $OUTPUT_DIR"
echo ""

# 显示统计
echo "Verifying embeddings..."
python3 /users/Minqiu/DarshanRAG/experiments/scripts/test_embeddings.py \
    --embeddings "$OUTPUT_DIR"

echo ""
echo "=========================================="
echo "Usage examples:"
echo "=========================================="
echo ""
echo "# 使用默认设置"
echo "./embed_kg_cpu_optimized.sh"
echo ""
echo "# 指定 KG 和输出目录"
echo "./embed_kg_cpu_optimized.sh /path/to/kg.json ./my_output"
echo ""
echo "# 指定模型"
echo "./embed_kg_cpu_optimized.sh /path/to/kg.json ./output sentence-transformers/paraphrase-MiniLM-L3-v2"
echo ""
