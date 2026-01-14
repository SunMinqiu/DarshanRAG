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
    "JOB": ["entity_name", "entity_type", "description", "source_id"],
    "APPLICATION": ["entity_name", "entity_type", "description", "source_id"],
    "MODULE": ["entity_name", "entity_type", "description", "source_id"],
    "FILE": ["entity_name", "entity_type", "description", "source_id"],
    "RECORD": ["entity_name", "entity_type", "description", "source_id"],
    "FILE_SYSTEM": ["entity_name", "entity_type", "description", "source_id"],
    "FILESYSTEM": ["entity_name", "entity_type", "description", "source_id"]
}


def get_value_or_na(entity, key, default="N/A"):
    """Get value from entity, returning default if missing or None."""
    value = entity.get(key)
    if value is None or value == "":
        return default
    return value


def generate_record_description_with_io_types(entity):
    """
    Generate RECORD description with separate read_start_ts, write_start_ts, meta_start_ts.
    This follows the requirement to split {io_start_ts} into read, write, meta variants.
    For each section, only {io_start_ts} is replaced with the specific type variant.
    """
    template = TEMPLATES["RECORD"]

    # Replace {io_start_ts} with read_start_ts
    read_desc = template.replace("{io_start_ts}", "{read_start_ts}")
    read_filled = fill_template(read_desc, entity)

    # Replace {io_start_ts} with write_start_ts
    write_desc = template.replace("{io_start_ts}", "{write_start_ts}")
    write_filled = fill_template(write_desc, entity)

    # Replace {io_start_ts} with meta_start_ts
    meta_desc = template.replace("{io_start_ts}", "{meta_start_ts}")
    meta_filled = fill_template(meta_desc, entity)

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


def fill_template(template, entity):
    """Fill template with entity attributes."""
    # Find all placeholders in the template
    import re
    placeholders = re.findall(r'\{(\w+)\}', template)

    filled = template
    for placeholder in placeholders:
        value = get_value_or_na(entity, placeholder)
        filled = filled.replace(f"{{{placeholder}}}", str(value))

    return filled


def generate_description(entity):
    """Generate description based on entity type."""
    entity_type = entity.get("entity_type")

    if entity_type not in TEMPLATES:
        return ""

    # Special handling for RECORD to split io_start_ts into read/write/meta
    if entity_type == "RECORD":
        return generate_record_description_with_io_types(entity)

    template = TEMPLATES[entity_type]
    return fill_template(template, entity)


def clean_entity(entity):
    """Remove extra attributes, keeping only those in KEEP_ATTRIBUTES."""
    entity_type = entity.get("entity_type")
    if entity_type not in KEEP_ATTRIBUTES:
        return entity

    keep_attrs = KEEP_ATTRIBUTES[entity_type]
    cleaned = {key: entity[key] for key in keep_attrs if key in entity}

    return cleaned


def process_json_file(input_path, output_path):
    """Process JSON file: generate descriptions and clean entities."""
    print(f"Reading {input_path}...")
    with open(input_path, 'r') as f:
        data = json.load(f)

    if "entities" not in data:
        print("Error: JSON file does not contain 'entities' key")
        return

    print(f"Processing {len(data['entities'])} entities...")

    for i, entity in enumerate(data['entities']):
        # Generate description
        description = generate_description(entity)
        entity["description"] = description

        # Clean entity (remove extra attributes)
        cleaned = clean_entity(entity)
        data['entities'][i] = cleaned

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} entities...")

    print(f"Writing to {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print("Done!")


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
