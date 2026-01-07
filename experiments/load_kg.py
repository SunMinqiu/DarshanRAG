#!/usr/bin/env python3
"""Simple script to load custom knowledge graph into LightRAG.
After loading, you can use WebUI or interactive query script to query the KG.
"""

import os
import sys
import asyncio
import argparse
import json
import glob
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG
from lightrag.llm.openai import openai_embed, openai_complete_if_cache
from lightrag.llm.hf import hf_embed
from lightrag.utils import EmbeddingFunc
from transformers import AutoModel, AutoTokenizer
import numpy as np


async def load_kg_async(
    kg_path: str,
    working_dir: str = "./experiments/rag_storage",
    workspace: str = "",
    gen_model: str = "gpt-4o",
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    use_local_embedding: bool = True,
    api_key: str = None,
    base_url: str = None,
    temperature: float = 0.1,
    synthetic_chunks: bool = False,
):
    """Load custom knowledge graph into LightRAG.
    
    Args:
        kg_path: Path to custom_kg JSON file
        working_dir: Working directory for LightRAG storage
        workspace: Workspace name for data isolation
        gen_model: Generation model name (not used for loading, only for future queries)
        embed_model: Embedding model name (HuggingFace model name if use_local_embedding=True)
        use_local_embedding: Use local sentence-transformers model instead of OpenAI API
        api_key: OpenAI API key (only needed if use_local_embedding=False)
        base_url: OpenAI API base URL (only needed if use_local_embedding=False)
        temperature: Generation temperature (not used for loading)
        synthetic_chunks: Whether to create synthetic chunks if none provided
    """
    print(f"Loading knowledge graph from: {kg_path}")
    print(f"Working directory: {working_dir}")
    print(f"Workspace: {workspace or '(default)'}")
    print(f"Embedding model: {embed_model}")
    print(f"Use local embedding: {use_local_embedding}")
    if use_local_embedding:
        print("✅ Using local embedding model (offline, no API required)")
    else:
        print("⚠️  Using OpenAI API for embeddings")
        # Get API key only if using OpenAI
        if api_key is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY env var or pass --api-key")
        
        if base_url is None:
            base_url = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    
    # Load KG
    with open(kg_path, 'r', encoding='utf-8') as f:
        kg = json.load(f)
    
    # Validate
    if "entities" not in kg or "relationships" not in kg:
        raise ValueError("KG must contain 'entities' and 'relationships' keys")
    
    has_chunks = "chunks" in kg and len(kg.get("chunks", [])) > 0
    print(f"KG contains: {len(kg.get('entities', []))} entities, {len(kg.get('relationships', []))} relationships, {len(kg.get('chunks', []))} chunks")
    
    if not has_chunks and synthetic_chunks:
        print("Creating synthetic chunks...")
        from utils_experiment import create_synthetic_chunks
        kg = create_synthetic_chunks(kg)
    
    # Setup embedding function
    if use_local_embedding:
        # Use local sentence-transformers model
        print(f"\n正在加载本地embedding模型: {embed_model}")
        print("首次使用时会自动下载模型，请耐心等待...")
        
        # Load model once and reuse
        tokenizer = AutoTokenizer.from_pretrained(embed_model)
        model = AutoModel.from_pretrained(embed_model)
        
        # Get embedding dimension from model config
        try:
            embedding_dim = model.config.hidden_size
        except:
            # Fallback dimensions for common models
            if "all-MiniLM-L6-v2" in embed_model:
                embedding_dim = 384
            elif "all-mpnet-base-v2" in embed_model:
                embedding_dim = 768
            elif "all-MiniLM-L12-v2" in embed_model:
                embedding_dim = 384
            else:
                embedding_dim = 384  # default
                print(f"⚠️  无法自动检测embedding维度，使用默认值: {embedding_dim}")
        
        async def embedding_func_impl(texts):
            return await hf_embed(texts, tokenizer=tokenizer, embed_model=model)
        
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            max_token_size=512,  # sentence-transformers models typically use 512
            func=embedding_func_impl
        )
        print(f"✅ 模型加载完成，embedding维度: {embedding_dim}")
    else:
        # Use OpenAI API
        if "3-large" in embed_model:
            embedding_dim = 3072
        elif "3-small" in embed_model:
            embedding_dim = 1536
        else:
            embedding_dim = 1536
        
        async def embedding_func_impl(texts):
            return await openai_embed.func(
                texts,
                model=embed_model,
                api_key=api_key,
                base_url=base_url,
            )
        
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            max_token_size=8192,
            func=embedding_func_impl
        )
    
    # Provide a dummy LLM function for loading KG
    # This won't be called during loading, but LightRAG requires it to be set
    async def dummy_llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        """Dummy LLM function - not used during KG loading, only needed for initialization."""
        raise NotImplementedError(
            "LLM function is not configured. This is normal during KG loading. "
            "You need to set llm_model_func when creating LightRAG for querying."
        )
    
    # Check for corrupted storage files before initialization
    # This can happen if a previous run was interrupted
    storage_files = glob.glob(os.path.join(working_dir, "*.json"))
    for storage_file in storage_files:
        if os.path.exists(storage_file):
            try:
                with open(storage_file, 'r', encoding='utf-8') as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                print(f"⚠️  发现损坏的存储文件: {storage_file}")
                print(f"   错误: {e}")
                backup_file = f"{storage_file}.backup"
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(storage_file, backup_file)
                print(f"   已备份到: {backup_file}，将创建新文件")
    
    # Initialize LightRAG with optimized settings for large KG
    print("Initializing LightRAG...")
    if use_local_embedding:
        print("Note: Using local embedding model (offline, fast processing)...")
    else:
        print("Note: Large KG detected. Using optimized settings for faster processing...")
    
    # Calculate total embeddings needed
    num_entities = len(kg.get('entities', []))
    num_relations = len(kg.get('relationships', []))
    num_chunks = len(kg.get('chunks', []))
    total_embeddings = num_entities + num_relations + num_chunks
    
    print(f"\n需要生成的embeddings数量:")
    print(f"  - 实体: {num_entities:,}")
    print(f"  - 关系: {num_relations:,}")
    print(f"  - Chunks: {num_chunks:,}")
    print(f"  - 总计: {total_embeddings:,}")
    
    if use_local_embedding:
        print(f"\n✅ 使用本地模型，预计时间: 约 {total_embeddings // 10000} - {total_embeddings // 5000} 分钟 (取决于硬件)")
        # 本地模型可以更高的并发
        embedding_batch_num = 32  # 本地模型批量大小
        embedding_func_max_async = 4  # 本地模型并发数（GPU限制）
    else:
        print(f"\n预计时间: 约 {total_embeddings // 1000} - {total_embeddings // 500} 分钟 (取决于API速率限制)")
        # 对于超大KG，使用更高的并发设置
        # 注意：根据OpenAI API的速率限制调整
        embedding_batch_num = 100  # 每批处理的文本数量（默认10-32）
        embedding_func_max_async = 50  # 最大并发embedding请求（默认16，可增加到50-100）
    
    print(f"并发设置: batch_size={embedding_batch_num}, max_async={embedding_func_max_async}")
    print("开始处理...\n")
    
    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=embedding_func,
        llm_model_func=dummy_llm_func,  # Dummy function - not called during loading
        workspace=workspace,
        # 优化参数：增加并发以提高处理速度
        embedding_batch_num=embedding_batch_num,
        embedding_func_max_async=embedding_func_max_async,
    )
    
    await rag.initialize_storages()
    
    # Insert KG with progress indication
    print("Inserting knowledge graph (this will take a while for large KG)...")
    import time
    start_time = time.time()
    
    await rag.ainsert_custom_kg(kg)
    
    elapsed_time = time.time() - start_time
    
    await rag.finalize_storages()
    
    print(f"\n✅ Knowledge graph loaded successfully!")
    print(f"⏱️  总耗时: {elapsed_time/60:.1f} 分钟 ({elapsed_time:.0f} 秒)")
    print(f"\nNext steps:")
    print(f"1. Start LightRAG Server:")
    print(f"   cd {working_dir}")
    print(f"   lightrag-server --working-dir . --workspace {workspace} --port 9621")
    print(f"2. Open http://localhost:9621 in your browser")
    print(f"3. Or use interactive query script:")
    print(f"   python experiments/interactive_query.py --working-dir {working_dir} --workspace {workspace}")


def main():
    parser = argparse.ArgumentParser(description="Load custom knowledge graph into LightRAG")
    parser.add_argument("kg_path", help="Path to custom_kg JSON file")
    parser.add_argument("--working-dir", default="./experiments/rag_storage", help="Working directory for LightRAG")
    parser.add_argument("--workspace", default="", help="Workspace name for data isolation")
    parser.add_argument("--gen-model", default="gpt-4o", help="Generation model (not used for loading, only for queries)")
    parser.add_argument("--embed-model", default="sentence-transformers/all-MiniLM-L6-v2", 
                       help="Embedding model (HuggingFace model name if --use-local-embedding, otherwise OpenAI model)")
    parser.add_argument("--use-local-embedding", action="store_true", default=True,
                       help="Use local sentence-transformers model (default: True, no API required)")
    parser.add_argument("--use-openai-embedding", action="store_true", default=False,
                       help="Use OpenAI API for embeddings (requires API key)")
    parser.add_argument("--api-key", help="OpenAI API key (only needed if --use-openai-embedding)")
    parser.add_argument("--base-url", help="OpenAI API base URL (only needed if --use-openai-embedding)")
    parser.add_argument("--temperature", type=float, default=0.1, help="Generation temperature (not used for loading)")
    parser.add_argument("--synthetic-chunks", action="store_true", help="Create synthetic chunks if none provided")
    
    args = parser.parse_args()
    
    # Determine if using local embedding
    use_local = args.use_local_embedding and not args.use_openai_embedding
    
    asyncio.run(load_kg_async(
        kg_path=args.kg_path,
        working_dir=args.working_dir,
        workspace=args.workspace,
        gen_model=args.gen_model,
        embed_model=args.embed_model,
        use_local_embedding=use_local,
        api_key=args.api_key,
        base_url=args.base_url,
        temperature=args.temperature,
        synthetic_chunks=args.synthetic_chunks,
    ))


if __name__ == "__main__":
    main()
