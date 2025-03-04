from multiprocessing import Process
from os import getpid, unlink
from tempfile import NamedTemporaryFile

from metaflow.decorators import StepDecorator

from .resource_tracker import PidTracker, SystemTracker, TinyDataFrame


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
        "artifact_name": {"type": str},
        "create_card": {"type": bool},
    }
    defaults = {
        "interval": 1.0,
        "artifact_name": "resource_tracker_data",
        "create_card": True,
    }

    def __init__(self, attributes=None, statically_defined=False):
        """Support overriding default attributes."""
        self._attributes_with_user_values = (
            set(attributes.keys()) if attributes is not None else set()
        )
        super().__init__(attributes, statically_defined)

    def step_init(
        self, flow, graph, step_name, decorators, environment, flow_datastore, logger
    ):
        """Optionally initialize the card as a later decorator."""
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
                    CardDecorator(
                        attributes={
                            "type": "tracked_resources",
                            "id": self.card_name,
                            "options": {
                                "artifact_name": self.attributes["artifact_name"]
                            },
                        }
                    )
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
        """Start resource tracker processes."""
        self.pid_tracker_data_file = NamedTemporaryFile(delete=False)
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

        self.system_tracker_data_file = NamedTemporaryFile(delete=False)
        self.system_tracker_process = Process(
            target=SystemTracker,
            kwargs={
                "interval": self.attributes["interval"],
                "output_file": self.system_tracker_data_file.name,
            },
            daemon=True,
        )
        self.system_tracker_process.start()

    def task_post_step(
        self,
        step_name,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
    ):
        """Store collected data as an artifact for card/user to process."""
        try:
            data = {
                "pid_tracker": TinyDataFrame(
                    csv_file_path=self.pid_tracker_data_file.name
                ),
                "system_tracker": TinyDataFrame(
                    csv_file_path=self.system_tracker_data_file.name
                ),
            }
            setattr(flow, self.attributes["artifact_name"], data)
        except Exception as e:
            self.logger(
                f"*ERROR* Failed to process resource tracking results: {e}",
                bad=True,  # NOTE this settings doesn't do anything here? works outside of the decorator, though
                timestamp=False,
            )
        finally:
            unlink(self.pid_tracker_data_file.name)
