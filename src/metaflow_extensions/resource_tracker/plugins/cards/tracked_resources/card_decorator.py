from metaflow.cards import MetaflowCard

from resource_tracker.tracker import ResourceTracker


class TrackedResourcesCard(MetaflowCard):
    """Card called by the track_resources step decorator, not for direct use."""

    ALLOW_USER_COMPONENTS = False
    RUNTIME_UPDATABLE = False
    type = "tracked_resources"

    def __init__(self, options={"artifact_name": "resource_tracker_data"}, **kwargs):
        super().__init__(**kwargs)
        self._artifact_name = options.get("artifact_name", "resource_tracker_data")

    def render(self, task):
        data = getattr(task.data, self._artifact_name)

        # check if there was any error
        if data.get("error", None):
            error_html = "<p>The resource tracker encountered the following error, so thus no data was collected.</p>"
            if isinstance(data["error"], dict) and "traceback" in data["error"]:
                error_html += "<hr>"
                error_html += (
                    "<p><b>Error Type:</b> "
                    + data["error"].get("error_type", "")
                    + "</p>"
                )
                error_html += (
                    "<p><b>Error Message:</b> "
                    + data["error"].get("error_message", "")
                    + "</p>"
                )
                error_html += (
                    "<p><b>Traceback:</b></p>"
                    "<pre style='white-space: pre-wrap; overflow-x: auto; background: #f8f8f8; padding: 10px; border-radius: 4px;'>"
                    + data["error"].get("traceback", "")
                    + "</pre>"
                )
            else:
                error_html += (
                    "<p><b>This is all we know:</b></p><pre>" + data["error"] + "</pre>"
                )
            return error_html

        tracker = ResourceTracker.from_snapshot(data["tracker"])
        return tracker.report(historical_stats=data["historical_stats"])
