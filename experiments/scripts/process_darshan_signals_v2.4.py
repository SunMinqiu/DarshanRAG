#!/usr/bin/env python3
"""
Darshan Log Signal Extraction Tool v2.4
- CRITICAL FIX: Added ALL time-related metrics and signals
- Time metrics: timestamps, cumulative times, spans, busy fractions
- Fixed: BW/IOPS now correctly use time fields (not zero!)
- Added: 20+ new time-based signals for POSIX and STDIO
- Maintains v2.3 output format with proper descriptions
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

    def compute_time_signals(self, metrics, prefix, op_type):
        """
        Compute time-based signals for a given operation type (READ/WRITE/META)
        Returns dict with: span, time, busy_frac, start_ts, end_ts
        """
        signals = {}
        eps = 1e-9

        # Get timestamps
        start_key = f"{prefix}_F_{op_type}_START_TIMESTAMP"
        end_key = f"{prefix}_F_{op_type}_END_TIMESTAMP"
        time_key = f"{prefix}_F_{op_type}_TIME"

        start_ts = self.get_metric(metrics, start_key, None)
        end_ts = self.get_metric(metrics, end_key, None)
        cumulative_time = self.get_metric(metrics, time_key, None)

        # Store raw timestamps
        signals[f'{op_type.lower()}_start_ts'] = start_ts if start_ts is not None and not isinstance(start_ts, str) else self.na_with_reason('missing_timestamp')
        signals[f'{op_type.lower()}_end_ts'] = end_ts if end_ts is not None and not isinstance(end_ts, str) else self.na_with_reason('missing_timestamp')

        # Store cumulative time
        signals[f'{op_type.lower()}_time'] = cumulative_time if cumulative_time is not None and not isinstance(cumulative_time, str) else self.na_with_reason('missing_time_counter')

        # Compute span
        if start_ts is not None and end_ts is not None and not isinstance(start_ts, str) and not isinstance(end_ts, str):
            span = max(0, end_ts - start_ts)
            signals[f'{op_type.lower()}_span'] = span

            # Compute busy fraction
            if cumulative_time is not None and not isinstance(cumulative_time, str) and span > eps:
                signals[f'{op_type.lower()}_busy_frac'] = cumulative_time / span
            elif cumulative_time is not None and not isinstance(cumulative_time, str):
                signals[f'{op_type.lower()}_busy_frac'] = self.na_with_reason('zero_span')
            else:
                signals[f'{op_type.lower()}_busy_frac'] = self.na_with_reason('dependency_missing')
        else:
            signals[f'{op_type.lower()}_span'] = self.na_with_reason('missing_timestamp')
            signals[f'{op_type.lower()}_busy_frac'] = self.na_with_reason('dependency_missing')

        return signals

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

        # ==== TIME-BASED SIGNALS ====
        # Compute time signals for READ, WRITE, META operations
        prefix = 'POSIX' if 'POSIX' in module else 'STDIO'

        # READ time signals
        read_time_sigs = self.compute_time_signals(metrics, prefix, 'READ')
        signals.update(read_time_sigs)

        # WRITE time signals
        write_time_sigs = self.compute_time_signals(metrics, prefix, 'WRITE')
        signals.update(write_time_sigs)

        # META time signals (mainly for POSIX)
        meta_time_sigs = self.compute_time_signals(metrics, prefix, 'META')
        signals.update(meta_time_sigs)

        # Compute overall I/O span (min START to max END across all ops)
        all_starts = []
        all_ends = []
        for op in ['read', 'write', 'meta']:
            start_val = signals.get(f'{op}_start_ts')
            end_val = signals.get(f'{op}_end_ts')
            if start_val is not None and not isinstance(start_val, str):
                all_starts.append(start_val)
            if end_val is not None and not isinstance(end_val, str):
                all_ends.append(end_val)

        if all_starts and all_ends:
            signals['io_span'] = max(0, max(all_ends) - min(all_starts))
        else:
            signals['io_span'] = self.na_with_reason('missing_timestamp')

        # Compute overall I/O time (cumulative across ops)
        io_time = 0
        io_time_valid = False
        for op in ['read', 'write', 'meta']:
            t = signals.get(f'{op}_time')
            if t is not None and not isinstance(t, str):
                io_time += t
                io_time_valid = True

        signals['io_time'] = io_time if io_time_valid else self.na_with_reason('missing_time_counter')

        # Compute overall busy fraction
        io_span = signals.get('io_span')
        if io_time_valid and io_span is not None and not isinstance(io_span, str) and io_span > 1e-9:
            signals['busy_frac'] = io_time / io_span
        else:
            signals['busy_frac'] = self.na_with_reason('dependency_missing')

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

            # ==== POSIX-SPECIFIC TIME SIGNALS ====
            # Average latency per operation
            if reads > 0 and read_time > 0:
                signals['avg_read_lat'] = read_time / reads
            else:
                signals['avg_read_lat'] = self.na_with_reason('no_reads' if reads == 0 else 'no_read_time')

            if writes > 0 and write_time > 0:
                signals['avg_write_lat'] = write_time / writes
            else:
                signals['avg_write_lat'] = self.na_with_reason('no_writes' if writes == 0 else 'no_write_time')

            # Max (slowest) operation times
            max_read_time = get('POSIX_F_MAX_READ_TIME', None)
            max_write_time = get('POSIX_F_MAX_WRITE_TIME', None)
            max_read_time_size = get('POSIX_MAX_READ_TIME_SIZE', None)
            max_write_time_size = get('POSIX_MAX_WRITE_TIME_SIZE', None)

            signals['max_read_time'] = max_read_time if max_read_time is not None and not isinstance(max_read_time, str) else self.na_with_reason('not_available')
            signals['max_write_time'] = max_write_time if max_write_time is not None and not isinstance(max_write_time, str) else self.na_with_reason('not_available')
            signals['max_read_time_size'] = max_read_time_size if max_read_time_size is not None and not isinstance(max_read_time_size, str) else self.na_with_reason('not_available')
            signals['max_write_time_size'] = max_write_time_size if max_write_time_size is not None and not isinstance(max_write_time_size, str) else self.na_with_reason('not_available')

            # Tail latency ratio (max / avg)
            avg_read_lat = signals.get('avg_read_lat')
            if max_read_time is not None and not isinstance(max_read_time, str) and avg_read_lat is not None and not isinstance(avg_read_lat, str) and avg_read_lat > 1e-9:
                signals['tail_read_ratio'] = max_read_time / avg_read_lat
            else:
                signals['tail_read_ratio'] = self.na_with_reason('dependency_missing')

            avg_write_lat = signals.get('avg_write_lat')
            if max_write_time is not None and not isinstance(max_write_time, str) and avg_write_lat is not None and not isinstance(avg_write_lat, str) and avg_write_lat > 1e-9:
                signals['tail_write_ratio'] = max_write_time / avg_write_lat
            else:
                signals['tail_write_ratio'] = self.na_with_reason('dependency_missing')

            # RW switches (access alternation)
            rw_switches = get('POSIX_RW_SWITCHES', None)
            signals['rw_switches'] = rw_switches if rw_switches is not None and not isinstance(rw_switches, str) else self.na_with_reason('not_available')

            # RW switch rate (normalized by span)
            io_span_val = signals.get('io_span')
            if rw_switches is not None and not isinstance(rw_switches, str) and io_span_val is not None and not isinstance(io_span_val, str) and io_span_val > 1e-9:
                signals['rw_switch_rate'] = rw_switches / io_span_val
            else:
                signals['rw_switch_rate'] = self.na_with_reason('dependency_missing')

            # Rank time imbalance (shared files only)
            if rank == -1:
                fastest_rank_time = get('POSIX_F_FASTEST_RANK_TIME', None)
                slowest_rank_time = get('POSIX_F_SLOWEST_RANK_TIME', None)
                variance_rank_time = get('POSIX_F_VARIANCE_RANK_TIME', None)

                signals['fastest_rank_time'] = fastest_rank_time if fastest_rank_time is not None and not isinstance(fastest_rank_time, str) else self.na_with_reason('not_available')
                signals['slowest_rank_time'] = slowest_rank_time if slowest_rank_time is not None and not isinstance(slowest_rank_time, str) else self.na_with_reason('not_available')
                signals['var_rank_time'] = variance_rank_time if variance_rank_time is not None and not isinstance(variance_rank_time, str) else self.na_with_reason('not_available')

                # Rank time imbalance ratio
                if fastest_rank_time is not None and slowest_rank_time is not None and not isinstance(fastest_rank_time, str) and not isinstance(slowest_rank_time, str) and slowest_rank_time > 1e-9:
                    signals['rank_time_imb'] = (slowest_rank_time - fastest_rank_time) / slowest_rank_time
                else:
                    signals['rank_time_imb'] = self.na_with_reason('dependency_missing')
            else:
                signals['fastest_rank_time'] = self.na_with_reason('not_shared_file')
                signals['slowest_rank_time'] = self.na_with_reason('not_shared_file')
                signals['var_rank_time'] = self.na_with_reason('not_shared_file')
                signals['rank_time_imb'] = self.na_with_reason('not_shared_file')

        # ==== STDIO-SPECIFIC TIME SIGNALS ====
        elif 'STDIO' in module:
            # Rank time imbalance (shared files only)
            if rank == -1:
                fastest_rank_time = get('STDIO_F_FASTEST_RANK_TIME', None)
                slowest_rank_time = get('STDIO_F_SLOWEST_RANK_TIME', None)
                variance_rank_time = get('STDIO_F_VARIANCE_RANK_TIME', None)

                signals['fastest_rank_time'] = fastest_rank_time if fastest_rank_time is not None and not isinstance(fastest_rank_time, str) else self.na_with_reason('not_available')
                signals['slowest_rank_time'] = slowest_rank_time if slowest_rank_time is not None and not isinstance(slowest_rank_time, str) else self.na_with_reason('not_available')
                signals['var_rank_time'] = variance_rank_time if variance_rank_time is not None and not isinstance(variance_rank_time, str) else self.na_with_reason('not_available')

                # Rank time imbalance ratio
                if fastest_rank_time is not None and slowest_rank_time is not None and not isinstance(fastest_rank_time, str) and not isinstance(slowest_rank_time, str) and slowest_rank_time > 1e-9:
                    signals['rank_time_imb'] = (slowest_rank_time - fastest_rank_time) / slowest_rank_time
                else:
                    signals['rank_time_imb'] = self.na_with_reason('dependency_missing')
            else:
                signals['fastest_rank_time'] = self.na_with_reason('not_shared_file')
                signals['slowest_rank_time'] = self.na_with_reason('not_shared_file')
                signals['var_rank_time'] = self.na_with_reason('not_shared_file')
                signals['rank_time_imb'] = self.na_with_reason('not_shared_file')

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

    def get_signal_descriptions(self, module):
        """Get signal descriptions for each module"""
        if 'POSIX' in module or 'STDIO' in module or 'MPI-IO' in module:
            base_desc = """# description of derived signals:
#
# ==== TIME METRICS (CORE) ====
#   SIGNAL_READ_START_TS: timestamp of first read operation
#   SIGNAL_READ_END_TS: timestamp of last read operation
#   SIGNAL_WRITE_START_TS: timestamp of first write operation
#   SIGNAL_WRITE_END_TS: timestamp of last write operation
#   SIGNAL_META_START_TS: timestamp of first metadata operation
#   SIGNAL_META_END_TS: timestamp of last metadata operation
#   SIGNAL_READ_TIME: cumulative time spent in read operations (seconds)
#   SIGNAL_WRITE_TIME: cumulative time spent in write operations (seconds)
#   SIGNAL_META_TIME: cumulative time spent in metadata operations (seconds)
#   SIGNAL_READ_SPAN: wall-clock span of read operations = READ_END_TS - READ_START_TS
#   SIGNAL_WRITE_SPAN: wall-clock span of write operations = WRITE_END_TS - WRITE_START_TS
#   SIGNAL_META_SPAN: wall-clock span of metadata operations = META_END_TS - META_START_TS
#   SIGNAL_IO_SPAN: overall I/O span = max(all_END_TS) - min(all_START_TS)
#   SIGNAL_IO_TIME: overall cumulative I/O time = READ_TIME + WRITE_TIME + META_TIME
#   SIGNAL_READ_BUSY_FRAC: read busy fraction = READ_TIME / READ_SPAN
#   SIGNAL_WRITE_BUSY_FRAC: write busy fraction = WRITE_TIME / WRITE_SPAN
#   SIGNAL_META_BUSY_FRAC: metadata busy fraction = META_TIME / META_SPAN
#   SIGNAL_BUSY_FRAC: overall busy fraction = IO_TIME / IO_SPAN
#
# ==== PERFORMANCE METRICS ====
#   SIGNAL_READ_BW: read bandwidth in MB/s = bytes_read / 1024² / read_time
#   SIGNAL_WRITE_BW: write bandwidth in MB/s = bytes_written / 1024² / write_time
#   SIGNAL_READ_IOPS: read operations per second = reads / read_time
#   SIGNAL_WRITE_IOPS: write operations per second = writes / read_time
#   SIGNAL_AVG_READ_SIZE: average read size in bytes = bytes_read / reads
#   SIGNAL_AVG_WRITE_SIZE: average write size in bytes = bytes_written / writes
#   SIGNAL_SEQ_RATIO: sequential access ratio = (seq_reads + seq_writes) / (reads + writes)
#   SIGNAL_CONSEC_RATIO: consecutive access ratio = (consec_reads + consec_writes) / (reads + writes)
#   SIGNAL_SEQ_READ_RATIO: sequential read ratio = seq_reads / reads (POSIX only)
#   SIGNAL_SEQ_WRITE_RATIO: sequential write ratio = seq_writes / writes (POSIX only)
#   SIGNAL_CONSEC_READ_RATIO: consecutive read ratio = consec_reads / reads (POSIX only)
#   SIGNAL_CONSEC_WRITE_RATIO: consecutive write ratio = consec_writes / writes (POSIX only)
#
# ==== METADATA (POSIX only) ====
#   SIGNAL_META_OPS: total metadata operations = opens + stats + seeks + fsyncs + fdsyncs
#   SIGNAL_META_INTENSITY: metadata intensity = meta_ops / (reads + writes)
#   SIGNAL_META_FRACTION: metadata time fraction = meta_time / total_time
#
# ==== ALIGNMENT (POSIX only) ====
#   SIGNAL_UNALIGNED_READ_RATIO: unaligned read ratio = not_aligned_reads / reads
#   SIGNAL_UNALIGNED_WRITE_RATIO: unaligned write ratio = not_aligned_writes / writes
#
# ==== SMALL I/O (POSIX only) ====
#   SIGNAL_SMALL_READ_RATIO: small read ratio (< 10KB) = (size_0-100 + size_100-1K + size_1K-10K) / reads
#   SIGNAL_SMALL_WRITE_RATIO: small write ratio (< 10KB) = (size_0-100 + size_100-1K + size_1K-10K) / writes
#
# ==== DATA REUSE (POSIX only) ====
#   SIGNAL_REUSE_PROXY: data reuse proxy = bytes_read / (MAX_BYTE_READ + 1)
#
# ==== RANK IMBALANCE (shared files only, rank=-1) ====
#   SIGNAL_RANK_IMBALANCE_RATIO: rank byte imbalance = slowest_rank_bytes / fastest_rank_bytes
#   SIGNAL_BW_VARIANCE_PROXY: bandwidth variance proxy = variance_rank_bytes
#   SIGNAL_FASTEST_RANK_TIME: fastest rank I/O time (shared files)
#   SIGNAL_SLOWEST_RANK_TIME: slowest rank I/O time (shared files)
#   SIGNAL_VAR_RANK_TIME: variance of rank I/O times (shared files)
#   SIGNAL_RANK_TIME_IMB: rank time imbalance = (slowest_time - fastest_time) / slowest_time
#   SIGNAL_IS_SHARED: shared file indicator = 1 if rank=-1, else 0
"""
            if 'POSIX' in module:
                posix_specific = """#
# ==== POSIX-SPECIFIC TIME METRICS ====
#   SIGNAL_AVG_READ_LAT: average read latency per operation = read_time / reads
#   SIGNAL_AVG_WRITE_LAT: average write latency per operation = write_time / writes
#   SIGNAL_MAX_READ_TIME: duration of slowest read operation
#   SIGNAL_MAX_WRITE_TIME: duration of slowest write operation
#   SIGNAL_MAX_READ_TIME_SIZE: size of slowest read operation (bytes)
#   SIGNAL_MAX_WRITE_TIME_SIZE: size of slowest write operation (bytes)
#   SIGNAL_TAIL_READ_RATIO: read tail latency ratio = max_read_time / avg_read_lat
#   SIGNAL_TAIL_WRITE_RATIO: write tail latency ratio = max_write_time / avg_write_lat
#   SIGNAL_RW_SWITCHES: number of read/write access alternations
#   SIGNAL_RW_SWITCH_RATE: RW switch rate = rw_switches / io_span
"""
                return base_desc + posix_specific
            else:
                return base_desc
        elif 'HEATMAP' in module:
            return """# description of HEATMAP derived signals:
#   SIGNAL_TOTAL_READ_EVENTS: total read events across all bins = Σ READ_BIN_k
#   SIGNAL_TOTAL_WRITE_EVENTS: total write events across all bins = Σ WRITE_BIN_k
#   SIGNAL_ACTIVE_BINS: number of bins with activity = |{k | (READ_BIN_k + WRITE_BIN_k) > 0}|
#   SIGNAL_ACTIVE_TIME: total active time in seconds = active_bins × BIN_WIDTH_SECONDS
#   SIGNAL_ACTIVITY_SPAN: time span from first to last active bin = (k_last - k_first + 1) × BIN_WIDTH_SECONDS
#   SIGNAL_PEAK_ACTIVITY_BIN: bin index with maximum activity = argmax_k (READ_BIN_k + WRITE_BIN_k)
#   SIGNAL_PEAK_ACTIVITY_VALUE: maximum activity value = max_k (READ_BIN_k + WRITE_BIN_k)
#   SIGNAL_READ_ACTIVITY_ENTROPY_NORM: normalized entropy of read distribution [0,1] = H(reads) / log(N)
#   SIGNAL_WRITE_ACTIVITY_ENTROPY_NORM: normalized entropy of write distribution [0,1] = H(writes) / log(N)
#   SIGNAL_TOP1_SHARE: fraction of activity in peak bin = max_k(activity) / Σ(activity)
"""
        return ""

    def write_signals_output(self, output_path):
        """Write output in Darshan log format"""
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write original header
            for header_line in self.header_lines:
                f.write(header_line + "\n")

            f.write("\n")
            f.write("# *******************************************************\n")
            f.write("# JOB LEVEL - Derived Signals\n")
            f.write("# *******************************************************\n")
            f.write("#\n")
            f.write("# Job-level aggregates:\n")
            f.write("#   total_bytes_read: sum of all bytes read across all modules\n")
            f.write("#   total_bytes_written: sum of all bytes written across all modules\n")
            f.write("#   total_reads: sum of all read operations\n")
            f.write("#   total_writes: sum of all write operations\n")
            f.write("#\n")
            f.write("#<level>\t<metric>\t<value>\n")

            job_agg = self.compute_job_aggregates()
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

            # Module Level and Record Level
            for module in sorted(modules.keys()):
                f.write("# *******************************************************\n")
                f.write(f"# {module} module - Derived Signals\n")
                f.write("# *******************************************************\n")
                f.write("#\n")

                # Signal descriptions
                f.write(self.get_signal_descriptions(module))
                f.write("#\n")

                # Module aggregates (skip for HEATMAP)
                if 'HEATMAP' not in module:
                    module_agg, module_signals = self.compute_module_aggregates(module)

                    f.write("# Module-level aggregates:\n")
                    f.write("#<module>\t<level>\t<metric>\t<value>\n")
                    for key, value in module_agg.items():
                        f.write(f"{module}\tMODULE_AGG\t{key}\t{value}\n")

                    f.write("\n# Module-level performance signals:\n")
                    f.write("#<module>\t<level>\t<metric>\t<value>\n")
                    for key, value in module_signals.items():
                        f.write(f"{module}\tMODULE_PERF\t{key}\t{value}\n")

                    f.write("\n")

                # Record Level
                for rank, record_id in sorted(modules[module]):
                    key = (module, rank, record_id)
                    record = self.records[key]
                    signals = record['signals']

                    # Get file metadata
                    if key in self.file_metadata:
                        meta = self.file_metadata[key]
                        file_name = meta['file_name']
                        mount_pt = meta['mount_pt']
                        fs_type = meta['fs_type']
                    else:
                        file_name = "UNKNOWN"
                        mount_pt = "UNKNOWN"
                        fs_type = "UNKNOWN"

                    # Record header (similar to original Darshan format)
                    f.write(f"# Record: {record_id}, rank={rank}, file={file_name}, mount={mount_pt}, fs={fs_type}\n")
                    f.write("#<counter>\t<value>\n")

                    # Write all signals for this record
                    for signal_key, signal_value in sorted(signals.items()):
                        counter_name = f"SIGNAL_{signal_key.upper()}"
                        f.write(f"{counter_name}\t{signal_value}\n")

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
        output_file = output_path / rel_path.parent / f"{rel_path.stem}_signals_v2.4.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            process_single_file(txt_file, output_file)
        except Exception as e:
            print(f"ERROR processing {txt_file}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description='Extract Darshan log signals v2.4',
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
            output_file = input_path.parent / f"{input_path.stem}_signals_v2.4.txt"
        process_single_file(input_path, output_file)

    elif input_path.is_dir():
        if args.output:
            output_dir = Path(args.output)
        else:
            output_dir = input_path.parent / f"{input_path.name}_signals_v2.4"
        process_directory(input_path, output_dir)

    print("\nProcessing complete!")


if __name__ == '__main__':
    main()
