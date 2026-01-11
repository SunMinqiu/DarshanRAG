#!/usr/bin/env python3
"""Debug script to test KG loading"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed
from lightrag.utils import setup_logger

async def debug_load():
    setup_logger("lightrag", level="DEBUG")

    # Load KG
    with open('kg_2025-1-1_fixed.json', 'r') as f:
        kg = json.load(f)

    print(f"=== KG Statistics ===")
    print(f"Chunks: {len(kg['chunks'])}")
    print(f"Entities: {len(kg['entities'])}")
    print(f"Relationships: {len(kg['relationships'])}")

    # Sample entity names
    entity_names = set(e['entity_name'] for e in kg['entities'])
    print(f"\n=== Entity Names (first 10) ===")
    for name in list(entity_names)[:10]:
        print(f"  - {name}")

    # Check if relationship src/tgt exist in entities
    print(f"\n=== Checking Relationships ===")
    missing_src = 0
    missing_tgt = 0

    for i, rel in enumerate(kg['relationships'][:100]):  # Check first 100
        if rel['src_id'] not in entity_names:
            missing_src += 1
            if missing_src == 1:
                print(f"  Missing src_id example: {rel['src_id']}")
        if rel['tgt_id'] not in entity_names:
            missing_tgt += 1
            if missing_tgt == 1:
                print(f"  Missing tgt_id example: {rel['tgt_id']}")

    print(f"  Missing src_id: {missing_src}/100")
    print(f"  Missing tgt_id: {missing_tgt}/100")

    if missing_src > 0 or missing_tgt > 0:
        print("\n❌ PROBLEM: Some relationships refer to non-existent entities!")
        return

    print("\n✅ All relationship endpoints exist in entities")

    # Try loading into LightRAG
    print(f"\n=== Testing LightRAG Load ===")

    working_dir = "./debug_storage"
    os.makedirs(working_dir, exist_ok=True)

    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete,
    )

    await rag.initialize_storages()

    print("Inserting KG (this may take a while)...")

    try:
        await rag.ainsert_custom_kg(kg)
        print("✅ KG inserted successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    # Check what was inserted
    print(f"\n=== Checking Storage ===")

    import glob
    for f in glob.glob(f"{working_dir}/*"):
        size = os.path.getsize(f)
        print(f"  {os.path.basename(f)}: {size} bytes")

    await rag.finalize_storages()

if __name__ == '__main__':
    asyncio.run(debug_load())
