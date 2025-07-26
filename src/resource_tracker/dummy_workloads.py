from multiprocessing import Pool, cpu_count
from time import time


def cpu_single(n: int = 10_000_000) -> float:
    """Finds the largest cube of the first n integers.

    Args:
        n: The number of integers to cube.

    Returns:
        Time it took to run the workload.
    """
    start = time()
    max(i**3 for i in range(n))
    return time() - start


def cpu_multi(n: int = 10_000_000, ncores: int = cpu_count()) -> float:
    """Finds the largest cube of the first n integers, run on ncores cores in parallel, all cores doing the same.

    Args:
        n: The number of integers to cube.
        ncores: The number of cores to use. Defaults to all available logical cores.

    Returns:
        Time it took to run the workload.
    """
    start = time()
    with Pool(ncores) as p:
        p.map(cpu_single, [n] * ncores)
    return time() - start
