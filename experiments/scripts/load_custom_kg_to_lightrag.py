#!/usr/bin/env python3
"""
load_custom_kg_to_lightrag.py

Load KG and embeddings to LightRAG for querying.

Usage:
    python3 load_custom_kg_to_lightrag.py --kg <kg_file> [options]

Input:
    - KG JSON file with chunks
    - Embeddings directory (optional, if pre-computed)

Output:
    - LightRAG working directory (vector DB, graph storage, KV storage)
    - Ready to accept queries

Implementation:
    1. Create local embedding function (consistent with pre-computed model)
    2. Configure OpenAI API as LLM
    3. Initialize LightRAG instance
    4. Insert custom KG (preserve graph structure)
    5. Generate notebook example code
"""

import argparse
import asyncio
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel


def load_kg(kg_path):
    """Load KG from JSON file."""
    with open(kg_path, 'r') as f:
        kg_data = json.load(f)
    return kg_data


def load_embeddings(embeddings_dir):
    """Load pre-computed embeddings."""
    entity_path = Path(embeddings_dir) / "entity_embeddings.pkl"
    rel_path = Path(embeddings_dir) / "relationship_embeddings.pkl"

    entity_embeddings = None
    rel_embeddings = None

    if entity_path.exists():
        with open(entity_path, 'rb') as f:
            entity_embeddings = pickle.load(f)
        print(f"✓ Loaded {len(entity_embeddings)} entity embeddings")

    if rel_path.exists():
        with open(rel_path, 'rb') as f:
            rel_embeddings = pickle.load(f)
        print(f"✓ Loaded {len(rel_embeddings)} relationship embeddings")

    return entity_embeddings, rel_embeddings


class LocalEmbeddingFunction:
    """Local embedding function using Hugging Face Transformers."""

    def __init__(self, model_name, device=None, batch_size=4):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = self.model.to(self.device).eval()
        self.embedding_dim = self.model.config.hidden_size
        self.batch_size = batch_size
        print(f"✓ Embedding model loaded: {model_name} ({self.embedding_dim}D)")

    def __call__(self, texts):
        """Synchronous embedding function."""
        embeddings = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                encoded = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt"
                ).to(self.device)

                outputs = self.model(**encoded)
                attention_mask = encoded['attention_mask']
                token_embeddings = outputs.last_hidden_state

                # Mean pooling
                input_mask_expanded = attention_mask.unsqueeze(-1).expand(
                    token_embeddings.size()
                ).float()
                batch_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1) / \
                                   torch.clamp(input_mask_expanded.sum(1), min=1e-9)

                # L2 normalization
                batch_embeddings = torch.nn.functional.normalize(batch_embeddings, p=2, dim=1)
                embeddings.append(batch_embeddings.cpu().numpy())

        return np.vstack(embeddings)


async def async_embed_func(texts, embedding_func):
    """Async wrapper for embedding function."""
    return embedding_func(texts)


async def load_kg_to_lightrag(kg_data, working_dir, embedding_func, llm_func):
    """Load KG to LightRAG."""
    from lightrag import LightRAG
    from lightrag.utils import EmbeddingFunc

    # Create LightRAG instance
    embedding_func_wrapper = EmbeddingFunc(
        embedding_dim=embedding_func.embedding_dim,
        max_token_size=2048,
        func=lambda texts: asyncio.run(async_embed_func(texts, embedding_func))
    )

    rag = LightRAG(
        working_dir=working_dir,
        embedding_func=embedding_func_wrapper,
        llm_model_func=llm_func,
    )

    await rag.initialize_storages()

    # Prepare documents from entities
    entities = kg_data.get('entities', [])
    relationships = kg_data.get('relationships', [])
    chunks = kg_data.get('chunks', [])

    print(f"\nInserting KG into LightRAG:")
    print(f"  - {len(entities)} entities")
    print(f"  - {len(relationships)} relationships")
    print(f"  - {len(chunks)} chunks")

    # Create documents from chunks
    documents = []
    for chunk in chunks:
        entity_name = chunk.get('entity_name', '')
        chunk_text = chunk.get('chunk_text', '')

        # Find corresponding entity description
        description = ""
        for entity in entities:
            if entity.get('entity_name') == entity_name:
                description = entity.get('description', '')
                break

        # Combine description and chunk text
        doc_text = f"{entity_name}\n\n{description}\n\n{chunk_text}"
        documents.append(doc_text)

    # Insert documents
    print("\nInserting documents to LightRAG...")
    for i, doc in enumerate(documents):
        await rag.ainsert(doc)
        if (i + 1) % 10 == 0:
            print(f"  Inserted {i + 1}/{len(documents)} documents")

    print(f"✓ Inserted {len(documents)} documents")

    return rag


def print_notebook_example(working_dir, model_name):
    """Print notebook example code."""
    print("\n" + "=" * 70)
    print("Notebook Example Code:")
    print("=" * 70)
    print("""
# Cell 1: Import libraries
import os
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.utils import EmbeddingFunc
from transformers import AutoTokenizer, AutoModel
import torch
import numpy as np

# Cell 2: Set API key
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("⚠️  Please set OPENAI_API_KEY environment variable")
else:
    print("✅ OPENAI_API_KEY loaded")

# Cell 3: Define local embedding function
class LocalEmbeddingFunction:
    def __init__(self, model_name="{model_name}", device=None, batch_size=4):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(self.device).eval()
        self.embedding_dim = self.model.config.hidden_size
        self.batch_size = batch_size
        print(f"✓ Model loaded: {{model_name}} ({{self.embedding_dim}}D)")

    async def __call__(self, texts):
        embeddings = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                encoded = self.tokenizer(batch, padding=True, truncation=True,
                                        max_length=512, return_tensors="pt").to(self.device)
                outputs = self.model(**encoded)
                attention_mask = encoded['attention_mask']
                token_embeddings = outputs.last_hidden_state
                input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
                batch_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1) / \\
                                  torch.clamp(input_mask_expanded.sum(1), min=1e-9)
                batch_embeddings = torch.nn.functional.normalize(batch_embeddings, p=2, dim=1)
                embeddings.append(batch_embeddings.cpu().numpy())
        return np.vstack(embeddings)

local_embed = LocalEmbeddingFunction()
embedding_func = EmbeddingFunc(
    embedding_dim=local_embed.embedding_dim,
    max_token_size=2048,
    func=lambda texts: local_embed(texts)
)

# Cell 4: Define LLM function
async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
    return await openai_complete_if_cache(
        "gpt-4o-mini",
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=OPENAI_API_KEY,
        **kwargs
    )

print("✓ LLM function configured")

# Cell 5: Load LightRAG
WORKING_DIR = "{working_dir}"

rag = LightRAG(
    working_dir=WORKING_DIR,
    embedding_func=embedding_func,
    llm_model_func=llm_model_func,
)

await rag.initialize_storages()
print("✓ LightRAG loaded successfully!")
print(f"  Working directory: {{WORKING_DIR}}")

# Cell 6: Query helper function
async def query(question, mode="hybrid", top_k=5):
    \"\"\"Query Darshan KG\"\"\"
    result = await rag.aquery(
        question,
        param=QueryParam(mode=mode, top_k=top_k)
    )
    return result

print("✓ Query helper ready!")

# Cell 7: Example queries
# Basic query
result = await query("What are the POSIX I/O operations?")
print(result)

# File access query
result = await query("Which files were accessed and where?")
print(result)

# Performance analysis
result = await rag.aquery(
    "Analyze the I/O performance",
    param=QueryParam(mode="hybrid", top_k=10, only_need_context=False)
)
print(result)

# Query modes:
# - naive: Simple vector search
# - local: Entity-based local search (good for specific details)
# - global: Relationship-based global search (good for overall summary)
# - hybrid: local + global (recommended)
# - mix: Mixed graph and vector retrieval
""".format(model_name=model_name, working_dir=working_dir))
    print("=" * 70)


async def async_main(args):
    """Async main function."""
    # Load KG
    print(f"Loading KG from: {args.kg}")
    kg_data = load_kg(args.kg)
    print(f"✓ Loaded KG:")
    print(f"  - {len(kg_data.get('entities', []))} entities")
    print(f"  - {len(kg_data.get('relationships', []))} relationships")
    print(f"  - {len(kg_data.get('chunks', []))} chunks")

    # Load embeddings (if provided)
    if args.embeddings:
        print(f"\nLoading embeddings from: {args.embeddings}")
        entity_embeddings, rel_embeddings = load_embeddings(args.embeddings)

    # Create embedding function
    print(f"\nCreating embedding function...")
    embedding_func = LocalEmbeddingFunction(
        model_name=args.embedding_model,
        device=args.device
    )

    # Create LLM function
    print(f"\nConfiguring LLM function...")
    openai_api_key = args.openai_key or os.environ.get('OPENAI_API_KEY')

    if not openai_api_key:
        print("Error: OpenAI API key not provided", file=sys.stderr)
        print("Set OPENAI_API_KEY environment variable or use --openai-key", file=sys.stderr)
        sys.exit(1)

    os.environ['OPENAI_API_KEY'] = openai_api_key

    from lightrag.llm.openai import openai_complete_if_cache

    async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        return await openai_complete_if_cache(
            args.openai_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=openai_api_key,
            **kwargs
        )

    print(f"✓ LLM function configured (model: {args.openai_model})")

    # Create working directory
    working_dir = Path(args.working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Working directory: {working_dir}")

    # Load KG to LightRAG
    print("\nInitializing LightRAG and inserting KG...")
    rag = await load_kg_to_lightrag(kg_data, str(working_dir), embedding_func, llm_model_func)

    print("\n" + "=" * 70)
    print("✅ LightRAG setup complete!")
    print("=" * 70)
    print(f"Working directory: {working_dir}")
    print(f"Embedding model: {args.embedding_model}")
    print(f"LLM model: {args.openai_model}")
    print("\nYou can now query the KG using LightRAG!")

    # Print notebook example
    print_notebook_example(str(working_dir), args.embedding_model)


def main():
    parser = argparse.ArgumentParser(
        description='Load KG and embeddings to LightRAG',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python3 load_custom_kg_to_lightrag.py \\
        --kg kg_with_chunks.json

    # With pre-computed embeddings
    python3 load_custom_kg_to_lightrag.py \\
        --kg kg_with_chunks.json \\
        --embeddings ./embeddings_gemma \\
        --embedding-model google/embeddinggemma-300m

    # Custom OpenAI model
    python3 load_custom_kg_to_lightrag.py \\
        --kg kg_with_chunks.json \\
        --openai-model gpt-4o \\
        --openai-key sk-your-key-here

Environment variables:
    OPENAI_API_KEY: OpenAI API key (required)
        """
    )

    parser.add_argument('--kg', required=True,
                        help='KG JSON file with chunks')
    parser.add_argument('--embeddings',
                        help='Embeddings directory (optional)')
    parser.add_argument('--embedding-model', default='sentence-transformers/all-MiniLM-L6-v2',
                        help='Embedding model name (default: sentence-transformers/all-MiniLM-L6-v2)')
    parser.add_argument('--working-dir', default='./lightrag_darshan_storage',
                        help='LightRAG working directory (default: ./lightrag_darshan_storage)')
    parser.add_argument('--openai-key',
                        help='OpenAI API key (or set OPENAI_API_KEY environment variable)')
    parser.add_argument('--openai-model', default='gpt-4o-mini',
                        help='OpenAI model (default: gpt-4o-mini)')
    parser.add_argument('--device',
                        help='Device: cpu or cuda (default: auto-detect)')

    args = parser.parse_args()

    # Validate inputs
    if not Path(args.kg).exists():
        print(f"Error: KG file does not exist: {args.kg}", file=sys.stderr)
        sys.exit(1)

    # Check if lightrag is installed
    try:
        import lightrag
    except ImportError:
        print("Error: lightrag is not installed", file=sys.stderr)
        print("Install it with: pip install lightrag-hku", file=sys.stderr)
        sys.exit(1)

    # Run async main
    try:
        asyncio.run(async_main(args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
