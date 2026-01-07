#!/usr/bin/env python3
"""分批加载超大知识图谱的脚本。
对于超大KG（>100万实体+关系），可以分批加载以避免内存和API限制问题。
"""

import os
import sys
import json
import argparse
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import load_kg functionality
import importlib.util
load_kg_path = Path(__file__).parent / "load_kg.py"
spec = importlib.util.spec_from_file_location("load_kg_module", load_kg_path)
load_kg_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load_kg_module)
load_kg_async = load_kg_module.load_kg_async


def split_kg(kg_path: str, batch_size: int = 50000, output_dir: str = "./experiments/kg_batches"):
    """将大KG分割成多个批次。
    
    Args:
        kg_path: 原始KG文件路径
        batch_size: 每批的实体数量（关系会按比例分配）
        output_dir: 输出目录
    """
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Loading KG from {kg_path}...")
    with open(kg_path, 'r', encoding='utf-8') as f:
        kg = json.load(f)
    
    entities = kg.get('entities', [])
    relationships = kg.get('relationships', [])
    chunks = kg.get('chunks', [])
    
    total_entities = len(entities)
    total_batches = (total_entities + batch_size - 1) // batch_size
    
    print(f"Total entities: {total_entities:,}")
    print(f"Will create {total_batches} batches of ~{batch_size:,} entities each")
    
    # Create entity ID to index mapping
    entity_names = {e['entity_name'] for e in entities}
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min((batch_idx + 1) * batch_size, total_entities)
        
        batch_entities = entities[start_idx:end_idx]
        batch_entity_names = {e['entity_name'] for e in batch_entities}
        
        # Filter relationships that involve entities in this batch
        batch_relationships = [
            r for r in relationships
            if r['src_id'] in batch_entity_names and r['tgt_id'] in batch_entity_names
        ]
        
        # Filter chunks (optional, can be shared across batches)
        batch_chunks = chunks  # 或者根据source_id过滤
        
        batch_kg = {
            'entities': batch_entities,
            'relationships': batch_relationships,
            'chunks': batch_chunks if batch_idx == 0 else [],  # 只在第一批包含chunks
        }
        
        output_path = os.path.join(output_dir, f"kg_batch_{batch_idx+1:03d}.json")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(batch_kg, f, ensure_ascii=False, indent=2)
        
        print(f"Batch {batch_idx+1}/{total_batches}: {len(batch_entities):,} entities, "
              f"{len(batch_relationships):,} relationships -> {output_path}")
    
    print(f"\n✅ Split complete! Created {total_batches} batch files in {output_dir}")
    return total_batches


async def load_batches(batch_dir: str, working_dir: str, **kwargs):
    """依次加载所有批次到同一个LightRAG实例。
    
    Args:
        batch_dir: 批次文件目录
        working_dir: LightRAG工作目录
        **kwargs: 传递给load_kg的其他参数
    """
    batch_files = sorted([f for f in os.listdir(batch_dir) if f.endswith('.json')])
    
    print(f"Found {len(batch_files)} batch files")
    print("Note: All batches will be loaded into the same LightRAG instance\n")
    
    for idx, batch_file in enumerate(batch_files, 1):
        batch_path = os.path.join(batch_dir, batch_file)
        print(f"\n{'='*60}")
        print(f"Loading batch {idx}/{len(batch_files)}: {batch_file}")
        print('='*60)
        
        await load_kg_async(
            kg_path=batch_path,
            working_dir=working_dir,
            **kwargs
        )
        
        print(f"✅ Batch {idx}/{len(batch_files)} loaded successfully\n")
    
    print(f"\n{'='*60}")
    print("✅ All batches loaded successfully!")
    print('='*60)


def main():
    parser = argparse.ArgumentParser(description="分批加载超大知识图谱")
    parser.add_argument("kg_path", help="原始KG文件路径")
    parser.add_argument("--batch-size", type=int, default=50000, 
                       help="每批的实体数量（默认50000）")
    parser.add_argument("--split-only", action="store_true",
                       help="只分割KG，不加载")
    parser.add_argument("--load-batches", type=str,
                       help="加载已分割的批次目录")
    parser.add_argument("--working-dir", default="./experiments/rag_storage",
                       help="LightRAG工作目录")
    parser.add_argument("--workspace", default="", help="工作空间名称")
    parser.add_argument("--gen-model", default="gpt-4o", help="生成模型（加载时不需要）")
    parser.add_argument("--embed-model", default="sentence-transformers/all-MiniLM-L6-v2", 
                       help="嵌入模型（默认使用本地模型）")
    parser.add_argument("--use-local-embedding", action="store_true", default=True,
                       help="使用本地embedding模型（默认：True，不需要API）")
    parser.add_argument("--use-openai-embedding", action="store_true", default=False,
                       help="使用OpenAI API进行embedding（需要API key）")
    parser.add_argument("--api-key", help="OpenAI API key（仅在--use-openai-embedding时需要）")
    parser.add_argument("--temperature", type=float, default=0.1, help="温度（加载时不需要）")
    
    args = parser.parse_args()
    
    if args.load_batches:
        # 加载已分割的批次
        use_local = args.use_local_embedding and not args.use_openai_embedding
        asyncio.run(load_batches(
            batch_dir=args.load_batches,
            working_dir=args.working_dir,
            workspace=args.workspace,
            gen_model=args.gen_model,
            embed_model=args.embed_model,
            use_local_embedding=use_local,
            api_key=args.api_key,
            temperature=args.temperature,
        ))
    else:
        # 分割KG
        batch_dir = "./experiments/kg_batches"
        split_kg(args.kg_path, args.batch_size, batch_dir)
        
        if not args.split_only:
            # 自动加载
            response = input("\n是否立即加载所有批次? (y/n): ")
            if response.lower() == 'y':
                use_local = args.use_local_embedding and not args.use_openai_embedding
                asyncio.run(load_batches(
                    batch_dir=batch_dir,
                    working_dir=args.working_dir,
                    workspace=args.workspace,
                    gen_model=args.gen_model,
                    embed_model=args.embed_model,
                    use_local_embedding=use_local,
                    api_key=args.api_key,
                    temperature=args.temperature,
                ))


if __name__ == "__main__":
    main()

