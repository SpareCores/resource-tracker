from csv import DictReader
from functools import wraps
from multiprocessing import Process
from os import getpid, unlink
from tempfile import NamedTemporaryFile

from .tracker import PidTracker


def results_reader(file_name: str) -> list[dict]:
    results = []
    with open(file_name, "r") as f:
        reader = DictReader(f)
        for row in reader:
            results.append(row)
    return results


class track_resources:
    """Track resources used in a step."""

    def __init__(
        self,
        interval: float = 1,
        create_artifact: bool = False,
        create_card: bool = True,
    ):
        self.interval = interval
        self.pid_tracker_data_file = NamedTemporaryFile(delete=False)
        self.create_artifact = create_artifact
        self.create_card = create_card

    def __call__(self, step_fn):
        @wraps(step_fn)
        def step_wrapper(step_obj):
            pid_tracker_process = Process(
                target=PidTracker,
                kwargs={
                    # although this is the default, but better to be explicit with multiprocessing
                    "pid": getpid(),
                    "interval": self.interval,
                    "output_file": self.pid_tracker_data_file.name,
                },
                daemon=True,
            )
            pid_tracker_process.start()
            try:
                step_fn(step_obj)
            finally:
                pid_tracker_results = results_reader(self.pid_tracker_data_file.name)
                if self.create_artifact:
                    setattr(step_obj, "pid_tracker_log", pid_tracker_results)
                unlink(self.pid_tracker_data_file.name)

        return step_wrapper
