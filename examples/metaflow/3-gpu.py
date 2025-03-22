from time import sleep

from metaflow import Flow, FlowSpec, pypi, step, track_resources


def run_heavy_computation_gpu(n=1e8, iterations=1e2):
    """Copy array to GPU and do some math there."""
    import numpy as np
    from numba import cuda

    n = int(n)
    total = np.zeros(n, dtype=np.float32)
    total_device = cuda.to_device(total)

    @cuda.jit
    def heavy_computation_gpu_kernel(total, n, iterations):
        idx = cuda.grid(1)
        if idx < n:
            for _ in range(iterations):
                total[idx] += idx * idx

    threads_per_block = 256
    blocks_per_grid = (n + (threads_per_block - 1)) // threads_per_block

    heavy_computation_gpu_kernel[blocks_per_grid, threads_per_block](
        total_device, n, iterations
    )
    total_device.copy_to_host(total)

    return total.sum()


class GpuTrackingFlow(FlowSpec):
    @step
    def start(self):
        print("Starting")
        self.next(self.do_heavy_computation)

    @pypi(packages={"numba": "0.61.0", "numpy": "2.1.3"})
    @track_resources
    @step
    def do_heavy_computation(self):
        run_heavy_computation_gpu(n=1e7, iterations=1e2)
        sleep(2)
        run_heavy_computation_gpu(n=2e8, iterations=1e3)
        self.next(self.end)

    @step
    def end(self):
        pass


def get_tracker_artifact() -> str:
    return Flow("GpuTrackingFlow").latest_run.data.resource_tracker_data


if __name__ == "__main__":
    GpuTrackingFlow()
