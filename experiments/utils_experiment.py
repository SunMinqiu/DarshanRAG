"""Utility functions for LightRAG experiment harness."""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import hashlib


def setup_logging(log_file: Optional[str] = None, log_level: str = "INFO") -> logging.Logger:
    """Set up logging configuration.
    
    Args:
        log_file: Path to log file (optional)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("lightrag_experiment")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        # Create log directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to YAML configuration file
    
    Returns:
        Configuration dictionary
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def save_config(config: Dict[str, Any], output_path: str) -> None:
    """Save configuration to YAML file.
    
    Args:
        config: Configuration dictionary
        output_path: Path to save configuration
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def load_custom_kg(kg_path: str) -> Dict[str, Any]:
    """Load custom knowledge graph from JSON file.
    
    Args:
        kg_path: Path to custom_kg JSON file
    
    Returns:
        Custom KG dictionary
    """
    with open(kg_path, 'r', encoding='utf-8') as f:
        kg = json.load(f)
    
    # Validate schema
    required_keys = ["entities", "relationships"]
    for key in required_keys:
        if key not in kg:
            raise ValueError(f"Missing required key '{key}' in custom_kg")
    
    # Chunks are optional
    if "chunks" not in kg:
        kg["chunks"] = []
    
    return kg


def load_queries(queries_path: str) -> List[Dict[str, Any]]:
    """Load queries from JSON file.
    
    Expected format:
    [
        {
            "query_id": "q1",
            "query": "What is the I/O pattern for job X?",
            "metadata": {...}  # optional
        },
        ...
    ]
    
    Args:
        queries_path: Path to queries JSON file
    
    Returns:
        List of query dictionaries
    """
    with open(queries_path, 'r', encoding='utf-8') as f:
        queries = json.load(f)
    
    # Support both list and dict with "queries" key
    if isinstance(queries, dict) and "queries" in queries:
        queries = queries["queries"]
    
    # Validate format
    for i, q in enumerate(queries):
        if "query" not in q:
            raise ValueError(f"Query {i} missing required 'query' field")
        if "query_id" not in q:
            q["query_id"] = f"q{i+1}"  # Auto-generate ID if missing
    
    return queries


def load_ground_truth(ground_truth_path: str) -> Dict[str, Any]:
    """Load ground truth from JSON file.
    
    Expected format:
    {
        "q1": {
            "expected_answer": "The answer text",
            "expected_entities": ["Entity1", "Entity2"],  # optional
            "expected_relations": [["Entity1", "Entity2"]],  # optional
            "metadata": {...}  # optional
        },
        ...
    }
    
    Args:
        ground_truth_path: Path to ground truth JSON file
    
    Returns:
        Ground truth dictionary keyed by query_id
    """
    if not os.path.exists(ground_truth_path):
        return {}
    
    with open(ground_truth_path, 'r', encoding='utf-8') as f:
        gt = json.load(f)
    
    return gt


def get_run_id(config: Dict[str, Any]) -> Optional[str]:
    """Generate or retrieve run ID.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Run ID string or None
    """
    run_id = config.get("storage", {}).get("run_id")
    if run_id is None:
        # Generate timestamp-based run ID
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        config.setdefault("storage", {})["run_id"] = run_id
    return run_id


def get_working_dir(config: Dict[str, Any]) -> str:
    """Get working directory with run_id subdirectory if specified.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        Working directory path
    """
    base_dir = config.get("storage", {}).get("working_dir", "./experiments/rag_storage")
    run_id = get_run_id(config)
    
    if run_id:
        working_dir = os.path.join(base_dir, f"run_{run_id}")
    else:
        working_dir = base_dir
    
    # Create directory if it doesn't exist
    os.makedirs(working_dir, exist_ok=True)
    
    return working_dir


def compute_hash(text: str) -> str:
    """Compute MD5 hash of text.
    
    Args:
        text: Input text
    
    Returns:
        Hex digest of MD5 hash
    """
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def save_results(results: Dict[str, Any], output_path: str) -> None:
    """Save experiment results to JSON file.
    
    Args:
        results: Results dictionary
        output_path: Path to save results
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)


def validate_custom_kg(kg: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate custom_kg schema.
    
    Args:
        kg: Custom KG dictionary
    
    Returns:
        (is_valid, error_message)
    """
    # Check required keys
    if "entities" not in kg:
        return False, "Missing required key 'entities'"
    if "relationships" not in kg:
        return False, "Missing required key 'relationships'"
    
    # Validate entities
    if not isinstance(kg["entities"], list):
        return False, "'entities' must be a list"
    
    for i, entity in enumerate(kg["entities"]):
        if not isinstance(entity, dict):
            return False, f"Entity {i} must be a dictionary"
        if "entity_name" not in entity:
            return False, f"Entity {i} missing required field 'entity_name'"
    
    # Validate relationships
    if not isinstance(kg["relationships"], list):
        return False, "'relationships' must be a list"
    
    for i, rel in enumerate(kg["relationships"]):
        if not isinstance(rel, dict):
            return False, f"Relationship {i} must be a dictionary"
        if "src_id" not in rel:
            return False, f"Relationship {i} missing required field 'src_id'"
        if "tgt_id" not in rel:
            return False, f"Relationship {i} missing required field 'tgt_id'"
    
    # Chunks are optional but must be a list if present
    if "chunks" in kg and not isinstance(kg["chunks"], list):
        return False, "'chunks' must be a list if present"
    
    return True, None


def create_synthetic_chunks(kg: Dict[str, Any], template: str = "Summary for source_id: {source_id}") -> Dict[str, Any]:
    """Create minimal synthetic chunks if chunks are missing.
    
    Args:
        kg: Custom KG dictionary
        template: Template string for synthetic chunks
    
    Returns:
        Updated KG dictionary with synthetic chunks
    """
    if "chunks" in kg and len(kg["chunks"]) > 0:
        return kg  # Chunks already exist
    
    # Collect unique source_ids from entities and relationships
    source_ids = set()
    for entity in kg.get("entities", []):
        if "source_id" in entity:
            source_ids.add(entity["source_id"])
    for rel in kg.get("relationships", []):
        if "source_id" in rel:
            source_ids.add(rel["source_id"])
    
    # Create synthetic chunks
    synthetic_chunks = []
    for source_id in source_ids:
        chunk = {
            "content": template.format(source_id=source_id),
            "source_id": source_id,
            "source_chunk_index": 0,
        }
        synthetic_chunks.append(chunk)
    
    kg["chunks"] = synthetic_chunks
    return kg


def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge configuration dictionaries.
    
    Args:
        base_config: Base configuration
        override_config: Override configuration (takes precedence)
    
    Returns:
        Merged configuration
    """
    result = base_config.copy()
    
    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result
