import subprocess
from pathlib import Path
from platform import system

import pytest

from resource_tracker.tracker import ResourceTracker


@pytest.mark.skipif(
    system() == "Windows", reason="Metaflow is not supported on Windows"
)
def test_flow_execution(artifacts_dir):
    """Test running a Metaflow flow and checking its artifacts."""
    from metaflow import Flow
    from metaflow.cards import get_cards

    # Run the flow with test tag
    result = subprocess.run(
        [
            "python",
            str(
                Path(__file__).parent.parent / "examples" / "metaflow" / "1-minimal.py"
            ),
            "run",
            "--tag=test",
        ],
    )

    assert result.returncode == 0

    run = Flow("MinimalFlow").latest_successful_run

    # check resource tracker data
    assert hasattr(run.data, "resource_tracker_data")
    tracker_data = run.data.resource_tracker_data

    tracker = ResourceTracker.from_snapshot(tracker_data["tracker"])
    process_metrics = tracker.process_metrics
    assert max(process_metrics["cpu_usage"]) > 0
    assert max(process_metrics["memory"]) > 0

    system_metrics = tracker.system_metrics
    assert max(system_metrics["cpu_usage"]) > 0
    assert max(system_metrics["memory_used"]) > 0

    assert tracker.snapshot()["metadata"]["duration"] > 0

    # check card
    step = list(run)[1]
    cards = get_cards(step.task)
    assert len(cards) == 1
    card = cards[0]
    assert card.type == "tracked_resources"
    html = card.get()
    assert "Process CPU usage" in html
    assert "System CPU usage" in html
    assert len(html) > 100_000

    # store html for inspection
    html_path = artifacts_dir / "metaflow_resource_card.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)


@pytest.mark.skipif(
    system() == "Windows", reason="Metaflow is not supported on Windows"
)
def test_flow_execution_failed(artifacts_dir):
    """Test running a failing Metaflow flow and checking its artifacts.

    Note that this is a total hack as cannot get the artifacts and cards
    via the standard Metaflow client, but the CLI can find those on disk.
    """
    import json
    import os
    import pickle
    import tempfile

    from metaflow import Flow

    # Run the flow with test tag
    result = subprocess.run(
        [
            "python",
            str(
                Path(__file__).parent.parent
                / "examples"
                / "metaflow"
                / "1-minimal-failed.py"
            ),
            "run",
            "--tag=test",
        ],
    )
    assert result.returncode == 1

    run = Flow("MinimalFailedFlow").latest_run

    # cannot get the artifacts via the API as datasatore doesn't keep track of that for failed runs
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = temp_file.name
    subprocess.run(
        [
            "python",
            str(
                Path(__file__).parent.parent
                / "examples"
                / "metaflow"
                / "1-minimal-failed.py"
            ),
            "dump",
            f"{run.id}/do_heavy_computation",
            "--max-value-size",
            "9999999",
            "--include",
            "resource_tracker_data",
            "--file",
            temp_path,
        ],
        capture_output=True,
        text=True,
    )
    with open(temp_path, "rb") as f:
        tracker_data = pickle.load(f)
        tracker_data = tracker_data[list(tracker_data)[0]]["resource_tracker_data"]
    os.unlink(temp_path)

    tracker = ResourceTracker.from_snapshot(tracker_data["tracker"])
    process_metrics = tracker.process_metrics
    assert max(process_metrics["cpu_usage"]) > 0
    assert max(process_metrics["memory"]) > 0

    system_metrics = tracker.system_metrics
    assert max(system_metrics["cpu_usage"]) > 0
    assert max(system_metrics["memory_used"]) > 0

    assert tracker.snapshot()["metadata"]["duration"] > 0

    # cannot get card via the Metaflow client, so use the CLI and locate on disk
    card_list_result = subprocess.run(
        [
            "python",
            str(
                Path(__file__).parent.parent
                / "examples"
                / "metaflow"
                / "1-minimal-failed.py"
            ),
            "card",
            "list",
            "--as-json",
        ],
        capture_output=True,
        text=True,
    )
    card_info = json.loads(card_list_result.stdout)
    assert len(card_info) > 0

    card_entry = None
    for entry in card_info:
        if f"{run.id}/do_heavy_computation" in entry["pathspec"]:
            card_entry = entry
            break
    assert card_entry is not None
    assert len(card_entry["cards"]) > 0

    card_data = card_entry["cards"][0]
    assert card_data["type"] == "tracked_resources"

    card_filename = card_data["filename"]
    pathspec_parts = card_entry["pathspec"].split("/")
    flow_name = pathspec_parts[0]
    run_id = pathspec_parts[1]
    step_name = pathspec_parts[2]
    task_id = pathspec_parts[3] if len(pathspec_parts) > 3 else "0"
    card_path = (
        Path(".metaflow/mf.cards")
        / flow_name
        / "runs"
        / run_id
        / "steps"
        / step_name
        / "tasks"
        / task_id
        / "cards"
        / card_filename
    )
    assert card_path.exists(), f"Card file not found at {card_path}"

    with open(card_path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "Process CPU usage" in html
    assert "System CPU usage" in html
    assert "Failed" in html
    assert len(html) > 100_000

    # store html for inspection
    html_path = artifacts_dir / "metaflow_resource_card.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
