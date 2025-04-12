from time import sleep

from metaflow import FlowSpec, step, track_resources


class MinimalFailedFlow(FlowSpec):
    @step
    def start(self):
        print("Starting")
        self.next(self.do_heavy_computation)

    @track_resources
    @step
    def do_heavy_computation(self):
        # reserve 500 MB memory
        big_array = bytearray(500 * 1024 * 1024)
        # do some calcs
        total = 0
        for i in range(int(1e7)):
            total += i**3
        # do nothing for bit after releasing memory
        del big_array
        sleep(1)
        raise Exception("This is a test error")
        self.next(self.end)

    @step
    def end(self):
        pass


if __name__ == "__main__":
    MinimalFailedFlow()
