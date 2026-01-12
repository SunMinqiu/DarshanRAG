#!/usr/bin/env python3
"""
Darshan Log Signal Extraction Tool
Processes Darshan log files to extract key metrics and compute derived anomaly signals.
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
import math


class DarshanLogProcessor:
    """Extract signals from Darshan log files"""

    # Metrics to extract from the log
    REQUIRED_METRICS = {
        # Basic I/O metrics
        'POSIX_BYTES_READ', 'POSIX_BYTES_WRITTEN',
        'POSIX_READS', 'POSIX_WRITES',
        'POSIX_F_READ_TIME', 'POSIX_F_WRITE_TIME',

        # Access patterns
        'POSIX_SEQ_READS', 'POSIX_SEQ_WRITES',
        'POSIX_CONSEC_READS', 'POSIX_CONSEC_WRITES',
        'POSIX_RW_SWITCHES',

        # Request size distribution
        'POSIX_SIZE_READ_0_100', 'POSIX_SIZE_READ_100_1K', 'POSIX_SIZE_READ_1K_10K',
        'POSIX_SIZE_READ_10K_100K', 'POSIX_SIZE_READ_100K_1M', 'POSIX_SIZE_READ_1M_4M',
        'POSIX_SIZE_READ_4M_10M', 'POSIX_SIZE_READ_10M_100M', 'POSIX_SIZE_READ_100M_1G',
        'POSIX_SIZE_READ_1G_PLUS',
        'POSIX_SIZE_WRITE_0_100', 'POSIX_SIZE_WRITE_100_1K', 'POSIX_SIZE_WRITE_1K_10K',
        'POSIX_SIZE_WRITE_10K_100K', 'POSIX_SIZE_WRITE_100K_1M', 'POSIX_SIZE_WRITE_1M_4M',
        'POSIX_SIZE_WRITE_4M_10M', 'POSIX_SIZE_WRITE_10M_100M', 'POSIX_SIZE_WRITE_100M_1G',
        'POSIX_SIZE_WRITE_1G_PLUS',

        # Alignment
        'POSIX_FILE_NOT_ALIGNED', 'POSIX_MEM_NOT_ALIGNED',
        'POSIX_FILE_ALIGNMENT', 'POSIX_MEM_ALIGNMENT',

        # Metadata operations
        'POSIX_OPENS', 'POSIX_STATS', 'POSIX_SEEKS',
        'POSIX_FSYNCS', 'POSIX_FDSYNCS', 'POSIX_F_META_TIME',

        # Parallel and shared file access
        'POSIX_FASTEST_RANK', 'POSIX_FASTEST_RANK_BYTES',
        'POSIX_SLOWEST_RANK', 'POSIX_SLOWEST_RANK_BYTES',
        'POSIX_F_VARIANCE_RANK_BYTES', 'POSIX_F_VARIANCE_RANK_TIME',

        # Additional for file size estimation
        'POSIX_MAX_BYTE_READ', 'POSIX_MAX_BYTE_WRITTEN',
    }

    STDIO_METRICS = {
        'STDIO_BYTES_READ', 'STDIO_BYTES_WRITTEN',
        'STDIO_READS', 'STDIO_WRITES',
        'STDIO_F_READ_TIME', 'STDIO_F_WRITE_TIME',
    }

    def __init__(self):
        self.header_data = {}
        self.file_records = []  # List of (rank, record_id, metrics_dict)
        self.has_apmpi = False
        self.apmpi_data = defaultdict(dict)
        self.heatmap_data = defaultdict(dict)
        self.header_lines = []  # Store all header lines before data sections

    def parse_log_file(self, input_path):
        """Parse a Darshan log file"""
        self.header_data = {}
        self.file_records = []
        self.has_apmpi = False
        self.apmpi_data = defaultdict(dict)
        self.heatmap_data = defaultdict(dict)
        self.header_lines = []

        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            current_module = None
            in_header = True  # Track if we're still in the header section

            for line in f:
                original_line = line  # Keep original line with whitespace
                line = line.strip()

                if not line or line.startswith('#'):
                    # Check if we've reached the end of header (description of columns)
                    if '# description of columns:' in line:
                        in_header = False

                    # Store header lines until we reach "description of columns"
                    if in_header and line:
                        self.header_lines.append(original_line.rstrip('\n'))

                    # Parse specific header information for processing
                    if line.startswith('# nprocs:'):
                        self.header_data['nprocs'] = int(line.split(':')[1].strip())
                    elif line.startswith('# run time:'):
                        self.header_data['runtime'] = float(line.split(':')[1].strip())
                    elif 'APMPI module:' in line:
                        self.has_apmpi = True
                    elif line.startswith('# POSIX module data'):
                        current_module = 'POSIX'
                    elif line.startswith('# STDIO module data'):
                        current_module = 'STDIO'
                    elif line.startswith('# APMPI module data'):
                        current_module = 'APMPI'
                    elif line.startswith('# HEATMAP module data'):
                        current_module = 'HEATMAP'
                    continue

                # Parse data lines
                parts = line.split('\t')
                if len(parts) < 5:
                    continue

                module = parts[0]
                rank = int(parts[1])
                record_id = parts[2]
                counter = parts[3]
                value = parts[4]

                try:
                    value = float(value)
                except ValueError:
                    continue

                if module == 'POSIX':
                    # Store POSIX metrics
                    if counter in self.REQUIRED_METRICS:
                        # Find or create record
                        record = self._get_or_create_record(rank, record_id)
                        record['metrics'][counter] = value

                elif module == 'STDIO':
                    if counter in self.STDIO_METRICS:
                        record = self._get_or_create_record(rank, record_id)
                        record['metrics'][counter] = value

                elif module == 'APMPI':
                    self.apmpi_data[(rank, record_id)][counter] = value

                elif module == 'HEATMAP':
                    self.heatmap_data[(rank, record_id)][counter] = value

    def _get_or_create_record(self, rank, record_id):
        """Get or create a file record"""
        for record in self.file_records:
            if record['rank'] == rank and record['record_id'] == record_id:
                return record

        new_record = {
            'rank': rank,
            'record_id': record_id,
            'metrics': {},
            'signals': {}
        }
        self.file_records.append(new_record)
        return new_record

    def compute_signals(self):
        """Compute derived signals for all file records"""
        nprocs = self.header_data.get('nprocs', 1)
        runtime = self.header_data.get('runtime', 1.0)

        for record in self.file_records:
            metrics = record['metrics']
            signals = record['signals']
            rank = record['rank']
            record_id = record['record_id']

            # Safe division helper
            def safe_div(a, b, default=0.0):
                return a / b if b != 0 else default

            # Get metric value with default
            def get_metric(key, default=0.0):
                return metrics.get(key, default)

            # --- HMD: High Metadata Load ---
            meta_ops = (get_metric('POSIX_OPENS') + get_metric('POSIX_STATS') +
                       get_metric('POSIX_SEEKS') + get_metric('POSIX_FSYNCS') +
                       get_metric('POSIX_FDSYNCS'))
            meta_time = get_metric('POSIX_F_META_TIME')
            read_time = get_metric('POSIX_F_READ_TIME')
            write_time = get_metric('POSIX_F_WRITE_TIME')
            total_time = meta_time + read_time + write_time

            signals['meta_ops'] = meta_ops
            signals['meta_fraction'] = safe_div(meta_time, total_time)
            signals['meta_ops_rate'] = safe_div(meta_ops, runtime)

            # --- MSL: Misaligned I/O ---
            reads = get_metric('POSIX_READS')
            writes = get_metric('POSIX_WRITES')
            file_not_aligned = get_metric('POSIX_FILE_NOT_ALIGNED')

            signals['unaligned_read_ratio'] = safe_div(file_not_aligned, reads)
            signals['unaligned_write_ratio'] = safe_div(file_not_aligned, writes)

            # --- RMA: Random Access ---
            seq_reads = get_metric('POSIX_SEQ_READS')
            consec_reads = get_metric('POSIX_CONSEC_READS')
            seq_writes = get_metric('POSIX_SEQ_WRITES')
            consec_writes = get_metric('POSIX_CONSEC_WRITES')
            rw_switches = get_metric('POSIX_RW_SWITCHES')

            signals['random_read_ratio'] = 1.0 - safe_div(seq_reads + consec_reads, reads)
            signals['random_write_ratio'] = 1.0 - safe_div(seq_writes + consec_writes, writes)
            signals['rw_switch_rate'] = safe_div(rw_switches, reads + writes)

            # --- SHF: Shared File Access ---
            is_shared = (rank == -1)
            signals['is_shared'] = 1 if is_shared else 0

            # --- SML: Small I/O ---
            small_reads = (get_metric('POSIX_SIZE_READ_0_100') +
                          get_metric('POSIX_SIZE_READ_100_1K') +
                          get_metric('POSIX_SIZE_READ_1K_10K'))
            small_writes = (get_metric('POSIX_SIZE_WRITE_0_100') +
                           get_metric('POSIX_SIZE_WRITE_100_1K') +
                           get_metric('POSIX_SIZE_WRITE_1K_10K'))

            signals['small_read_ratio'] = safe_div(small_reads, reads)
            signals['small_write_ratio'] = safe_div(small_writes, writes)

            # --- RDA: Repetitive Data Access ---
            bytes_read = get_metric('POSIX_BYTES_READ')
            max_byte_read = get_metric('POSIX_MAX_BYTE_READ')
            estimated_file_size = max(max_byte_read, get_metric('POSIX_MAX_BYTE_WRITTEN'))

            if estimated_file_size > 0:
                signals['read_reuse_ratio'] = safe_div(bytes_read, estimated_file_size)
            else:
                signals['read_reuse_ratio'] = 0.0

            signals['low_unique_offset_signal'] = 1 if (max_byte_read < bytes_read and bytes_read > 0) else 0

            # --- RLIM: Rank Load Imbalance ---
            fastest_bytes = get_metric('POSIX_FASTEST_RANK_BYTES')
            slowest_bytes = get_metric('POSIX_SLOWEST_RANK_BYTES')

            if fastest_bytes > 0:
                signals['rank_imbalance_ratio'] = safe_div(slowest_bytes, fastest_bytes)
            else:
                signals['rank_imbalance_ratio'] = 0.0

            # --- SLIM: Server Load Imbalance (proxy) ---
            variance_bytes = get_metric('POSIX_F_VARIANCE_RANK_BYTES')
            signals['bw_variance_proxy'] = variance_bytes

            # Heatmap burstiness (if available)
            heatmap = self.heatmap_data.get((rank, record_id), {})
            if heatmap:
                bin_values = [v for k, v in heatmap.items() if k.startswith('HEATMAP_')]
                if bin_values:
                    mean_bw = sum(bin_values) / len(bin_values)
                    peak_bw = max(bin_values)
                    signals['burstiness'] = safe_div(peak_bw, mean_bw)
                else:
                    signals['burstiness'] = 0.0
            else:
                signals['burstiness'] = 0.0

            # --- MPNM: Multi-Process without MPI ---
            has_multiple_ranks = (nprocs > 1)
            uses_mpi = self.has_apmpi
            signals['mpnm'] = 1 if (has_multiple_ranks and not uses_mpi) else 0

            # --- NC: No Collective I/O ---
            apmpi = self.apmpi_data.get((rank, record_id), {})
            if apmpi:
                collective_reads = apmpi.get('APMPI_INDEP_READS', 0)
                collective_writes = apmpi.get('APMPI_INDEP_WRITES', 0)
                total_reads = apmpi.get('APMPI_INDEP_READS', 0) + apmpi.get('APMPI_COLL_READS', 0)
                total_writes = apmpi.get('APMPI_INDEP_WRITES', 0) + apmpi.get('APMPI_COLL_WRITES', 0)

                signals['collective_read_ratio'] = safe_div(collective_reads, total_reads)
                signals['collective_write_ratio'] = safe_div(collective_writes, total_writes)
            else:
                signals['collective_read_ratio'] = 0.0
                signals['collective_write_ratio'] = 0.0

            # --- LLL: Low-Level Library ---
            stdio_bytes_read = get_metric('STDIO_BYTES_READ')
            stdio_bytes_written = get_metric('STDIO_BYTES_WRITTEN')
            posix_bytes_read = get_metric('POSIX_BYTES_READ')
            posix_bytes_written = get_metric('POSIX_BYTES_WRITTEN')

            total_read = stdio_bytes_read + posix_bytes_read
            total_written = stdio_bytes_written + posix_bytes_written

            signals['stdio_read_fraction'] = safe_div(stdio_bytes_read, total_read)
            signals['stdio_write_fraction'] = safe_div(stdio_bytes_written, total_written)

    def write_signals_output(self, output_path):
        """Write extracted signals and metrics to output file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write preserved original header from log file
            f.write("# ============================================================\n")
            f.write("# ORIGINAL DARSHAN LOG HEADER (Preserved)\n")
            f.write("# ============================================================\n")
            for header_line in self.header_lines:
                f.write(header_line + "\n")

            f.write("\n")
            f.write("# ============================================================\n")
            f.write("# SIGNAL EXTRACTION OUTPUT - Darshan Signal Extraction v1\n")
            f.write("# ============================================================\n")
            f.write("#\n")
            f.write("# Format: <rank> <record_id> <metric_name> <value>\n")
            f.write("#\n")
            f.write("# Section 1: Original Metrics (Required Minimal Sufficient Set)\n")
            f.write("# -----------------------------------------------------------\n")

            # Write original metrics
            for record in self.file_records:
                rank = record['rank']
                record_id = record['record_id']

                f.write(f"\n## File Record: rank={rank}, record_id={record_id}\n")
                f.write("### Original Metrics:\n")

                for metric_name in sorted(record['metrics'].keys()):
                    value = record['metrics'][metric_name]
                    f.write(f"{rank}\t{record_id}\t{metric_name}\t{value}\n")

            # Write derived signals
            f.write("\n#\n")
            f.write("# Section 2: Derived Anomaly Signals\n")
            f.write("# -----------------------------------\n")

            for record in self.file_records:
                rank = record['rank']
                record_id = record['record_id']

                f.write(f"\n## File Record: rank={rank}, record_id={record_id}\n")
                f.write("### Derived Signals:\n")

                signals = record['signals']

                # HMD
                f.write(f"# HMD - High Metadata Load\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_HMD_meta_ops\t{signals.get('meta_ops', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_HMD_meta_fraction\t{signals.get('meta_fraction', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_HMD_meta_ops_rate\t{signals.get('meta_ops_rate', 0)}\n")

                # MSL
                f.write(f"# MSL - Misaligned I/O\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_MSL_unaligned_read_ratio\t{signals.get('unaligned_read_ratio', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_MSL_unaligned_write_ratio\t{signals.get('unaligned_write_ratio', 0)}\n")

                # RMA
                f.write(f"# RMA - Random Access\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_RMA_random_read_ratio\t{signals.get('random_read_ratio', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_RMA_random_write_ratio\t{signals.get('random_write_ratio', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_RMA_rw_switch_rate\t{signals.get('rw_switch_rate', 0)}\n")

                # SHF
                f.write(f"# SHF - Shared File Access\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_SHF_is_shared\t{signals.get('is_shared', 0)}\n")

                # SML
                f.write(f"# SML - Small I/O\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_SML_small_read_ratio\t{signals.get('small_read_ratio', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_SML_small_write_ratio\t{signals.get('small_write_ratio', 0)}\n")

                # RDA
                f.write(f"# RDA - Repetitive Data Access\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_RDA_read_reuse_ratio\t{signals.get('read_reuse_ratio', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_RDA_low_unique_offset_signal\t{signals.get('low_unique_offset_signal', 0)}\n")

                # RLIM
                f.write(f"# RLIM - Rank Load Imbalance\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_RLIM_rank_imbalance_ratio\t{signals.get('rank_imbalance_ratio', 0)}\n")

                # SLIM
                f.write(f"# SLIM - Server Load Imbalance\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_SLIM_bw_variance_proxy\t{signals.get('bw_variance_proxy', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_SLIM_burstiness\t{signals.get('burstiness', 0)}\n")

                # MPNM
                f.write(f"# MPNM - Multi-Process without MPI\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_MPNM\t{signals.get('mpnm', 0)}\n")

                # NC
                f.write(f"# NC - No Collective I/O\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_NC_collective_read_ratio\t{signals.get('collective_read_ratio', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_NC_collective_write_ratio\t{signals.get('collective_write_ratio', 0)}\n")

                # LLL
                f.write(f"# LLL - Low-Level Library\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_LLL_stdio_read_fraction\t{signals.get('stdio_read_fraction', 0)}\n")
                f.write(f"{rank}\t{record_id}\tSIGNAL_LLL_stdio_write_fraction\t{signals.get('stdio_write_fraction', 0)}\n")


def process_single_file(input_path, output_path):
    """Process a single Darshan log file"""
    print(f"Processing: {input_path}")

    processor = DarshanLogProcessor()
    processor.parse_log_file(input_path)
    processor.compute_signals()
    processor.write_signals_output(output_path)

    print(f"  -> Output: {output_path}")


def process_directory(input_dir, output_dir):
    """Process all .txt files in a directory, preserving structure"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Find all .txt files
    txt_files = list(input_path.rglob('*.txt'))

    if not txt_files:
        print(f"No .txt files found in {input_dir}")
        return

    print(f"Found {len(txt_files)} .txt files")

    for txt_file in txt_files:
        # Calculate relative path
        rel_path = txt_file.relative_to(input_path)

        # Create output file path with _signals_v1 suffix
        output_file = output_path / rel_path.parent / f"{rel_path.stem}_signals_v1.txt"

        # Create output directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Process the file
        try:
            process_single_file(txt_file, output_file)
        except Exception as e:
            print(f"ERROR processing {txt_file}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract Darshan log signals for anomaly detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single file
  python process_darshan_signals.py input.txt

  # Process a single file with custom output name
  python process_darshan_signals.py input.txt -o output.txt

  # Process all .txt files in a directory
  python process_darshan_signals.py /path/to/logs/

  # Process directory with custom output directory
  python process_darshan_signals.py /path/to/logs/ -o /path/to/output/
        """
    )

    parser.add_argument('input', help='Input file or directory containing Darshan .txt logs')
    parser.add_argument('-o', '--output', help='Output file or directory (optional)')

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"ERROR: Input path does not exist: {input_path}")
        sys.exit(1)

    if input_path.is_file():
        # Process single file
        if args.output:
            output_file = Path(args.output)
        else:
            output_file = input_path.parent / f"{input_path.stem}_signals_v1.txt"

        process_single_file(input_path, output_file)

    elif input_path.is_dir():
        # Process directory
        if args.output:
            output_dir = Path(args.output)
        else:
            output_dir = input_path.parent / f"{input_path.name}_signals_v1"

        process_directory(input_path, output_dir)

    else:
        print(f"ERROR: Invalid input path: {input_path}")
        sys.exit(1)

    print("\nProcessing complete!")


if __name__ == '__main__':
    main()
