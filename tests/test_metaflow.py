import subprocess
from pathlib import Path
from platform import system

import pytest


@pytest.mark.skipif(
    system() == "Windows", reason="Metaflow is not supported on Windows"
)
def test_flow_execution():
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

    pid = tracker_data["pid_tracker"]
    assert max(pid["cpu_usage"]) > 0
    assert max(pid["memory"]) > 0

    system = tracker_data["system_tracker"]
    assert max(system["cpu_usage"]) > 0
    assert max(system["memory_used"]) > 0

    assert tracker_data["stats"]["duration"] > 0

    # check card
    step = list(run)[1]
    cards = get_cards(step.task)
    assert len(cards) == 1
    card = cards[0]
    assert card.type == "tracked_resources"
    html = card.get()
    assert "Task CPU usage" in html
    assert "System CPU usage" in html
    assert len(html) > 100_000
