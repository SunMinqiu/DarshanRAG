#!/usr/bin/env python3
"""
Darshan Log Signal Extraction Tool v2.0
Processes Darshan log files with hierarchical structure: Job -> Module -> Record
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict


class DarshanLogProcessor:
    """Extract signals from Darshan log files with 3-level hierarchy"""

    def __init__(self):
        self.header_lines = []
        self.job_data = {}
        self.modules = defaultdict(lambda: defaultdict(dict))  # module -> record_id -> data
        self.file_metadata = {}  # (module, record_id) -> {file_name, mount_pt, fs_type}

    def parse_log_file(self, input_path):
        """Parse a Darshan log file"""
        self.header_lines = []
        self.job_data = {}
        self.modules = defaultdict(lambda: defaultdict(dict))
        self.file_metadata = {}

        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_header = True
            current_module = None

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

                # Parse data lines: module rank record_id counter value [file_name mount_pt fs_type]
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

                # Store file metadata (file_name, mount_pt, fs_type)
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

                # Store metrics by module and record
                if record_id not in self.modules[module]:
                    self.modules[module][record_id] = {
                        'rank': rank,
                        'metrics': {},
                        'signals': {}
                    }

                self.modules[module][record_id]['metrics'][counter] = value

    def safe_div(self, a, b, na_value='NA'):
        """Safe division returning NA for division by zero"""
        if b == 0 or b is None:
            return na_value
        return a / b

    def get_metric(self, metrics, key, default='NA'):
        """Get metric value, return NA if missing or -1"""
        value = metrics.get(key, default)
        if value == -1:
            return 'NA'
        return value

    def compute_record_signals(self, module, record_id, record):
        """Compute signals for a single record"""
        metrics = record['metrics']
        signals = record['signals']
        rank = record['rank']

        # Helper functions
        def get(key, default='NA'):
            return self.get_metric(metrics, key, default)

        def div(a, b):
            return self.safe_div(a, b)

        # Basic I/O metrics (always extract)
        bytes_read = get('POSIX_BYTES_READ' if 'POSIX' in module else 'STDIO_BYTES_READ', 0)
        bytes_written = get('POSIX_BYTES_WRITTEN' if 'POSIX' in module else 'STDIO_BYTES_WRITTEN', 0)
        reads = get('POSIX_READS' if 'POSIX' in module else 'STDIO_READS', 0)
        writes = get('POSIX_WRITES' if 'POSIX' in module else 'STDIO_WRITES', 0)
        read_time = get('POSIX_F_READ_TIME' if 'POSIX' in module else 'STDIO_F_READ_TIME', 0)
        write_time = get('POSIX_F_WRITE_TIME' if 'POSIX' in module else 'STDIO_F_WRITE_TIME', 0)

        # Convert NA to 0 for calculations
        if bytes_read == 'NA': bytes_read = 0
        if bytes_written == 'NA': bytes_written = 0
        if reads == 'NA': reads = 0
        if writes == 'NA': writes = 0
        if read_time == 'NA': read_time = 0
        if write_time == 'NA': write_time = 0

        # Performance metrics (必算)
        signals['bytes_read'] = bytes_read
        signals['bytes_written'] = bytes_written
        signals['reads'] = reads
        signals['writes'] = writes

        # Bandwidth (MB/s)
        signals['read_bw'] = div(bytes_read / (1024*1024), read_time) if read_time > 0 else 'NA'
        signals['write_bw'] = div(bytes_written / (1024*1024), write_time) if write_time > 0 else 'NA'

        # IOPS
        signals['read_iops'] = div(reads, read_time) if read_time > 0 else 'NA'
        signals['write_iops'] = div(writes, write_time) if write_time > 0 else 'NA'

        # Average request size (bytes)
        signals['avg_read_size'] = div(bytes_read, reads)
        signals['avg_write_size'] = div(bytes_written, writes)

        # Only for POSIX module
        if 'POSIX' in module:
            seq_reads = get('POSIX_SEQ_READS', 0)
            consec_reads = get('POSIX_CONSEC_READS', 0)
            seq_writes = get('POSIX_SEQ_WRITES', 0)
            consec_writes = get('POSIX_CONSEC_WRITES', 0)

            if seq_reads == 'NA': seq_reads = 0
            if consec_reads == 'NA': consec_reads = 0
            if seq_writes == 'NA': seq_writes = 0
            if consec_writes == 'NA': consec_writes = 0

            # Access pattern signals (改为 seq_ratio 和 consec_ratio)
            signals['seq_read_ratio'] = div(seq_reads, reads)
            signals['seq_write_ratio'] = div(seq_writes, writes)
            signals['consec_read_ratio'] = div(consec_reads, reads)
            signals['consec_write_ratio'] = div(consec_writes, writes)

            # Overall seq and consec ratios
            total_io = reads + writes
            signals['seq_ratio'] = div(seq_reads + seq_writes, total_io)
            signals['consec_ratio'] = div(consec_reads + consec_writes, total_io)

            # Metadata intensity (meta_ops per I/O operation)
            meta_ops = 0
            for key in ['POSIX_OPENS', 'POSIX_STATS', 'POSIX_SEEKS', 'POSIX_FSYNCS', 'POSIX_FDSYNCS']:
                val = get(key, 0)
                if val != 'NA':
                    meta_ops += val

            signals['meta_ops'] = meta_ops
            signals['meta_intensity'] = div(meta_ops, reads + writes)

            meta_time = get('POSIX_F_META_TIME', 0)
            if meta_time == 'NA': meta_time = 0
            total_time = meta_time + read_time + write_time
            signals['meta_fraction'] = div(meta_time, total_time)

            # Alignment
            file_not_aligned = get('POSIX_FILE_NOT_ALIGNED', 0)
            if file_not_aligned == 'NA': file_not_aligned = 0
            signals['unaligned_read_ratio'] = div(file_not_aligned, reads)
            signals['unaligned_write_ratio'] = div(file_not_aligned, writes)

            # Small I/O
            small_reads = 0
            for key in ['POSIX_SIZE_READ_0_100', 'POSIX_SIZE_READ_100_1K', 'POSIX_SIZE_READ_1K_10K']:
                val = get(key, 0)
                if val != 'NA':
                    small_reads += val

            small_writes = 0
            for key in ['POSIX_SIZE_WRITE_0_100', 'POSIX_SIZE_WRITE_100_1K', 'POSIX_SIZE_WRITE_1K_10K']:
                val = get(key, 0)
                if val != 'NA':
                    small_writes += val

            signals['small_read_ratio'] = div(small_reads, reads)
            signals['small_write_ratio'] = div(small_writes, writes)

            # RDA (Repetitive Data Access) - 改为 reuse_proxy
            max_byte_read = get('POSIX_MAX_BYTE_READ', 0)
            if max_byte_read == 'NA': max_byte_read = 0
            estimated_file_size = max_byte_read + 1  # From MAX_BYTE_READ + 1

            if estimated_file_size > 1:
                signals['reuse_proxy'] = div(bytes_read, estimated_file_size)
            else:
                signals['reuse_proxy'] = 'NA'

            # RLIM (只在 rank == -1 且 bytes > 0 时计算)
            if rank == -1 and (bytes_read + bytes_written) > 0:
                fastest_bytes = get('POSIX_FASTEST_RANK_BYTES', 0)
                slowest_bytes = get('POSIX_SLOWEST_RANK_BYTES', 0)
                if fastest_bytes == 'NA': fastest_bytes = 0
                if slowest_bytes == 'NA': slowest_bytes = 0

                signals['rank_imbalance_ratio'] = div(slowest_bytes, fastest_bytes)

                variance_bytes = get('POSIX_F_VARIANCE_RANK_BYTES', 0)
                if variance_bytes == 'NA': variance_bytes = 0
                signals['bw_variance_proxy'] = variance_bytes
            else:
                # rank != -1 时不计算 RLIM
                signals['rank_imbalance_ratio'] = 'NA'
                signals['bw_variance_proxy'] = 'NA'

            # Shared file indicator
            signals['is_shared'] = 1 if rank == -1 else 0

    def compute_module_aggregates(self, module):
        """Compute module-level aggregates"""
        agg = {
            'total_bytes_read': 0,
            'total_bytes_written': 0,
            'total_reads': 0,
            'total_writes': 0,
            'total_read_time': 0,
            'total_write_time': 0,
        }

        for record_id, record in self.modules[module].items():
            signals = record['signals']

            # Sum up from individual records (不跨模块相加)
            for key in ['bytes_read', 'bytes_written', 'reads', 'writes']:
                val = signals.get(key, 0)
                if val != 'NA' and val != 0:
                    agg[f'total_{key}'] += val

        # Compute module-level performance metrics
        module_signals = {}

        # Bandwidth
        if agg['total_read_time'] > 0:
            module_signals['read_bw'] = agg['total_bytes_read'] / (1024*1024) / agg['total_read_time']
        else:
            module_signals['read_bw'] = 'NA'

        if agg['total_write_time'] > 0:
            module_signals['write_bw'] = agg['total_bytes_written'] / (1024*1024) / agg['total_write_time']
        else:
            module_signals['write_bw'] = 'NA'

        # IOPS
        if agg['total_read_time'] > 0:
            module_signals['read_iops'] = agg['total_reads'] / agg['total_read_time']
        else:
            module_signals['read_iops'] = 'NA'

        if agg['total_write_time'] > 0:
            module_signals['write_iops'] = agg['total_writes'] / agg['total_write_time']
        else:
            module_signals['write_iops'] = 'NA'

        # Average sizes
        module_signals['avg_read_size'] = self.safe_div(agg['total_bytes_read'], agg['total_reads'])
        module_signals['avg_write_size'] = self.safe_div(agg['total_bytes_written'], agg['total_writes'])

        return agg, module_signals

    def compute_job_aggregates(self):
        """Compute job-level aggregates across all modules"""
        job_agg = {
            'total_bytes_read': 0,
            'total_bytes_written': 0,
            'total_reads': 0,
            'total_writes': 0,
        }

        # Aggregate across modules (但不混合 POSIX 和 STDIO 的数据层)
        for module in self.modules:
            for record_id, record in self.modules[module].items():
                signals = record['signals']
                for key in ['bytes_read', 'bytes_written', 'reads', 'writes']:
                    val = signals.get(key, 0)
                    if val != 'NA' and val != 0:
                        job_agg[f'total_{key}'] += val

        return job_agg

    def compute_all_signals(self):
        """Compute all signals at all levels"""
        # Record level
        for module in self.modules:
            for record_id in self.modules[module]:
                self.compute_record_signals(module, record_id, self.modules[module][record_id])

    def write_signals_output(self, output_path):
        """Write hierarchical output: Job -> Module -> Record"""
        with open(output_path, 'w', encoding='utf-8') as f:
            # ============================================================
            # HEADER
            # ============================================================
            f.write("# ============================================================\n")
            f.write("# ORIGINAL DARSHAN LOG HEADER (Preserved)\n")
            f.write("# ============================================================\n")
            for header_line in self.header_lines:
                f.write(header_line + "\n")

            f.write("\n")
            f.write("# ============================================================\n")
            f.write("# SIGNAL EXTRACTION OUTPUT v2.0\n")
            f.write("# Structure: Job Level -> Module Level -> Record Level\n")
            f.write("# ============================================================\n")
            f.write("#\n")

            # ============================================================
            # JOB LEVEL
            # ============================================================
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

            # ============================================================
            # MODULE LEVEL
            # ============================================================
            for module in sorted(self.modules.keys()):
                f.write("# ============================================================\n")
                f.write(f"# MODULE: {module}\n")
                f.write("# ============================================================\n")
                f.write("#\n")

                # Module-level aggregates
                module_agg, module_signals = self.compute_module_aggregates(module)

                f.write("## Module-Level Aggregates:\n")
                for key, value in module_agg.items():
                    f.write(f"{module}\tMODULE_AGG\t{key}\t{value}\n")

                f.write("\n## Module-Level Performance Metrics:\n")
                for key, value in module_signals.items():
                    f.write(f"{module}\tMODULE_PERF\t{key}\t{value}\n")

                f.write("\n")

                # ============================================================
                # RECORD LEVEL
                # ============================================================
                for record_id in sorted(self.modules[module].keys()):
                    record = self.modules[module][record_id]
                    rank = record['rank']

                    f.write(f"# ------------------------------------------------------------\n")
                    f.write(f"# RECORD: {record_id} (rank={rank})\n")

                    # File metadata
                    meta_key = (module, rank, record_id)
                    if meta_key in self.file_metadata:
                        meta = self.file_metadata[meta_key]
                        f.write(f"# file_name: {meta['file_name']}\n")
                        f.write(f"# mount_pt: {meta['mount_pt']}\n")
                        f.write(f"# fs_type: {meta['fs_type']}\n")

                    f.write(f"# ------------------------------------------------------------\n")
                    f.write("#\n")

                    # Original metrics
                    f.write("### Original Metrics:\n")
                    for metric_name in sorted(record['metrics'].keys()):
                        value = record['metrics'][metric_name]
                        f.write(f"{module}\t{rank}\t{record_id}\t{metric_name}\t{value}\n")

                    f.write("\n")

                    # Derived signals
                    f.write("### Derived Signals:\n")
                    signals = record['signals']

                    # Performance metrics (必算)
                    f.write("# Performance Metrics\n")
                    for key in ['read_bw', 'write_bw', 'read_iops', 'write_iops',
                               'avg_read_size', 'avg_write_size', 'seq_ratio', 'consec_ratio']:
                        if key in signals:
                            f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                    # Access patterns
                    if 'seq_read_ratio' in signals:
                        f.write("\n# Access Patterns\n")
                        for key in ['seq_read_ratio', 'seq_write_ratio',
                                   'consec_read_ratio', 'consec_write_ratio']:
                            if key in signals:
                                f.write(f"{module}\t{rank}\t{record_id}\tSIGNAL_{key.upper()}\t{signals[key]}\n")

                    # Metadata
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

                    # RLIM (只有 rank=-1 时才有)
                    if signals.get('rank_imbalance_ratio') != 'NA':
                        f.write("\n# Rank Imbalance (shared file only)\n")
                        for key in ['rank_imbalance_ratio', 'bw_variance_proxy']:
                            if key in signals and signals[key] != 'NA':
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
        output_file = output_path / rel_path.parent / f"{rel_path.stem}_signals_v2.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            process_single_file(txt_file, output_file)
        except Exception as e:
            print(f"ERROR processing {txt_file}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract Darshan log signals v2.0 (hierarchical structure)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_darshan_signals_v2.py input.txt
  python process_darshan_signals_v2.py input.txt -o output.txt
  python process_darshan_signals_v2.py /path/to/logs/
  python process_darshan_signals_v2.py /path/to/logs/ -o /path/to/output/
        """
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
            output_file = input_path.parent / f"{input_path.stem}_signals_v2.txt"
        process_single_file(input_path, output_file)

    elif input_path.is_dir():
        if args.output:
            output_dir = Path(args.output)
        else:
            output_dir = input_path.parent / f"{input_path.name}_signals_v2"
        process_directory(input_path, output_dir)

    print("\nProcessing complete!")


if __name__ == '__main__':
    main()
