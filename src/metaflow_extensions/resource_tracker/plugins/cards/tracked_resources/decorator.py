from collections import Counter
from math import ceil
from os import listdir, path
from statistics import mean

from metaflow.cards import MetaflowCard
from metaflow.plugins.cards.card_modules import chevron

from .helpers import (
    get_instance_price,
    get_recommended_cloud_servers,
    pretty_number,
    round_memory,
)

SERVER_ALLOCATION_CHECKS = [
    {"column": "CPU usage", "percent": 1.25, "absolute": 0.25},
    {"column": "memory usage", "percent": 1.5, "absolute": 512 * 1024 * 1024},
    {"column": "GPU usage", "percent": 1.25, "absolute": 0.2},
    {"column": "VRAM used", "percent": 1.25, "absolute": 512 * 1024 * 1024},
]


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
                "memory_inactive_anon",
                "disk_read_bytes",
                "disk_write_bytes",
                "disk_space_used_gb",
                "net_recv_bytes",
                "net_sent_bytes",
                "gpu_usage",
                "gpu_vram",
                "gpu_utilized",
            ]
        ]
        joined["memory_usage"] = [
            memory_active_anon + memory_inactive_anon
            for memory_active_anon, memory_inactive_anon in zip(
                joined["memory_active_anon"], joined["memory_inactive_anon"]
            )
        ]
        joined.rename(
            columns={
                "cpu_usage": "Server CPU usage",
                "memory_usage": "Server memory usage",
                "disk_read_bytes": "Server disk read",
                "disk_write_bytes": "Server disk write",
                "disk_space_used_gb": "Server disk space used",
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
        for col in ["Server disk space used"]:  # GiB -> B
            joined[col] = [m * 1024 * 1024 * 1024 for m in joined[col]]
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
        variables["csv_disk_space"] = joined[
            ["timestamp", "Server disk space used"]
        ].to_csv(quote_strings=False)
        variables["csv_net"] = joined[
            ["timestamp", "Inbound network traffic", "Outbound network traffic"]
        ].to_csv(quote_strings=False)
        variables["csv_gpu_usage"] = joined[
            ["timestamp", "Task GPU usage", "Server GPU usage"]
        ].to_csv(quote_strings=False)
        variables["csv_vram"] = joined[
            ["timestamp", "Task VRAM used", "Server VRAM used"]
        ].to_csv(quote_strings=False)
        variables["csv_gpu_utilized"] = joined[
            ["timestamp", "Task GPUs in use", "Server GPUs in use"]
        ].to_csv(quote_strings=False)

        variables["cloud_info"] = data["cloud_info"]
        if variables["cloud_info"]["instance_type"] == "unknown":
            variables["cloud_info"]["instance_type_html"] = "unknown"
        else:
            variables["cloud_info"]["instance_type_url"] = (
                f"https://sparecores.com/server/{data['cloud_info']['vendor']}/{data['cloud_info']['instance_type']}"
            )
            variables["cloud_info"]["instance_type_html"] = (
                f"<a href='{data['cloud_info']['instance_type_url']}' target='_blank' style='color: #34D399;'>{data['cloud_info']['instance_type']} {variables['icon_external_link']}</a>"
            )
            compute_costs = get_instance_price(
                data["cloud_info"]["vendor"],
                data["cloud_info"]["region"],
                data["cloud_info"]["instance_type"],
            )
            if compute_costs:
                variables["cloud_info"]["compute_costs"] = round(
                    compute_costs / 60 / 60 * data["stats"]["duration"], 6
                )

        variables["server_info"] = data["server_info"]
        if variables["server_info"]["gpu_names"]:
            variables["server_info"]["gpu_name"] = Counter(
                variables["server_info"]["gpu_names"]
            ).most_common(1)[0][0]
        else:
            variables["server_info"]["gpu_name"] = ""
        variables["server_info"]["disk_space_total_gb"] = pretty_number(
            system["disk_space_total_gb"][0], 0
        )
        variables["server_info"]["allocation"] = "Dedicated"
        for check in SERVER_ALLOCATION_CHECKS:
            system_val = mean(joined["Server " + check["column"]])
            task_val = mean(joined["Task " + check["column"]])
            if (system_val > task_val * check["percent"]) or (
                system_val > task_val + check["absolute"]
            ):
                variables["server_info"]["allocation"] = "Shared"
                break

        variables["stats"] = data["stats"]
        variables["historical_stats"] = data["historical_stats"]
        # strikethrough in HTML if no historical data
        if not variables["historical_stats"]["available"]:
            variables["historical_stats"]["avg_cpu_mean"] = "-"
            variables["historical_stats"]["max_memory_max_pretty"] = "-"
            variables["historical_stats"]["max_vram_max_pretty"] = "-"
        # convert memory usage stats to MB and make it pretty
        for keys in [
            ["server_info", "memory_mb"],
            ["server_info", "gpu_memory_mb"],
            ["stats", "memory_usage", "mean"],
            ["stats", "memory_usage", "max"],
            ["stats", "gpu_vram", "mean"],
            ["stats", "gpu_vram", "max"],
            ["stats", "disk_usage", "max"],
            ["historical_stats", "max_memory_max"],
            ["historical_stats", "max_vram_max"],
        ]:
            if len(keys) == 3:
                if (
                    variables.get(keys[0], {}).get(keys[1], {}).get(keys[2], None)
                    is not None
                ):
                    # some are already in MB (e.g. VRAM)
                    if (
                        not keys[2].endswith("_mb")
                        and "vram" not in keys[1]
                        and "disk_usage" != keys[1]
                    ):
                        variables[keys[0]][keys[1]][keys[2] + "_pretty"] = (
                            pretty_number(
                                variables[keys[0]][keys[1]][keys[2]] / 1024, 0
                            )
                        )
                    else:
                        variables[keys[0]][keys[1]][keys[2] + "_pretty"] = (
                            pretty_number(variables[keys[0]][keys[1]][keys[2]], 0)
                        )
            elif len(keys) == 2:
                if variables.get(keys[0], {}).get(keys[1], None) is not None:
                    if not keys[1].endswith("_mb") and "vram" not in keys[1]:
                        variables[keys[0]][keys[1] + "_pretty"] = pretty_number(
                            variables[keys[0]][keys[1]] / 1024, 0
                        )
                    else:
                        variables[keys[0]][keys[1] + "_pretty"] = pretty_number(
                            variables[keys[0]][keys[1]], 0
                        )
        for key in ["inbound", "outbound"]:
            variables["stats"]["traffic"][key + "_pretty"] = pretty_number(
                variables["stats"]["traffic"][key] / 1000**3, digits=3
            )

        # get recommended resources
        rec = {
            "cpu": ceil(variables["stats"]["cpu_usage"]["mean"]),
            "memory": round_memory(variables["stats"]["memory_usage"]["max"]),
        }
        if variables["historical_stats"]["available"] and (
            variables["historical_stats"]["max_memory_max"]
            > variables["stats"]["memory_usage"]["max"]
        ):
            rec["memory"] = round_memory(
                variables["historical_stats"]["max_memory_max"]
            )
        if variables["stats"]["gpu_usage"]["mean"] > 0:
            rec["gpu"] = ceil(variables["stats"]["gpu_usage"]["max"])
        rec["memory"] = round_memory(rec["memory"] / 1024 * 1.2)
        rec_str = ", ".join(f"{key}={value}" for key, value in rec.items())
        variables["recommended_resources"] = f"@resources({rec_str})"
        # get recommended cloud servers
        if variables["stats"]["gpu_vram"]["max"] > 0:
            rec["vram"] = ceil(variables["stats"]["gpu_vram"]["max"] / 1024)
        variables["recommended_cloud_servers"] = get_recommended_cloud_servers(
            **rec, n=1
        )
        for server in variables["recommended_cloud_servers"]:
            server["price_task"] = pretty_number(
                server.get("min_price_ondemand", 0)
                / 60
                / 60
                * data["stats"]["duration"],
                6,
            )
        cost_current = variables["cloud_info"].get("compute_costs")
        cost_rec = variables["recommended_cloud_servers"][0].get("price_task")
        if cost_current and cost_rec:
            cost_current = float(cost_current)
            cost_rec = float(cost_rec)
            if cost_rec < cost_current:
                variables["cost_savings"] = {
                    "percent": round((cost_current - cost_rec) / cost_current * 100, 2),
                    "amount": round(cost_current - cost_rec, 6),
                }

        return chevron.render(variables["base_html"], variables)
