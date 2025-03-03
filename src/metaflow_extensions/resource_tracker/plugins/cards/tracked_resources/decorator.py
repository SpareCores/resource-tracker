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
            (
                "dygraphs_crosshair_js",
                ["dygraphs-2.2.1", "crosshair.min.js"],
            ),
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
        pid["timestamp"] = [t * 1000 for t in pid["timestamp"]]
        variables = self._read_component_files()
        variables["csv_cpu"] = pid[["timestamp", "cpu_usage"]].to_csv(
            quote_strings=False
        )
        variables["csv_mem"] = pid[["timestamp", "pss"]].to_csv(quote_strings=False)
        return chevron.render(variables["base_html"], variables)
