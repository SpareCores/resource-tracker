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
        """Override default attributes."""
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
            historical_stats = self._get_historical_stats(flow, step_name)

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
                    "gpu_usage": {
                        "mean": round(mean(pid_tracker_data["gpu_usage"]), 2),
                        "max": round(max(pid_tracker_data["gpu_usage"]), 2),
                    },
                    "gpu_vram": {
                        "mean": round(mean(pid_tracker_data["gpu_vram"]), 2),
                        "max": round(max(pid_tracker_data["gpu_vram"]), 2),
                    },
                    "gpu_utilized": {
                        "mean": round(mean(pid_tracker_data["gpu_utilized"]), 2),
                        "max": round(max(pid_tracker_data["gpu_utilized"]), 2),
                    },
                    "disk_usage": {
                        "max": round(max(system_tracker_data["disk_space_used_gb"]), 2),
                    },
                    "traffic": {
                        "inbound": sum(system_tracker_data["net_recv_bytes"]),
                        "outbound": sum(system_tracker_data["net_sent_bytes"]),
                    },
                    "duration": round(time() - self.start_time, 2),
                },
                "historical_stats": historical_stats,
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

    def _get_historical_stats(self, flow, step_name):
        """Fetch historical resource stats from previous runs' artifacts."""
        try:
            from metaflow import Flow

            # Get the flow name from the current flow object
            flow_name = flow.__class__.__name__

            # get the current + last 5 successful runs
            runs = list(Flow(flow_name).runs())
            runs.sort(key=lambda run: run.created_at, reverse=True)
            previous_runs = [run for run in runs[0:6] if run.successful]

            if not previous_runs:
                return {
                    "available": False,
                    "message": "No previous successful runs found",
                }

            cpu_means = []
            memory_maxes = []
            durations = []
            gpu_means = []
            vram_maxes = []
            gpu_counts = []

            for run in previous_runs:
                try:
                    step = next((s for s in run.steps() if s.id == step_name), None)
                    if not step:
                        continue
                    # usually there's only one task per step
                    task = next(iter(step.tasks()), None)
                    if not task:
                        continue
                    if not hasattr(task.data, self.attributes["artifact_name"]):
                        continue
                    resource_data = getattr(task.data, self.attributes["artifact_name"])
                    cpu_means.append(resource_data["stats"]["cpu_usage"]["mean"])
                    memory_maxes.append(resource_data["stats"]["memory_usage"]["max"])
                    durations.append(resource_data["stats"]["duration"])
                    gpu_means.append(resource_data["stats"]["gpu_usage"]["mean"])
                    vram_maxes.append(resource_data["stats"]["gpu_vram"]["max"])
                    gpu_counts.append(resource_data["stats"]["gpu_utilized"]["max"])
                except Exception as e:
                    self.logger(
                        f"Warning: Could not process historical data for run {run.id}: {e}"
                    )
                    continue

            if cpu_means and memory_maxes and durations:
                return {
                    "available": True,
                    "runs_analyzed": len(cpu_means),
                    "avg_cpu_mean": round(mean(cpu_means), 2),
                    "max_memory_max": round(max(memory_maxes), 2),
                    "avg_gpu_mean": round(mean(gpu_means), 2),
                    "max_vram_max": round(max(vram_maxes), 2),
                    "max_gpu_count": round(max(gpu_counts), 2),
                    "avg_duration": round(mean(durations), 2),
                }
            else:
                return {
                    "available": False,
                    "message": "No resource data found in previous runs",
                }

        except Exception as e:
            self.logger(f"Warning: Failed to retrieve historical stats: {e}")
            return {"available": False, "error": str(e)}
