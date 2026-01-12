#!/usr/bin/env python3
"""
Darshan Log Signal Extraction Tool v2.2
- Fixed: Each (module, rank, record_id) is unique
- Fixed: HEATMAP module excludes aggregates/performance metrics
- Fixed: PEAK_ACTIVITY_BIN returns bin index, added PEAK_ACTIVITY_VALUE
- Removed: "### Original Metrics" section (only derived signals)
"""

import os
import sys
import argparse
import math
from pathlib import Path
from collections import defaultdict


class DarshanLogProcessor:
    """Extract signals from Darshan log files with 3-level hierarchy"""

    def __init__(self):
        self.header_lines = []
        self.job_data = {}
        # Key change: (module, rank, record_id) as unique key
        self.records = {}  # (module, rank, record_id) -> {metrics, signals}
        self.file_metadata = {}  # (module, rank, record_id) -> {file_name, mount_pt, fs_type}

    def parse_log_file(self, input_path):
        """Parse a Darshan log file"""
        self.header_lines = []
        self.job_data = {}
        self.records = {}
        self.file_metadata = {}

        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_header = True

            for line in f:
                original_line = line
                line = line.strip()

                # Store header until "description of columns"
                if in_header and line:
                    if '# description of columns:' in line:
                        in_header = False
                    else:
                        self.header_lines.append(original_line.rstrip('\n'))

                    # Parse job-level info
                    if line.startswith('# nprocs:'):
                        self.job_data['nprocs'] = int(line.split(':')[1].strip())
                    elif line.startswith('# run time:'):
                        self.job_data['runtime'] = float(line.split(':')[1].strip())
                    elif line.startswith('# start_time:') and 'asci' not in line:
                        self.job_data['start_time'] = int(line.split(':')[1].strip())
                    elif line.startswith('# end_time:') and 'asci' not in line:
                        self.job_data['end_time'] = int(line.split(':')[1].strip())
                    elif line.startswith('# jobid:'):
                        self.job_data['jobid'] = line.split(':')[1].strip()
                    continue

                if not line or line.startswith('#'):
                    continue

                # Parse data lines
                parts = line.split('\t')
                if len(parts) < 5:
                    continue

                module = parts[0]
                try:
                    rank = int(parts[1])
                except ValueError:
                    continue

                record_id = parts[2]
                counter = parts[3]

                try:
                    value = float(parts[4])
                except ValueError:
                    continue

                # Store file metadata
                if len(parts) >= 8:
                    file_name = parts[5]
                    mount_pt = parts[6]
                    fs_type = parts[7]
                    key = (module, rank, record_id)
                    if key not in self.file_metadata:
                        self.file_metadata[key] = {
                            'file_name': file_name,
                            'mount_pt': mount_pt,
                            'fs_type': fs_type
                        }

                # Use (module, rank, record_id) as unique key
                key = (module, rank, record_id)
                if key not in self.records:
                    self.records[key] = {
                        'metrics': {},
                        'signals': {}
                    }

                self.records[key]['metrics'][counter] = value

    def na_with_reason(self, reason):
        """Return NA with reason annotation"""
        return f"NA({reason})"

    def safe_div(self, a, b, reason='div_by_zero'):
        """Safe division returning NA with reason"""
        if b == 0 or b is None:
            return self.na_with_reason(reason)
        return a / b

    def get_metric(self, metrics, key, default='NA'):
        """Get metric value, return NA if missing or -1"""
        value = metrics.get(key, default)
        if value == -1:
            return self.na_with_reason('not_monitored')
        if value == default and value == 'NA':
            return self.na_with_reason('not_available')
        return value

    def compute_heatmap_signals(self, module, rank, record_id, record):
        """Compute HEATMAP-specific signals"""
        metrics = record['metrics']
        signals = record['signals']

        # Get bin width
        bin_width = metrics.get('HEATMAP_F_BIN_WIDTH_SECONDS', 0)
        if bin_width == 0:
            signals['heatmap_bin_width'] = self.na_with_reason('no_bin_width')
            return

        signals['heatmap_bin_width'] = bin_width

        # Collect all READ and WRITE bins
        read_bins = []
        write_bins = []

        # Find max bin number
        max_bin_num = -1
        for k in metrics.keys():
            if k.startswith('HEATMAP_READ_BIN_') or k.startswith('HEATMAP_WRITE_BIN_'):
                try:
                    bin_num = int(k.split('_')[-1])
                    max_bin_num = max(max_bin_num, bin_num)
                except ValueError:
                    continue

        N = max_bin_num + 1 if max_bin_num >= 0 else 0

        if N == 0:
            return

        # Initialize bins with 0
        read_bins = [0.0] * N
        write_bins = [0.0] * N

        # Fill bins
        for k, v in metrics.items():
            if k.startswith('HEATMAP_READ_BIN_'):
                try:
                    idx = int(k.split('_')[-1])
                    if 0 <= idx < N:
                        read_bins[idx] = v
                except ValueError:
                    continue
            elif k.startswith('HEATMAP_WRITE_BIN_'):
                try:
                    idx = int(k.split('_')[-1])
                    if 0 <= idx < N:
                        write_bins[idx] = v
                except ValueError:
                    continue

        # Activity bins
        activity_bins = [r + w for r, w in zip(read_bins, write_bins)]

        # 1. total_read_events
        total_read = sum(read_bins)
        signals['total_read_events'] = total_read

        # 2. total_write_events
        total_write = sum(write_bins)
        signals['total_write_events'] = total_write

        # 3. active_bins
        active_bins = sum(1 for a in activity_bins if a > 0)
        signals['active_bins'] = active_bins

        # 4. active_time
        signals['active_time'] = active_bins * bin_width

        # 5. activity_span
        first_active = -1
        last_active = -1
        for i, a in enumerate(activity_bins):
            if a > 0:
                if first_active == -1:
                    first_active = i
                last_active = i

        if first_active >= 0:
            signals['activity_span'] = (last_active - first_active + 1) * bin_width
        else:
            signals['activity_span'] = 0

        # 6. peak_activity_bin (bin INDEX, not value)
        if activity_bins:
            peak_idx = activity_bins.index(max(activity_bins))
            signals['peak_activity_bin'] = peak_idx
            signals['peak_activity_value'] = activity_bins[peak_idx]
        else:
            signals['peak_activity_bin'] = self.na_with_reason('no_activity')
            signals['peak_activity_value'] = 0

        # 7. read_activity_entropy_norm
        if total_read > 0:
            entropy_r = 0.0
            for r in read_bins:
                if r > 0:
                    p = r / total_read
                    entropy_r -= p * math.log(p)
            signals['read_activity_entropy_norm'] = entropy_r / math.log(N) if N > 1 else 0
        else:
            signals['read_activity_entropy_norm'] = 0

        # 8. write_activity_entropy_norm
        if total_write > 0:
            entropy_w = 0.0
            for w in write_bins:
                if w > 0:
                    q = w / total_write
                    entropy_w -= q * math.log(q)
            signals['write_activity_entropy_norm'] = entropy_w / math.log(N) if N > 1 else 0
        else:
            signals['write_activity_entropy_norm'] = 0

        # 9. top1_share
        total_activity = sum(activity_bins)
        if total_activity > 0:
            signals['top1_share'] = max(activity_bins) / total_activity
        else:
            signals['top1_share'] = 0

    def compute_record_signals(self, module, rank, record_id, record):
        """Compute signals for a single record"""
        metrics = record['metrics']
        signals = record['signals']

        # HEATMAP module has special processing
        if 'HEATMAP' in module:
            self.compute_heatmap_signals(module, rank, record_id, record)
            return

        # Helper functions
        def get(key, default='NA'):
            return self.get_metric(metrics, key, default)

        def div(a, b, reason='div_by_zero'):
            return self.safe_div(a, b, reason)

        # Basic I/O metrics
        bytes_read = get('POSIX_BYTES_READ' if 'POSIX' in module else 'STDIO_BYTES_READ', 0)
        bytes_written = get('POSIX_BYTES_WRITTEN' if 'POSIX' in module else 'STDIO_BYTES_WRITTEN', 0)
        reads = get('POSIX_READS' if 'POSIX' in module else 'STDIO_READS', 0)
        writes = get('POSIX_WRITES' if 'POSIX' in module else 'STDIO_WRITES', 0)
        read_time = get('POSIX_F_READ_TIME' if 'POSIX' in module else 'STDIO_F_READ_TIME', 0)
        write_time = get('POSIX_F_WRITE_TIME' if 'POSIX' in module else 'STDIO_F_WRITE_TIME', 0)

        # Convert NA to 0 for calculations
        if isinstance(bytes_read, str): bytes_read = 0
        if isinstance(bytes_written, str): bytes_written = 0
        if isinstance(reads, str): reads = 0
        if isinstance(writes, str): writes = 0
        if isinstance(read_time, str): read_time = 0
        if isinstance(write_time, str): write_time = 0

        # Performance metrics
        signals['bytes_read'] = bytes_read
        signals['bytes_written'] = bytes_written
        signals['reads'] = reads
        signals['writes'] = writes

        # Bandwidth
        if read_time > 0:
            signals['read_bw'] = bytes_read / (1024*1024) / read_time
        else:
            signals['read_bw'] = self.na_with_reason('no_read_time')

        if write_time > 0:
            signals['write_bw'] = bytes_written / (1024*1024) / write_time
        else:
            signals['write_bw'] = self.na_with_reason('no_write_time')

        # IOPS
        if read_time > 0:
            signals['read_iops'] = reads / read_time
        else:
            signals['read_iops'] = self.na_with_reason('no_read_time')

        if write_time > 0:
            signals['write_iops'] = writes / write_time
        else:
            signals['write_iops'] = self.na_with_reason('no_write_time')

        # Average sizes
        signals['avg_read_size'] = div(bytes_read, reads, 'no_reads')
        signals['avg_write_size'] = div(bytes_written, writes, 'no_writes')

        # Only for POSIX module
        if 'POSIX' in module:
            seq_reads = get('POSIX_SEQ_READS', 0)
            consec_reads = get('POSIX_CONSEC_READS', 0)
            seq_writes = get('POSIX_SEQ_WRITES', 0)
            consec_writes = get('POSIX_CONSEC_WRITES', 0)

            if isinstance(seq_reads, str): seq_reads = 0
            if isinstance(consec_reads, str): consec_reads = 0
            if isinstance(seq_writes, str): seq_writes = 0
            if isinstance(consec_writes, str): consec_writes = 0

            # Access pattern signals
            signals['seq_read_ratio'] = div(seq_reads, reads, 'no_reads')
            signals['seq_write_ratio'] = div(seq_writes, writes, 'no_writes')
            signals['consec_read_ratio'] = div(consec_reads, reads, 'no_reads')
            signals['consec_write_ratio'] = div(consec_writes, writes, 'no_writes')

            # Overall ratios
            total_io = reads + writes
            signals['seq_ratio'] = div(seq_reads + seq_writes, total_io, 'no_io')
            signals['consec_ratio'] = div(consec_reads + consec_writes, total_io, 'no_io')

            # Metadata
            meta_ops = 0
            for key in ['POSIX_OPENS', 'POSIX_STATS', 'POSIX_SEEKS', 'POSIX_FSYNCS', 'POSIX_FDSYNCS']:
                val = get(key, 0)
                if not isinstance(val, str):
                    meta_ops += val

            signals['meta_ops'] = meta_ops
            signals['meta_intensity'] = div(meta_ops, reads + writes, 'no_io')

            meta_time = get('POSIX_F_META_TIME', 0)
            if isinstance(meta_time, str): meta_time = 0
            total_time = meta_time + read_time + write_time
            signals['meta_fraction'] = div(meta_time, total_time, 'no_time')

            # Alignment
            file_not_aligned = get('POSIX_FILE_NOT_ALIGNED', 0)
            if isinstance(file_not_aligned, str): file_not_aligned = 0
            signals['unaligned_read_ratio'] = div(file_not_aligned, reads, 'no_reads')
            signals['unaligned_write_ratio'] = div(file_not_aligned, writes, 'no_writes')

            # Small I/O
            small_reads = 0
            for key in ['POSIX_SIZE_READ_0_100', 'POSIX_SIZE_READ_100_1K', 'POSIX_SIZE_READ_1K_10K']:
                val = get(key, 0)
                if not isinstance(val, str):
                    small_reads += val

            small_writes = 0
            for key in ['POSIX_SIZE_WRITE_0_100', 'POSIX_SIZE_WRITE_100_1K', 'POSIX_SIZE_WRITE_1K_10K']:
                val = get(key, 0)
                if not isinstance(val, str):
                    small_writes += val

            signals['small_read_ratio'] = div(small_reads, reads, 'no_reads')
            signals['small_write_ratio'] = div(small_writes, writes, 'no_writes')

            # RDA
            max_byte_read = get('POSIX_MAX_BYTE_READ', 0)
            if isinstance(max_byte_read, str): max_byte_read = 0
            estimated_file_size = max_byte_read + 1

            if estimated_file_size > 1:
                signals['reuse_proxy'] = div(bytes_read, estimated_file_size, 'no_file_size')
            else:
                signals['reuse_proxy'] = self.na_with_reason('no_file_size')

            # RLIM (only when rank=-1 and bytes>0)
            if rank == -1 and (bytes_read + bytes_written) > 0:
                fastest_bytes = get('POSIX_FASTEST_RANK_BYTES', 0)
                slowest_bytes = get('POSIX_SLOWEST_RANK_BYTES', 0)
                if isinstance(fastest_bytes, str): fastest_bytes = 0
                if isinstance(slowest_bytes, str): slowest_bytes = 0

                signals['rank_imbalance_ratio'] = div(slowest_bytes, fastest_bytes, 'no_fastest_bytes')

                variance_bytes = get('POSIX_F_VARIANCE_RANK_BYTES', 0)
                if isinstance(variance_bytes, str): variance_bytes = 0
                signals['bw_variance_proxy'] = variance_bytes
            else:
                reason = 'not_shared_file' if rank != -1 else 'no_bytes'
                signals['rank_imbalance_ratio'] = self.na_with_reason(reason)
                signals['bw_variance_proxy'] = self.na_with_reason(reason)

            # Shared indicator
            signals['is_shared'] = 1 if rank == -1 else 0

    def compute_module_aggregates(self, module):
        """Compute module-level aggregates (skip for HEATMAP)"""
        if 'HEATMAP' in module:
            return {}, {}  # No aggregates for HEATMAP

        agg = {
            'total_bytes_read': 0,
            'total_bytes_written': 0,
            'total_reads': 0,
            'total_writes': 0,
            'total_read_time': 0,
            'total_write_time': 0,
        }

        for key, record in self.records.items():
            mod, rank, rec_id = key
            if mod != module:
                continue

            signals = record['signals']
            for sig_key in ['bytes_read', 'bytes_written', 'reads', 'writes']:
                val = signals.get(sig_key, 0)
                if not isinstance(val, str) and val != 0:
                    agg[f'total_{sig_key}'] += val

        # Module performance
        module_signals = {}

        if agg['total_read_time'] > 0:
            module_signals['read_bw'] = agg['total_bytes_read'] / (1024*1024) / agg['total_read_time']
        else:
            module_signals['read_bw'] = self.na_with_reason('no_time')

        if agg['total_write_time'] > 0:
            module_signals['write_bw'] = agg['total_bytes_written'] / (1024*1024) / agg['total_write_time']
        else:
            module_signals['write_bw'] = self.na_with_reason('no_time')

        if agg['total_read_time'] > 0:
            module_signals['read_iops'] = agg['total_reads'] / agg['total_read_time']
        else:
            module_signals['read_iops'] = self.na_with_reason('no_time')

        if agg['total_write_time'] > 0:
            module_signals['write_iops'] = agg['total_writes'] / agg['total_write_time']
        else:
            module_signals['write_iops'] = self.na_with_reason('no_time')

        module_signals['avg_read_size'] = self.safe_div(agg['total_bytes_read'], agg['total_reads'], 'no_reads')
        module_signals['avg_write_size'] = self.safe_div(agg['total_bytes_written'], agg['total_writes'], 'no_writes')

        return agg, module_signals

    def compute_job_aggregates(self):
        """Compute job-level aggregates"""
        job_agg = {
            'total_bytes_read': 0,
            'total_bytes_written': 0,
            'total_reads': 0,
            'total_writes': 0,
        }

        for key, record in self.records.items():
            signals = record['signals']
            for sig_key in ['bytes_read', 'bytes_written', 'reads', 'writes']:
                val = signals.get(sig_key, 0)
                if not isinstance(val, str) and val != 0:
                    job_agg[f'total_{sig_key}'] += val

        return job_agg

    def compute_all_signals(self):
        """Compute all signals at all levels"""
        for key in self.records:
            module, rank, record_id = key
            self.compute_record_signals(module, rank, record_id, self.records[key])

    def write_signals_output(self, output_path):
        """Write hierarchical output"""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Header
            f.write("# ============================================================\n")
            f.write("# ORIGINAL DARSHAN LOG HEADER\n")
            f.write("# ============================================================\n")
            for header_line in self.header_lines:
                f.write(header_line + "\n")

            f.write("\n")
            f.write("# ============================================================\n")
            f.write("# SIGNAL EXTRACTION OUTPUT v2.2\n")
            f.write("# Structure: Job Level -> Module Level -> Record Level\n")
            f.write("# ============================================================\n")
            f.write("#\n")

            # Job Level
            f.write("# ============================================================\n")
            f.write("# JOB LEVEL METRICS\n")
            f.write("# ============================================================\n")
            f.write(f"# JobID: {self.job_data.get('jobid', 'NA')}\n")
            f.write(f"# nprocs: {self.job_data.get('nprocs', 'NA')}\n")
            f.write(f"# runtime: {self.job_data.get('runtime', 'NA')} seconds\n")
            f.write("#\n")

            job_agg = self.compute_job_aggregates()
            f.write("## Job-Level Aggregates:\n")
            for key, value in job_agg.items():
                f.write(f"JOB\t{key}\t{value}\n")

            f.write("\n")

            # Group records by module
            modules = {}
            for key in self.records:
                module, rank, record_id = key
                if module not in modules:
                    modules[module] = []
                modules[module].append((rank, record_id))

            # Module Level
            for module in sorted(modules.keys()):
                f.write("# ============================================================\n")
                f.write(f"# MODULE: {module}\n")
                f.write("# ============================================================\n")
                f.write("#\n")

                # Skip aggregates for HEATMAP
                if 'HEATMAP' not in module:
                    module_agg, module_signals = self.compute_module_aggregates(module)

                    f.write("## Module-Level Aggregates:\n")
                    for key, value in module_agg.items():
                        f.write(f"{module}\tMODULE_AGG\t{key}\t{value}\n")

                    f.write("\n## Module-Level Performance Metrics:\n")
                    for key, value in module_signals.items():
                        f.write(f"{module}\tMODULE_PERF\t{key}\t{value}\n")

                    f.write("\n")

                # Record Level
                for rank, record_id in sorted(modules[module]):
                    key = (module, rank, record_id)
                    record = self.records[key]

                    f.write(f"# ------------------------------------------------------------\n")
                    f.write(f"# RECORD: {record_id} (rank={rank})\n")

                    # File metadata
                    if key in self.file_metadata:
                        meta = self.file_metadata[key]
                        f.write(f"# file_name: {meta['file_name']}\n")
                        f.write(f"# mount_pt: {meta['mount_pt']}\n")
                        f.write(f"# fs_type: {meta['fs_type']}\n")

                    f.write(f"# ------------------------------------------------------------\n")
                    f.write("#\n")

                    # Only Derived signals (no Original Metrics section)
                    f.write("### Derived Signals:\n")
                    signals = record['signals']

                    # HEATMAP specific signals
                    if 'HEATMAP' in module:
                        f.write("# HEATMAP Statistics\n")
                        for key in ['total_read_events', 'total_write_events', 'active_bins',
                                   'active_time', 'activity_span', 'peak_activity_bin', 'peak_activity_value',
                                   'read_activity_entropy_norm', 'write_activity_entropy_norm', 'top1_share']:
                            if key in signals:
                                f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")
                    else:
                        # Performance metrics
                        f.write("# Performance Metrics\n")
                        for key in ['read_bw', 'write_bw', 'read_iops', 'write_iops',
                                   'avg_read_size', 'avg_write_size', 'seq_ratio', 'consec_ratio']:
                            if key in signals:
                                f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                        # Access patterns (POSIX only)
                        if 'seq_read_ratio' in signals:
                            f.write("\n# Access Patterns\n")
                            for key in ['seq_read_ratio', 'seq_write_ratio',
                                       'consec_read_ratio', 'consec_write_ratio']:
                                if key in signals:
                                    f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                        # Metadata (POSIX only)
                        if 'meta_ops' in signals:
                            f.write("\n# Metadata\n")
                            for key in ['meta_ops', 'meta_intensity', 'meta_fraction']:
                                if key in signals:
                                    f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                        # Alignment
                        if 'unaligned_read_ratio' in signals:
                            f.write("\n# Alignment\n")
                            for key in ['unaligned_read_ratio', 'unaligned_write_ratio']:
                                if key in signals:
                                    f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                        # Small I/O
                        if 'small_read_ratio' in signals:
                            f.write("\n# Small I/O\n")
                            for key in ['small_read_ratio', 'small_write_ratio']:
                                if key in signals:
                                    f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                        # Reuse
                        if 'reuse_proxy' in signals:
                            f.write("\n# Data Reuse (proxy from MAX_BYTE_READ+1)\n")
                            f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_REUSE_PROXY\t{signals['reuse_proxy']}\n")

                        # RLIM
                        if 'rank_imbalance_ratio' in signals and not isinstance(signals['rank_imbalance_ratio'], str):
                            f.write("\n# Rank Imbalance (shared file only)\n")
                            for key in ['rank_imbalance_ratio', 'bw_variance_proxy']:
                                if key in signals:
                                    f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                        # Shared indicator
                        if 'is_shared' in signals:
                            f.write(f"\n{module}\t{rank}\t{record_id}\tSIGNAL_IS_SHARED\t{signals['is_shared']}\n")

                    f.write("\n")


def process_single_file(input_path, output_path):
    """Process a single Darshan log file"""
    print(f"Processing: {input_path}")

    processor = DarshanLogProcessor()
    processor.parse_log_file(input_path)
    processor.compute_all_signals()
    processor.write_signals_output(output_path)

    print(f"  -> Output: {output_path}")


def process_directory(input_dir, output_dir):
    """Process all .txt files in a directory"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    txt_files = list(input_path.rglob('*.txt'))

    if not txt_files:
        print(f"No .txt files found in {input_dir}")
        return

    print(f"Found {len(txt_files)} .txt files")

    for txt_file in txt_files:
        rel_path = txt_file.relative_to(input_path)
        output_file = output_path / rel_path.parent / f"{rel_path.stem}_signals_v2.2.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            process_single_file(txt_file, output_file)
        except Exception as e:
            print(f"ERROR processing {txt_file}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract Darshan log signals v2.2',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('input', help='Input file or directory')
    parser.add_argument('-o', '--output', help='Output file or directory')

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"ERROR: Input path does not exist: {input_path}")
        sys.exit(1)

    if input_path.is_file():
        if args.output:
            output_file = Path(args.output)
        else:
            output_file = input_path.parent / f"{input_path.stem}_signals_v2.2.txt"
        process_single_file(input_path, output_file)

    elif input_path.is_dir():
        if args.output:
            output_dir = Path(args.output)
        else:
            output_dir = input_path.parent / f"{input_path.name}_signals_v2.2"
        process_directory(input_path, output_dir)

    print("\nProcessing complete!")


if __name__ == '__main__':
    main()
