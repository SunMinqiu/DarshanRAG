#!/usr/bin/env python3
"""
Generate entity and relationship descriptions from Darshan log JSON files.
Fills templates with attributes and tracks unused placeholders.
"""

import json
import sys
import re
from pathlib import Path
from collections import defaultdict


# Entity template definitions
ENTITY_TEMPLATES = {
    "JOB": """This JOB is a single HPC job, describing when it ran, how large it was, and what application it executed.

The job is identified by job_id {job_id} and was submitted by user {uid}. It ran on {nprocs} processes across {nnodes} compute nodes, indicating the scale of parallelism involved.

From a temporal perspective, the job started at {start_time_asci} and finished at {end_time_asci}, resulting in a total runtime of {runtime} seconds.

The job executes application {exe}, providing the high-level workload identity that is used for historical comparison and baseline analysis.""",

    "APPLICATION": """This APPLICATION entity represents a logical workload identity shared across multiple jobs, enabling cross-run comparison and baseline reasoning.

The application is identified by app_name {exe}, which typically corresponds to the executable name or user-defined workload label.

Across observed jobs, this application is commonly launched with {nprocs} processes, reflecting its typical parallel scale.

This entity serves as a stable anchor for grouping jobs with similar I/O and execution behavior, independent of individual job IDs.""",

    "MODULE": """This MODULE entity describes a specific I/O interface or stack component used during execution, capturing how the application interacted with the storage system.

The module type is {module_name}, indicating the API layer responsible for I/O operations.

The module reports total I/O activity consisting of {total_bytes_read} bytes read and {total_bytes_written} bytes written.

The access behavior includes {total_reads} read operations and {total_writes} write operations, which together characterize the I/O intensity and balance of this module.

This entity abstracts I/O behavior at the interface level, independent of individual files.""",

    "FILE": """This FILE entity represents a logical file accessed during job execution, focusing on where the file is located and how it is shared.

The file is identified by file_name {file_path_raw} and resides on mount_pt {mount_pt}, using filesystem type fs_type {fs_type}.

The file is accessed by rank {rank}, and is_shared is {is_shared} indicates whether the file is shared across multiple ranks or accessed privately.

This entity provides a stable reference for aggregating multiple I/O records associated with the same file.""",

    "RECORD": """This FILE I/O RECORD describes how a single file was accessed during execution, focusing on when I/O happened, how intensive it was, and what kind of access pattern dominated.

The record is associated with file_name {file_name} on mount_pt {mount_pt} using fs_type {fs_type}.
The access originates from rank {rank}, and is_shared is {is_shared}, indicating whether the file was accessed collectively or by an individual process.

From a temporal perspective, I/O activity begins at {io_start_ts} and spans {io_span} seconds.
Within this window, the file is actively performing I/O for {io_time} seconds, resulting in a busy_frac {busy_frac}, which reflects how continuously the file was accessed.

In terms of I/O composition, the workload includes bytes_read {bytes_read} and bytes_written {bytes_written}, issued through reads {reads} read operations and writes {writes} write operations.
This balance indicates whether the access is read-dominated, write-dominated, or mixed.

Performance observations show that the measured read bandwidth is {read_bw} and the write bandwidth is {write_bw}.
If a bandwidth metric is unavailable, this is explicitly explained by {read_bw_na_reason} or {write_bw_na_reason}.
Similarly, I/O operation rates are captured by read_iops {read_iops} and write_iops {write_iops}, with missing values explained by read_iops_na_reason {read_iops_na_reason} and write_iops_na_reason {write_iops_na_reason}.

The access pattern shows structural characteristics.
Sequential access tendencies are reflected by seq_read_ratio: {seq_read_ratio} and seq_write_ratio: {seq_write_ratio}, while short-range locality is indicated by consec_read_ratio: {consec_read_ratio} and consec_write_ratio: {consec_write_ratio}.
The value rw_switches: {rw_switches} captures how frequently the workload alternates between read and write operations.

Metadata-related activity is quantified by metadata_ops: {meta_ops}, indicating the extent to which metadata operations contribute to the overall I/O behavior.

Finally, performance stability is summarized by bw_variance_proxy:{bw_variance_proxy}, which serves as a proxy for bandwidth variability and helps identify bursty or unstable I/O behavior.""",

    "FILESYSTEM": """This FILE SYSTEM entity describes the storage backend used during execution, capturing the type and mounting context of the filesystem.

The filesystem is mounted at mount_pt {mount_pt} and is identified as fs_type {fs_type}.

This entity provides environmental context for interpreting I/O behavior, including performance characteristics and metadata handling semantics that are shared across all files on this filesystem."""
}


# Relationship template definitions
# Map from (src_type, tgt_type) to template
RELATIONSHIP_TEMPLATES = {
    ("APPLICATION", "JOB"): """This relationship indicates that job {tgt_id} runs the application {src_id}. The job is an execution instance of this application, meaning that all observed computation and I/O behavior originates from this application binary or workflow.""",

    ("JOB", "FILE"): """The job {src_id} performs file I/O operations on file {tgt_id}, including reads and writes, and an overall data volume of {bytes_read} read and {bytes_written} written. This interaction spans from {io_start_time} to {io_end_time}, indicating the role of this file in the job's I/O behavior.""",

    ("JOB", "FILESYSTEM"): """This relationship represents the interaction between job {src_id} and storage resource {tgt_id}. All I/O operations targeting files on this filesystem are ultimately served by this storage backend, making it the underlying storage resource for the job's I/O.""",

    ("JOB", "MODULE"): """This relationship indicates that job {src_id} uses the I/O module {tgt_id} during execution. The job's file I/O requests are issued through this module, which determines the I/O interface and semantics used for accessing storage.""",

    ("MODULE", "RECORD"): """This relationship links the I/O module {src_id} to a specific I/O record {tgt_id} observed during execution. The record reflects actual I/O behavior expressed through this module, including operations such as {operation_types}.""",

    ("RECORD", "FILE"): """This relationship describes that record {src_id} corresponds to I/O operations performed on file {tgt_id}. The record reflects access activity targeting this file, capturing how the file is involved in the observed I/O behavior.""",

    ("RECORD", "MODULE"): """This relationship indicates that record {src_id} is executed under the I/O module {tgt_id}. The recorded I/O behavior follows the semantics and execution context defined by this module, rather than alternative I/O interfaces.""",

    ("FILE", "FILESYSTEM"): """This relationship indicates that file {src_id} resides on filesystem {tgt_id}. All I/O operations targeting this file are ultimately served by this filesystem, which determines the storage backend and performance characteristics for file access."""
}


# Define which attributes to keep for entities
KEEP_ENTITY_ATTRIBUTES = {
    "JOB": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "APPLICATION": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "MODULE": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "FILE": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "RECORD": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "FILESYSTEM": ["entity_name", "entity_type", "description", "source_id", "file_path"]
}

# Define which attributes to keep for relationships
KEEP_RELATIONSHIP_ATTRIBUTES = ["src_id", "tgt_id", "description", "keywords", "weight", "source_id", "file_path"]


def get_value_or_na(obj, key, default="N/A"):
    """Get value from object, returning default if missing or None."""
    value = obj.get(key)
    if value is None or value == "":
        return default
    return value


def fill_template(template, obj, track_usage=None, obj_type="entity"):
    """Fill template with object attributes."""
    # Find all placeholders in the template
    placeholders = re.findall(r'\{(\w+)\}', template)

    filled = template
    for placeholder in placeholders:
        value = get_value_or_na(obj, placeholder)

        # Track which placeholders were actually filled (not N/A)
        if track_usage is not None:
            if obj_type not in track_usage["placeholders"]:
                track_usage["placeholders"][obj_type] = {}
            if placeholder not in track_usage["placeholders"][obj_type]:
                track_usage["placeholders"][obj_type][placeholder] = {"used": 0, "missing": 0}

            if value != "N/A":
                track_usage["placeholders"][obj_type][placeholder]["used"] += 1
            else:
                track_usage["placeholders"][obj_type][placeholder]["missing"] += 1

        filled = filled.replace(f"{{{placeholder}}}", str(value))

    return filled


def generate_entity_description(entity, track_usage=None):
    """Generate description for an entity based on its type."""
    entity_type = entity.get("entity_type")

    if entity_type not in ENTITY_TEMPLATES:
        return ""

    template = ENTITY_TEMPLATES[entity_type]
    return fill_template(template, entity, track_usage, obj_type=entity_type)


def generate_relationship_description(relationship, entities_by_name, track_usage=None):
    """Generate description for a relationship based on src and tgt entity types."""
    src_id = relationship.get("src_id")
    tgt_id = relationship.get("tgt_id")

    # Get entity types
    src_entity = entities_by_name.get(src_id)
    tgt_entity = entities_by_name.get(tgt_id)

    if not src_entity or not tgt_entity:
        return ""

    src_type = src_entity.get("entity_type")
    tgt_type = tgt_entity.get("entity_type")

    # Find template for this relationship type
    template_key = (src_type, tgt_type)
    if template_key not in RELATIONSHIP_TEMPLATES:
        return ""

    template = RELATIONSHIP_TEMPLATES[template_key]

    # Merge relationship attributes with relevant entity attributes for template filling
    merged = dict(relationship)
    # Add entity attributes that might be referenced in template
    merged.update({k: v for k, v in src_entity.items() if k not in merged})
    merged.update({k: v for k, v in tgt_entity.items() if k not in merged})

    obj_type_key = f"{src_type}→{tgt_type}"
    return fill_template(template, merged, track_usage, obj_type=obj_type_key)


def clean_entity(entity):
    """Remove extra attributes, keeping only those in KEEP_ENTITY_ATTRIBUTES."""
    entity_type = entity.get("entity_type")
    if entity_type not in KEEP_ENTITY_ATTRIBUTES:
        return entity

    keep_attrs = KEEP_ENTITY_ATTRIBUTES[entity_type]
    cleaned = {key: entity[key] for key in keep_attrs if key in entity}

    return cleaned


def clean_relationship(relationship):
    """Remove extra attributes, keeping only those in KEEP_RELATIONSHIP_ATTRIBUTES."""
    cleaned = {key: relationship[key] for key in KEEP_RELATIONSHIP_ATTRIBUTES if key in relationship}
    return cleaned


def print_usage_statistics(track_usage, all_entity_attributes, all_relationship_attributes):
    """Print statistics about unused placeholders and attributes."""
    print("\n" + "="*70)
    print("使用统计报告")
    print("="*70)

    # Part 1: Entity template placeholders that were never filled
    print("\n【1】实体模板中永远没有匹配到的属性（总是 N/A）:")
    print("-" * 70)

    entity_types = [k for k in track_usage["placeholders"].keys() if "→" not in k]
    for entity_type in sorted(entity_types):
        placeholders = track_usage["placeholders"][entity_type]
        never_filled = []

        for placeholder, stats in placeholders.items():
            if stats["used"] == 0 and stats["missing"] > 0:
                never_filled.append(f"{placeholder} (缺失{stats['missing']}次)")

        if never_filled:
            print(f"\n  {entity_type}:")
            for item in never_filled:
                print(f"    - {item}")

    # Part 2: Relationship template placeholders that were never filled
    print("\n【2】关系模板中永远没有匹配到的属性（总是 N/A）:")
    print("-" * 70)

    rel_types = [k for k in track_usage["placeholders"].keys() if "→" in k]
    for rel_type in sorted(rel_types):
        placeholders = track_usage["placeholders"][rel_type]
        never_filled = []

        for placeholder, stats in placeholders.items():
            if stats["used"] == 0 and stats["missing"] > 0:
                never_filled.append(f"{placeholder} (缺失{stats['missing']}次)")

        if never_filled:
            print(f"\n  {rel_type}:")
            for item in never_filled:
                print(f"    - {item}")

    # Part 3: JSON entity attributes that were never used in templates
    print("\n\n【3】实体 JSON 中永远没有用到的属性:")
    print("-" * 70)

    for entity_type in sorted(all_entity_attributes.keys()):
        # Get all placeholders used in this entity type's template
        template_placeholders = set()

        if entity_type in ENTITY_TEMPLATES:
            template = ENTITY_TEMPLATES[entity_type]
            template_placeholders = set(re.findall(r'\{(\w+)\}', template))

        # Get all attributes from JSON entities of this type
        json_attributes = all_entity_attributes[entity_type]

        # Find attributes that are never referenced in templates
        excluded = {"entity_name", "entity_type", "description", "source_id", "file_path"}
        unused_attributes = []

        for attr in sorted(json_attributes):
            if attr not in excluded and attr not in template_placeholders:
                unused_attributes.append(attr)

        if unused_attributes:
            print(f"\n  {entity_type} ({len(unused_attributes)}个未使用属性):")
            for attr in unused_attributes:
                print(f"    - {attr}")

    # Part 4: Summary
    print("\n\n【4】总体统计:")
    print("-" * 70)

    for obj_type in sorted(track_usage["placeholders"].keys()):
        placeholders = track_usage["placeholders"][obj_type]
        total_placeholders = len(placeholders)
        never_filled = sum(1 for stats in placeholders.values() if stats["used"] == 0)
        sometimes_filled = sum(1 for stats in placeholders.values() if stats["used"] > 0 and stats["missing"] > 0)
        always_filled = sum(1 for stats in placeholders.values() if stats["missing"] == 0)

        print(f"\n  {obj_type}:")
        print(f"    模板占位符总数: {total_placeholders}")
        print(f"    - 总是有值: {always_filled}")
        print(f"    - 有时有值: {sometimes_filled}")
        print(f"    - 从不有值: {never_filled}")

    print("\n" + "="*70)


def process_json_file(input_path, output_path):
    """Process JSON file: generate descriptions for entities and relationships."""
    print(f"Reading {input_path}...")
    with open(input_path, 'r') as f:
        data = json.load(f)

    if "entities" not in data or "relationships" not in data:
        print("Error: JSON file must contain 'entities' and 'relationships' keys")
        return

    print(f"Processing {len(data['entities'])} entities and {len(data['relationships'])} relationships...")

    # Track usage statistics
    track_usage = {
        "placeholders": {}
    }

    # Collect all attributes by type
    all_entity_attributes = defaultdict(set)
    for entity in data['entities']:
        entity_type = entity.get("entity_type", "UNKNOWN")
        all_entity_attributes[entity_type].update(entity.keys())

    all_relationship_attributes = set()
    for rel in data['relationships']:
        all_relationship_attributes.update(rel.keys())

    # Build entity lookup by name
    entities_by_name = {e['entity_name']: e for e in data['entities']}

    # Process entities
    processed_entities = []
    for i, entity in enumerate(data['entities']):
        # Generate description FIRST (before cleaning)
        description = generate_entity_description(entity, track_usage)
        entity["description"] = description

        # Clean entity (remove extra attributes)
        cleaned = clean_entity(entity)
        processed_entities.append(cleaned)

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} entities...")

    # Process relationships
    processed_relationships = []
    for i, relationship in enumerate(data['relationships']):
        # Generate description
        description = generate_relationship_description(relationship, entities_by_name, track_usage)
        relationship["description"] = description

        # Clean relationship (remove extra attributes)
        cleaned = clean_relationship(relationship)
        processed_relationships.append(cleaned)

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} relationships...")

    # Replace with processed versions
    data['entities'] = processed_entities
    data['relationships'] = processed_relationships

    print(f"Writing to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print("Done!")

    # Print usage statistics
    print_usage_statistics(track_usage, all_entity_attributes, all_relationship_attributes)


def process_directory(input_dir, output_dir):
    """Process all JSON files in a directory tree, preserving structure."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        print(f"Error: Input directory {input_dir} does not exist")
        return

    if not input_path.is_dir():
        print(f"Error: {input_dir} is not a directory")
        return

    # Find all JSON files recursively
    json_files = list(input_path.rglob("*.json"))

    if not json_files:
        print(f"Warning: No JSON files found in {input_dir}")
        return

    print(f"Found {len(json_files)} JSON files in {input_dir}")
    print()

    # Process each JSON file
    for i, json_file in enumerate(json_files, 1):
        # Compute relative path from input directory
        rel_path = json_file.relative_to(input_path)

        # Construct output path preserving directory structure
        output_file = output_path / rel_path.parent / f"{rel_path.stem}_with_descriptions{rel_path.suffix}"

        # Create output directory if it doesn't exist
        output_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"[{i}/{len(json_files)}] Processing: {rel_path}")
        print(f"  → Output: {output_file.relative_to(output_path)}")

        try:
            process_json_file(str(json_file), str(output_file))
        except Exception as e:
            print(f"  ✗ Error: {e}")

        print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_descriptions_v3.py <input> [output]")
        print()
        print("Arguments:")
        print("  <input>   Input JSON file or directory")
        print("  [output]  Output JSON file or directory (optional)")
        print()
        print("Examples:")
        print("  # Single file")
        print("  python generate_descriptions_v3.py input.json output.json")
        print()
        print("  # Directory (preserves structure)")
        print("  python generate_descriptions_v3.py input_dir/ output_dir/")
        print()
        print("  # Auto-generate output path")
        print("  python generate_descriptions_v3.py input.json")
        print("  # → Creates: input_with_descriptions.json")
        print()
        print("  python generate_descriptions_v3.py input_dir/")
        print("  # → Creates: input_dir_with_descriptions/")
        sys.exit(1)

    input_arg = sys.argv[1]
    input_path = Path(input_arg)

    # Check if input is a file or directory
    if input_path.is_file():
        # Single file mode
        if len(sys.argv) >= 3:
            output_path = sys.argv[2]
        else:
            output_path = input_path.parent / f"{input_path.stem}_with_descriptions{input_path.suffix}"

        process_json_file(str(input_path), str(output_path))

    elif input_path.is_dir():
        # Directory mode
        if len(sys.argv) >= 3:
            output_dir = sys.argv[2]
        else:
            # Auto-generate output directory name
            output_dir = input_path.parent / f"{input_path.name}_with_descriptions"

        process_directory(str(input_path), str(output_dir))

    else:
        print(f"Error: {input_arg} is neither a file nor a directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
