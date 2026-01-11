import os
import re
import math
import argparse
from dataclasses import dataclass
from typing import Optional, List, Iterable
import statistics

RE_EXE = re.compile(r"^#\s*exe:\s*(\S+)\s*$")
RE_JOBID = re.compile(r"^#\s*jobid:\s*(\d+)\s*$")
RE_NPROCS = re.compile(r"^#\s*nprocs:\s*(\d+)\s*$")
RE_AGG_PERF = re.compile(r"^#\s*agg_perf_by_slowest:\s*([0-9]*\.?[0-9]+)")
# Match data rows like: POSIX	0	...	POSIX_BYTES_READ	77	...
# Format: MODULE\tRANK\tRECORD_ID\tCOUNTER_NAME\tCOUNTER_VALUE\t...
RE_BYTES_ROW = re.compile(r"^(POSIX|MPIIO|STDIO)\t[^\t]+\t[^\t]+\t(POSIX_BYTES_READ|POSIX_BYTES_WRITTEN|MPIIO_BYTES_READ|MPIIO_BYTES_WRITTEN|STDIO_BYTES_READ|STDIO_BYTES_WRITTEN)\t(\d+)\t")

# Constants for counters
POSIX_READS = "POSIX_READS"
POSIX_WRITES = "POSIX_WRITES"
POSIX_F_READ_TIME = "POSIX_F_READ_TIME"
POSIX_F_WRITE_TIME = "POSIX_F_WRITE_TIME"

STDIO_READS = "STDIO_READS"
STDIO_WRITES = "STDIO_WRITES"
STDIO_F_READ_TIME = "STDIO_F_READ_TIME"
STDIO_F_WRITE_TIME = "STDIO_F_WRITE_TIME"

MPIIO_READS = "MPIIO_READS"
MPIIO_WRITES = "MPIIO_WRITES"
MPIIO_F_READ_TIME = "MPIIO_F_READ_TIME"
MPIIO_F_WRITE_TIME = "MPIIO_F_WRITE_TIME"

@dataclass
class JobRec:
    path: str
    jobid: Optional[int]
    exe: Optional[str]
    nprocs: Optional[int]
    total_bytes_sum: int  # sum of all bytes from POSIX/STDIO/MPIIO
    # POSIX metrics
    posix_reads: int
    posix_writes: int
    posix_f_read_time: float
    posix_f_write_time: float
    posix_total_bytes: int
    posix_bw_mibs: Optional[float]  # POSIX bandwidth in MiB/s
    posix_iops: Optional[float]  # POSIX IOPS
    # STDIO metrics
    stdio_reads: int
    stdio_writes: int
    stdio_f_read_time: float
    stdio_f_write_time: float
    stdio_total_bytes: int
    stdio_bw_mibs: Optional[float]  # STDIO bandwidth in MiB/s
    stdio_iops: Optional[float]  # STDIO IOPS
    # MPIIO metrics
    mpiio_reads: int
    mpiio_writes: int
    mpiio_f_read_time: float
    mpiio_f_write_time: float
    mpiio_total_bytes: int
    mpiio_bw_mibs: Optional[float]  # MPIIO bandwidth in MiB/s
    mpiio_iops: Optional[float]  # MPIIO IOPS
    # Calculated metrics (aggregate across all modules)
    bw_mibs: Optional[float]  # Total bandwidth in MiB/s = total_bytes / total_time
    iops: Optional[float]  # Total IOPS = (total_reads + total_writes) / total_time

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

def parse_one_txt(path: str) -> JobRec:
    jobid = None
    exe = None
    nprocs = None
    
    # POSIX counters
    posix_reads = 0
    posix_writes = 0
    posix_f_read_time = 0.0
    posix_f_write_time = 0.0
    posix_bytes_read = 0
    posix_bytes_written = 0
    
    # STDIO counters
    stdio_reads = 0
    stdio_writes = 0
    stdio_f_read_time = 0.0
    stdio_f_write_time = 0.0
    stdio_bytes_read = 0
    stdio_bytes_written = 0
    
    # MPIIO counters
    mpiio_reads = 0
    mpiio_writes = 0
    mpiio_f_read_time = 0.0
    mpiio_f_write_time = 0.0
    mpiio_bytes_read = 0
    mpiio_bytes_written = 0

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")

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

            # Parse data rows: MODULE\tRANK\tRECORD_ID\tCOUNTER_NAME\tCOUNTER_VALUE\t...
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            
            module = parts[0]
            counter = parts[3]
            value_s = parts[4]
            
            # Parse POSIX module
            if module == "POSIX":
                if counter == POSIX_READS:
                    v = safe_int(value_s)
                    if v is not None:
                        posix_reads += v
                elif counter == POSIX_WRITES:
                    v = safe_int(value_s)
                    if v is not None:
                        posix_writes += v
                elif counter == POSIX_F_READ_TIME:
                    v = safe_float(value_s)
                    if v is not None and v > 0:
                        posix_f_read_time += v
                elif counter == POSIX_F_WRITE_TIME:
                    v = safe_float(value_s)
                    if v is not None and v > 0:
                        posix_f_write_time += v
                elif counter == "POSIX_BYTES_READ":
                    v = safe_int(value_s)
                    if v is not None:
                        posix_bytes_read += v
                elif counter == "POSIX_BYTES_WRITTEN":
                    v = safe_int(value_s)
                    if v is not None:
                        posix_bytes_written += v
            
            # Parse STDIO module
            elif module == "STDIO":
                if counter == STDIO_READS:
                    v = safe_int(value_s)
                    if v is not None:
                        stdio_reads += v
                elif counter == STDIO_WRITES:
                    v = safe_int(value_s)
                    if v is not None:
                        stdio_writes += v
                elif counter == STDIO_F_READ_TIME:
                    v = safe_float(value_s)
                    if v is not None and v > 0:
                        stdio_f_read_time += v
                elif counter == STDIO_F_WRITE_TIME:
                    v = safe_float(value_s)
                    if v is not None and v > 0:
                        stdio_f_write_time += v
                elif counter == "STDIO_BYTES_READ":
                    v = safe_int(value_s)
                    if v is not None:
                        stdio_bytes_read += v
                elif counter == "STDIO_BYTES_WRITTEN":
                    v = safe_int(value_s)
                    if v is not None:
                        stdio_bytes_written += v
            
            # Parse MPIIO module
            elif module == "MPIIO":
                if counter == MPIIO_READS:
                    v = safe_int(value_s)
                    if v is not None:
                        mpiio_reads += v
                elif counter == MPIIO_WRITES:
                    v = safe_int(value_s)
                    if v is not None:
                        mpiio_writes += v
                elif counter == MPIIO_F_READ_TIME:
                    v = safe_float(value_s)
                    if v is not None and v > 0:
                        mpiio_f_read_time += v
                elif counter == MPIIO_F_WRITE_TIME:
                    v = safe_float(value_s)
                    if v is not None and v > 0:
                        mpiio_f_write_time += v
                elif counter == "MPIIO_BYTES_READ":
                    v = safe_int(value_s)
                    if v is not None:
                        mpiio_bytes_read += v
                elif counter == "MPIIO_BYTES_WRITTEN":
                    v = safe_int(value_s)
                    if v is not None:
                        mpiio_bytes_written += v

    # Calculate totals
    posix_total_bytes = posix_bytes_read + posix_bytes_written
    stdio_total_bytes = stdio_bytes_read + stdio_bytes_written
    mpiio_total_bytes = mpiio_bytes_read + mpiio_bytes_written
    total_bytes_sum = posix_total_bytes + stdio_total_bytes + mpiio_total_bytes
    
    # Calculate total time: POSIX_Total_T = POSIX_F_READ_TIME + POSIX_F_WRITE_TIME (same for STDIO/MPIIO)
    posix_total_t = posix_f_read_time + posix_f_write_time
    stdio_total_t = stdio_f_read_time + stdio_f_write_time
    mpiio_total_t = mpiio_f_read_time + mpiio_f_write_time
    
    # Calculate BW and IOPS for each module
    # POSIX
    posix_bw_mibs = None
    posix_iops = None
    if posix_total_t > 0:
        if posix_total_bytes > 0:
            posix_bw_mibs = (posix_total_bytes / posix_total_t) / (1024 * 1024)
        posix_total_ops = posix_reads + posix_writes
        if posix_total_ops > 0:
            posix_iops = posix_total_ops / posix_total_t
    
    # STDIO
    stdio_bw_mibs = None
    stdio_iops = None
    if stdio_total_t > 0:
        if stdio_total_bytes > 0:
            stdio_bw_mibs = (stdio_total_bytes / stdio_total_t) / (1024 * 1024)
        stdio_total_ops = stdio_reads + stdio_writes
        if stdio_total_ops > 0:
            stdio_iops = stdio_total_ops / stdio_total_t
    
    # MPIIO
    mpiio_bw_mibs = None
    mpiio_iops = None
    if mpiio_total_t > 0:
        if mpiio_total_bytes > 0:
            mpiio_bw_mibs = (mpiio_total_bytes / mpiio_total_t) / (1024 * 1024)
        mpiio_total_ops = mpiio_reads + mpiio_writes
        if mpiio_total_ops > 0:
            mpiio_iops = mpiio_total_ops / mpiio_total_t
    
    # Aggregate total time across all modules
    total_io_time = posix_total_t + stdio_total_t + mpiio_total_t
    
    # Calculate aggregate BW: BW = Total_bytes / Total_T (convert to MiB/s)
    bw_mibs = None
    if total_io_time > 0 and total_bytes_sum > 0:
        bw_mibs = (total_bytes_sum / total_io_time) / (1024 * 1024)
    
    # Calculate aggregate IOPS: IOPS = (sum READS + sum WRITES) / Total_T
    total_reads = posix_reads + stdio_reads + mpiio_reads
    total_writes = posix_writes + stdio_writes + mpiio_writes
    total_ops = total_reads + total_writes
    
    iops = None
    if total_io_time > 0 and total_ops > 0:
        iops = total_ops / total_io_time

    return JobRec(
        path=path,
        jobid=jobid,
        exe=exe,
        nprocs=nprocs,
        total_bytes_sum=total_bytes_sum,
        posix_reads=posix_reads,
        posix_writes=posix_writes,
        posix_f_read_time=posix_f_read_time,
        posix_f_write_time=posix_f_write_time,
        posix_total_bytes=posix_total_bytes,
        posix_bw_mibs=posix_bw_mibs,
        posix_iops=posix_iops,
        stdio_reads=stdio_reads,
        stdio_writes=stdio_writes,
        stdio_f_read_time=stdio_f_read_time,
        stdio_f_write_time=stdio_f_write_time,
        stdio_total_bytes=stdio_total_bytes,
        stdio_bw_mibs=stdio_bw_mibs,
        stdio_iops=stdio_iops,
        mpiio_reads=mpiio_reads,
        mpiio_writes=mpiio_writes,
        mpiio_f_read_time=mpiio_f_read_time,
        mpiio_f_write_time=mpiio_f_write_time,
        mpiio_total_bytes=mpiio_total_bytes,
        mpiio_bw_mibs=mpiio_bw_mibs,
        mpiio_iops=mpiio_iops,
        bw_mibs=bw_mibs,
        iops=iops,
    )

def iter_txt_files(report_dir: str) -> Iterable[str]:
    """
    Recursively traverse report_dir and all its subdirectories,
    yielding paths to all non-hidden files.
    """
    # visited_dirs = set()
    # for root, dirs, files in os.walk(report_dir):
    #     visited_dirs.add(root)
    #     for fn in files:
    #         if fn.startswith("."):
    #             continue
    #         yield os.path.join(root, fn)
    # # Print summary of directories searched
    # print(f"Searched {len(visited_dirs)} directories under: {report_dir}")
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
    # keep only records with at least exe + some bytes
    recs = [r for r in recs if r.exe is not None and r.total_bytes_sum > 0]
    return recs

def log_dist_bytes(a: int, b: int) -> float:
    a = max(a, 1)
    b = max(b, 1)
    return abs(math.log(a) - math.log(b))

def apply_pipeline(
    recs: List[JobRec],
    filter_by: str,  # "exe" or "bytes"
    exe: Optional[str],
    total_bytes: Optional[int],
    nprocs: Optional[int],
    nprocs_tol: float,
    limit: Optional[int],
) -> List[JobRec]:
    """
    Filter jobs by application name OR I/O scale.
    filter_by: "exe" to filter by application name, "bytes" to filter by I/O scale
    """
    cur = list(recs)
    
    # Filter by exe or bytes
    if filter_by == "exe":
        if exe is None:
            raise ValueError("filter_by='exe' but exe is not provided.")
        cur = [r for r in cur if r.exe == exe]
    elif filter_by == "bytes":
        if total_bytes is None:
            raise ValueError("filter_by='bytes' but total_bytes is not provided.")
        # Sort by log distance to total_bytes
        cur.sort(key=lambda r: log_dist_bytes(r.total_bytes_sum, total_bytes))
    else:
        raise ValueError(f"filter_by must be 'exe' or 'bytes', got '{filter_by}'")
    
    # Optional: filter by nprocs
    if nprocs is not None:
        lo = math.floor(nprocs * (1 - nprocs_tol))
        hi = math.ceil(nprocs * (1 + nprocs_tol))
        cur = [r for r in cur if r.nprocs is not None and lo <= r.nprocs <= hi]
    
    # Apply limit if specified
    if limit is not None and limit > 0:
        cur = cur[:limit]
    
    return cur

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
    # ap = argparse.ArgumentParser(
    #     description="Parse a darshan txt file and find similar jobs based on exe/total_bytes/nprocs"
    # )
    # ap.add_argument("--target", required=True, help="target darshan txt file to parse (extract exe, total_bytes, nprocs)")
    # ap.add_argument(
    #     "--order", required=True,
    #     help="comma-separated pipeline steps, e.g. 'exe,total_bytes' or 'total_bytes,exe' or 'exe,nprocs,total_bytes'"
    # )
    # ap.add_argument(
    #     "--dir", default=None,
    #     help="optional: directory to search for similar jobs (default: parent directory of target file)"
    # )
    # ap.add_argument("--nprocs_tol", type=float, default=0.10, help="tolerance for nprocs filter (default: 0.10)")
    # ap.add_argument("--limit", type=int, default=None, help="optional: limit output to first N results")
    # args = ap.parse_args()
    
    ap = argparse.ArgumentParser(
        description="Parse a darshan txt file and find similar jobs, calculate BW/IOPS metrics and z-score/percentile"
    )
    ap.add_argument("--target", required=True, help="target darshan txt file to parse")
    ap.add_argument(
        "--filter_by", default="exe", choices=["exe", "bytes"],
        help="filter by application name (exe) or I/O scale (bytes)"
    )
    ap.add_argument(
        "--dir", default=None,
        help="optional: parent directory to search for similar jobs (default: parent directory of target file)"
    )
    ap.add_argument("--nprocs_tol", type=float, default=0.10, help="tolerance for nprocs filter (default: 0.10)")
    ap.add_argument("--limit", type=int, default=None, help="optional: limit number of results (default: all)")
    args = ap.parse_args()

    # Parse target file
    target_rec = parse_one_txt(args.target)
    print(f"Target file: {args.target}")
    print(f"  exe: {target_rec.exe}")
    print(f"  total_bytes: {target_rec.total_bytes_sum}")
    print(f"  nprocs: {target_rec.nprocs}")
    print(f"  jobid: {target_rec.jobid}")
    print(f"  Total BW (MiB/s): {target_rec.bw_mibs}")
    print(f"  Total IOPS: {target_rec.iops}")
    print(f"  POSIX - BW (MiB/s): {target_rec.posix_bw_mibs}, IOPS: {target_rec.posix_iops}")
    print(f"  STDIO - BW (MiB/s): {target_rec.stdio_bw_mibs}, IOPS: {target_rec.stdio_iops}")
    print(f"  MPIIO - BW (MiB/s): {target_rec.mpiio_bw_mibs}, IOPS: {target_rec.mpiio_iops}")
    print()

    # Determine search directory
    search_dir = args.dir if args.dir else os.path.dirname(os.path.abspath(args.target))
    
    # Load all jobs
    recs = load_all(search_dir)
    if not recs:
        raise SystemExit("No valid darshan txt reports parsed from the directory.")

    # Apply pipeline
    out_all = apply_pipeline(
        recs=recs,
        filter_by=args.filter_by,
        exe=target_rec.exe if args.filter_by == "exe" else None,
        total_bytes=target_rec.total_bytes_sum if args.filter_by == "bytes" else None,
        nprocs=target_rec.nprocs,
        nprocs_tol=args.nprocs_tol,
        limit=args.limit,
    )
    
    # Exclude target from results for comparison
    out = [r for r in out_all if r.path != args.target]

    print(f"Filter by: {args.filter_by}")
    print(f"Parsed jobs: {len(recs)}")
    print(f"Candidates after filter: {len(out_all)}")
    print(f"Results (excluding target): {len(out)}")
    if args.limit is not None:
        print(f"Limit applied: {args.limit}")

    # Calculate z-score and percentile for target
    bw_values = [r.bw_mibs for r in out if r.bw_mibs is not None]
    iops_values = [r.iops for r in out if r.iops is not None]
    
    target_bw_zscore = None
    target_bw_percentile = None
    if target_rec.bw_mibs is not None and bw_values:
        target_bw_zscore = calculate_z_score(target_rec.bw_mibs, bw_values)
        target_bw_percentile = calculate_percentile(target_rec.bw_mibs, bw_values)
    
    target_iops_zscore = None
    target_iops_percentile = None
    if target_rec.iops is not None and iops_values:
        target_iops_zscore = calculate_z_score(target_rec.iops, iops_values)
        target_iops_percentile = calculate_percentile(target_rec.iops, iops_values)

    print("\n=== Results ===")
    for r in out:
        print(
            f"path={r.path}\t"
            f"jobid={r.jobid}\texe={r.exe}\tnprocs={r.nprocs}\t"
            f"total_bytes={r.total_bytes_sum}\t"
            f"Total_BW_MiB_s={r.bw_mibs}\tTotal_IOPS={r.iops}\t"
            f"POSIX_BW={r.posix_bw_mibs}\tPOSIX_IOPS={r.posix_iops}\t"
            f"STDIO_BW={r.stdio_bw_mibs}\tSTDIO_IOPS={r.stdio_iops}\t"
            f"MPIIO_BW={r.mpiio_bw_mibs}\tMPIIO_IOPS={r.mpiio_iops}"
        )

    print("\n=== Target Metrics Comparison ===")
    print(f"Target BW (MiB/s): {target_rec.bw_mibs}")
    if target_bw_zscore is not None:
        print(f"  Z-score: {target_bw_zscore:.4f}")
    if target_bw_percentile is not None:
        print(f"  Percentile: {target_bw_percentile:.2f}%")
    
    print(f"Target IOPS: {target_rec.iops}")
    if target_iops_zscore is not None:
        print(f"  Z-score: {target_iops_zscore:.4f}")
    if target_iops_percentile is not None:
        print(f"  Percentile: {target_iops_percentile:.2f}%")

if __name__ == "__main__":
    main()