from multiprocessing import Pool, cpu_count
from random import random
from time import time


def cpu_single(duration: float = 1) -> None:
    """Multiplies random numbers for a given duration.

    Args:
        duration: The duration in seconds to run the workload.
    """
    start = time()
    while time() - start < duration:
        random() * random()


def cpu_multi(duration: float = 1, ncores: int = cpu_count()) -> float:
    """Multiplies random numbers for a given duration using ncores cores in parallel.

    Args:
        duration: The duration in seconds to run the workload.
        ncores: The number of cores to use. Defaults to all available logical cores.
    """
    with Pool(ncores) as p:
        p.map(cpu_single, [duration] * ncores)
