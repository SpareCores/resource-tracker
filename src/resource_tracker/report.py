from os import listdir, path
from typing import Union


def _read_report_template_files():
    root = path.join(path.dirname(__file__), "report_template")
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
    icon_path = path.join(root, "icons")
    for icon in listdir(icon_path):
        with open(path.join(icon_path, icon), "r") as f:
            icon_name = path.splitext(icon)[0]
            files["icon_" + icon_name] = f.read()
    return files


def round_memory(mb: Union[int, float]) -> int:
    """Round a number to the nearest meaningful memory amount.

    Args:
        mb: The value in MB to round.

    Returns:
        The rounded value in MB as an integer.

    Example:
        >>> round_memory(68)
        128
        >>> round_memory(896)
        1024
        >>> round_memory(3863)
        4096
    """
    if mb <= 128:
        rounded = 128
    elif mb <= 256:
        rounded = 256
    elif mb <= 512:
        rounded = 512
    elif mb <= 1024:
        rounded = 1024
    elif mb <= 2048:
        rounded = 2048
    else:
        # round up to the next GB
        rounded_gb = mb / 1024
        rounded = int(1024 * (rounded_gb // 1 + (1 if rounded_gb % 1 > 0 else 0)))
    return rounded
