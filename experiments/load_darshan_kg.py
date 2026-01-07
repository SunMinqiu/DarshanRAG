#!/usr/bin/env python3
"""
Example script to load Darshan KG into LightRAG

This script demonstrates:
1. Building KG from Darshan logs using build_darshan_kg.py
2. Loading the custom KG into LightRAG
3. Querying the knowledge graph

Usage:
    python load_darshan_kg.py --kg_path darshan_kg.json --working_dir ./lightrag_storage
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

# Add parent directory to path to import lightrag
sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed
from lightrag.utils import setup_logger


async def load_kg_into_lightrag(kg_path: str, working_dir: str):
    """Load Darshan KG into LightRAG."""

    # Setup logger
    setup_logger("lightrag", level="INFO")

    print(f"📂 Loading KG from: {kg_path}")

    # Load KG from JSON
    with open(kg_path, 'r', encoding='utf-8') as f:
        custom_kg = json.load(f)

    print(f"📊 KG Statistics:")
    print(f"   - Chunks: {len(custom_kg.get('chunks', []))}")
    print(f"   - Entities: {len(custom_kg.get('entities', []))}")
    print(f"   - Relationships: {len(custom_kg.get('relationships', []))}")

    # Initialize LightRAG
    print(f"\n🚀 Initializing LightRAG (working_dir: {working_dir})...")

    # Create working directory if it doesn't exist
    os.makedirs(working_dir, exist_ok=True)

    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete,
    )

    # IMPORTANT: Initialize storage backends
    await rag.initialize_storages()

    print("✅ LightRAG initialized")

    # Insert custom KG
    print("\n📥 Inserting KG into LightRAG...")
    print("⚠️  This will generate embeddings for all entities and relationships.")
    print("⏳ This may take a while depending on the KG size...\n")

    try:
        await rag.ainsert_custom_kg(custom_kg)
        print("✅ KG inserted successfully!")
    except Exception as e:
        print(f"❌ Error inserting KG: {e}")
        raise

    return rag


async def query_examples(rag: LightRAG):
    """Run example queries on the Darshan KG."""

    print("\n" + "="*70)
    print("🔍 Running Example Queries")
    print("="*70)

    queries = [
        {
            "question": "What jobs are in the knowledge graph?",
            "mode": "local"
        },
        {
            "question": "Which files were accessed most frequently across all jobs?",
            "mode": "global"
        },
        {
            "question": "What are the I/O patterns for checkpoint files?",
            "mode": "hybrid"
        },
        {
            "question": "Which jobs had shared file access?",
            "mode": "local"
        },
        {
            "question": "What is the relationship between jobs and modules?",
            "mode": "mix"
        }
    ]

    for i, query_info in enumerate(queries, 1):
        print(f"\n--- Query {i}/{len(queries)} ---")
        print(f"Q: {query_info['question']}")
        print(f"Mode: {query_info['mode']}")
        print(f"{'─'*70}")

        try:
            result = await rag.aquery(
                query_info['question'],
                param=QueryParam(mode=query_info['mode'])
            )

            print(f"A: {result}\n")
        except Exception as e:
            print(f"Error: {e}\n")


async def main():
    parser = argparse.ArgumentParser(
        description='Load Darshan KG into LightRAG and run queries',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load KG and initialize LightRAG
  python load_darshan_kg.py --kg_path darshan_kg.json

  # Specify custom working directory
  python load_darshan_kg.py --kg_path darshan_kg.json --working_dir ./my_rag_storage

  # Skip example queries
  python load_darshan_kg.py --kg_path darshan_kg.json --no-queries
        """
    )

    parser.add_argument(
        '--kg_path',
        type=str,
        required=True,
        help='Path to the Darshan KG JSON file (output from build_darshan_kg.py)'
    )

    parser.add_argument(
        '--working_dir',
        type=str,
        default='./lightrag_darshan_storage',
        help='LightRAG working directory (default: ./lightrag_darshan_storage)'
    )

    parser.add_argument(
        '--no-queries',
        action='store_true',
        help='Skip running example queries after loading KG'
    )

    args = parser.parse_args()

    # Check if KG file exists
    if not os.path.exists(args.kg_path):
        print(f"❌ Error: KG file not found: {args.kg_path}")
        print("\n💡 First, build the KG using:")
        print(f"   python build_darshan_kg.py --input_path /path/to/logs --output_path {args.kg_path}")
        return

    # Check for OpenAI API key
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("\n💡 Set your API key:")
        print("   export OPENAI_API_KEY='sk-...'")
        return

    # Load KG into LightRAG
    rag = await load_kg_into_lightrag(args.kg_path, args.working_dir)

    # Run example queries (unless --no-queries flag is set)
    if not args.no_queries:
        await query_examples(rag)
    else:
        print("\n✅ KG loaded. Skipping example queries.")

    # Finalize
    print("\n" + "="*70)
    print("✅ Done!")
    print("="*70)
    print(f"\n📂 LightRAG storage location: {args.working_dir}")
    print("\n💡 You can now query the KG programmatically:")
    print("""
    from lightrag import LightRAG, QueryParam
    rag = LightRAG(working_dir='./lightrag_darshan_storage')
    await rag.initialize_storages()
    result = await rag.aquery("Your question here", param=QueryParam(mode="hybrid"))
    """)

    # Finalize storage
    await rag.finalize_storages()


if __name__ == '__main__':
    asyncio.run(main())
