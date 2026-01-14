#!/usr/bin/env python3
"""
Generate entity descriptions from Darshan log JSON files.
Fills templates with entity attributes and cleans up extra properties.
"""

import json
import sys
from pathlib import Path


# Template definitions
TEMPLATES = {
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

    "FILE_SYSTEM": """This FILE SYSTEM entity describes the storage backend used during execution, capturing the type and mounting context of the filesystem.

The filesystem is mounted at mount_pt {mount_pt} and is identified as fs_type {fs_type}.

This entity provides environmental context for interpreting I/O behavior, including performance characteristics and metadata handling semantics that are shared across all files on this filesystem.""",

    "FILESYSTEM": """This FILE SYSTEM entity describes the storage backend used during execution, capturing the type and mounting context of the filesystem.

The filesystem is mounted at mount_pt {mount_pt} and is identified as fs_type {fs_type}.

This entity provides environmental context for interpreting I/O behavior, including performance characteristics and metadata handling semantics that are shared across all files on this filesystem."""
}


# Define which attributes to keep for each entity type (all others will be removed)
KEEP_ATTRIBUTES = {
    "JOB": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "APPLICATION": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "MODULE": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "FILE": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "RECORD": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "FILE_SYSTEM": ["entity_name", "entity_type", "description", "source_id", "file_path"],
    "FILESYSTEM": ["entity_name", "entity_type", "description", "source_id", "file_path"]
}


def get_value_or_na(entity, key, default="N/A"):
    """Get value from entity, returning default if missing or None."""
    value = entity.get(key)
    if value is None or value == "":
        return default
    return value


def fill_template(template, entity, track_usage=None):
    """Fill template with entity attributes."""
    # Find all placeholders in the template
    import re
    placeholders = re.findall(r'\{(\w+)\}', template)

    filled = template
    for placeholder in placeholders:
        value = get_value_or_na(entity, placeholder)

        # Track which placeholders were actually filled (not N/A)
        if track_usage is not None:
            entity_type = entity.get("entity_type", "UNKNOWN")
            if entity_type not in track_usage["placeholders"]:
                track_usage["placeholders"][entity_type] = {}
            if placeholder not in track_usage["placeholders"][entity_type]:
                track_usage["placeholders"][entity_type][placeholder] = {"used": 0, "missing": 0}

            if value != "N/A":
                track_usage["placeholders"][entity_type][placeholder]["used"] += 1
            else:
                track_usage["placeholders"][entity_type][placeholder]["missing"] += 1

        filled = filled.replace(f"{{{placeholder}}}", str(value))

    return filled


def generate_record_description_with_io_types(entity, track_usage=None):
    """
    Generate RECORD description with separate read_start_ts, write_start_ts, meta_start_ts.
    This follows the requirement to split {io_start_ts} into read, write, meta variants.
    For each section, only {io_start_ts} is replaced with the specific type variant.
    """
    template = TEMPLATES["RECORD"]

    # Replace {io_start_ts} with read_start_ts
    read_desc = template.replace("{io_start_ts}", "{read_start_ts}")
    read_filled = fill_template(read_desc, entity, track_usage)

    # Replace {io_start_ts} with write_start_ts
    write_desc = template.replace("{io_start_ts}", "{write_start_ts}")
    write_filled = fill_template(write_desc, entity, track_usage)

    # Replace {io_start_ts} with meta_start_ts
    meta_desc = template.replace("{io_start_ts}", "{meta_start_ts}")
    meta_filled = fill_template(meta_desc, entity, track_usage)

    # Combine all three
    full_description = f"""READ I/O ACTIVITY:
{read_filled}

⸻

WRITE I/O ACTIVITY:
{write_filled}

⸻

METADATA I/O ACTIVITY:
{meta_filled}"""

    return full_description


def generate_description(entity, track_usage=None):
    """Generate description based on entity type."""
    entity_type = entity.get("entity_type")

    if entity_type not in TEMPLATES:
        return ""

    # Special handling for RECORD to split io_start_ts into read/write/meta
    if entity_type == "RECORD":
        return generate_record_description_with_io_types(entity, track_usage)

    template = TEMPLATES[entity_type]
    return fill_template(template, entity, track_usage)


def clean_entity(entity):
    """Remove extra attributes, keeping only those in KEEP_ATTRIBUTES."""
    entity_type = entity.get("entity_type")
    if entity_type not in KEEP_ATTRIBUTES:
        return entity

    keep_attrs = KEEP_ATTRIBUTES[entity_type]
    cleaned = {key: entity[key] for key in keep_attrs if key in entity}

    return cleaned


def print_usage_statistics(track_usage, all_attributes_by_type):
    """Print statistics about unused placeholders and attributes."""
    import re

    print("\n" + "="*70)
    print("使用统计报告")
    print("="*70)

    # Part 1: Template placeholders that were never filled (always N/A)
    print("\n【1】模板中永远没有匹配到的属性（总是 N/A）:")
    print("-" * 70)

    for entity_type in sorted(track_usage["placeholders"].keys()):
        placeholders = track_usage["placeholders"][entity_type]
        never_filled = []

        for placeholder, stats in placeholders.items():
            # If it was never used (always N/A)
            if stats["used"] == 0 and stats["missing"] > 0:
                never_filled.append(f"{placeholder} (缺失{stats['missing']}次)")

        if never_filled:
            print(f"\n  {entity_type}:")
            for item in never_filled:
                print(f"    - {item}")

    # Part 2: JSON attributes that were never used in templates
    print("\n\n【2】JSON中永远没有用到的属性:")
    print("-" * 70)

    for entity_type in sorted(all_attributes_by_type.keys()):
        # Get all placeholders used in this entity type's template
        template_placeholders = set()

        if entity_type in TEMPLATES:
            template = TEMPLATES[entity_type]
            # For RECORD, we need to check the modified templates too
            if entity_type == "RECORD":
                template = template.replace("{io_start_ts}", "{read_start_ts}")
                template += TEMPLATES["RECORD"].replace("{io_start_ts}", "{write_start_ts}")
                template += TEMPLATES["RECORD"].replace("{io_start_ts}", "{meta_start_ts}")

            template_placeholders = set(re.findall(r'\{(\w+)\}', template))

        # Get all attributes from JSON entities of this type
        json_attributes = all_attributes_by_type[entity_type]

        # Find attributes that are never referenced in templates
        # Exclude the standard ones we always keep
        excluded = {"entity_name", "entity_type", "description", "source_id", "file_path"}
        unused_attributes = []

        for attr in sorted(json_attributes):
            if attr not in excluded and attr not in template_placeholders:
                unused_attributes.append(attr)

        if unused_attributes:
            print(f"\n  {entity_type} ({len(unused_attributes)}个未使用属性):")
            for attr in unused_attributes:
                print(f"    - {attr}")

    # Part 3: Summary statistics
    print("\n\n【3】总体统计:")
    print("-" * 70)

    for entity_type in sorted(track_usage["placeholders"].keys()):
        placeholders = track_usage["placeholders"][entity_type]
        total_placeholders = len(placeholders)
        never_filled = sum(1 for stats in placeholders.values() if stats["used"] == 0)
        sometimes_filled = sum(1 for stats in placeholders.values() if stats["used"] > 0 and stats["missing"] > 0)
        always_filled = sum(1 for stats in placeholders.values() if stats["missing"] == 0)

        print(f"\n  {entity_type}:")
        print(f"    模板占位符总数: {total_placeholders}")
        print(f"    - 总是有值: {always_filled}")
        print(f"    - 有时有值: {sometimes_filled}")
        print(f"    - 从不有值: {never_filled}")

    print("\n" + "="*70)


def process_json_file(input_path, output_path):
    """Process JSON file: generate descriptions and clean entities."""
    print(f"Reading {input_path}...")
    with open(input_path, 'r') as f:
        data = json.load(f)

    if "entities" not in data:
        print("Error: JSON file does not contain 'entities' key")
        return

    print(f"Processing {len(data['entities'])} entities...")

    # Track usage statistics
    track_usage = {
        "placeholders": {},  # Which template placeholders were used/missing
        "attributes": {}     # Which entity attributes were never used
    }

    # Collect all attributes from all entities by type
    all_attributes_by_type = {}
    for entity in data['entities']:
        entity_type = entity.get("entity_type", "UNKNOWN")
        if entity_type not in all_attributes_by_type:
            all_attributes_by_type[entity_type] = set()
        all_attributes_by_type[entity_type].update(entity.keys())

    processed_entities = []
    for i, entity in enumerate(data['entities']):
        entity_type = entity.get("entity_type", "UNKNOWN")

        # Track which attributes from this entity are accessed
        if entity_type not in track_usage["attributes"]:
            track_usage["attributes"][entity_type] = {}

        # Mark all attributes as potentially unused initially
        for attr in entity.keys():
            if attr not in track_usage["attributes"][entity_type]:
                track_usage["attributes"][entity_type][attr] = 0

        # IMPORTANT: Generate description FIRST (before cleaning)
        # so that all original attributes are still available
        description = generate_description(entity, track_usage)
        entity["description"] = description

        # Track which attributes were actually accessed in the description
        # (This is done in fill_template via track_usage)

        # NOW clean entity (remove extra attributes)
        cleaned = clean_entity(entity)
        processed_entities.append(cleaned)

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} entities...")

    # Replace entities with processed ones
    data['entities'] = processed_entities

    print(f"Writing to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print("Done!")

    # Print usage statistics
    print_usage_statistics(track_usage, all_attributes_by_type)


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_entity_descriptions.py <input_json> [output_json]")
        print("Example: python generate_entity_descriptions.py input.json output.json")
        sys.exit(1)

    input_path = sys.argv[1]

    # Default output path
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        input_file = Path(input_path)
        output_path = input_file.parent / f"{input_file.stem}_with_descriptions{input_file.suffix}"

    process_json_file(input_path, output_path)


if __name__ == "__main__":
    main()
