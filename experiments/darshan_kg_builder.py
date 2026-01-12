#!/usr/bin/env python3
"""
Darshan Log to LightRAG Knowledge Graph Builder

This script converts Darshan signal extraction output (v2.2 format) into
LightRAG's custom KG format for incident-level retrieval and analysis.

Design Principles:
1. Incident = Minimum retrievable unit (one record = one incident)
2. Signals = Node attributes (not separate nodes)
3. Graph connectivity = Comparability (not semantic similarity)

Node Types:
- Job: One per Darshan log
- Incident: One per record (HEATMAP/POSIX/STDIO/MPIIO)
- FileSystem: Unique (mount_point, fs_type) combinations
- Application: Unique exe identifier

Edge Types:
- Job -> Incident: HAS_INCIDENT (containment)
- Incident -> FileSystem: ON_FS (conditional, for real file I/O)
- Job -> Application: RUNS
- Incident -> Application: BELONGS_TO
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict


class DarshanKGBuilder:
    """Build Knowledge Graph from Darshan signal extraction output."""

    def __init__(self):
        self.job_info = {}
        self.mount_table = {}  # mount_point -> fs_type
        self.incidents = []  # List of incident records
        self.filesystems = {}  # (mount_point, fs_type) -> FS info
        self.applications = {}  # exe -> App info

    def parse_darshan_signal_file(self, file_path: str) -> None:
        """Parse a single Darshan signal extraction output file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse job-level metadata from header
        self._parse_job_metadata(content)

        # Parse mount table
        self._parse_mount_table(content)

        # Parse incidents by module
        self._parse_heatmap_incidents(content)
        self._parse_posix_incidents(content)
        self._parse_stdio_incidents(content)
        # TODO: Add MPIIO if needed

    def _parse_job_metadata(self, content: str) -> None:
        """Extract job-level metadata from header."""
        # Parse job metadata
        job_id_match = re.search(r'#\s+jobid:\s+(\d+)', content)
        nprocs_match = re.search(r'#\s+nprocs:\s+(\d+)', content)
        runtime_match = re.search(r'#\s+run time:\s+([\d.]+)', content)
        exe_match = re.search(r'#\s+exe:\s+(\S+)', content)
        start_time_match = re.search(r'#\s+start_time:\s+(\d+)', content)
        end_time_match = re.search(r'#\s+end_time:\s+(\d+)', content)

        if job_id_match:
            self.job_info = {
                "job_id": int(job_id_match.group(1)),
                "nprocs": int(nprocs_match.group(1)) if nprocs_match else None,
                "runtime": float(runtime_match.group(1)) if runtime_match else None,
                "exe": exe_match.group(1) if exe_match else None,
                "start_time": int(start_time_match.group(1)) if start_time_match else None,
                "end_time": int(end_time_match.group(1)) if end_time_match else None,
            }

            # Register application
            if self.job_info.get("exe"):
                self.applications[self.job_info["exe"]] = {
                    "exe": self.job_info["exe"]
                }

    def _parse_mount_table(self, content: str) -> None:
        """Parse mount table from header."""
        mount_entries = re.findall(r'#\s+mount entry:\s+(\S+)\s+(\S+)', content)
        for mount_point, fs_type in mount_entries:
            self.mount_table[mount_point] = fs_type

    def _parse_heatmap_incidents(self, content: str) -> None:
        """Parse HEATMAP module incidents."""
        # Find HEATMAP module section
        heatmap_section = re.search(
            r'# MODULE: HEATMAP\s+#.*?(?=# MODULE:|# ={60}|$)',
            content,
            re.DOTALL
        )

        if not heatmap_section:
            return

        heatmap_content = heatmap_section.group(0)

        # Split into record sections
        record_sections = re.split(
            r'# -{60}\s+# RECORD: (\d+) \(rank=(-?\d+)\)',
            heatmap_content
        )

        # Process each record (skip first empty section)
        for i in range(1, len(record_sections), 3):
            if i + 2 >= len(record_sections):
                break

            record_id = record_sections[i]
            rank = int(record_sections[i + 1])
            record_content = record_sections[i + 2]

            # Extract file_name
            file_name_match = re.search(r'#\s+file_name:\s+(.+)', record_content)
            file_name = file_name_match.group(1).strip() if file_name_match else "UNKNOWN"

            # Parse all SIGNAL_* fields
            incident = {
                "module": "HEATMAP",
                "rank": rank,
                "record_id": record_id,
                "file_name": file_name,
                "mount_pt": "UNKNOWN",
                "fs_type": "UNKNOWN"
            }

            # Extract signals
            signal_pattern = r'HEATMAP\s+' + str(rank) + r'\s+' + record_id + r'\s+SIGNAL_(\w+)\s+([\d.]+|NA\(.*?\))'
            signals = re.findall(signal_pattern, record_content)

            for signal_name, signal_value in signals:
                # Convert to appropriate type
                if signal_value.startswith("NA"):
                    incident[signal_name.lower()] = signal_value
                elif '.' in signal_value:
                    incident[signal_name.lower()] = float(signal_value)
                else:
                    incident[signal_name.lower()] = int(float(signal_value))

            self.incidents.append(incident)

    def _parse_posix_incidents(self, content: str) -> None:
        """Parse POSIX module incidents."""
        # Find POSIX module section
        posix_section = re.search(
            r'# MODULE: POSIX\s+#.*?(?=# MODULE:|# ={60}|$)',
            content,
            re.DOTALL
        )

        if not posix_section:
            return

        posix_content = posix_section.group(0)

        # Split into record sections
        record_sections = re.split(
            r'# -{60}\s+# RECORD: (\d+) \(rank=(-?\d+)\)',
            posix_content
        )

        # Process each record
        for i in range(1, len(record_sections), 3):
            if i + 2 >= len(record_sections):
                break

            record_id = record_sections[i]
            rank = int(record_sections[i + 1])
            record_content = record_sections[i + 2]

            # Extract file metadata
            file_name_match = re.search(r'#\s+file_name:\s+(.+)', record_content)
            mount_pt_match = re.search(r'#\s+mount_pt:\s+(.+)', record_content)
            fs_type_match = re.search(r'#\s+fs_type:\s+(.+)', record_content)

            file_name = file_name_match.group(1).strip() if file_name_match else "UNKNOWN"
            mount_pt = mount_pt_match.group(1).strip() if mount_pt_match else "UNKNOWN"
            fs_type = fs_type_match.group(1).strip() if fs_type_match else "UNKNOWN"

            # Create incident
            incident = {
                "module": "POSIX",
                "rank": rank,
                "record_id": record_id,
                "file_name": file_name,
                "mount_pt": mount_pt,
                "fs_type": fs_type
            }

            # Extract signals
            signal_pattern = r'POSIX\s+' + str(rank) + r'\s+' + record_id + r'\s+SIGNAL_(\w+)\s+([\d.]+|NA\(.*?\))'
            signals = re.findall(signal_pattern, record_content)

            for signal_name, signal_value in signals:
                # Convert to appropriate type
                if signal_value.startswith("NA"):
                    incident[signal_name.lower()] = signal_value
                elif '.' in signal_value:
                    incident[signal_name.lower()] = float(signal_value)
                else:
                    incident[signal_name.lower()] = int(float(signal_value))

            self.incidents.append(incident)

            # Register filesystem if valid
            if fs_type != "UNKNOWN" and mount_pt != "UNKNOWN":
                fs_key = (mount_pt, fs_type)
                if fs_key not in self.filesystems:
                    self.filesystems[fs_key] = {
                        "fs_type": fs_type,
                        "mount_point": mount_pt
                    }

    def _parse_stdio_incidents(self, content: str) -> None:
        """Parse STDIO module incidents."""
        # Find STDIO module section
        stdio_section = re.search(
            r'# MODULE: STDIO\s+#.*?(?=# MODULE:|# ={60}|$)',
            content,
            re.DOTALL
        )

        if not stdio_section:
            return

        stdio_content = stdio_section.group(0)

        # Split into record sections
        record_sections = re.split(
            r'# -{60}\s+# RECORD: (\d+) \(rank=(-?\d+)\)',
            stdio_content
        )

        # Process each record
        for i in range(1, len(record_sections), 3):
            if i + 2 >= len(record_sections):
                break

            record_id = record_sections[i]
            rank = int(record_sections[i + 1])
            record_content = record_sections[i + 2]

            # Extract file metadata
            file_name_match = re.search(r'#\s+file_name:\s+(.+)', record_content)
            mount_pt_match = re.search(r'#\s+mount_pt:\s+(.+)', record_content)
            fs_type_match = re.search(r'#\s+fs_type:\s+(.+)', record_content)

            file_name = file_name_match.group(1).strip() if file_name_match else "UNKNOWN"
            mount_pt = mount_pt_match.group(1).strip() if mount_pt_match else "UNKNOWN"
            fs_type = fs_type_match.group(1).strip() if fs_type_match else "UNKNOWN"

            # Create incident
            incident = {
                "module": "STDIO",
                "rank": rank,
                "record_id": record_id,
                "file_name": file_name,
                "mount_pt": mount_pt,
                "fs_type": fs_type
            }

            # Extract signals
            signal_pattern = r'STDIO\s+' + str(rank) + r'\s+' + record_id + r'\s+SIGNAL_(\w+)\s+([\d.]+|NA\(.*?\))'
            signals = re.findall(signal_pattern, record_content)

            for signal_name, signal_value in signals:
                # Convert to appropriate type
                if signal_value.startswith("NA"):
                    incident[signal_name.lower()] = signal_value
                elif '.' in signal_value:
                    incident[signal_name.lower()] = float(signal_value)
                else:
                    incident[signal_name.lower()] = int(float(signal_value))

            self.incidents.append(incident)

            # Register filesystem if valid
            if fs_type != "UNKNOWN" and mount_pt != "UNKNOWN":
                fs_key = (mount_pt, fs_type)
                if fs_key not in self.filesystems:
                    self.filesystems[fs_key] = {
                        "fs_type": fs_type,
                        "mount_point": mount_pt
                    }

    def build_lightrag_kg(self, source_id: str, file_path: str) -> Dict:
        """
        Build LightRAG custom KG format from parsed data.

        Returns:
            Dict in LightRAG custom KG format with:
            - chunks: Text descriptions
            - entities: Job, Incident, FileSystem, Application nodes
            - relationships: Edges between entities
        """
        chunks = []
        entities = []
        relationships = []

        # 1. Create Job entity
        job_id = str(self.job_info.get("job_id", "unknown"))
        job_entity_name = f"Job_{job_id}"

        job_desc_parts = [
            f"Darshan Job {job_id}",
            f"Processes: {self.job_info.get('nprocs', 'N/A')}",
            f"Runtime: {self.job_info.get('runtime', 'N/A')} seconds",
            f"Executable: {self.job_info.get('exe', 'N/A')}"
        ]

        entities.append({
            "entity_name": job_entity_name,
            "entity_type": "JOB",
            "description": ", ".join(job_desc_parts),
            "source_id": source_id,
            "file_path": file_path,
            **{k: v for k, v in self.job_info.items() if v is not None}
        })

        # Create chunk for job
        chunks.append({
            "content": f"Job {job_id} executed {self.job_info.get('exe', 'unknown executable')} with {self.job_info.get('nprocs', 'N/A')} processes for {self.job_info.get('runtime', 'N/A')} seconds.",
            "source_id": source_id,
            "file_path": file_path
        })

        # 2. Create Application entity
        exe = self.job_info.get("exe")
        if exe:
            app_entity_name = f"App_{exe}"
            entities.append({
                "entity_name": app_entity_name,
                "entity_type": "APPLICATION",
                "description": f"Application with executable identifier {exe}",
                "source_id": source_id,
                "file_path": file_path,
                "exe": exe
            })

            # Job -> Application: RUNS
            relationships.append({
                "src_id": job_entity_name,
                "tgt_id": app_entity_name,
                "description": f"Job {job_id} runs application {exe}",
                "keywords": "executes runs application",
                "weight": 1.0,
                "source_id": source_id,
                "file_path": file_path
            })

        # 3. Create FileSystem entities
        fs_entity_map = {}  # (mount_pt, fs_type) -> entity_name
        for (mount_pt, fs_type), fs_info in self.filesystems.items():
            fs_entity_name = f"FS_{fs_type}_{mount_pt.replace('/', '_')}"
            fs_entity_map[(mount_pt, fs_type)] = fs_entity_name

            entities.append({
                "entity_name": fs_entity_name,
                "entity_type": "FILESYSTEM",
                "description": f"File system {fs_type} mounted at {mount_pt}",
                "source_id": source_id,
                "file_path": file_path,
                "fs_type": fs_type,
                "mount_point": mount_pt
            })

        # 4. Create Incident entities and relationships
        for idx, incident in enumerate(self.incidents):
            incident_entity_name = f"Incident_{incident['module']}_{incident['record_id']}_rank{incident['rank']}"

            # Build description
            desc_parts = [
                f"{incident['module']} I/O incident",
                f"Rank {incident['rank']}",
                f"Record ID {incident['record_id']}"
            ]

            if incident.get('file_name') and incident['file_name'] != "UNKNOWN":
                desc_parts.append(f"File: {incident['file_name']}")

            # Add key signals to description
            if incident.get('total_read_events'):
                desc_parts.append(f"Read events: {incident['total_read_events']}")
            if incident.get('total_write_events'):
                desc_parts.append(f"Write events: {incident['total_write_events']}")
            if incident.get('read_bw') and not str(incident['read_bw']).startswith('NA'):
                desc_parts.append(f"Read BW: {incident['read_bw']}")

            # Create entity with all signals as attributes
            entity_data = {
                "entity_name": incident_entity_name,
                "entity_type": "INCIDENT",
                "description": "; ".join(desc_parts),
                "source_id": source_id,
                "file_path": file_path
            }

            # Add all incident attributes (signals)
            entity_data.update(incident)
            entities.append(entity_data)

            # Create chunk for incident
            chunk_content = f"{incident['module']} incident on rank {incident['rank']}: "
            signal_descriptions = []
            for key, value in incident.items():
                if key not in ['module', 'rank', 'record_id', 'file_name', 'mount_pt', 'fs_type']:
                    if not str(value).startswith('NA'):
                        signal_descriptions.append(f"{key}={value}")

            if signal_descriptions:
                chunk_content += ", ".join(signal_descriptions[:10])  # Limit to first 10 signals

            chunks.append({
                "content": chunk_content,
                "source_id": source_id,
                "file_path": file_path
            })

            # Job -> Incident: HAS_INCIDENT
            relationships.append({
                "src_id": job_entity_name,
                "tgt_id": incident_entity_name,
                "description": f"Job {job_id} contains {incident['module']} incident on rank {incident['rank']}",
                "keywords": "contains has incident record",
                "weight": 1.0,
                "source_id": source_id,
                "file_path": file_path
            })

            # Incident -> FileSystem: ON_FS (conditional)
            if (incident['module'] in ['POSIX', 'STDIO', 'MPIIO'] and
                incident.get('fs_type') not in [None, "UNKNOWN", "NONE"] and
                incident.get('mount_pt') not in [None, "UNKNOWN", "NONE"]):

                fs_key = (incident['mount_pt'], incident['fs_type'])
                if fs_key in fs_entity_map:
                    fs_entity_name = fs_entity_map[fs_key]
                    relationships.append({
                        "src_id": incident_entity_name,
                        "tgt_id": fs_entity_name,
                        "description": f"{incident['module']} incident operates on {incident['fs_type']} filesystem at {incident['mount_pt']}",
                        "keywords": "operates_on filesystem access",
                        "weight": 1.0,
                        "source_id": source_id,
                        "file_path": file_path
                    })

            # Incident -> Application: BELONGS_TO
            if exe:
                relationships.append({
                    "src_id": incident_entity_name,
                    "tgt_id": app_entity_name,
                    "description": f"{incident['module']} incident belongs to application {exe}",
                    "keywords": "belongs_to application generated_by",
                    "weight": 1.0,
                    "source_id": source_id,
                    "file_path": file_path
                })

        return {
            "chunks": chunks,
            "entities": entities,
            "relationships": relationships
        }


def process_darshan_files(input_path: str, output_path: str) -> None:
    """
    Process Darshan signal files and generate LightRAG custom KG JSON.

    Args:
        input_path: Path to txt file, directory with txt files, or parent directory
        output_path: Path for output JSON file
    """
    input_path_obj = Path(input_path)

    # Collect all txt files
    txt_files = []
    if input_path_obj.is_file():
        if input_path_obj.suffix == '.txt':
            txt_files.append(input_path_obj)
    elif input_path_obj.is_dir():
        txt_files = list(input_path_obj.rglob('*.txt'))
    else:
        raise ValueError(f"Invalid input path: {input_path}")

    if not txt_files:
        print(f"No .txt files found in {input_path}")
        return

    print(f"Found {len(txt_files)} txt file(s) to process")

    # Process each file and build KG
    all_chunks = []
    all_entities = []
    all_relationships = []

    for txt_file in txt_files:
        print(f"Processing: {txt_file}")

        builder = DarshanKGBuilder()
        builder.parse_darshan_signal_file(str(txt_file))

        # Generate source_id from file name
        source_id = f"darshan_{txt_file.stem}"

        # Build KG
        kg = builder.build_lightrag_kg(source_id, str(txt_file))

        # Accumulate
        all_chunks.extend(kg["chunks"])
        all_entities.extend(kg["entities"])
        all_relationships.extend(kg["relationships"])

        print(f"  - Extracted {len(kg['entities'])} entities, {len(kg['relationships'])} relationships")

    # Combine into final KG
    final_kg = {
        "chunks": all_chunks,
        "entities": all_entities,
        "relationships": all_relationships
    }

    # Write to output file
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_kg, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Knowledge Graph saved to: {output_path}")
    print(f"   Total chunks: {len(all_chunks)}")
    print(f"   Total entities: {len(all_entities)}")
    print(f"   Total relationships: {len(all_relationships)}")


def main():
    """Command-line interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build LightRAG Knowledge Graph from Darshan signal extraction output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single file
  python darshan_kg_builder.py -i /path/to/darshan_log.txt -o output.json

  # Process directory
  python darshan_kg_builder.py -i /path/to/logs/ -o output.json

  # Process parent directory (recursive)
  python darshan_kg_builder.py -i /path/to/parent/ -o output.json
        """
    )

    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Input: txt file, directory with txt files, or parent directory'
    )

    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output JSON file path'
    )

    args = parser.parse_args()

    try:
        process_darshan_files(args.input, args.output)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
