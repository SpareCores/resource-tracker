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

    def __init__(self, attributes=None, statically_defined=False):
        self._attributes_with_user_values = (
            set(attributes.keys()) if attributes is not None else set()
        )
        super().__init__(attributes, statically_defined)

    def step_init(
        self, flow, graph, step_name, decorators, environment, flow_datastore, logger
    ):
        self.pid_tracker_data_file = NamedTemporaryFile(delete=False)
        self.logger = logger
        if self.attributes["create_card"]:
            self.card_name = "resource_tracker_" + step_name
            resource_tracker_card_exists = any(
                getattr(decorator, "name", None) == "card"
                and getattr(decorator, "attributes", None).get("id") == self.card_name
                for decorator in decorators
            )
            if not resource_tracker_card_exists:
                from metaflow.plugins.cards.card_decorator import CardDecorator

                decorators.append(
                    CardDecorator(attributes={"type": "blank", "id": self.card_name})
                )

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
                "interval": self.attributes["interval"],
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
            # TODO fix
            if self.attributes["create_artifact"]:
            #     task_datastore.set_task_info("pid_tracker_log", pid_tracker_results)

            if self.attributes["create_card"] and pid_tracker_results:
                from metaflow import current
                from metaflow.cards import Table

                current.card[self.card_name].append(
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
