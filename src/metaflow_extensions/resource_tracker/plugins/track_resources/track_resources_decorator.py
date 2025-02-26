from csv import DictReader
from multiprocessing import Process
from os import getpid, unlink
from tempfile import NamedTemporaryFile

from metaflow.decorators import StepDecorator

from .resource_tracker.tracker import PidTracker


def results_reader(file_name: str) -> list[dict]:
    results = []
    with open(file_name, "r") as f:
        reader = DictReader(f)
        for row in reader:
            results.append(row)
    return results


class ResourceTrackerDecorator(StepDecorator):
    """Track resources used in a step."""

    name = "track_resources"
    attrs = {
        "interval": {"type": float},
        "create_artifact": {"type": bool},
        "create_card": {"type": bool},
    }
    defaults = {"interval": 1.0, "create_artifact": False, "create_card": True}

    def __init__(
        self,
        interval: float = 1,
        create_artifact: bool = False,
        create_card: bool = True,
        **kwargs,
    ):
        self.interval = interval
        self.create_artifact = create_artifact
        self.create_card = create_card
        super().__init__(**kwargs)

    def step_init(self, flow, graph, step, decos, environment, datastore, logger):
        self.pid_tracker_data_file = NamedTemporaryFile(delete=False)
        self.logger = logger

    def task_pre_step(
        self,
        step_name,
        task_datastore,
        metadata,
        run_id,
        task_id,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
        ubf_context,
        inputs,
    ):
        self.pid_tracker_process = Process(
            target=PidTracker,
            kwargs={
                "pid": getpid(),
                "interval": self.interval,
                "output_file": self.pid_tracker_data_file.name,
            },
            daemon=True,
        )
        self.pid_tracker_process.start()

    def task_post_step(
        self,
        step_name,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
    ):
        try:
            pid_tracker_results = results_reader(self.pid_tracker_data_file.name)
            # if self.create_artifact:
            #     task_datastore.set_task_info("pid_tracker_log", pid_tracker_results)

            if self.create_card and pid_tracker_results:
                from metaflow import current
                from metaflow.cards import Table

                current.card["resource_tracker"].append(
                    Table(
                        [list(p.values()) for p in pid_tracker_results],
                        headers=list(pid_tracker_results[0].keys()),
                    ),
                )
        except Exception as e:
            self.logger(
                f"Failed to process resource tracking results: {e}",
                # TODO bad doesn't work here?
                bad=True,
                timestamp=False,
            )
        finally:
            unlink(self.pid_tracker_data_file.name)
