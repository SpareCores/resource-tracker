from statistics import mean
from threading import Thread
from time import time

from metaflow.decorators import StepDecorator

from .resource_tracker._version import __version__
from .resource_tracker.cloud_info import get_cloud_info
from .resource_tracker.helpers import is_psutil_available
from .resource_tracker.server_info import get_server_info


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
        # error details from main process and threads
        self.error_details = None
        # override default attributes.
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
        try:
            from .resource_tracker import ResourceTracker

            self.resource_tracker = ResourceTracker()

            self.cloud_info = None
            self.cloud_info_thread = Thread(
                target=self._get_cloud_info_with_error_handling,
                daemon=True,
            )
            self.cloud_info_thread.start()

            self.server_info = get_server_info()
            self.start_time = time()

        except Exception as e:
            import traceback

            self.error_details = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }
            self.logger(
                f"*WARNING* [@resource_tracker] Failed to start resource tracker processes: {type(e).__name__} / {e}",
                timestamp=False,
            )

    def _get_cloud_info_with_error_handling(self):
        """Get cloud info and capture any exceptions."""
        try:
            self.cloud_info = get_cloud_info()
        except Exception as e:
            import traceback

            self.error_details = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }

    def task_post_step(
        self,
        step_name,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
    ):
        """Store collected data as an artifact for card/user to process."""
        self._store_resource_tracking_data(flow, step_name)

    def task_exception(
        self,
        exception,
        step_name,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
    ):
        """Store resource tracking data even when an exception occurs so that the card can be rendered."""
        self._store_resource_tracking_data(flow, step_name, failed=True)

    def task_finished(
        self,
        step_name,
        flow,
        graph,
        is_task_ok,
        retry_count,
        max_user_code_retries,
    ):
        """Render card for failed step."""
        if not is_task_ok and self.attributes["create_card"]:
            try:
                # find our card decorator
                for decorator in graph[step_name].decorators:
                    if (
                        getattr(decorator, "name", None) == "card"
                        and getattr(decorator, "attributes", {}).get("id")
                        == self.card_name
                    ):
                        # CardDecorator.task_finished but without
                        # checking if task was OK and skipping the refresh
                        create_options = dict(
                            card_uuid=decorator._card_uuid,
                            user_set_card_id=decorator._user_set_card_id,
                            runtime_card=decorator._is_runtime_card,
                            decorator_attributes=decorator.attributes,
                            card_options=decorator.card_options,
                            logger=self.logger,
                        )
                        decorator.card_creator.create(
                            mode="render", final=True, **create_options
                        )
                        break
            except Exception as e:
                import traceback

                self.logger(
                    f"*WARNING* [@resource_tracker] Failed to render card for failed step: {type(e).__name__} / {e}\n{traceback.format_exc()}",
                    timestamp=False,
                )

    def _store_resource_tracking_data(self, flow, step_name, failed=False):
        """Store collected resource tracking data as an artifact.

        This method is used by both task_post_step and task_exception to ensure
        resource data is captured regardless of how the step completes.

        Args:
            flow: The flow object to store data on
            step_name: The name of the current step
            failed: Whether the step failed
        """
        # check for previous errors in the subprocesses
        if not self.resource_tracker.error_queue.empty():
            subprocess_error = self.resource_tracker.error_queue.get()
            self.error_details = {
                "error_message": subprocess_error["message"],
                "error_type": subprocess_error["name"],
                "traceback": subprocess_error["traceback"],
            }
            self.logger(
                f"*WARNING* [@resource_tracker] Subprocess failed: {self.error_details['error_type']} / {self.error_details['error_message']}",
                timestamp=False,
            )
        # terminate tracker processes
        self.resource_tracker.stop()
        # early return if there was an error either in the main process, threads, or in the subprocesses
        if self.error_details is not None:
            setattr(
                flow, self.attributes["artifact_name"], {"error": self.error_details}
            )
            return

        try:
            # wait for the cloud_info thread to complete
            if self.cloud_info_thread.is_alive():
                self.cloud_info_thread.join()

            # nothing to report on
            pid_tracker_data = self.resource_tracker.pid_tracker
            if len(pid_tracker_data) == 0:
                if self.attributes["interval"] * 2 > (time() - self.start_time):
                    setattr(
                        flow,
                        self.attributes["artifact_name"],
                        {
                            "error": {
                                "error_type": "ValueError",
                                "error_message": f"The step ran for too short time ({round(time() - self.start_time, 2)} seconds) to collect any data with the specified interval ({self.attributes['interval']} seconds).",
                                "traceback": "-",
                            }
                        },
                    )
                else:
                    setattr(
                        flow,
                        self.attributes["artifact_name"],
                        {
                            "error": {
                                "error_type": "ValueError",
                                "error_message": "Somehow, the tracker did not collect any data. Please report this issue at https://github.com/SpareCores/resource-tracker/issues",
                            }
                        },
                    )
                return

            system_tracker_data = self.resource_tracker.system_tracker
            historical_stats = self._get_historical_stats(flow, step_name)

            data = {
                "step_failed": failed,
                "resource_tracker": {
                    "version": __version__,
                    "implementation": "psutil" if is_psutil_available() else "procfs",
                },
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
                        "mean": round(mean(pid_tracker_data["memory"]), 2),
                        "max": round(max(pid_tracker_data["memory"]), 2),
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
            import traceback

            error_details = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }
            setattr(flow, self.attributes["artifact_name"], {"error": error_details})
            self.logger(
                f"*WARNING* [@resource_tracker] Failed to process resource tracking results: {type(e).__name__} / {e}. See the artifact or card for more details, including the traceback.",
                timestamp=False,
            )

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
                    # cannot use hasattr on the artifact object, so force try/catch to see if we have an artifact
                    try:
                        resource_data = getattr(
                            task.data, self.attributes["artifact_name"]
                        )
                    except Exception:
                        self.logger(
                            f"*NOTE* [@resource_tracker] No historical data found for run {run.id}",
                            timestamp=False,
                        )
                        continue
                    # successful run, but tracker failed
                    if resource_data.get("error"):
                        self.logger(
                            f"*NOTE* [@resource_tracker] Failed historical data found for run {run.id}",
                            timestamp=False,
                        )
                        continue
                    cpu_means.append(resource_data["stats"]["cpu_usage"]["mean"])
                    memory_maxes.append(resource_data["stats"]["memory_usage"]["max"])
                    durations.append(resource_data["stats"]["duration"])
                    gpu_means.append(resource_data["stats"]["gpu_usage"]["mean"])
                    vram_maxes.append(resource_data["stats"]["gpu_vram"]["max"])
                    gpu_counts.append(resource_data["stats"]["gpu_utilized"]["max"])
                except Exception as e:
                    import traceback

                    self.logger(
                        f"*WARNING* [@resource_tracker] Could not process historical data for run {run.id}: {type(e).__name__} / {e} / {traceback.format_exc()}",
                        timestamp=False,
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
            self.logger(
                f"*WARNING* [@resource_tracker] Failed to retrieve historical stats: {e}",
                timestamp=False,
            )
            return {"available": False, "error": str(e)}
