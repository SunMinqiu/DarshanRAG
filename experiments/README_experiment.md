# LightRAG Experiment Harness for Darshan Logs

This experiment harness evaluates LightRAG on Darshan logs using a pre-built custom knowledge graph. It compares hybrid vs mix retrieval modes and evaluates both retrieval and answer generation.

> **Quick Start**: If you just want to query your KG interactively without evaluation, see [README_interactive.md](README_interactive.md) for a simpler interface.

## Features

- **Custom KG Loading**: Import pre-built knowledge graphs using `insert_custom_kg`
- **Multiple Query Modes**: Compare hybrid, mix, and other retrieval modes
- **Dual Evaluation**: Evaluate both retrieval (entities/relations) and generation (answers)
- **Comprehensive Configuration**: All parameters exposed via YAML config and CLI arguments
- **Reproducibility**: Versioned configs, deterministic generation options, strict logging
- **OpenAI-Only**: Uses OpenAI models for LLM, embeddings, and optional reranking

## Installation

### Prerequisites

1. Python 3.10 or higher
2. OpenAI API key (set `OPENAI_API_KEY` environment variable)
3. LightRAG installed (already in this repository)

### Setup

```bash
# Install required dependencies
pip install pyyaml numpy

# Ensure you're in the DarshanRAG directory
cd /users/Minqiu/DarshanRAG

# Make experiment harness executable
chmod +x experiments/experiment_harness.py
```

## Quick Start

### 1. Prepare Input Files

Create three JSON files:

#### `custom_kg.json` - Knowledge Graph

```json
{
  "entities": [
    {
      "entity_name": "Job_12345",
      "entity_type": "job",
      "description": "HPC job with ID 12345...",
      "source_id": "darshan_log_2025_01_01_job12345",
      "file_path": "/path/to/logs/job12345.darshan"
    }
  ],
  "relationships": [
    {
      "src_id": "Job_12345",
      "tgt_id": "MPI-IO",
      "description": "Job 12345 uses MPI-IO pattern",
      "keywords": "uses, io_pattern",
      "weight": 1.0,
      "source_id": "darshan_log_2025_01_01_job12345"
    }
  ],
  "chunks": []
}
```

**Note**: `chunks` can be empty or omitted if you only have entities and relationships.

#### `queries.json` - Test Queries

```json
[
  {
    "query_id": "q1",
    "query": "What I/O pattern does job 12345 use?",
    "metadata": {}
  }
]
```

#### `ground_truth.json` - Expected Results (Optional)

```json
{
  "q1": {
    "expected_answer": "Job 12345 uses MPI-IO pattern",
    "expected_entities": ["Job_12345", "MPI-IO"],
    "expected_relations": [["Job_12345", "MPI-IO"]]
  }
}
```

### 2. Configure Experiment

Edit `experiments/config.yaml` or use CLI arguments to set:

- Model choices (gen_model, embed_model)
- Query modes to test (default: ["hybrid", "mix"])
- Retrieval parameters (top_k, token budgets, etc.)
- Storage settings (working_dir, workspace)

### 3. Run Experiment

```bash
# Basic run with default config
python experiments/experiment_harness.py

# With custom paths
python experiments/experiment_harness.py \
  --kg-path ./experiments/ground_truth/my_kg.json \
  --queries-path ./experiments/ground_truth/my_queries.json \
  --ground-truth-path ./experiments/ground_truth/my_gt.json

# Override specific parameters
python experiments/experiment_harness.py \
  --gen-model gpt-4o-mini \
  --embed-model text-embedding-3-large \
  --temperature 0.1 \
  --top-k 60 \
  --run-id my_experiment_001

# Test only retrieval (no generation)
python experiments/experiment_harness.py --retrieval-only
```

## Configuration

### Configuration File (`config.yaml`)

All settings can be configured in `experiments/config.yaml`. Key sections:

#### Models

```yaml
models:
  gen_model: "gpt-4o"  # or "gpt-4o-mini", "gpt-4-turbo"
  embed_model: "text-embedding-3-large"
  api_key: null  # Use OPENAI_API_KEY env var
  base_url: "https://api.openai.com/v1"
```

#### Retrieval Parameters

```yaml
retrieval:
  modes: ["hybrid", "mix"]  # Query modes to evaluate
  top_k: 60
  chunk_top_k: 20
  max_entity_tokens: 6000
  max_relation_tokens: 8000
  max_total_tokens: 30000
  enable_rerank: false  # OpenAI rerank not available via standard API
  cosine_better_than_threshold: 0.2
```

#### Generation Parameters

```yaml
generation:
  temperature: 0.1  # Low for reproducibility
  max_output_tokens: 2000
  seed: null  # Set to integer for deterministic generation
```

#### Storage

```yaml
storage:
  working_dir: "./experiments/rag_storage"
  workspace: ""  # Workspace name for data isolation
  run_id: null  # Auto-generated if not set
  graph_storage: "NetworkXStorage"
  vector_storage: "NanoVectorDBStorage"
  kv_storage: "JsonKVStorage"
```

### CLI Arguments

All config options can be overridden via CLI:

```bash
python experiments/experiment_harness.py --help
```

Common overrides:

- `--kg-path`: Path to custom_kg JSON
- `--queries-path`: Path to queries JSON
- `--ground-truth-path`: Path to ground truth JSON
- `--gen-model`: Generation model name
- `--embed-model`: Embedding model name
- `--run-id`: Experiment run ID (creates subdirectory)
- `--temperature`: Generation temperature
- `--top-k`: Retrieval top_k
- `--modes`: Query modes (e.g., `--modes hybrid mix`)
- `--retrieval-only`: Run retrieval-only evaluation

## Output

### Results Structure

Results are saved to `experiments/results/results_{run_id}.json`:

```json
{
  "config": {...},
  "run_id": "20250101_120000",
  "timestamp": "2025-01-01T12:00:00",
  "summary": {
    "total_queries": 3,
    "modes": ["hybrid", "mix"],
    "mean_entity_f1": 0.85,
    "mean_relation_f1": 0.80,
    "mean_token_f1": 0.75
  },
  "results": [
    {
      "query_id": "q1",
      "mode": "hybrid",
      "query": "What I/O pattern does job 12345 use?",
      "retrieved_entities": ["Job_12345", "MPI-IO"],
      "retrieved_relations": [["Job_12345", "MPI-IO"]],
      "generated_answer": "Job 12345 uses MPI-IO pattern...",
      "retrieval_metrics": {
        "entity_precision": 1.0,
        "entity_recall": 1.0,
        "entity_f1": 1.0
      },
      "generation_metrics": {
        "token_f1": 0.85,
        "exact_match": false
      }
    }
  ]
}
```

### Logs

Logs are saved to `experiments/logs/experiment_{run_id}.log` with detailed execution information.

### Config Snapshots

Configuration used for each run is saved to `experiments/results/config_{run_id}.yaml`.

## Evaluation Metrics

### Retrieval Metrics

- **Entity Precision/Recall/F1**: Based on retrieved vs expected entities
- **Relation Precision/Recall/F1**: Based on retrieved vs expected relations

### Generation Metrics

- **Token-based F1**: Word overlap between generated and expected answers
- **Exact Match**: Whether generated answer exactly matches expected

## Parameter Sweeping

To sweep parameters across multiple runs:

```bash
# Sweep top_k values
for top_k in 30 60 90; do
  python experiments/experiment_harness.py \
    --top-k $top_k \
    --run-id sweep_topk_${top_k}
done

# Sweep query modes
for mode in hybrid mix local global; do
  python experiments/experiment_harness.py \
    --modes $mode \
    --run-id sweep_mode_${mode}
done

# Sweep temperature
for temp in 0.0 0.1 0.5 1.0; do
  python experiments/experiment_harness.py \
    --temperature $temp \
    --run-id sweep_temp_${temp}
done
```

## Handling "No Chunks"

The harness supports knowledge graphs without text chunks:

1. **Default behavior**: If `chunks` is empty or omitted, the system proceeds with entities and relations only. Logs will note `chunks_provided=false`.

2. **Synthetic chunks** (if needed): If LightRAG errors without chunks, enable synthetic chunks in config:

```yaml
chunks:
  synthetic_chunks: true
  synthetic_chunk_template: "Summary for source_id: {source_id}"
```

This creates minimal placeholder chunks per source_id. Default is `false`.

## Provenance Fields

The harness preserves `source_id` and `file_path` metadata from your KG:

- Stored in LightRAG storage
- Included in logs and results
- Can be used for filtering evaluation by specific jobs/runs
- Not embedded separately (preserved as metadata only)

## Integration with Web UI

After running experiments, you can visualize the knowledge graph using LightRAG Web UI:

```bash
# Start LightRAG Server (using same working_dir as experiment)
cd experiments/rag_storage/run_20250101_120000
lightrag-server --working-dir . --port 9621

# Open browser to http://localhost:9621
# Navigate to graph visualization page
```

**Note**: Use the same `working_dir` and `workspace` as your experiment to see the same KG.

## Troubleshooting

### Error: "OpenAI API key not found"

Set the API key:
```bash
export OPENAI_API_KEY="sk-..."
```

Or add to config:
```yaml
models:
  api_key: "sk-..."
```

### Error: "Invalid custom_kg schema"

Ensure your KG JSON has:
- `entities` (list, required)
- `relationships` (list, required)
- `chunks` (list, optional)

Each entity needs `entity_name`. Each relationship needs `src_id` and `tgt_id`.

### Error: "LightRAG errors when no chunks present"

Enable synthetic chunks (see "Handling 'No Chunks'" section above).

### Low retrieval performance

Try adjusting:
- `top_k`: Increase to retrieve more entities/relations
- `cosine_better_than_threshold`: Lower threshold (e.g., 0.1) for more matches
- `max_entity_tokens` / `max_relation_tokens`: Increase token budgets

### Generation quality issues

Try adjusting:
- `temperature`: Lower (0.0-0.1) for more deterministic, higher (0.7-1.0) for more creative
- `max_output_tokens`: Increase for longer answers
- Use stronger model: `--gen-model gpt-4o` instead of `gpt-4o-mini`

## Examples

See example files in `experiments/ground_truth/`:
- `custom_kg_example.json`: Example knowledge graph
- `queries_example.json`: Example queries
- `ground_truth_example.json`: Example ground truth

## Advanced Usage

### Custom Storage Backends

```yaml
storage:
  graph_storage: "Neo4JStorage"  # Requires Neo4j connection
  vector_storage: "PGVectorStorage"  # Requires PostgreSQL
  kv_storage: "PGKVStorage"
```

Set corresponding environment variables (see LightRAG README for details).

### LLM-based Evaluation

Configure judge model (future feature):

```yaml
models:
  judge_model: "gpt-4o"  # For LLM-based answer evaluation
```

### Filtering by Source ID

If your ground truth includes `source_id`, enable filtering:

```yaml
provenance:
  filter_by_source_id: true
```

## Contributing

To add new evaluation metrics or query modes:

1. Edit `experiments/evaluation.py` for new metrics
2. Edit `experiments/experiment_harness.py` to integrate new features
3. Update this README with usage instructions

## License

Same as LightRAG project.
