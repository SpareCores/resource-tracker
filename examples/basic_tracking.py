from multiprocessing import Pool
from time import sleep

from metaflow import FlowSpec, step

from metaflow_resource_tracker import track_resources


def heavy_computation(n=1e8):
    """Dummy heavy task."""
    total = 0
    for i in range(int(n)):
        total += i * i
    return total


class ResourceTrackingFlow(FlowSpec):
    @step
    def start(self):
        print("Starting")
        self.next(self.do_heavy_computation)

    @track_resources()
    @step
    def do_heavy_computation(self):
        heavy_computation()
        sleep(3)
        with Pool(6) as p:
            p.map(heavy_computation, [1e7] * 6)
        self.next(self.end)

    @step
    def end(self):
        pass


if __name__ == "__main__":
    ResourceTrackingFlow()
