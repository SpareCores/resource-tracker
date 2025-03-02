from os import path

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
        ]:
            with open(path.join(root, *fname)) as f:
                files[key] = f.read()
        return files

    def render(self, task):
        data = getattr(task.data, self._artifact_name)
        variables = self._read_component_files()
        variables["csv"] = data["pid_tracker"].to_csv()
        return chevron.render(variables["base_html"], variables)
