import argparse
import os
import time


def compare_get_process_stats_performance(pid=None, iterations=10):
    """Compare performance between psutil and procfs implementations of get_process_stats.

    Args:
        pid: Process ID to analyze. Defaults to current process if None.
        iterations: Number of times to run each implementation for averaging

    Returns:
        Dictionary with average execution times for both implementations
    """
    if pid is None:
        pid = os.getpid()

    # Benchmark psutil implementation
    psutil_times = []
    for _ in range(iterations):
        start_time = time.time()
        get_process_stats_psutil(pid)
        psutil_times.append(time.time() - start_time)

    # Benchmark procfs implementation
    procfs_times = []
    for _ in range(iterations):
        start_time = time.time()
        get_process_stats_procfs(pid)
        procfs_times.append(time.time() - start_time)

    results = {
        "psutil_avg_time": sum(psutil_times) / iterations,
        "procfs_avg_time": sum(procfs_times) / iterations,
        "psutil_min_time": min(psutil_times),
        "procfs_min_time": min(procfs_times),
        "psutil_max_time": max(psutil_times),
        "procfs_max_time": max(procfs_times),
        "speedup_factor": (sum(psutil_times) / iterations)
        / (sum(procfs_times) / iterations),
    }

    print(
        f"PSUtil implementation: {results['psutil_avg_time']:.6f}s avg (min: {results['psutil_min_time']:.6f}s, max: {results['psutil_max_time']:.6f}s)"
    )
    print(
        f"ProcFS implementation: {results['procfs_avg_time']:.6f}s avg (min: {results['procfs_min_time']:.6f}s, max: {results['procfs_max_time']:.6f}s)"
    )
    print(
        f"Speedup factor: {results['speedup_factor']:.2f}x {'(procfs faster)' if results['speedup_factor'] > 1 else '(psutil faster)'}"
    )

    return results


# Run the comparison
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare performance of PID stats implementations"
    )
    parser.add_argument(
        "--pid", type=int, help="Process ID to analyze (defaults to current process)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations for benchmarking (default: 10)",
    )
    args = parser.parse_args()

    compare_get_process_stats_performance(pid=args.pid, iterations=args.iterations)
