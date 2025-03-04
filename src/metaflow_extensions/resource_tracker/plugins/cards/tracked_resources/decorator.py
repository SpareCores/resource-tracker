from os import listdir, path

from metaflow.cards import MetaflowCard
from metaflow.plugins.cards.card_modules import chevron


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

        joined = system[
            [
                "timestamp",
                "cpu_usage",
                "disk_read_bytes",
                "disk_write_bytes",
                "net_recv_bytes",
                "net_sent_bytes",
            ]
        ]
        joined.rename(
            columns={
                "cpu_usage": "System CPU usage",
                "disk_read_bytes": "System disk read",
                "disk_write_bytes": "System disk write",
                "net_recv_bytes": "Inbound network traffic",
                "net_sent_bytes": "Outbound network traffic",
            }
        )
        # convert to JS milliseconds
        joined["timestamp"] = [t * 1000 for t in joined["timestamp"]]
        # dummy merge
        joined["Task CPU usage"] = pid["cpu_usage"]
        joined["Task disk read"] = pid["read_bytes"]
        joined["Task disk write"] = pid["write_bytes"]
        # convert memory usage to bytes so that we can pretty format on the client side
        joined["Task memory usage"] = [m * 1024 for m in pid["pss"]]
        joined["System memory usage"] = [m * 1024 for m in system["memory_active_anon"]]

        variables = self._read_component_files()
        variables["csv_cpu"] = joined[
            ["timestamp", "Task CPU usage", "System CPU usage"]
        ].to_csv(quote_strings=False)
        variables["csv_mem"] = joined[
            ["timestamp", "Task memory usage", "System memory usage"]
        ].to_csv(quote_strings=False)
        variables["csv_disk"] = joined[
            [
                "timestamp",
                "Task disk read",
                "System disk read",
                "Task disk write",
                "System disk write",
            ]
        ].to_csv(quote_strings=False)
        variables["csv_net"] = joined[
            ["timestamp", "Inbound network traffic", "Outbound network traffic"]
        ].to_csv(quote_strings=False)
        return chevron.render(variables["base_html"], variables)
