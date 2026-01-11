import os
import re
import math
import argparse
from dataclasses import dataclass
from typing import Optional, List, Iterable, Dict
import statistics

RE_EXE = re.compile(r"^#\s*exe:\s*(\S+)\s*$")
RE_JOBID = re.compile(r"^#\s*jobid:\s*(\d+)\s*$")
RE_NPROCS = re.compile(r"^#\s*nprocs:\s*(\d+)\s*$")

# Constants for counters
POSIX_OPENS = "POSIX_OPENS"
POSIX_READS = "POSIX_READS"
POSIX_WRITES = "POSIX_WRITES"
POSIX_STATS = "POSIX_STATS"
POSIX_SEEKS = "POSIX_SEEKS"
POSIX_BYTES_READ = "POSIX_BYTES_READ"
POSIX_BYTES_WRITTEN = "POSIX_BYTES_WRITTEN"

@dataclass
class JobRec:
    path: str
    jobid: Optional[int]
    exe: Optional[str]
    nprocs: Optional[int]
    total_bytes: int  # sum of all bytes
    
    # I/O phases counts
    posix_opens: int
    posix_reads: int
    posix_writes: int
    posix_stats: int
    posix_seeks: int
    
    # I/O behavior metrics
    io_phase_open_ratio: Optional[float]  # opens / total_ops
    io_phase_read_ratio: Optional[float]  # reads / total_ops
    io_phase_write_ratio: Optional[float]  # writes / total_ops
    avg_request_size: Optional[float]  # total_bytes / (reads + writes)
    open_stat_seek_ratio: Optional[float]  # (opens + stats + seeks) / total_bytes
    
    # Rank imbalance (gini coefficient)
    rank_imbalance_gini: Optional[float]  # Gini coefficient of bytes per rank

def safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None

def safe_int(s: str) -> Optional[int]:
    try:
        return int(float(s))
    except Exception:
        return None

def calculate_gini(values: List[float], include_zeros: bool = False) -> Optional[float]:
    """
    Calculate Gini coefficient for a list of values.
    Gini coefficient measures inequality (0 = perfect equality, 1 = maximum inequality).
    
    Args:
        values: List of values to calculate Gini for
        include_zeros: If True, include zero values in calculation. If False, filter them out.
    """
    if not values or len(values) < 2:
        return None
    
    # Filter out non-positive values if not including zeros
    if include_zeros:
        # Include zeros, but filter out negative values
        filtered_vals = [v for v in values if v >= 0]
    else:
        # Filter out non-positive values
        filtered_vals = [v for v in values if v > 0]
    
    if len(filtered_vals) < 2:
        return None
    
    # Sort values
    sorted_vals = sorted(filtered_vals)
    n = len(sorted_vals)
    
    # Check if all values are zero
    total_sum = sum(sorted_vals)
    if total_sum == 0:
        return 0.0
    
    cumsum = 0
    for i, val in enumerate(sorted_vals):
        cumsum += (i + 1) * val
    
    # Gini = (2 * cumsum) / (n * sum) - (n + 1) / n
    gini = (2 * cumsum) / (n * total_sum) - (n + 1) / n
    return gini

def parse_one_txt(path: str) -> JobRec:
    jobid = None
    exe = None
    nprocs = None
    
    # POSIX counters
    posix_opens = 0
    posix_reads = 0
    posix_writes = 0
    posix_stats = 0
    posix_seeks = 0
    posix_bytes_read = 0
    posix_bytes_written = 0
    
    # Collect bytes per rank for gini calculation
    rank_bytes: Dict[int, int] = {}  # rank -> total bytes

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue

            # Header lines
            m = RE_EXE.match(line)
            if m:
                exe = m.group(1)
                continue

            m = RE_JOBID.match(line)
            if m:
                jobid = int(m.group(1))
                continue

            m = RE_NPROCS.match(line)
            if m:
                nprocs = int(m.group(1))
                continue

            # Data rows: MODULE\tRANK\tRECORD_ID\tCOUNTER_NAME\tCOUNTER_VALUE\t...
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            
            module = parts[0]
            if module != "POSIX":
                continue
            
            rank_str = parts[1]
            counter = parts[3]
            value_s = parts[4]
            
            # Parse rank (can be -1 for shared files)
            try:
                rank = int(rank_str)
            except (ValueError, IndexError):
                rank = -1
            
            # Parse POSIX counters
            if counter == POSIX_OPENS:
                v = safe_int(value_s)
                if v is not None:
                    posix_opens += v
            elif counter == POSIX_READS:
                v = safe_int(value_s)
                if v is not None:
                    posix_reads += v
            elif counter == POSIX_WRITES:
                v = safe_int(value_s)
                if v is not None:
                    posix_writes += v
            elif counter == POSIX_STATS:
                v = safe_int(value_s)
                if v is not None:
                    posix_stats += v
            elif counter == POSIX_SEEKS:
                v = safe_int(value_s)
                if v is not None:
                    posix_seeks += v
            elif counter == POSIX_BYTES_READ:
                v = safe_int(value_s)
                if v is not None and v > 0:
                    posix_bytes_read += v
                    # Track bytes per rank (only for non-shared files, rank >= 0)
                    if rank >= 0:
                        rank_bytes[rank] = rank_bytes.get(rank, 0) + v
            elif counter == POSIX_BYTES_WRITTEN:
                v = safe_int(value_s)
                if v is not None and v > 0:
                    posix_bytes_written += v
                    # Track bytes per rank (only for non-shared files, rank >= 0)
                    if rank >= 0:
                        rank_bytes[rank] = rank_bytes.get(rank, 0) + v

    # Calculate totals
    total_bytes = posix_bytes_read + posix_bytes_written
    total_ops = posix_opens + posix_reads + posix_writes
    
    # Calculate I/O behavior metrics
    # I/O phases ratios
    io_phase_open_ratio = None
    io_phase_read_ratio = None
    io_phase_write_ratio = None
    if total_ops > 0:
        io_phase_open_ratio = posix_opens / total_ops
        io_phase_read_ratio = posix_reads / total_ops
        io_phase_write_ratio = posix_writes / total_ops
    
    # Average request size
    avg_request_size = None
    read_write_ops = posix_reads + posix_writes
    if read_write_ops > 0 and total_bytes > 0:
        avg_request_size = total_bytes / read_write_ops
    
    # open/stat/seek ratio per total_bytes
    open_stat_seek_ratio = None
    open_stat_seek_ops = posix_opens + posix_stats + posix_seeks
    if total_bytes > 0 and open_stat_seek_ops > 0:
        open_stat_seek_ratio = open_stat_seek_ops / total_bytes
    
    # Calculate rank imbalance (gini coefficient)
    # If we know nprocs, initialize all ranks to 0, then update with actual data
    rank_imbalance_gini = None
    
    if nprocs is not None and nprocs > 0:
        # Initialize all ranks to 0
        all_rank_bytes = {r: 0 for r in range(nprocs)}
        
        # Update with actual data
        for rank, bytes_val in rank_bytes.items():
            if 0 <= rank < nprocs:
                all_rank_bytes[rank] = bytes_val
        
        # Calculate gini on all ranks (including zeros)
        bytes_per_rank = list(all_rank_bytes.values())
        
        if len(bytes_per_rank) >= 2:
            # When we know nprocs, include zeros in gini calculation
            rank_imbalance_gini = calculate_gini(bytes_per_rank, include_zeros=True)
    elif rank_bytes and len(rank_bytes) >= 2:
        # Don't know nprocs, but have data from multiple ranks
        bytes_per_rank = list(rank_bytes.values())
        rank_imbalance_gini = calculate_gini(bytes_per_rank)
    elif rank_bytes and len(rank_bytes) == 1:
        # Only one rank has data, but we don't know total nprocs
        # Can't determine imbalance without knowing if other ranks should have data
        rank_imbalance_gini = None

    return JobRec(
        path=path,
        jobid=jobid,
        exe=exe,
        nprocs=nprocs,
        total_bytes=total_bytes,
        posix_opens=posix_opens,
        posix_reads=posix_reads,
        posix_writes=posix_writes,
        posix_stats=posix_stats,
        posix_seeks=posix_seeks,
        io_phase_open_ratio=io_phase_open_ratio,
        io_phase_read_ratio=io_phase_read_ratio,
        io_phase_write_ratio=io_phase_write_ratio,
        avg_request_size=avg_request_size,
        open_stat_seek_ratio=open_stat_seek_ratio,
        rank_imbalance_gini=rank_imbalance_gini,
    )

def iter_txt_files(report_dir: str) -> Iterable[str]:
    """
    Recursively traverse report_dir and all its subdirectories,
    yielding paths to all non-hidden files.
    """
    visited_dirs = set()
    for root, dirs, files in os.walk(report_dir):
        visited_dirs.add(root)
        for fn in files:
            if fn.startswith("."):
                continue
            yield os.path.join(root, fn)
    # Print summary of directories searched
    print(f"Searched {len(visited_dirs)} directories under: {report_dir}")

def load_all(report_dir: str) -> List[JobRec]:
    recs = []
    for p in iter_txt_files(report_dir):
        try:
            recs.append(parse_one_txt(p))
        except Exception:
            continue
    # keep only records with at least exe
    recs = [r for r in recs if r.exe is not None]
    return recs

def calculate_z_score(value: float, values: List[float]) -> Optional[float]:
    """Calculate z-score for a value relative to a list of values."""
    if not values or len(values) < 2:
        return None
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    if stdev == 0:
        return None
    return (value - mean) / stdev

def calculate_percentile(value: float, values: List[float]) -> Optional[float]:
    """Calculate percentile (0-100) for a value in a sorted list."""
    if not values:
        return None
    sorted_vals = sorted([v for v in values if v is not None])
    if not sorted_vals:
        return None
    count_below = sum(1 for v in sorted_vals if v < value)
    percentile = (count_below / len(sorted_vals)) * 100
    return percentile

def main():
    ap = argparse.ArgumentParser(
        description="Parse a darshan txt file and find similar jobs by application name, calculate I/O behavior metrics and rank imbalance, output z-score/percentile"
    )
    ap.add_argument("--target", required=True, help="target darshan txt file to parse")
    ap.add_argument(
        "--dir", default=None,
        help="optional: parent directory to search for similar jobs (default: parent directory of target file)"
    )
    ap.add_argument("--limit", type=int, default=None, help="optional: limit number of results (default: all)")
    args = ap.parse_args()

    # Parse target file
    target_rec = parse_one_txt(args.target)
    print(f"Target file: {args.target}")
    print(f"  exe: {target_rec.exe}")
    print(f"  total_bytes: {target_rec.total_bytes}")
    print(f"  nprocs: {target_rec.nprocs}")
    print(f"  jobid: {target_rec.jobid}")
    print(f"  I/O Phases - Open ratio: {target_rec.io_phase_open_ratio}, Read ratio: {target_rec.io_phase_read_ratio}, Write ratio: {target_rec.io_phase_write_ratio}")
    print(f"  Avg request size: {target_rec.avg_request_size}")
    print(f"  Open/Stat/Seek ratio: {target_rec.open_stat_seek_ratio}")
    print(f"  Rank imbalance (Gini): {target_rec.rank_imbalance_gini}")
    print()

    # Determine search directory
    search_dir = args.dir if args.dir else os.path.dirname(os.path.abspath(args.target))
    
    # Load all jobs
    recs = load_all(search_dir)
    if not recs:
        raise SystemExit("No valid darshan txt reports parsed from the directory.")

    # Filter by same application name (exe)
    if target_rec.exe is None:
        raise SystemExit("Target file has no exe identifier.")
    
    filtered_recs = [r for r in recs if r.exe == target_rec.exe]
    
    # Exclude target from results for comparison
    out = [r for r in filtered_recs if r.path != args.target]
    
    # Apply limit if specified
    if args.limit is not None and args.limit > 0:
        out = out[:args.limit]

    print(f"Filter by: exe (application name)")
    print(f"Parsed jobs: {len(recs)}")
    print(f"Candidates after filter (same exe): {len(filtered_recs)}")
    print(f"Results (excluding target): {len(out)}")
    if args.limit is not None:
        print(f"Limit applied: {args.limit}")
    print()

    # Calculate z-score and percentile for target metrics
    metrics_to_calculate = [
        ("IO Phase Open Ratio", target_rec.io_phase_open_ratio, [r.io_phase_open_ratio for r in out if r.io_phase_open_ratio is not None]),
        ("IO Phase Read Ratio", target_rec.io_phase_read_ratio, [r.io_phase_read_ratio for r in out if r.io_phase_read_ratio is not None]),
        ("IO Phase Write Ratio", target_rec.io_phase_write_ratio, [r.io_phase_write_ratio for r in out if r.io_phase_write_ratio is not None]),
        ("Avg Request Size", target_rec.avg_request_size, [r.avg_request_size for r in out if r.avg_request_size is not None]),
        ("Open/Stat/Seek Ratio", target_rec.open_stat_seek_ratio, [r.open_stat_seek_ratio for r in out if r.open_stat_seek_ratio is not None]),
        ("Rank Imbalance (Gini)", target_rec.rank_imbalance_gini, [r.rank_imbalance_gini for r in out if r.rank_imbalance_gini is not None]),
    ]

    print("=== Results ===")
    for r in out:
        print(
            f"path={r.path}\t"
            f"jobid={r.jobid}\texe={r.exe}\tnprocs={r.nprocs}\t"
            f"total_bytes={r.total_bytes}\t"
            f"open_ratio={r.io_phase_open_ratio}\tread_ratio={r.io_phase_read_ratio}\twrite_ratio={r.io_phase_write_ratio}\t"
            f"avg_req_size={r.avg_request_size}\topen_stat_seek_ratio={r.open_stat_seek_ratio}\t"
            f"rank_imbalance_gini={r.rank_imbalance_gini}"
        )

    print("\n=== Target Metrics Comparison ===")
    for metric_name, target_value, cohort_values in metrics_to_calculate:
        if target_value is None:
            print(f"{metric_name}: N/A (target value is None)")
            continue
        
        if not cohort_values:
            print(f"{metric_name}: {target_value} (no cohort values for comparison)")
            continue
        
        zscore = calculate_z_score(target_value, cohort_values)
        percentile = calculate_percentile(target_value, cohort_values)
        
        print(f"{metric_name}: {target_value}")
        if zscore is not None:
            print(f"  Z-score: {zscore:.4f}")
        if percentile is not None:
            print(f"  Percentile: {percentile:.2f}%")
        print()

if __name__ == "__main__":
    main()

