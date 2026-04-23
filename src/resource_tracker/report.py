"""Helper class to browser and save HTML reports."""

import tempfile
import webbrowser
from os import listdir, path
from typing import Union


def _read_report_template_files():
    root = path.join(path.dirname(__file__), "report_template")
    files = {}
    for key, fname in [
        ("dygraphs_js", ["dygraphs-2.2.1", "dygraphs.min.js"]),
        ("dygraphs_css", ["dygraphs-2.2.1", "dygraphs.min.css"]),
        ("dygraphs_crosshair_js", ["dygraphs-2.2.1", "crosshair.min.js"]),
        ("dygraphs_synchronizer_js", ["dygraphs-2.2.1", "synchronizer.min.js"]),
        ("helpers_js", ["helpers.js"]),
        ("custom_css", ["custom.css"]),
    ]:
        with open(path.join(root, *fname)) as f:
            files[key] = f.read()
    icon_path = path.join(root, "icons")
    for icon in listdir(icon_path):
        with open(path.join(icon_path, icon), "r") as f:
            icon_name = path.splitext(icon)[0]
            files["icon_" + icon_name] = f.read()
    return files


class Report(str):
    """A string subclass representing an HTML report with methods to view and save it."""

    def browse(self) -> "Report":
        """Open the report in the default web browser.

        Creates a temporary HTML file and opens it in the default web browser.

        Returns:
            self: Returns the Report object for method chaining
        """
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(self.encode("utf-8"))
            temp_path = f.name

        webbrowser.open("file://" + temp_path)
        return self

    def save(self, filepath: str) -> "Report":
        """Save the report to a file.

        Args:
            filepath: The path where to save the HTML report

        Returns:
            self: Returns the Report object for method chaining
        """
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self)
        return self


def round_memory(mib: Union[int, float]) -> int:
    """Round a number to the nearest meaningful memory amount.

    Args:
        mib: The value in MiB to round.

    Returns:
        The rounded value in MiB as an integer.

    Example:

        >>> round_memory(68)
        128
        >>> round_memory(896)
        1024
        >>> round_memory(3863)
        4096
    """
    if mib <= 128:
        rounded = 128
    elif mib <= 256:
        rounded = 256
    elif mib <= 512:
        rounded = 512
    elif mib <= 1024:
        rounded = 1024
    elif mib <= 2048:
        rounded = 2048
    else:
        # round up to the next GiB
        rounded_gib = mib / 1024
        rounded = int(1024 * (rounded_gib // 1 + (1 if rounded_gib % 1 > 0 else 0)))
    return rounded
