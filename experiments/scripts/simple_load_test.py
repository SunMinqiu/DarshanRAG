#!/usr/bin/env python3
"""Simple test to load a SMALL subset of the KG"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lightrag import LightRAG
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed
from lightrag.utils import setup_logger

async def test_small_kg():
    setup_logger("lightrag", level="INFO")

    # Load full KG
    with open('kg_2025-1-1_fixed.json', 'r') as f:
        full_kg = json.load(f)

    # Create a SMALL test KG (first job only)
    test_job_id = list(set(c['source_id'] for c in full_kg['chunks']))[0]
    print(f"Testing with job: {test_job_id}")

    small_kg = {
        'chunks': [c for c in full_kg['chunks'] if c['source_id'] == test_job_id],
        'entities': [e for e in full_kg['entities'] if e.get('source_id') == test_job_id],
        'relationships': [r for r in full_kg['relationships'] if r.get('source_id') == test_job_id]
    }

    print(f"\nSmall KG:")
    print(f"  Chunks: {len(small_kg['chunks'])}")
    print(f"  Entities: {len(small_kg['entities'])}")
    print(f"  Relationships: {len(small_kg['relationships'])}")

    # Load into LightRAG
    working_dir = "./test_small_storage"
    os.makedirs(working_dir, exist_ok=True)

    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=openai_embed,
        llm_model_func=gpt_4o_mini_complete,
    )

    await rag.initialize_storages()

    print("\nInserting small KG...")
    try:
        await rag.ainsert_custom_kg(small_kg)
        print("✅ Insert completed!")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Check results
    print("\n=== Checking Results ===")

    # Count edges in graph
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(f"{working_dir}/graph_chunk_entity_relation.graphml")
        root = tree.getroot()

        # Find namespace
        ns = {'g': 'http://graphml.graphdrawing.org/xmlns'}

        nodes = root.findall('.//g:node', ns)
        edges = root.findall('.//g:edge', ns)

        print(f"  Graph nodes: {len(nodes)}")
        print(f"  Graph edges: {len(edges)}")

        if len(edges) > 0:
            print("\n✅ SUCCESS! Edges were inserted into the graph!")
        else:
            print("\n❌ PROBLEM: No edges in the graph!")

    except Exception as e:
        print(f"  Error reading graph: {e}")

    # Check vdb_relationships
    with open(f"{working_dir}/vdb_relationships.json", 'r') as f:
        vdb_rel = json.load(f)
        rel_count = len(vdb_rel.get('data', []))
        print(f"  VDB relationships: {rel_count}")

    await rag.finalize_storages()

if __name__ == '__main__':
    asyncio.run(test_small_kg())
