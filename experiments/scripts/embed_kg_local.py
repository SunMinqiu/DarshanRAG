#!/usr/bin/env python3
"""
embed_kg_local.py

Generate embeddings for KG entities and relationships using local Transformer models.

Usage:
    python3 embed_kg_local.py --kg <kg_file> --output <output_dir> [options]

Input:
    - KG JSON file with chunks
    - Each entity has description and chunk_text

Output:
    - entity_embeddings.pkl: Entity vectors (entity_name + description)
    - relationship_embeddings.pkl: Relationship vectors (src_id → tgt_id + description)
    - entity_embeddings.npy: NumPy array format
    - relationship_embeddings.npy: NumPy array format
    - embedding_metadata.json: Metadata (model name, dimension, count)

Implementation:
    1. Load Hugging Face Transformer model
    2. Entity text = "{entity_name}: {description}"
    3. Relationship text = "{src_id} -> {tgt_id}: {description}"
    4. Tokenize + Encode
    5. Mean pooling (using attention mask)
    6. L2 normalization
    7. Batch processing (avoid OOM)
    8. Save as pickle and numpy
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import torch
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModel


def load_kg(kg_path):
    """Load KG from JSON file."""
    with open(kg_path, 'r') as f:
        kg_data = json.load(f)

    entities = kg_data.get('entities', [])
    relationships = kg_data.get('relationships', [])

    return entities, relationships


def prepare_entity_texts(entities):
    """
    Prepare entity texts for embedding.

    Format: "{entity_name}: {description}"
    """
    texts = []
    entity_names = []

    for entity in entities:
        entity_name = entity.get('entity_name', '')
        description = entity.get('description', '')

        # Combine entity name and description
        text = f"{entity_name}: {description}"
        texts.append(text)
        entity_names.append(entity_name)

    return texts, entity_names


def prepare_relationship_texts(relationships):
    """
    Prepare relationship texts for embedding.

    Format: "{src_id} -> {tgt_id}: {description}"
    """
    texts = []
    relationship_ids = []

    for rel in relationships:
        src_id = rel.get('src_id', '')
        tgt_id = rel.get('tgt_id', '')
        description = rel.get('description', '')

        # Combine src, tgt, and description
        text = f"{src_id} -> {tgt_id}: {description}"
        texts.append(text)
        relationship_ids.append(f"{src_id}→{tgt_id}")

    return texts, relationship_ids


def mean_pooling(token_embeddings, attention_mask):
    """
    Mean pooling with attention mask.

    Args:
        token_embeddings: [batch_size, seq_len, hidden_dim]
        attention_mask: [batch_size, seq_len]

    Returns:
        pooled: [batch_size, hidden_dim]
    """
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
    sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    return sum_embeddings / sum_mask


def embed_texts(texts, model, tokenizer, device, batch_size=32, max_length=512):
    """
    Embed texts using the model.

    Args:
        texts: List of text strings
        model: Transformer model
        tokenizer: Tokenizer
        device: 'cpu' or 'cuda'
        batch_size: Batch size for processing
        max_length: Maximum sequence length

    Returns:
        embeddings: numpy array of shape (len(texts), embedding_dim)
    """
    embeddings = []

    model.eval()
    with torch.no_grad():
        for i in tqdm(range(0, len(texts), batch_size), desc="Embedding"):
            batch = texts[i:i + batch_size]

            # Tokenize
            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt"
            ).to(device)

            # Get model output
            outputs = model(**encoded)

            # Mean pooling
            attention_mask = encoded['attention_mask']
            token_embeddings = outputs.last_hidden_state
            batch_embeddings = mean_pooling(token_embeddings, attention_mask)

            # L2 normalization
            batch_embeddings = torch.nn.functional.normalize(batch_embeddings, p=2, dim=1)

            # Move to CPU and store
            embeddings.append(batch_embeddings.cpu().numpy())

    return np.vstack(embeddings)


def save_embeddings(embeddings, ids, output_path):
    """
    Save embeddings as pickle and numpy files.

    Args:
        embeddings: numpy array of shape (n, dim)
        ids: list of entity/relationship IDs
        output_path: output file path (without extension)
    """
    # Save as pickle (dict format)
    embedding_dict = {id_: emb for id_, emb in zip(ids, embeddings)}
    with open(f"{output_path}.pkl", 'wb') as f:
        pickle.dump(embedding_dict, f)

    # Save as numpy array
    np.save(f"{output_path}.npy", embeddings)


def main():
    parser = argparse.ArgumentParser(
        description='Generate embeddings for KG using local Transformer models',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Using Gemma model (recommended)
    python3 embed_kg_local.py \\
        --kg kg_with_chunks.json \\
        --output ./embeddings_gemma \\
        --model google/embeddinggemma-300m \\
        --batch-size 32

    # Using lightweight model (CPU friendly)
    python3 embed_kg_local.py \\
        --kg kg_with_chunks.json \\
        --output ./embeddings_cpu \\
        --model sentence-transformers/all-MiniLM-L6-v2 \\
        --batch-size 4 \\
        --device cpu

Recommended models:
    - google/embeddinggemma-300m: 768D, high accuracy (default)
    - sentence-transformers/all-MiniLM-L6-v2: 384D, fast
    - BAAI/bge-small-en-v1.5: 384D, English optimized
        """
    )

    parser.add_argument('--kg', required=True,
                        help='KG JSON file')
    parser.add_argument('--output', required=True,
                        help='Output directory')
    parser.add_argument('--model', default='google/embeddinggemma-300m',
                        help='Hugging Face model name (default: google/embeddinggemma-300m)')
    parser.add_argument('--batch-size', type=int, default=32,
                        help='Batch size (default: 32)')
    parser.add_argument('--max-length', type=int, default=512,
                        help='Maximum sequence length (default: 512)')
    parser.add_argument('--device', default=None,
                        help='Device: cpu or cuda (default: auto-detect)')

    args = parser.parse_args()

    # Validate inputs
    if not Path(args.kg).exists():
        print(f"Error: KG file does not exist: {args.kg}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Detect device
    if args.device:
        device = args.device
    else:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

    print(f"Loading KG from: {args.kg}")
    entities, relationships = load_kg(args.kg)
    print(f"✓ Loaded KG:")
    print(f"  - {len(entities)} entities")
    print(f"  - {len(relationships)} relationships")

    print(f"\nLoading embedding model: {args.model}")
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model)
        model = AutoModel.from_pretrained(args.model)
        model = model.to(device)
        model.eval()
        print(f"✓ Model loaded on device: {device}")

        # Get embedding dimension
        embedding_dim = model.config.hidden_size
        print(f"✓ Model embedding dimension: {embedding_dim}")

    except Exception as e:
        print(f"Error loading model: {e}", file=sys.stderr)
        sys.exit(1)

    # Prepare entity texts
    print(f"\nPreparing entity texts...")
    entity_texts, entity_names = prepare_entity_texts(entities)
    print(f"✓ Prepared {len(entity_texts)} entity texts")

    # Embed entities
    print(f"\nEmbedding entities...")
    entity_embeddings = embed_texts(
        entity_texts, model, tokenizer, device,
        batch_size=args.batch_size,
        max_length=args.max_length
    )
    print(f"✓ Generated entity embeddings: {entity_embeddings.shape}")

    # Prepare relationship texts
    print(f"\nPreparing relationship texts...")
    rel_texts, rel_ids = prepare_relationship_texts(relationships)
    print(f"✓ Prepared {len(rel_texts)} relationship texts")

    # Embed relationships
    print(f"\nEmbedding relationships...")
    rel_embeddings = embed_texts(
        rel_texts, model, tokenizer, device,
        batch_size=args.batch_size,
        max_length=args.max_length
    )
    print(f"✓ Generated relationship embeddings: {rel_embeddings.shape}")

    # Save embeddings
    print(f"\nSaving embeddings...")
    entity_output = output_dir / "entity_embeddings"
    rel_output = output_dir / "relationship_embeddings"

    save_embeddings(entity_embeddings, entity_names, entity_output)
    print(f"✓ Saved entity embeddings to: {entity_output}.pkl")

    save_embeddings(rel_embeddings, rel_ids, rel_output)
    print(f"✓ Saved relationship embeddings to: {rel_output}.pkl")

    # Save metadata
    metadata = {
        'model': args.model,
        'embedding_dim': embedding_dim,
        'num_entities': len(entities),
        'num_relationships': len(relationships),
        'batch_size': args.batch_size,
        'max_length': args.max_length,
        'device': device
    }

    metadata_path = output_dir / "embedding_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata to: {metadata_path}")

    # Summary
    print("\n" + "=" * 60)
    print("Embedding Summary:")
    print(f"  - Entity embeddings: {entity_embeddings.shape}")
    print(f"  - Relationship embeddings: {rel_embeddings.shape}")
    print(f"  - Embedding dimension: {embedding_dim}")
    print(f"  - Output directory: {output_dir}")
    print("=" * 60)
    print("\n✓ Done!")


if __name__ == '__main__':
    main()
