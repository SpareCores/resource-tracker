from multiprocessing import Process
from os import getpid, unlink
from statistics import mean
from tempfile import NamedTemporaryFile
from threading import Thread
from time import time

from metaflow.decorators import StepDecorator

from .resource_tracker import (
    PidTracker,
    SystemTracker,
    TinyDataFrame,
    get_cloud_info,
    get_server_info,
)


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

        self.cloud_info = None
        self.cloud_info_thread = Thread(
            target=lambda: setattr(self, "cloud_info", get_cloud_info()),
            daemon=True,
        )
        self.cloud_info_thread.start()

        self.server_info = get_server_info()

        self.start_time = time()

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
            # wait for the cloud_info thread to complete
            if self.cloud_info_thread.is_alive():
                self.cloud_info_thread.join()

            pid_tracker_data = TinyDataFrame(
                csv_file_path=self.pid_tracker_data_file.name
            )
            system_tracker_data = TinyDataFrame(
                csv_file_path=self.system_tracker_data_file.name
            )
            data = {
                "pid_tracker": pid_tracker_data,
                "system_tracker": system_tracker_data,
                "cloud_info": self.cloud_info,
                "server_info": self.server_info,
                "stats": {
                    "cpu_usage": {
                        "mean": round(mean(pid_tracker_data["cpu_usage"]), 2),
                        "max": round(max(pid_tracker_data["cpu_usage"]), 2),
                    },
                    "memory_usage": {
                        "mean": round(mean(pid_tracker_data["pss"]), 2),
                        "max": round(max(pid_tracker_data["pss"]), 2),
                    },
                    "duration": round(time() - self.start_time, 2),
                },
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
