import os
import re
import math
import argparse
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple
import statistics

# -----------------------------
# Patterns for header fields
# -----------------------------
RE_JOBID = re.compile(r"^#\s*jobid:\s*(\d+)\s*$")
RE_EXE = re.compile(r"^#\s*exe:\s*(\S+)\s*$")
RE_NPROCS = re.compile(r"^#\s*nprocs:\s*(\d+)\s*$")
RE_AGG_PERF = re.compile(r"^#\s*agg_perf_by_slowest:\s*([0-9]*\.?[0-9]+)")

# -----------------------------
# Counters we need from data rows
# -----------------------------
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
class JobMetrics:
    path: str
    jobid: Optional[int]
    exe: Optional[str]
    nprocs: Optional[int]

    # environment-ish fields inferred from data lines
    fs_type: Optional[str]          # e.g., "lustre"
    mount_pt: Optional[str]         # e.g., "/home"

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

    # derived (aggregate across all modules)
    total_bytes: int
    total_ops: int
    total_io_time: float
    derived_iops: Optional[float]  # Total IOPS
    bw_mibs: Optional[float]  # Total bandwidth in MiB/s

def quantile(values: List[float], q: float) -> Optional[float]:
    """Simple quantile with linear interpolation; values must be non-empty."""
    xs = sorted(v for v in values if v is not None and not math.isnan(v))
    if not xs:
        return None
    if q <= 0:
        return xs[0]
    if q >= 1:
        return xs[-1]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w

def safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None

def safe_int(s: str) -> Optional[int]:
    try:
        # some darshan outputs may have floats for counters; only int when expected
        return int(float(s))
    except Exception:
        return None

def iter_all_files(root_dir: str) -> List[str]:
    out = []
    for root, _, files in os.walk(root_dir):
        for fn in files:
            if fn.startswith("."):
                continue
            # 你可以在这里更严格地筛选，比如只要 .txt
            out.append(os.path.join(root, fn))
    return out

def parse_darshan_txt(path: str) -> Optional[JobMetrics]:
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

    # infer fs/mount from data rows (take the most frequent non-empty)
    fs_counts: Dict[str, int] = {}
    mnt_counts: Dict[str, int] = {}

    def bump(d: Dict[str, int], key: str):
        if not key:
            return
        d[key] = d.get(key, 0) + 1

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue

                # header lines
                if line.startswith("#"):
                    m = RE_JOBID.match(line)
                    if m:
                        jobid = int(m.group(1))
                        continue
                    m = RE_EXE.match(line)
                    if m:
                        exe = m.group(1)
                        continue
                    m = RE_NPROCS.match(line)
                    if m:
                        nprocs = int(m.group(1))
                        continue
                    continue

                # data lines: MODULE\tRANK\tRECORD_ID\tCOUNTER_NAME\tCOUNTER_VALUE\t...
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                
                module = parts[0]
                counter = parts[3]
                value_s = parts[4]
                
                # Parse POSIX module
                if module == "POSIX":
                    # infer mount/fs: commonly the last two columns are mount_pt and fs_type
                    # Format: MODULE\tRANK\tRECORD_ID\tCOUNTER\tVALUE\tFILE_NAME\tMOUNT_PT\tFS_TYPE
                    if len(parts) >= 8:
                        fs = parts[-1].strip()  # last column is fs_type
                        mnt = parts[-2].strip()  # second to last is mount_pt
                        # heuristic: fs_type tends to be small tokens like lustre/gpfs/nfs
                        # mount tends to start with "/"
                        if fs and not fs.startswith("/") and fs not in ["", "-1"]:
                            bump(fs_counts, fs)
                        if mnt and mnt.startswith("/"):
                            bump(mnt_counts, mnt)
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
                    # infer mount/fs for STDIO module too
                    if len(parts) >= 8:
                        fs = parts[-1].strip()
                        mnt = parts[-2].strip()
                        if fs and not fs.startswith("/") and fs not in ["", "-1"]:
                            bump(fs_counts, fs)
                        if mnt and mnt.startswith("/"):
                            bump(mnt_counts, mnt)
                    
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
                    # infer mount/fs for MPIIO module too
                    if len(parts) >= 8:
                        fs = parts[-1].strip()
                        mnt = parts[-2].strip()
                        if fs and not fs.startswith("/") and fs not in ["", "-1"]:
                            bump(fs_counts, fs)
                        if mnt and mnt.startswith("/"):
                            bump(mnt_counts, mnt)
                    
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

    except Exception:
        return None

    # must have at least exe to be useful
    if exe is None:
        return None

    fs_type = max(fs_counts.items(), key=lambda kv: kv[1])[0] if fs_counts else None
    mount_pt = max(mnt_counts.items(), key=lambda kv: kv[1])[0] if mnt_counts else None

    # Calculate totals
    posix_total_bytes = posix_bytes_read + posix_bytes_written
    stdio_total_bytes = stdio_bytes_read + stdio_bytes_written
    mpiio_total_bytes = mpiio_bytes_read + mpiio_bytes_written
    total_bytes = posix_total_bytes + stdio_total_bytes + mpiio_total_bytes
    
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
    if total_io_time > 0 and total_bytes > 0:
        bw_mibs = (total_bytes / total_io_time) / (1024 * 1024)
    
    # Calculate aggregate IOPS: IOPS = (sum READS + sum WRITES) / Total_T
    total_reads = posix_reads + stdio_reads + mpiio_reads
    total_writes = posix_writes + stdio_writes + mpiio_writes
    total_ops = total_reads + total_writes
    
    derived_iops = None
    if total_io_time > 0 and total_ops > 0:
        derived_iops = total_ops / total_io_time

    return JobMetrics(
        path=path,
        jobid=jobid,
        exe=exe,
        nprocs=nprocs,
        fs_type=fs_type,
        mount_pt=mount_pt,
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
        total_bytes=total_bytes,
        total_ops=total_ops,
        total_io_time=total_io_time,
        derived_iops=derived_iops,
        bw_mibs=bw_mibs,
    )

def within_tol(x: int, ref: int, tol: float) -> bool:
    if ref <= 0:
        return False
    return (ref * (1 - tol)) <= x <= (ref * (1 + tol))

def log_dist_bytes(a: int, b: int) -> float:
    """Calculate log distance between two byte values."""
    a = max(a, 1)
    b = max(b, 1)
    return abs(math.log(a) - math.log(b))

def build_cohort(
    all_jobs: List[JobMetrics],
    target: JobMetrics,
    filter_by: str,  # "fs" or "bytes"
    nprocs_tol: float = 0.10,
    limit: Optional[int] = None,
) -> List[JobMetrics]:
    """
    Filter jobs by partition (fs_type) OR I/O load (total_bytes).
    filter_by: "fs" to filter by fs_type, "bytes" to filter by I/O scale
    """
    cohort = []
    for j in all_jobs:
        if j.path == target.path:
            continue
        
        # Filter by fs_type or total_bytes
        if filter_by == "fs":
            if target.fs_type is None or j.fs_type is None:
                continue
            if j.fs_type != target.fs_type:
                continue
        elif filter_by == "bytes":
            # Sort by log distance to target's total_bytes
            # We'll sort after collecting candidates
            pass
        else:
            raise ValueError(f"filter_by must be 'fs' or 'bytes', got '{filter_by}'")
        
        # Optional: filter by nprocs
        if target.nprocs is not None and j.nprocs is not None:
            if not within_tol(j.nprocs, target.nprocs, nprocs_tol):
                continue
        
        # must have metrics
        if j.bw_mibs is None or j.derived_iops is None:
            continue
        
        cohort.append(j)
    
    # If filtering by bytes, sort by log distance
    if filter_by == "bytes":
        cohort.sort(key=lambda r: log_dist_bytes(r.total_bytes, target.total_bytes))
    
    # Apply limit if specified
    if limit is not None and limit > 0:
        cohort = cohort[:limit]
    
    return cohort

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

def compare_to_cohort(target: JobMetrics, cohort: List[JobMetrics]) -> Dict:
    bw_vals = [j.bw_mibs for j in cohort if j.bw_mibs is not None]
    iops_vals = [j.derived_iops for j in cohort if j.derived_iops is not None]

    bw_p10 = quantile(bw_vals, 0.10)
    bw_med = quantile(bw_vals, 0.50)
    iops_p10 = quantile(iops_vals, 0.10)
    iops_med = quantile(iops_vals, 0.50)

    bw_flag = (bw_p10 is not None and target.bw_mibs is not None and target.bw_mibs < bw_p10)
    iops_flag = (iops_p10 is not None and target.derived_iops is not None and target.derived_iops < iops_p10)
    
    # Calculate z-score and percentile
    target_bw_zscore = None
    target_bw_percentile = None
    if target.bw_mibs is not None and bw_vals:
        target_bw_zscore = calculate_z_score(target.bw_mibs, bw_vals)
        target_bw_percentile = calculate_percentile(target.bw_mibs, bw_vals)
    
    target_iops_zscore = None
    target_iops_percentile = None
    if target.derived_iops is not None and iops_vals:
        target_iops_zscore = calculate_z_score(target.derived_iops, iops_vals)
        target_iops_percentile = calculate_percentile(target.derived_iops, iops_vals)

    return {
        "cohort_size": len(cohort),
        "target_bw_mibs": target.bw_mibs,
        "bw_p10": bw_p10,
        "bw_median": bw_med,
        "bw_is_below_p10": bw_flag,
        "target_bw_zscore": target_bw_zscore,
        "target_bw_percentile": target_bw_percentile,
        "target_iops": target.derived_iops,
        "iops_p10": iops_p10,
        "iops_median": iops_med,
        "iops_is_below_p10": iops_flag,
        "target_iops_zscore": target_iops_zscore,
        "target_iops_percentile": target_iops_percentile,
    }

def main():
    # ap = argparse.ArgumentParser()
    # ap.add_argument("--root", required=True, help="Parent directory containing many darshan txt logs (recursive).")
    # ap.add_argument("--target", required=True, help="Target log file path OR a jobid (integer).")
    # ap.add_argument("--nprocs_tol", type=float, default=0.10, help="± tolerance for nprocs in cohort.")
    # ap.add_argument("--require_same_fs", action="store_true", help="Require same fs_type for cohort.")
    # ap.add_argument("--ext", default=None, help="Optional: only parse files with this extension (e.g., .txt).")
    # args = ap.parse_args()
    
    ap = argparse.ArgumentParser(
        description="Parse a darshan txt file and find similar jobs by partition or I/O load, calculate BW/IOPS metrics and z-score/percentile"
    )
    ap.add_argument("--target", required=True, help="target darshan txt file to parse")
    ap.add_argument(
        "--filter_by", required=True, choices=["fs", "bytes"],
        help="filter by partition (fs) or I/O load (bytes)"
    )
    ap.add_argument(
        "--dir", default=None,
        help="optional: parent directory to search for similar jobs (default: parent directory of target file)"
    )
    ap.add_argument("--nprocs_tol", type=float, default=0.10, help="tolerance for nprocs filter (default: 0.10)")
    ap.add_argument("--limit", type=int, default=None, help="optional: limit number of results (default: all)")
    args = ap.parse_args()

    # Determine search directory
    search_dir = args.dir if args.dir else os.path.dirname(os.path.abspath(args.target))

    files = iter_all_files(search_dir)

    jobs: List[JobMetrics] = []
    for p in files:
        jm = parse_darshan_txt(p)
        if jm is not None:
            jobs.append(jm)

    if not jobs:
        raise SystemExit("No parsable darshan txt logs found.")

    # locate target
    target: Optional[JobMetrics] = None
    if os.path.exists(args.target):
        target = parse_darshan_txt(args.target)
        if target is None:
            raise SystemExit("Target file exists but could not be parsed as darshan txt.")
    else:
        raise SystemExit(f"Target file does not exist: {args.target}")

    # Print target summary
    print("=== Target ===")
    print(f"Target file: {args.target}")
    print(f"  path: {target.path}")
    print(f"  jobid: {target.jobid}")
    print(f"  exe: {target.exe}")
    print(f"  nprocs: {target.nprocs}")
    print(f"  fs_type: {target.fs_type}  mount_pt: {target.mount_pt}")
    print(f"  total_bytes: {target.total_bytes}")
    print(f"  Total BW (MiB/s): {target.bw_mibs}")
    print(f"  Total IOPS: {target.derived_iops}")
    print(f"  POSIX - BW (MiB/s): {target.posix_bw_mibs}, IOPS: {target.posix_iops}")
    print(f"  STDIO - BW (MiB/s): {target.stdio_bw_mibs}, IOPS: {target.stdio_iops}")
    print(f"  MPIIO - BW (MiB/s): {target.mpiio_bw_mibs}, IOPS: {target.mpiio_iops}")
    print()

    cohort = build_cohort(
        all_jobs=jobs,
        target=target,
        filter_by=args.filter_by,
        nprocs_tol=args.nprocs_tol,
        limit=args.limit,
    )
    report = compare_to_cohort(target, cohort)

    print(f"Filter by: {args.filter_by}")
    print(f"Parsed jobs: {len(jobs)}")
    print(f"Candidates after filter: {len(cohort)}")
    if args.limit is not None:
        print(f"Limit applied: {args.limit}")
    print()

    # Print all matching jobs
    print("=== Results ===")
    for j in cohort:
        print(
            f"path={j.path}\t"
            f"jobid={j.jobid}\texe={j.exe}\tnprocs={j.nprocs}\t"
            f"fs_type={j.fs_type}\ttotal_bytes={j.total_bytes}\t"
            f"Total_BW_MiB_s={j.bw_mibs}\tTotal_IOPS={j.derived_iops}\t"
            f"POSIX_BW={j.posix_bw_mibs}\tPOSIX_IOPS={j.posix_iops}\t"
            f"STDIO_BW={j.stdio_bw_mibs}\tSTDIO_IOPS={j.stdio_iops}\t"
            f"MPIIO_BW={j.mpiio_bw_mibs}\tMPIIO_IOPS={j.mpiio_iops}"
        )

    # Print target metrics comparison with z-score and percentile
    print("\n=== Target Metrics Comparison ===")
    print(f"Target BW (MiB/s): {report['target_bw_mibs']}")
    if report['target_bw_zscore'] is not None:
        print(f"  Z-score: {report['target_bw_zscore']:.4f}")
    if report['target_bw_percentile'] is not None:
        print(f"  Percentile: {report['target_bw_percentile']:.2f}%")
    
    print(f"Target IOPS: {report['target_iops']}")
    if report['target_iops_zscore'] is not None:
        print(f"  Z-score: {report['target_iops_zscore']:.4f}")
    if report['target_iops_percentile'] is not None:
        print(f"  Percentile: {report['target_iops_percentile']:.2f}%")

if __name__ == "__main__":
    main()