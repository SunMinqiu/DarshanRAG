#!/usr/bin/env python3
"""
parse_darshan_chunks.py

Parse raw Darshan logs and add counter chunks to KG entities.

Usage:
    python3 parse_darshan_chunks.py --log <log_file> --kg <kg_file> [--output <output_file>]

Input:
    - Raw Darshan log file (parsed text format)
    - KG JSON file with descriptions

Output:
    - Updated KG JSON with chunks array
    - Each chunk contains entity_name and chunk_text (original counter data)
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict


def parse_darshan_log(log_path):
    """
    Parse raw Darshan log and extract all counter lines.

    Returns:
        list of tuples: (module, rank, record_id, counter, value, file_path, mount, fs)
    """
    counters = []

    with open(log_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Parse counter lines: MODULE RANK RECORD_ID COUNTER VALUE [FILE MOUNT FS]
            parts = line.split('\t')
            if len(parts) < 5:
                continue

            module = parts[0]
            rank = parts[1]
            record_id = parts[2]
            counter = parts[3]
            value = parts[4]
            file_path = parts[5] if len(parts) > 5 else ""
            mount = parts[6] if len(parts) > 6 else ""
            fs = parts[7] if len(parts) > 7 else ""

            counters.append({
                'module': module,
                'rank': rank,
                'record_id': record_id,
                'counter': counter,
                'value': value,
                'file_path': file_path,
                'mount': mount,
                'fs': fs,
                'raw_line': line
            })

    return counters


def normalize_file_path(file_path):
    """Normalize file path for entity name matching."""
    if not file_path:
        return ""
    # Remove leading/trailing slashes and normalize
    return file_path.strip().strip('/')


def group_by_entity(counters, job_id=None):
    """
    Group counter lines by entity name.

    Entity naming:
        - MODULE: {job_id}::{module_name}
        - RECORD: {job_id}::{module}::{record_id}::rank{rank}
        - FILE: File_{file_path_norm}
        - FILESYSTEM: FS_{fs_type}_{mount_pt}

    Returns:
        dict: {entity_name: [counter_lines]}
    """
    entity_chunks = defaultdict(list)

    for counter in counters:
        module = counter['module']
        rank = counter['rank']
        record_id = counter['record_id']
        file_path = counter['file_path']
        mount = counter['mount']
        fs = counter['fs']
        raw_line = counter['raw_line']

        # MODULE entity
        if job_id:
            module_entity = f"{job_id}::{module}"
            entity_chunks[module_entity].append(raw_line)

        # RECORD entity
        if record_id and record_id != '-':
            if job_id:
                record_entity = f"{job_id}::{module}::{record_id}::rank{rank}"
            else:
                record_entity = f"{module}::{record_id}::rank{rank}"
            entity_chunks[record_entity].append(raw_line)

        # FILE entity
        if file_path:
            file_norm = normalize_file_path(file_path)
            file_entity = f"File_{file_norm}"
            entity_chunks[file_entity].append(raw_line)

        # FILESYSTEM entity
        if fs and mount:
            mount_norm = mount.strip('/').replace('/', '_')
            fs_entity = f"FS_{fs}_{mount_norm}"
            entity_chunks[fs_entity].append(raw_line)

    return entity_chunks


def extract_job_id_from_kg(kg_data):
    """Extract job_id from KG entities."""
    for entity in kg_data.get('entities', []):
        if entity.get('entity_type') == 'JOB':
            return entity.get('job_id')
    return None


def add_chunks_to_kg(kg_data, entity_chunks):
    """
    Add chunks array to KG.

    Args:
        kg_data: KG JSON data
        entity_chunks: dict of {entity_name: [counter_lines]}

    Returns:
        Updated KG data with chunks
    """
    chunks = []
    matched_entities = set()

    # Create chunks for each entity
    for entity_name, counter_lines in entity_chunks.items():
        chunk_text = '\n'.join(counter_lines)
        chunks.append({
            'entity_name': entity_name,
            'chunk_text': chunk_text
        })
        matched_entities.add(entity_name)

    # Add chunks to KG
    kg_data['chunks'] = chunks

    return kg_data, matched_entities


def find_log_files(log_path):
    """Find all log files (file or directory)."""
    path = Path(log_path)

    if path.is_file():
        return [path]
    elif path.is_dir():
        # Find all .txt files
        return sorted(path.glob('**/*.txt'))
    else:
        raise ValueError(f"Invalid log path: {log_path}")


def process_logs(log_paths, kg_path, output_path):
    """Process logs and add chunks to KG."""
    print(f"Searching for log files in: {log_paths}")

    # Find log files
    if isinstance(log_paths, str):
        log_files = find_log_files(log_paths)
    else:
        log_files = []
        for log_path in log_paths:
            log_files.extend(find_log_files(log_path))

    print(f"✓ Found {len(log_files)} log file(s)")

    # Load KG
    with open(kg_path, 'r') as f:
        kg_data = json.load(f)

    # Extract job_id from KG
    job_id = extract_job_id_from_kg(kg_data)

    # Parse all logs and aggregate counters
    all_counters = []
    for log_file in log_files:
        print(f"\nProcessing: {log_file}")
        counters = parse_darshan_log(log_file)
        all_counters.extend(counters)
        print(f"✓ Parsed {len(counters)} counter lines")

    # Group by entity
    entity_chunks = group_by_entity(all_counters, job_id=job_id)
    print(f"✓ Grouped into {len(entity_chunks)} entities")

    # Add chunks to KG
    print("\n" + "=" * 60)
    print("Adding chunks to KG...")
    kg_data, matched_entities = add_chunks_to_kg(kg_data, entity_chunks)

    # Save output
    with open(output_path, 'w') as f:
        json.dump(kg_data, f, indent=2)

    print(f"✓ Updated KG with {len(kg_data['chunks'])} chunks")
    print(f"✓ Saved to: {output_path}")

    # Statistics
    total_entities = len(kg_data.get('entities', []))
    print(f"✓ Statistics: {len(matched_entities)}/{total_entities} entities have counter data")
    print("=" * 60)
    print("✓ Done!")


def main():
    parser = argparse.ArgumentParser(
        description='Parse Darshan logs and add counter chunks to KG',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Single log file
    python3 parse_darshan_chunks.py \\
        --log raw_log.txt \\
        --kg kg_with_desc.json \\
        --output kg_with_chunks.json

    # Directory of logs
    python3 parse_darshan_chunks.py \\
        --log ./logs/ \\
        --kg kg_with_desc.json \\
        --output kg_with_chunks.json
        """
    )

    parser.add_argument('--log', required=True,
                        help='Raw Darshan log file or directory')
    parser.add_argument('--kg', required=True,
                        help='KG JSON file with descriptions')
    parser.add_argument('--output',
                        help='Output KG JSON file (default: overwrite input)')

    args = parser.parse_args()

    # Validate inputs
    if not Path(args.log).exists():
        print(f"Error: Log path does not exist: {args.log}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.kg).exists():
        print(f"Error: KG file does not exist: {args.kg}", file=sys.stderr)
        sys.exit(1)

    # Set output path
    output_path = args.output if args.output else args.kg

    # Process logs
    try:
        process_logs(args.log, args.kg, output_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
