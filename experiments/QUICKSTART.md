# Quick Start Guide

## 1. Prepare Your Knowledge Graph

Create a JSON file following this structure:

```json
{
  "entities": [
    {
      "entity_name": "YourEntity",
      "entity_type": "type",
      "description": "Description text",
      "source_id": "optional_source_id",
      "file_path": "optional_file_path"
    }
  ],
  "relationships": [
    {
      "src_id": "Entity1",
      "tgt_id": "Entity2",
      "description": "Relationship description",
      "keywords": "key, words",
      "weight": 1.0
    }
  ],
  "chunks": []  # Optional, can be empty
}
```

## 2. Prepare Queries

Create `queries.json`:

```json
[
  {
    "query_id": "q1",
    "query": "Your question here"
  }
]
```

## 3. (Optional) Prepare Ground Truth

Create `ground_truth.json`:

```json
{
  "q1": {
    "expected_answer": "Expected answer text",
    "expected_entities": ["Entity1", "Entity2"],
    "expected_relations": [["Entity1", "Entity2"]]
  }
}
```

## 4. Set OpenAI API Key

```bash
export OPENAI_API_KEY="sk-..."
```

## 5. Run Experiment

```bash
# Basic run
python experiments/experiment_harness.py \
  --kg-path ./experiments/ground_truth/custom_kg.json \
  --queries-path ./experiments/ground_truth/queries.json \
  --ground-truth-path ./experiments/ground_truth/ground_truth.json

# With custom settings
python experiments/experiment_harness.py \
  --gen-model gpt-4o \
  --embed-model text-embedding-3-large \
  --temperature 0.1 \
  --top-k 60 \
  --modes hybrid mix \
  --run-id my_experiment
```

## 6. View Results

Results are saved to:
- `experiments/results/results_{run_id}.json` - Full results
- `experiments/logs/experiment_{run_id}.log` - Execution logs

Convert to CSV:
```bash
python experiments/export_results.py experiments/results/results_*.json
```

## 7. Visualize Graph in Web UI

```bash
# Start server pointing to your experiment's working directory
cd experiments/rag_storage/run_{run_id}
lightrag-server --working-dir . --port 9621

# Open http://localhost:9621 in browser
```

## Common Issues

**Missing dependencies**: Install with `pip install pyyaml`

**API key error**: Set `OPENAI_API_KEY` environment variable

**Import errors**: Ensure you're in the DarshanRAG directory and LightRAG is properly installed

For detailed documentation, see [README_experiment.md](README_experiment.md)
