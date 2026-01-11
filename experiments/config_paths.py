#!/usr/bin/env python3
"""
Path Configuration Module for DarshanRAG Experiments

This module provides centralized path management for all experiments.
All experiment scripts and notebooks should import paths from this module
instead of using hardcoded paths.

Usage:
    from config_paths import PATHS

    # Access paths
    input_logs = PATHS['parsed_logs'] / '2025-1-1'
    output_kg = PATHS['knowledge_graphs'] / 'kg_2025-1-1.json'
"""

import os
from pathlib import Path
from typing import Dict

# ============================================================
# Project Root Detection
# ============================================================

def get_project_root() -> Path:
    """
    Auto-detect project root directory.

    Returns:
        Path: Project root directory (DarshanRAG/)
    """
    # Try from environment variable first
    if 'DARSHAN_RAG_ROOT' in os.environ:
        return Path(os.environ['DARSHAN_RAG_ROOT'])

    # Auto-detect from this file's location
    # config_paths.py is in: DarshanRAG/experiments/
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent  # Go up 2 levels

    return project_root


# ============================================================
# Path Configuration
# ============================================================

PROJECT_ROOT = get_project_root()

# Core directories
DATA_ROOT = PROJECT_ROOT / 'data'
KG_ROOT = PROJECT_ROOT / 'knowledge_graphs'
EXPERIMENTS_ROOT = PROJECT_ROOT / 'experiments'

# Data subdirectories
RAW_LOGS = DATA_ROOT / 'raw'
PARSED_LOGS = DATA_ROOT / 'parsed'
ARCHIVES = DATA_ROOT / 'archives'
EXAMPLES = DATA_ROOT / 'examples'

# Experiment subdirectories
NOTEBOOKS = EXPERIMENTS_ROOT / 'notebooks'
SCRIPTS = EXPERIMENTS_ROOT / 'scripts'
RESULTS = EXPERIMENTS_ROOT / 'results'
STORAGE = EXPERIMENTS_ROOT / 'storage'

# Legacy directories (for backward compatibility)
LEGACY_IORAG = Path('/users/Minqiu/IORAG')

# ============================================================
# Path Dictionary for Easy Access
# ============================================================

PATHS: Dict[str, Path] = {
    # Project structure
    'project_root': PROJECT_ROOT,
    'data_root': DATA_ROOT,
    'kg_root': KG_ROOT,
    'experiments_root': EXPERIMENTS_ROOT,

    # Data directories
    'raw_logs': RAW_LOGS,
    'parsed_logs': PARSED_LOGS,
    'archives': ARCHIVES,
    'examples': EXAMPLES,

    # Experiment directories
    'notebooks': NOTEBOOKS,
    'scripts': SCRIPTS,
    'results': RESULTS,
    'storage': STORAGE,

    # Legacy (deprecated)
    'legacy_iorag': LEGACY_IORAG,
}


# ============================================================
# Utility Functions
# ============================================================

def ensure_dirs():
    """Create all necessary directories if they don't exist."""
    dirs_to_create = [
        DATA_ROOT, RAW_LOGS, PARSED_LOGS, ARCHIVES, EXAMPLES,
        KG_ROOT, NOTEBOOKS, SCRIPTS, RESULTS, STORAGE
    ]

    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)

    print(f"✅ All directories ensured under: {PROJECT_ROOT}")


def get_parsed_log_path(date_str: str) -> Path:
    """
    Get parsed log path for a specific date.

    Args:
        date_str: Date string (e.g., '2025-1-1')

    Returns:
        Path: Parsed log directory path
    """
    return PARSED_LOGS / f'parsed-logs-{date_str}'


def get_kg_path(name: str, date_str: str = None) -> Path:
    """
    Get knowledge graph file path.

    Args:
        name: KG name (e.g., 'kg', 'darshan_graph')
        date_str: Optional date string (e.g., '2025-1-1')

    Returns:
        Path: KG file path
    """
    if date_str:
        filename = f'{name}_{date_str}.json'
    else:
        filename = f'{name}.json'

    return KG_ROOT / filename


def get_result_dir(experiment_name: str) -> Path:
    """
    Get result directory for a specific experiment.

    Args:
        experiment_name: Experiment name (e.g., 'eval_2025_1_1')

    Returns:
        Path: Result directory path
    """
    result_dir = RESULTS / experiment_name
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def get_storage_dir(storage_name: str) -> Path:
    """
    Get storage directory for RAG systems.

    Args:
        storage_name: Storage name (e.g., 'lightrag_storage_2025_1_1')

    Returns:
        Path: Storage directory path
    """
    storage_dir = STORAGE / storage_name
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


# ============================================================
# Display Configuration
# ============================================================

def print_config():
    """Print current path configuration."""
    print("=" * 70)
    print("DarshanRAG Path Configuration")
    print("=" * 70)
    print(f"\n📁 Project Root: {PROJECT_ROOT}")
    print(f"\n📊 Data Directories:")
    print(f"  - Raw logs:    {RAW_LOGS}")
    print(f"  - Parsed logs: {PARSED_LOGS}")
    print(f"  - Archives:    {ARCHIVES}")
    print(f"  - Examples:    {EXAMPLES}")
    print(f"\n🕸️  Knowledge Graphs: {KG_ROOT}")
    print(f"\n🧪 Experiment Directories:")
    print(f"  - Notebooks: {NOTEBOOKS}")
    print(f"  - Scripts:   {SCRIPTS}")
    print(f"  - Results:   {RESULTS}")
    print(f"  - Storage:   {STORAGE}")
    print("=" * 70)


# ============================================================
# Auto-initialization
# ============================================================

# Ensure directories exist on import
try:
    ensure_dirs()
except Exception as e:
    print(f"⚠️  Warning: Could not create directories: {e}")


# ============================================================
# Main (for testing)
# ============================================================

if __name__ == '__main__':
    print_config()

    # Test path generation
    print("\n🧪 Testing path generation:")
    print(f"  Parsed logs (2025-1-1): {get_parsed_log_path('2025-1-1')}")
    print(f"  KG file (kg_2025-1-1):  {get_kg_path('kg', '2025-1-1')}")
    print(f"  Result dir (test):      {get_result_dir('test_experiment')}")
    print(f"  Storage dir (rag):      {get_storage_dir('lightrag_test')}")
