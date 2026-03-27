"""Integration tests for ResourceTracker + StreamingManager (Step 3)."""

from __future__ import annotations

import gzip
from unittest.mock import patch

import pytest

from resource_tracker.dummy_workloads import cpu_single

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_RUN_ID = "run-integration-001"
FAKE_URI_PREFIX = "s3://bucket/runs/integration-001"

FAKE_REGISTER_RESPONSE = {
    "run_id": FAKE_RUN_ID,
    "upload_uri_prefix": FAKE_URI_PREFIX,
    "upload_credentials": {
        "access_key": "AKIA...",
        "secret_key": "secret...",
        "session_token": "token...",
        "expires_at": "2099-12-31T23:59:59Z",
        "region": "us-east-1",
    },
}


def _wait_for_tracker(tracker, timeout=5):
    """Spin-wait until at least one sample has been collected."""
    for _ in range(timeout * 10):
        if tracker.n_samples > 0:
            return
        cpu_single(duration=0.1)
    pytest.fail(f"No data collected after {timeout} seconds")


# ---------------------------------------------------------------------------
# Streaming disabled (default behaviour — no token)
# ---------------------------------------------------------------------------


def test_no_streaming_when_token_is_absent(monkeypatch):
    """Without a token, streaming should be fully disabled."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker()
    _wait_for_tracker(tracker)
    tracker.stop()

    assert tracker._streaming is None
    assert tracker.sentinel_result is None
    assert len(tracker.process_metrics) > 0


# ---------------------------------------------------------------------------
# Streaming enabled — start() registers a run
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_start_registers_run_with_sentinel(mock_register, monkeypatch):
    """When a token is provided, start() should register the run."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(
        sentinel_token="test-token",
        upload_interval=9999,
        streaming_metadata={"project_name": "test-project"},
    )
    _wait_for_tracker(tracker)

    mock_register.assert_called_once()
    reg_kwargs = mock_register.call_args
    assert reg_kwargs[0][0] == "test-token"
    assert reg_kwargs[1]["metadata"] == {"project_name": "test-project"}
    assert tracker._streaming is not None
    assert tracker._streaming.run_id == FAKE_RUN_ID

    # Cleanup without calling finish_run (mock it)
    with patch("resource_tracker.streaming.finish_run", return_value={}):
        tracker.stop()


# ---------------------------------------------------------------------------
# Streaming enabled — stop() calls finish_run
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_calls_finish_run(mock_register, mock_finish, monkeypatch):
    """stop() should call finish_run and store the result."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {"stats": {"cpu_mean": 0.5}}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(
        sentinel_token="test-token",
        upload_interval=9999,
    )
    _wait_for_tracker(tracker)
    tracker.stop(exit_code=0, run_status="finished")

    mock_finish.assert_called_once()
    finish_kwargs = mock_finish.call_args[1]
    assert finish_kwargs["exit_code"] == 0
    assert finish_kwargs["run_status"] == "finished"

    assert tracker.sentinel_result == {"stats": {"cpu_mean": 0.5}}
    assert tracker._streaming is None  # cleared after stop


# ---------------------------------------------------------------------------
# stop() forwards exit_code and run_status
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_forwards_failure_status(mock_register, mock_finish, monkeypatch):
    """stop() should forward exit_code and run_status to finish_run."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)
    tracker.stop(exit_code=1, run_status="failed")

    finish_kwargs = mock_finish.call_args[1]
    assert finish_kwargs["exit_code"] == 1
    assert finish_kwargs["run_status"] == "failed"


# ---------------------------------------------------------------------------
# Short run — inline CSV fallback
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_short_run_sends_inline_csv(mock_register, mock_finish, monkeypatch):
    """A short run with no upload cycles should send inline CSV."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)
    tracker.stop()

    finish_kwargs = mock_finish.call_args[1]
    assert finish_kwargs["data_source"] == "inline"
    # data_csv is gzipped bytes — decompress and verify structure
    csv_text = gzip.decompress(finish_kwargs["data_csv"]).decode()
    assert "timestamp" in csv_text
    assert "system_" in csv_text
    assert "process_" in csv_text
    # Should have at least a header + one data row
    lines = [line for line in csv_text.strip().split("\n") if line]
    assert len(lines) >= 2


# ---------------------------------------------------------------------------
# _update_combined_csv writes the expected data
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_update_combined_csv_appends_rows(mock_register, monkeypatch):
    """_update_combined_csv should incrementally append rows to the temp file."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)

    # Manually trigger a combined CSV update
    tracker._update_combined_csv()
    n_first = tracker._combined_csv_rows_written
    assert n_first > 0

    # Read the file and verify structure
    with open(tracker._combined_csv_filepath, "r") as f:
        content = f.read()
    lines = [line for line in content.strip().split("\n") if line]
    assert len(lines) == n_first + 1  # header + data rows
    assert "timestamp" in lines[0]
    assert "system_" in lines[0]
    assert "process_" in lines[0]

    # Wait for more samples and update again — should only append
    cpu_single(duration=1.5)
    tracker._update_combined_csv()
    n_second = tracker._combined_csv_rows_written
    assert n_second > n_first

    with open(tracker._combined_csv_filepath, "r") as f:
        content2 = f.read()
    lines2 = [line for line in content2.strip().split("\n") if line]
    assert len(lines2) == n_second + 1  # header + all data rows
    # First lines should be identical (append-only)
    for i in range(len(lines)):
        assert lines2[i] == lines[i]

    with patch("resource_tracker.streaming.finish_run", return_value={}):
        tracker.stop()


# ---------------------------------------------------------------------------
# Token from environment variable
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_token_from_env_variable(mock_register, monkeypatch):
    """sentinel_token=None should fall back to SENTINEL_API_TOKEN env var."""
    monkeypatch.setenv("SENTINEL_API_TOKEN", "env-token")
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(upload_interval=9999)
    _wait_for_tracker(tracker)

    mock_register.assert_called_once()
    assert mock_register.call_args[0][0] == "env-token"
    assert tracker._streaming is not None

    with patch("resource_tracker.streaming.finish_run", return_value={}):
        tracker.stop()


# ---------------------------------------------------------------------------
# Streaming start failure — graceful degradation
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_streaming_start_failure_degrades_gracefully(mock_register, monkeypatch):
    """If register_run fails, streaming is disabled but tracker keeps working."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.side_effect = RuntimeError("API unreachable")

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)

    assert tracker._streaming is None  # streaming disabled after failure
    assert len(tracker.process_metrics) > 0  # tracker still works

    tracker.stop()  # should not raise
    assert tracker.sentinel_result is None


# ---------------------------------------------------------------------------
# stop() with streaming failure — graceful degradation
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_streaming_stop_failure_degrades_gracefully(
    mock_register, mock_finish, monkeypatch
):
    """If finish_run fails during stop(), the tracker should still stop cleanly."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.side_effect = RuntimeError("API error")

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)
    tracker.stop()  # should not raise despite finish_run failure

    assert tracker._streaming is None  # cleared after stop
    assert tracker.sentinel_result is None  # no result due to failure


# ---------------------------------------------------------------------------
# Backward compatibility — stop() with no args
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_no_args_backward_compatible(mock_register, mock_finish, monkeypatch):
    """stop() with no args should work exactly as before (defaults)."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)
    tracker.stop()  # no args — uses defaults

    finish_kwargs = mock_finish.call_args[1]
    assert finish_kwargs["exit_code"] == 0
    assert finish_kwargs["run_status"].value == "finished"


# ---------------------------------------------------------------------------
# Upload batch with csv_update_fn callback
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_upload_batch_uses_csv_update_fn(
    mock_register, mock_finish, mock_put, monkeypatch
):
    """The upload batch should call csv_update_fn before reading the file."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_put.side_effect = lambda **kw: kw["s3_uri"]
    mock_finish.return_value = {}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)

    # Manually trigger an upload cycle
    tracker._streaming._upload_batch()

    # The combined CSV should have been written (via the callback)
    assert tracker._combined_csv_rows_written > 0

    # An upload should have happened
    assert mock_put.call_count == 1
    put_kwargs = mock_put.call_args[1]
    assert put_kwargs["s3_uri"].endswith("0001.csv.gz")

    # Decompress and verify the uploaded data
    decompressed = gzip.decompress(put_kwargs["body"])
    assert b"timestamp" in decompressed
    assert b"system_" in decompressed
    assert b"process_" in decompressed

    tracker.stop()


# ---------------------------------------------------------------------------
# With S3 uploads — stop sends data_uris
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_with_uploads_sends_data_uris(
    mock_register, mock_finish, mock_put, monkeypatch
):
    """When uploads have happened, stop() should send data_uris instead of inline CSV."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_put.side_effect = lambda **kw: kw["s3_uri"]
    mock_finish.return_value = {}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)

    # Manually trigger an upload to get at least one S3 URI
    tracker._streaming._upload_batch()
    assert len(tracker._streaming.uploaded_uris) >= 1

    tracker.stop()

    finish_kwargs = mock_finish.call_args[1]
    assert finish_kwargs["data_source"] == "s3"
    assert len(finish_kwargs["data_uris"]) >= 1


# ---------------------------------------------------------------------------
# sentinel_result property
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_sentinel_result_property(mock_register, mock_finish, monkeypatch):
    """sentinel_result should be None before stop and populated after."""
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {"stats": {"cpu_mean": 1.2}}

    from resource_tracker import ResourceTracker

    tracker = ResourceTracker(sentinel_token="test-token", upload_interval=9999)
    _wait_for_tracker(tracker)

    assert tracker.sentinel_result is None  # not set yet

    tracker.stop()

    assert tracker.sentinel_result == {"stats": {"cpu_mean": 1.2}}
