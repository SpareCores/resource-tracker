from functools import wraps
from multiprocessing import Process
from os import getpid, unlink
from tempfile import NamedTemporaryFile

from .tracker import PidTracker


class track_resources:
    """Track resources used in a step."""

    def __init__(self, interval=1):
        self.interval = interval
        self.pid_tracker_data_file = NamedTemporaryFile(delete=False)

    def __call__(self, step_fn):
        @wraps(step_fn)
        def step_wrapper(step_obj):
            print(f"Tracking resources in {getpid()}")
            pid_tracker_process = Process(
                target=PidTracker,
                kwargs={"output_file": self.pid_tracker_data_file.name},
                daemon=True,
            )
            pid_tracker_process.start()
            step_result = step_fn(step_obj)
            print(f"Resources tracked in {getpid()}")
            with open(self.pid_tracker_data_file.name, "r") as f:
                print(f.read())
            unlink(self.pid_tracker_data_file.name)
            return step_result

        return step_wrapper
