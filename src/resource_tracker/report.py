from os import listdir, path


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
