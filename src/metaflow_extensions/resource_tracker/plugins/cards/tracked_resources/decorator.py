from collections import Counter
from os import listdir, path

from metaflow.cards import MetaflowCard
from metaflow.plugins.cards.card_modules import chevron

from .helpers import pretty_number, round_memory


class TrackedResourcesCard(MetaflowCard):
    """Card called by the track_resources step decorator, not for direct use."""

    ALLOW_USER_COMPONENTS = True
    RUNTIME_UPDATABLE = True
    type = "tracked_resources"

    def __init__(self, options={"artifact_name": "resource_tracker_data"}, **kwargs):
        self._artifact_name = options.get("artifact_name", "resource_tracker_data")

    def _read_component_files(self):
        root = path.join(path.dirname(__file__), "components")
        files = {}
        for key, fname in [
            ("base_html", ["base.html"]),
            ("dygraphs_js", ["dygraphs-2.2.1", "dygraphs.min.js"]),
            ("dygraphs_css", ["dygraphs-2.2.1", "dygraphs.min.css"]),
            ("dygraphs_crosshair_js", ["dygraphs-2.2.1", "crosshair.min.js"]),
            ("dygraphs_synchronizer_js", ["dygraphs-2.2.1", "synchronizer.min.js"]),
            ("helpers_js", ["helpers.js"]),
            ("custom_css", ["custom.css"]),
        ]:
            with open(path.join(root, *fname)) as f:
                files[key] = f.read()
        icon_path = path.join(path.dirname(__file__), "components", "icons")
        for icon in listdir(icon_path):
            with open(path.join(icon_path, icon), "r") as f:
                icon_name = path.splitext(icon)[0]
                files["icon_" + icon_name] = f.read()
        return files

    def render(self, task):
        data = getattr(task.data, self._artifact_name)
        pid = data["pid_tracker"]
        system = data["system_tracker"]

        # ensure both have the same length
        if len(pid) > len(system):
            pid = pid[: len(system)]
        elif len(system) > len(pid):
            system = system[: len(pid)]

        # nothing to report on
        if len(pid) == 0:
            return "The tracker did not collect any data. Please check if the step run for longer than the specified interval."

        joined = system[
            [
                "timestamp",
                "cpu_usage",
                "memory_active_anon",
                "disk_read_bytes",
                "disk_write_bytes",
                "net_recv_bytes",
                "net_sent_bytes",
                "gpu_usage",
                "gpu_vram",
                "gpu_utilized",
            ]
        ]
        joined.rename(
            columns={
                "cpu_usage": "Server CPU usage",
                "memory_active_anon": "Server memory usage",
                "disk_read_bytes": "Server disk read",
                "disk_write_bytes": "Server disk write",
                "net_recv_bytes": "Inbound network traffic",
                "net_sent_bytes": "Outbound network traffic",
                "gpu_usage": "Server GPU usage",
                "gpu_vram": "Server VRAM used",
                "gpu_utilized": "Server GPUs in use",
            }
        )
        # dummy merge
        joined["Task CPU usage"] = pid["cpu_usage"]
        joined["Task memory usage"] = pid["pss"]
        joined["Task disk read"] = pid["read_bytes"]
        joined["Task disk write"] = pid["write_bytes"]
        joined["Task GPU usage"] = pid["gpu_usage"]
        joined["Task GPUs in use"] = pid["gpu_utilized"]
        joined["Task VRAM used"] = pid["gpu_vram"]
        # convert memory usage to bytes so that we can pretty format on the client side
        for col in ["Task memory usage", "Server memory usage"]:  # KiB -> B
            joined[col] = [m * 1024 for m in joined[col]]
        for col in ["Task VRAM used", "Server VRAM used"]:  # MiB -> B
            joined[col] = [m * 1024 * 1024 for m in joined[col]]
        # convert to JS milliseconds
        joined["timestamp"] = [t * 1000 for t in joined["timestamp"]]

        variables = self._read_component_files()
        variables["csv_cpu"] = joined[
            ["timestamp", "Task CPU usage", "Server CPU usage"]
        ].to_csv(quote_strings=False)
        variables["csv_mem"] = joined[
            ["timestamp", "Task memory usage", "Server memory usage"]
        ].to_csv(quote_strings=False)
        variables["csv_disk"] = joined[
            [
                "timestamp",
                "Task disk read",
                "Server disk read",
                "Task disk write",
                "Server disk write",
            ]
        ].to_csv(quote_strings=False)
        variables["csv_net"] = joined[
            ["timestamp", "Inbound network traffic", "Outbound network traffic"]
        ].to_csv(quote_strings=False)
        variables["csv_gpu_usage"] = joined[
            ["timestamp", "Server GPU usage", "Task GPU usage"]
        ].to_csv(quote_strings=False)
        variables["csv_vram"] = joined[
            ["timestamp", "Server VRAM used", "Task VRAM used"]
        ].to_csv(quote_strings=False)
        variables["csv_gpu_utilized"] = joined[
            ["timestamp", "Server GPUs in use", "Task GPUs in use"]
        ].to_csv(quote_strings=False)

        variables["cloud_info"] = data["cloud_info"]
        variables["server_info"] = data["server_info"]
        if variables["server_info"]["gpu_names"]:
            variables["server_info"]["gpu_name"] = Counter(
                variables["server_info"]["gpu_names"]
            ).most_common(1)[0][0]
        else:
            variables["server_info"]["gpu_name"] = ""

        variables["stats"] = data["stats"]
        variables["historical_stats"] = data["historical_stats"]
        # strikethrough in HTML if no historical data
        if not variables["historical_stats"]["available"]:
            variables["historical_stats"]["avg_cpu_mean"] = "-"
            variables["historical_stats"]["max_memory_max_pretty"] = "-"
        # convert memory usage stats to MB and make it pretty
        for keys in [
            ["server_info", "memory_mb"],
            ["server_info", "gpu_memory_mb"],
            ["stats", "memory_usage", "mean"],
            ["stats", "memory_usage", "max"],
            ["historical_stats", "max_memory_max"],
        ]:
            if len(keys) == 3:
                if variables.get(keys[0], {}).get(keys[1], {}).get(keys[2], {}):
                    if not keys[2].endswith("_mb"):
                        variables[keys[0]][keys[1]][keys[2] + "_pretty"] = (
                            pretty_number(variables[keys[0]][keys[1]][keys[2]] / 1024)
                        )
                    else:
                        variables[keys[0]][keys[1]][keys[2] + "_pretty"] = (
                            pretty_number(variables[keys[0]][keys[1]][keys[2]])
                        )
            elif len(keys) == 2:
                if variables.get(keys[0], {}).get(keys[1], {}):
                    if not keys[1].endswith("_mb"):
                        variables[keys[0]][keys[1] + "_pretty"] = pretty_number(
                            variables[keys[0]][keys[1]] / 1024
                        )
                    else:
                        variables[keys[0]][keys[1] + "_pretty"] = pretty_number(
                            variables[keys[0]][keys[1]]
                        )
        # get recommended resources
        rec_cpu = round(variables["stats"]["cpu_usage"]["mean"])
        if variables["historical_stats"]["available"]:
            rec_mem = variables["historical_stats"]["max_memory_max"]
        else:
            rec_mem = variables["stats"]["memory_usage"]["max"]
        variables["recommended_resources"] = (
            f"@resources(cpu={rec_cpu}, memory={round_memory(rec_mem / 1024 * 1.2)})"
        )
        return chevron.render(variables["base_html"], variables)
