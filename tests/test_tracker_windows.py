"""Tests for Windows-safe background tracker startup."""

from unittest.mock import MagicMock, patch

import pytest

from resource_tracker import ResourceTracker


@pytest.fixture
def windows_tracker():
    with patch("resource_tracker.tracker.platform", "win32"):
        with patch("resource_tracker.tracker.is_psutil_available", return_value=True):
            yield ResourceTracker()


def test_windows_uses_subprocess_workers(windows_tracker):
    assert windows_tracker._use_subprocess_workers is True
    assert windows_tracker.mpc is None
    assert windows_tracker.error_queue is None


@patch("subprocess.Popen")
def test_windows_start_launches_worker_module(mock_popen, windows_tracker):
    mock_proc = MagicMock()
    mock_popen.return_value = mock_proc

    windows_tracker.start()

    worker_calls = [
        call
        for call in mock_popen.call_args_list
        if "resource_tracker._tracker_worker" in call.args[0]
    ]
    assert len(worker_calls) == 2
    for call in worker_calls:
        cmd = call.args[0]
        assert cmd[1:3] == ["-m", "resource_tracker._tracker_worker"]
        assert cmd[3] in {"process", "system"}
        assert "--error-file" in cmd
        assert "--output-file" in cmd

    windows_tracker.stop()
    mock_proc.terminate.assert_called()


def test_tracker_worker_module_runs_process_tracker(tmp_path):
    from resource_tracker._tracker_worker import main

    output_file = tmp_path / "process.csv"
    error_file = tmp_path / "error.json"

    with patch("resource_tracker.tracker._run_tracker") as mock_run_tracker:
        main(
            [
                "process",
                "--start-time",
                "0",
                "--interval",
                "1",
                "--output-file",
                str(output_file),
                "--error-file",
                str(error_file),
                "--pid",
                "1234",
            ]
        )

    mock_run_tracker.assert_called_once_with(
        "process",
        error_queue=None,
        error_file=str(error_file),
        start_time=0.0,
        interval=1.0,
        children=True,
        output_file=str(output_file),
        pid=1234,
    )
