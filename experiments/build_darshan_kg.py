#!/usr/bin/env python3
"""
Darshan Log to Knowledge Graph Builder

Converts Darshan parsed logs to LightRAG custom KG format.
Supports folder traversal, single files, and custom output paths.

Usage:
    python build_darshan_kg.py --input_path /path/to/logs --output_path output.json
"""

import argparse
import json
import os
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from collections import defaultdict


class DarshanLogParser:
    """Parse Darshan text-format logs (output from darshan-parser)."""

    def __init__(self, log_path: str):
        self.log_path = log_path
        self.log_file = Path(log_path).name
        self.raw_text = ""
        self.header = {}
        self.modules = {}

    def parse(self) -> Dict[str, Any]:
        """Parse the Darshan log file."""
        try:
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.raw_text = f.read()
        except Exception as e:
            print(f"Error reading {self.log_path}: {e}")
            return None

        # Parse different sections
        self._parse_header()
        self._parse_modules()

        return {
            'header': self.header,
            'modules': self.modules,
            'log_file': self.log_file,
            'log_path': self.log_path
        }

    def _parse_header(self):
        """Extract header information (job metadata)."""
        header_patterns = {
            'job_id': r'#\s*jobid:\s*(\S+)',
            'uid': r'#\s*uid:\s*(\d+)',
            'start_time': r'#\s*start_time:\s*(\d+)',
            'start_time_asci': r'#\s*start_time_asci:\s*(.+)',
            'end_time': r'#\s*end_time:\s*(\d+)',
            'end_time_asci': r'#\s*end_time_asci:\s*(.+)',
            'nprocs': r'#\s*nprocs:\s*(\d+)',
            'run_time': r'#\s*run time:\s*([\d.]+)',
            'exe': r'#\s*exe:\s*(.+)',
            'version': r'#\s*darshan log version:\s*(\S+)',
            'log_ver': r'#\s*log_ver:\s*(\S+)',
        }

        for key, pattern in header_patterns.items():
            match = re.search(pattern, self.raw_text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Convert numeric fields
                if key in ['start_time', 'end_time', 'nprocs']:
                    try:
                        self.header[key] = int(value)
                    except ValueError:
                        self.header[key] = value
                elif key == 'run_time':
                    try:
                        self.header[key] = float(value)
                    except ValueError:
                        self.header[key] = value
                else:
                    self.header[key] = value

        # Parse mount table
        mount_table = self._extract_mount_table()
        if mount_table:
            self.header['mount_table'] = mount_table
            self.header['mount_table_digest'] = hashlib.md5(
                json.dumps(mount_table, sort_keys=True).encode()
            ).hexdigest()

    def _extract_mount_table(self) -> List[Dict]:
        """Extract mount table information."""
        mount_section = re.search(
            r'#\s*mount\s+table:(.+?)(?=\n#\s*\w+:|$)',
            self.raw_text,
            re.DOTALL | re.IGNORECASE
        )

        if not mount_section:
            return []

        mount_entries = []
        lines = mount_section.group(1).strip().split('\n')

        for line in lines:
            line = line.strip().lstrip('#').strip()
            if not line:
                continue
            # Example: mount[0] = lustre://scratch1
            match = re.match(r'mount\[(\d+)\]\s*=\s*(\S+)://(\S+)', line)
            if match:
                mount_entries.append({
                    'index': int(match.group(1)),
                    'fs_type': match.group(2),
                    'mount_point': match.group(3)
                })

        return mount_entries

    def _parse_modules(self):
        """Parse module sections (POSIX, STDIO, MPIIO, etc.)."""
        # Find all module sections
        # Pattern matches both "# Module: POSIX" and "# POSIX module data"
        module_pattern = r'#\s*(?:Module:\s*)?(\w+(?:-\w+)?)\s+module(?:\s+data)?'
        module_matches = list(re.finditer(module_pattern, self.raw_text, re.IGNORECASE))

        for i, match in enumerate(module_matches):
            module_name = match.group(1).upper()
            start_pos = match.end()

            # Find end position (next module or end of file)
            if i + 1 < len(module_matches):
                end_pos = module_matches[i + 1].start()
            else:
                end_pos = len(self.raw_text)

            module_text = self.raw_text[start_pos:end_pos]

            # Parse file records in this module
            records = self._parse_module_records(module_name, module_text)

            if records:
                self.modules[module_name] = {
                    'module_name': module_name,
                    'module_present': True,
                    'record_count': len(records),
                    'records': records
                }

    def _parse_module_records(self, module_name: str, module_text: str) -> List[Dict]:
        """Parse individual file records within a module."""
        records = []

        # New format: MODULE_NAME	rank	file_id	counter_name	counter_value	file_path	mount_pt	fs_type
        # Old format: rank	file_id	counter	value
        # We need to group counters by (rank, file_id)

        counter_lines = []
        for line in module_text.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            counter_lines.append(line)

        # Group by (rank, file_id/hash)
        record_groups = defaultdict(lambda: {
            'counters': {},
            'rank': None,
            'record_id': None,
            'file_path': None,
            'mount_pt': None,
            'fs_type': None
        })

        for line in counter_lines:
            parts = line.split('\t')

            # Try new format first (8 fields)
            if len(parts) >= 8:
                # New format: MODULE_NAME	rank	file_id	counter_name	counter_value	file_path	mount_pt	fs_type
                try:
                    # parts[0] is module name, skip it
                    rank = int(parts[1])
                    file_id = parts[2].strip()
                    counter_name = parts[3].strip()
                    counter_value = parts[4].strip()
                    file_path = parts[5].strip()
                    mount_pt = parts[6].strip()
                    fs_type = parts[7].strip()
                except (ValueError, IndexError):
                    continue

                record_key = (rank, file_id)
                record_groups[record_key]['rank'] = rank
                record_groups[record_key]['record_id'] = file_id
                record_groups[record_key]['file_path'] = file_path
                record_groups[record_key]['mount_pt'] = mount_pt
                record_groups[record_key]['fs_type'] = fs_type

            # Try old format (4 fields)
            elif len(parts) >= 4:
                # Old format: rank	file_id	counter	value
                try:
                    rank = int(parts[0])
                    file_id = parts[1].strip()
                    counter_name = parts[2].strip()
                    counter_value = parts[3].strip()
                except (ValueError, IndexError):
                    continue

                record_key = (rank, file_id)
                record_groups[record_key]['rank'] = rank
                record_groups[record_key]['record_id'] = file_id

                # Extract file path if this is a filename counter
                if 'FILENAME' in counter_name.upper() or counter_name.endswith('_FILE'):
                    record_groups[record_key]['file_path'] = counter_value
            else:
                continue

            # Parse counter value
            parsed_value = self._parse_counter_value(counter_value)
            record_groups[record_key]['counters'][counter_name] = parsed_value

        # Convert grouped records to list
        for (rank, file_id), record_data in record_groups.items():
            # Use mount_pt and fs_type from data if available, otherwise infer
            mount_pt = record_data.get('mount_pt') or 'unknown'
            fs_type = record_data.get('fs_type') or 'unknown'

            # If not available in data, infer from file path
            if mount_pt == 'unknown' or fs_type == 'unknown':
                inferred_mount, inferred_fs = self._infer_mount_info(record_data['file_path'])
                if mount_pt == 'unknown':
                    mount_pt = inferred_mount
                if fs_type == 'unknown':
                    fs_type = inferred_fs

            record = {
                'rank': rank,
                'record_id': file_id,
                'file_path': record_data['file_path'] or 'unknown',
                'mount_pt': mount_pt,
                'fs_type': fs_type,
                'is_shared': rank == -1,
                'counters_blob': record_data['counters']
            }

            # Add derived fields
            record['path_tokens'] = self._tokenize_path(record['file_path'])
            record['path_depth'] = len(Path(record['file_path']).parts) if record['file_path'] != 'unknown' else 0
            record['file_role_hint'] = self._infer_file_role(record['file_path'])
            record['time_anchors'] = self._extract_time_anchors(record_data['counters'])

            records.append(record)

        return records

    def _parse_counter_value(self, value_str: str) -> Any:
        """Parse counter value (scalar, array, histogram, etc.)."""
        value_str = value_str.strip()

        # Try to parse as number
        try:
            if '.' in value_str or 'e' in value_str.lower():
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            pass

        # Check if it's a list/array format
        if value_str.startswith('[') and value_str.endswith(']'):
            try:
                return json.loads(value_str)
            except json.JSONDecodeError:
                pass

        # Return as string
        return value_str

    def _infer_mount_info(self, file_path: Optional[str]) -> tuple:
        """Infer mount point and fs_type from file path and header mount table."""
        if not file_path or file_path == 'unknown':
            return 'unknown', 'unknown'

        # Check against mount table
        mount_table = self.header.get('mount_table', [])
        for entry in mount_table:
            if file_path.startswith(entry['mount_point']):
                return entry['mount_point'], entry['fs_type']

        # Heuristic-based inference
        if '/scratch' in file_path or '/lustre' in file_path:
            return '/scratch', 'lustre'
        elif '/gpfs' in file_path:
            return '/gpfs', 'gpfs'
        elif '/nfs' in file_path:
            return '/nfs', 'nfs'

        return 'unknown', 'unknown'

    def _tokenize_path(self, file_path: str) -> List[str]:
        """Tokenize file path for search."""
        if not file_path or file_path == 'unknown':
            return []

        # Split by path separator and filter empty
        tokens = [p for p in file_path.split('/') if p]
        return tokens

    def _infer_file_role(self, file_path: str) -> str:
        """Infer file role from path patterns."""
        if not file_path or file_path == 'unknown':
            return 'unknown'

        path_lower = file_path.lower()

        # Checkpoint patterns
        if any(kw in path_lower for kw in ['checkpoint', 'ckpt', 'chk', '.ckpt']):
            return 'checkpoint'

        # Log patterns
        if any(kw in path_lower for kw in ['.log', 'log/', '/logs/']):
            return 'log'

        # Temporary patterns
        if any(kw in path_lower for kw in ['tmp/', 'temp/', '.tmp', '.temp']):
            return 'temp'

        # Data patterns (HDF5, NetCDF, etc.)
        if any(ext in path_lower for ext in ['.h5', '.hdf5', '.nc', '.dat', '.bin']):
            return 'data'

        return 'unknown'

    def _extract_time_anchors(self, counters: Dict) -> Dict[str, Any]:
        """Extract timestamp anchors from counters."""
        anchors = {}

        # Common timestamp patterns
        timestamp_patterns = [
            'FIRST_OPEN', 'LAST_OPEN',
            'FIRST_READ', 'LAST_READ',
            'FIRST_WRITE', 'LAST_WRITE',
            'FIRST_CLOSE', 'LAST_CLOSE',
            'OPEN_START', 'OPEN_END',
            'READ_START', 'READ_END',
            'WRITE_START', 'WRITE_END',
            'CLOSE_START', 'CLOSE_END'
        ]

        for counter_name, value in counters.items():
            counter_upper = counter_name.upper()

            for pattern in timestamp_patterns:
                if pattern in counter_upper and 'TIMESTAMP' in counter_upper:
                    key = pattern.lower() + '_ts'
                    anchors[key] = {
                        'timestamp': value,
                        'source_counter': counter_name,
                        'confidence': 1.0
                    }

        return anchors


class KnowledgeGraphBuilder:
    """Build knowledge graph from parsed Darshan logs."""

    def __init__(self):
        self.entities = []
        self.relationships = []
        self.chunks = []
        self.entity_ids = set()
        self.chunk_id_counter = 0

    def build_from_logs(self, parsed_logs: List[Dict]) -> Dict[str, Any]:
        """Build KG from multiple parsed logs."""
        for log_data in parsed_logs:
            if log_data is None:
                continue

            self._process_log(log_data)

        return {
            'chunks': self.chunks,
            'entities': self.entities,
            'relationships': self.relationships
        }

    def _process_log(self, log_data: Dict):
        """Process a single parsed log."""
        header = log_data['header']
        modules = log_data['modules']
        log_file = log_data['log_file']

        # Create Job entity
        job_id = header.get('job_id', hashlib.md5(log_file.encode()).hexdigest()[:16])
        job_entity = self._create_job_entity(job_id, header, log_file)

        # Create a chunk summarizing this job
        job_chunk = self._create_job_chunk(job_id, header, log_file)

        # Process each module
        for module_name, module_data in modules.items():
            module_entity = self._create_module_entity(job_id, module_name, module_data, log_file)

            # Create relationship: Job -> Module
            self._add_relationship(
                src_id=job_entity['entity_name'],
                tgt_id=module_entity['entity_name'],
                description=f"Job {job_id} uses module {module_name}",
                keywords="has_module uses",
                source_id=job_chunk['source_id'],
                file_path=log_file
            )

            # Process file records
            for record in module_data.get('records', []):
                file_record_entity, phase_entities, event_entities, counter_entities = \
                    self._create_file_record_entities(job_id, module_name, record, log_file)

                # Module -> FileRecord
                self._add_relationship(
                    src_id=module_entity['entity_name'],
                    tgt_id=file_record_entity['entity_name'],
                    description=f"Module {module_name} observed file record {record['record_id']}",
                    keywords="has_record observes",
                    source_id=job_chunk['source_id'],
                    file_path=log_file
                )

                # FileRecord -> Phases
                for phase_entity in phase_entities:
                    phase_type = phase_entity.get('properties', {}).get('phase_type', 'unknown')
                    self._add_relationship(
                        src_id=file_record_entity['entity_name'],
                        tgt_id=phase_entity['entity_name'],
                        description=f"File record has {phase_type} phase",
                        keywords="has_phase contains",
                        source_id=job_chunk['source_id'],
                        file_path=log_file
                    )

                # Phase -> EventAnchors
                for event_entity in event_entities:
                    # Find the corresponding phase
                    event_kind = event_entity.get('properties', {}).get('kind', event_entity.get('kind', 'unknown'))
                    phase_type = self._infer_phase_from_event(event_kind)
                    matching_phases = [p for p in phase_entities if p.get('properties', {}).get('phase_type') == phase_type]

                    if matching_phases:
                        self._add_relationship(
                            src_id=matching_phases[0]['entity_name'],
                            tgt_id=event_entity['entity_name'],
                            description=f"Phase contains event anchor {event_kind}",
                            keywords="contains_anchor has_event",
                            source_id=job_chunk['source_id'],
                            file_path=log_file
                        )

                # FileRecord -> Counters (optional)
                for counter_entity in counter_entities:
                    self._add_relationship(
                        src_id=file_record_entity['entity_name'],
                        tgt_id=counter_entity['entity_name'],
                        description=f"File record has counter {counter_entity['counter_name']}",
                        keywords="has_counter measures",
                        source_id=job_chunk['source_id'],
                        file_path=log_file
                    )

    def _create_job_entity(self, job_id: str, header: Dict, log_file: str) -> Dict:
        """Create Job entity."""
        entity_name = f"Job_{job_id}"

        if entity_name in self.entity_ids:
            return {'entity_name': entity_name}

        # Extract exe and normalize
        exe = header.get('exe', 'unknown')
        exe_norm = Path(exe).name if exe != 'unknown' else 'unknown'

        # Calculate runtime
        start_time = header.get('start_time', 0)
        end_time = header.get('end_time', 0)
        runtime_sec = header.get('run_time', end_time - start_time if end_time > start_time else 0)

        description = (
            f"Job {job_id} executed {exe_norm} "
            f"with {header.get('nprocs', 'unknown')} processes "
            f"for {runtime_sec} seconds"
        )

        entity = {
            'entity_name': entity_name,
            'entity_type': 'Job',
            'description': description,
            'source_id': f"doc-{job_id}",
            'file_path': log_file,
            # Additional properties (stored in description for LightRAG compatibility)
            'properties': {
                'job_id': job_id,
                'start_time': start_time,
                'end_time': end_time,
                'runtime_sec': runtime_sec,
                'nprocs': header.get('nprocs'),
                'log_version': header.get('version') or header.get('log_ver'),
                'exe': exe,
                'exe_norm': exe_norm,
                'uid': header.get('uid'),
                'mount_table_digest': header.get('mount_table_digest')
            }
        }

        self.entities.append(entity)
        self.entity_ids.add(entity_name)
        return entity

    def _create_job_chunk(self, job_id: str, header: Dict, log_file: str) -> Dict:
        """Create a text chunk summarizing the job."""
        self.chunk_id_counter += 1

        content = f"""Job {job_id} Summary:
- Executable: {header.get('exe', 'unknown')}
- Number of Processes: {header.get('nprocs', 'unknown')}
- Start Time: {header.get('start_time_asci', header.get('start_time', 'unknown'))}
- End Time: {header.get('end_time_asci', header.get('end_time', 'unknown'))}
- Runtime: {header.get('run_time', 'unknown')} seconds
- Darshan Version: {header.get('version') or header.get('log_ver', 'unknown')}
"""

        chunk = {
            'content': content,
            'source_id': f"doc-{job_id}",
            'chunk_order_index': self.chunk_id_counter,
            'file_path': log_file
        }

        self.chunks.append(chunk)
        return chunk

    def _create_module_entity(self, job_id: str, module_name: str, module_data: Dict, log_file: str) -> Dict:
        """Create Module entity."""
        entity_name = f"Module_{job_id}_{module_name}"

        if entity_name in self.entity_ids:
            return {'entity_name': entity_name}

        description = (
            f"Module {module_name} in job {job_id} "
            f"with {module_data.get('record_count', 0)} file records"
        )

        entity = {
            'entity_name': entity_name,
            'entity_type': 'Module',
            'description': description,
            'source_id': f"doc-{job_id}",
            'file_path': log_file,
            'properties': {
                'module_name': module_name,
                'job_id': job_id,
                'module_present': module_data.get('module_present', True),
                'record_count': module_data.get('record_count', 0)
            }
        }

        self.entities.append(entity)
        self.entity_ids.add(entity_name)
        return entity

    def _create_file_record_entities(self, job_id: str, module_name: str, record: Dict, log_file: str):
        """Create FileRecord and related entities (Phases, EventAnchors, Counters)."""
        record_id = record['record_id']
        entity_name = f"FileRecord_{job_id}_{module_name}_{record_id}"

        phase_entities = []
        event_entities = []
        counter_entities = []

        # Skip if already created
        if entity_name in self.entity_ids:
            return {'entity_name': entity_name}, [], [], []

        # FileRecord entity
        description = (
            f"File record {record_id} in module {module_name} "
            f"for file {record.get('file_path', 'unknown')} "
            f"(rank={record.get('rank', -1)}, shared={record.get('is_shared', False)})"
        )

        file_record_entity = {
            'entity_name': entity_name,
            'entity_type': 'FileRecord',
            'description': description,
            'source_id': f"doc-{job_id}",
            'file_path': log_file,
            'properties': {
                'job_id': job_id,
                'module_name': module_name,
                'record_id': record_id,
                'file_path': record.get('file_path'),
                'rank': record.get('rank'),
                'mount_pt': record.get('mount_pt'),
                'fs_type': record.get('fs_type'),
                'is_shared': record.get('is_shared'),
                'path_tokens': record.get('path_tokens'),
                'path_depth': record.get('path_depth'),
                'file_role_hint': record.get('file_role_hint'),
                'time_anchors': record.get('time_anchors'),
                'counters_blob': record.get('counters_blob')  # KEY: All counters stored here
            }
        }

        self.entities.append(file_record_entity)
        self.entity_ids.add(entity_name)

        # Create Phase entities from counters
        phases = self._derive_phases(job_id, module_name, record_id, record['counters_blob'], log_file)
        phase_entities.extend(phases)

        # Create EventAnchor entities from time_anchors
        events = self._create_event_anchors(job_id, module_name, record_id, record.get('time_anchors', {}), log_file)
        event_entities.extend(events)

        # Optionally create Counter entities (for indexing)
        # counters = self._create_counter_entities(job_id, module_name, record_id, record['counters_blob'], log_file)
        # counter_entities.extend(counters)

        return file_record_entity, phase_entities, event_entities, counter_entities

    def _derive_phases(self, job_id: str, module_name: str, record_id: str, counters: Dict, log_file: str) -> List[Dict]:
        """Derive Phase entities from counters."""
        phases = []

        # Phase types to look for
        phase_types = ['open', 'read', 'write', 'close', 'meta']

        for phase_type in phase_types:
            phase_upper = phase_type.upper()

            # Find relevant counters
            start_ts = None
            end_ts = None
            bytes_val = 0
            ops_val = 0
            time_val = 0

            for counter_name, value in counters.items():
                counter_upper = counter_name.upper()

                # Extract timestamps
                if f'{phase_upper}_START_TIMESTAMP' in counter_upper or f'FIRST_{phase_upper}' in counter_upper:
                    start_ts = value if isinstance(value, (int, float)) else None
                if f'{phase_upper}_END_TIMESTAMP' in counter_upper or f'LAST_{phase_upper}' in counter_upper:
                    end_ts = value if isinstance(value, (int, float)) else None

                # Extract bytes
                if phase_upper in counter_upper and 'BYTES' in counter_upper:
                    bytes_val += value if isinstance(value, (int, float)) else 0

                # Extract ops
                if phase_upper in counter_upper and ('OPS' in counter_upper or 'COUNT' in counter_upper):
                    ops_val += value if isinstance(value, (int, float)) else 0

                # Extract time
                if phase_upper in counter_upper and ('TIME' in counter_upper or 'DURATION' in counter_upper):
                    time_val += value if isinstance(value, (int, float)) else 0

            # Skip if no data for this phase
            if start_ts is None and end_ts is None and bytes_val == 0 and ops_val == 0:
                continue

            # Calculate duration
            duration = 0
            is_sparse_time = True

            if start_ts is not None and end_ts is not None and end_ts > start_ts:
                duration = end_ts - start_ts
                is_sparse_time = False
            elif time_val > 0:
                duration = time_val
                is_sparse_time = False

            # Calculate derived metrics
            iops_est = ops_val / duration if duration > 0 else 0
            bw_est = bytes_val / duration if duration > 0 else 0

            entity_name = f"Phase_{job_id}_{module_name}_{record_id}_{phase_type}"

            if entity_name not in self.entity_ids:
                description = (
                    f"{phase_type.capitalize()} phase for record {record_id}: "
                    f"{bytes_val} bytes, {ops_val} ops, {duration:.2f}s duration"
                )

                phase_entity = {
                    'entity_name': entity_name,
                    'entity_type': 'Phase',
                    'description': description,
                    'source_id': f"doc-{job_id}",
                    'file_path': log_file,
                    'properties': {
                        'job_id': job_id,
                        'module_name': module_name,
                        'record_id': record_id,
                        'phase_type': phase_type,
                        't_start': start_ts,
                        't_end': end_ts,
                        'duration': duration,
                        'bytes': bytes_val,
                        'iops_est': iops_est,
                        'bw_est': bw_est,
                        'is_sparse_time': is_sparse_time
                    }
                }

                self.entities.append(phase_entity)
                self.entity_ids.add(entity_name)
                phases.append(phase_entity)

        return phases

    def _create_event_anchors(self, job_id: str, module_name: str, record_id: str, time_anchors: Dict, log_file: str) -> List[Dict]:
        """Create EventAnchor entities from time_anchors."""
        events = []

        for anchor_key, anchor_data in time_anchors.items():
            kind = anchor_key.replace('_ts', '')
            entity_name = f"EventAnchor_{job_id}_{module_name}_{record_id}_{kind}"

            if entity_name not in self.entity_ids:
                description = f"Event anchor: {kind} at timestamp {anchor_data.get('timestamp')}"

                event_entity = {
                    'entity_name': entity_name,
                    'entity_type': 'EventAnchor',
                    'description': description,
                    'source_id': f"doc-{job_id}",
                    'file_path': log_file,
                    'properties': {
                        'kind': kind,
                        'timestamp': anchor_data.get('timestamp'),
                        'source_counter_name': anchor_data.get('source_counter'),
                        'confidence': anchor_data.get('confidence', 1.0)
                    }
                }

                self.entities.append(event_entity)
                self.entity_ids.add(entity_name)
                events.append(event_entity)

        return events

    def _create_counter_entities(self, job_id: str, module_name: str, record_id: str, counters: Dict, log_file: str) -> List[Dict]:
        """Create Counter entities (optional, for indexing)."""
        counter_entities = []

        for counter_name, counter_value in counters.items():
            entity_name = f"Counter_{job_id}_{module_name}_{record_id}_{counter_name}"

            if entity_name not in self.entity_ids:
                # Determine counter type
                counter_type = 'scalar'
                if isinstance(counter_value, list):
                    counter_type = 'array'
                elif 'TIMESTAMP' in counter_name.upper():
                    counter_type = 'timestamp'
                elif 'HIST' in counter_name.upper():
                    counter_type = 'hist'

                description = f"Counter {counter_name} = {counter_value}"

                counter_entity = {
                    'entity_name': entity_name,
                    'entity_type': 'Counter',
                    'description': description,
                    'source_id': f"doc-{job_id}",
                    'file_path': log_file,
                    'properties': {
                        'counter_name': counter_name,
                        'counter_type': counter_type,
                        'value_json': json.dumps(counter_value)
                    }
                }

                self.entities.append(counter_entity)
                self.entity_ids.add(entity_name)
                counter_entities.append(counter_entity)

        return counter_entities

    def _infer_phase_from_event(self, event_kind: str) -> str:
        """Infer phase type from event kind."""
        event_upper = event_kind.upper()

        if 'OPEN' in event_upper:
            return 'open'
        elif 'READ' in event_upper:
            return 'read'
        elif 'WRITE' in event_upper:
            return 'write'
        elif 'CLOSE' in event_upper:
            return 'close'
        else:
            return 'meta'

    def _add_relationship(self, src_id: str, tgt_id: str, description: str, keywords: str, source_id: str, file_path: str):
        """Add a relationship to the graph."""
        relationship = {
            'src_id': src_id,
            'tgt_id': tgt_id,
            'description': description,
            'keywords': keywords,
            'source_id': source_id,
            'file_path': file_path,
            'weight': 1.0
        }

        self.relationships.append(relationship)


def find_log_files(input_path: str) -> List[str]:
    """Find all log files (.txt) in the input path."""
    input_path_obj = Path(input_path)

    if not input_path_obj.exists():
        print(f"Error: Input path does not exist: {input_path}")
        return []

    log_files = []

    if input_path_obj.is_file():
        # Single file
        if input_path_obj.suffix == '.txt':
            log_files.append(str(input_path_obj))
    else:
        # Directory - traverse recursively
        log_files = [str(p) for p in input_path_obj.rglob('*.txt')]

    return log_files


def main():
    parser = argparse.ArgumentParser(
        description='Build Knowledge Graph from Darshan Logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single log file
  python build_darshan_kg.py --input_path /path/to/log.txt --output_path graph.json

  # Process all logs in a folder (recursive)
  python build_darshan_kg.py --input_path /path/to/logs/ --output_path graph.json

  # Use default output path
  python build_darshan_kg.py --input_path /path/to/logs/
        """
    )

    parser.add_argument(
        '--input_path',
        type=str,
        required=True,
        help='Path to Darshan log file(s). Can be a single .txt file, a folder, or parent folder (will traverse recursively).'
    )

    parser.add_argument(
        '--output_path',
        type=str,
        default='darshan_kg.json',
        help='Output path for the knowledge graph JSON file (default: darshan_kg.json)'
    )

    args = parser.parse_args()

    print(f"🔍 Searching for Darshan logs in: {args.input_path}")

    # Find all log files
    log_files = find_log_files(args.input_path)

    if not log_files:
        print("❌ No log files found!")
        return

    print(f"✅ Found {len(log_files)} log file(s)")

    # Parse all logs
    parsed_logs = []
    for i, log_file in enumerate(log_files, 1):
        print(f"📄 [{i}/{len(log_files)}] Parsing: {log_file}")
        parser = DarshanLogParser(log_file)
        parsed_data = parser.parse()

        if parsed_data:
            parsed_logs.append(parsed_data)
            print(f"   ✓ Extracted {len(parsed_data.get('modules', {}))} modules")
        else:
            print(f"   ✗ Failed to parse")

    print(f"\n🔨 Building knowledge graph from {len(parsed_logs)} parsed log(s)...")

    # Build knowledge graph
    kg_builder = KnowledgeGraphBuilder()
    kg = kg_builder.build_from_logs(parsed_logs)

    print(f"\n📊 Knowledge Graph Statistics:")
    print(f"   - Chunks: {len(kg['chunks'])}")
    print(f"   - Entities: {len(kg['entities'])}")
    print(f"   - Relationships: {len(kg['relationships'])}")

    # Save to file
    print(f"\n💾 Saving to: {args.output_path}")

    output_path_obj = Path(args.output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    with open(args.output_path, 'w', encoding='utf-8') as f:
        json.dump(kg, f, indent=2, ensure_ascii=False)

    print(f"✅ Knowledge graph saved successfully!")
    print(f"\n📝 You can now load this into LightRAG using:")
    print(f"   rag.insert_custom_kg(json.load(open('{args.output_path}')))")


if __name__ == '__main__':
    main()
