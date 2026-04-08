"""Tests for the streaming manager (streaming.py)."""

from __future__ import annotations

import time as time_module
from unittest.mock import patch

import pytest

from resource_tracker.sentinel_api import DataSource, RunStatus
from resource_tracker.streaming import (
    StreamingManager,
    _parse_expires_at,
    _read_new_bytes,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_TOKEN = "test-token-streaming"
FAKE_RUN_ID = "run-stream-001"
FAKE_URI_PREFIX = "s3://bucket/runs/stream-001"

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

FAKE_REFRESH_RESPONSE = {
    "upload_credentials": {
        "access_key": "AKIA-NEW...",
        "secret_key": "secret-new...",
        "session_token": "token-new...",
        "expires_at": "2099-12-31T23:59:59Z",
        "region": "us-east-1",
    },
}

COMBINED_CSV_HEADER = '"timestamp","system_cpu_usage","system_memory_used","process_cpu_usage","process_memory"\n'
COMBINED_CSV_ROW1 = "1774468571.001,0.57,6108688.0,0.0294,9840.0\n"
COMBINED_CSV_ROW2 = "1774468572.001,1.5301,5868064.0,0.8516,8576.0\n"
COMBINED_CSV_ROW3 = "1774468573.001,2.6301,5859120.0,1.1353,8464.0\n"


# ---------------------------------------------------------------------------
# _parse_expires_at
# ---------------------------------------------------------------------------


def test_parse_expires_at_z_suffix():
    ts = _parse_expires_at("2026-03-26T12:00:00Z")
    assert isinstance(ts, float)
    assert ts > 0


def test_parse_expires_at_offset_suffix():
    ts = _parse_expires_at("2026-03-26T12:00:00+00:00")
    assert isinstance(ts, float)
    assert ts > 0


def test_parse_expires_at_z_and_offset_equal():
    ts_z = _parse_expires_at("2026-03-26T12:00:00Z")
    ts_off = _parse_expires_at("2026-03-26T12:00:00+00:00")
    assert ts_z == ts_off


# ---------------------------------------------------------------------------
# _read_new_bytes
# ---------------------------------------------------------------------------


def test_read_new_bytes_full_file(tmp_path):
    f = tmp_path / "test.csv"
    f.write_bytes(b"header\nrow1\nrow2\n")

    data, offset = _read_new_bytes(str(f), 0)
    assert data == b"header\nrow1\nrow2\n"
    assert offset == len(data)


def test_read_new_bytes_incremental(tmp_path):
    f = tmp_path / "test.csv"
    f.write_bytes(b"header\nrow1\n")

    data1, offset1 = _read_new_bytes(str(f), 0)
    assert data1 == b"header\nrow1\n"

    # Append more data
    with open(str(f), "ab") as fh:
        fh.write(b"row2\nrow3\n")

    data2, offset2 = _read_new_bytes(str(f), offset1)
    assert data2 == b"row2\nrow3\n"
    assert offset2 == offset1 + len(data2)


def test_read_new_bytes_no_new_data(tmp_path):
    f = tmp_path / "test.csv"
    f.write_bytes(b"header\n")

    _, offset = _read_new_bytes(str(f), 0)
    data, new_offset = _read_new_bytes(str(f), offset)
    assert data == b""
    assert new_offset == offset


def test_read_new_bytes_missing_file():
    data, offset = _read_new_bytes("/nonexistent/path.csv", 0)
    assert data == b""
    assert offset == 0


# ---------------------------------------------------------------------------
# StreamingManager.start
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_start_calls_register_run(mock_register):
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        metadata={"project_name": "test"},
        host_info={"host_vcpus": 4},
        cloud_info={"cloud_vendor_id": "aws"},
    )
    mgr.start()

    mock_register.assert_called_once_with(
        FAKE_TOKEN,
        metadata={"project_name": "test"},
        host_info={"host_vcpus": 4},
        cloud_info={"cloud_vendor_id": "aws"},
    )
    assert mgr.run_id == FAKE_RUN_ID
    assert mgr.is_alive

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.register_run")
def test_start_raises_when_run_id_missing(mock_register):
    mock_register.return_value = {
        "upload_uri_prefix": FAKE_URI_PREFIX,
        "upload_credentials": {
            "access_key": "AKIA",
            "secret_key": "secret",
            "session_token": "token",
            "expires_at": "2099-12-31T23:59:59Z",
            "region": "us-east-1",
        },
    }

    mgr = StreamingManager(token=FAKE_TOKEN)
    with pytest.raises(KeyError, match="run_id"):
        mgr.start()


# ---------------------------------------------------------------------------
# StreamingManager.stop — short run (inline CSV)
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_short_run_sends_inline_csv(mock_register, mock_finish, tmp_path):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {"stats": {}}

    csv_file = tmp_path / "combined.csv"
    csv_file.write_text(COMBINED_CSV_HEADER + COMBINED_CSV_ROW1 + COMBINED_CSV_ROW2)

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,  # won't trigger during test
    )
    mgr.start()
    result = mgr.stop(exit_code=0, run_status=RunStatus.finished)

    mock_finish.assert_called_once()
    finish_kwargs = mock_finish.call_args
    assert finish_kwargs[1]["data_source"] == DataSource.inline
    csv_text = finish_kwargs[1]["data_csv"]
    assert "timestamp" in csv_text
    assert "system_cpu_usage" in csv_text
    assert "process_cpu_usage" in csv_text
    assert finish_kwargs[1]["exit_code"] == 0
    assert finish_kwargs[1]["run_status"] == RunStatus.finished
    assert result == {"stats": {}}


# ---------------------------------------------------------------------------
# StreamingManager.stop — final upload failure is swallowed
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_final_upload_failure_is_handled(mock_register, mock_finish):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {"stats": {}}

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()

    # Simulate having a prior successful upload so that stop() tries a final flush
    mgr._uploaded_uris.append("s3://bucket/0001.csv.gz")

    # Make the final _upload_batch raise so the warning branch (lines 190-191) is hit
    with patch.object(mgr, "_upload_batch", side_effect=RuntimeError("network down")):
        result = mgr.stop(exit_code=0, run_status=RunStatus.finished)

    # finish_run must still be called with s3 data_source (uploaded_uris is non-empty)
    mock_finish.assert_called_once()
    assert mock_finish.call_args[1]["data_source"] == DataSource.s3
    assert result == {"stats": {}}


# ---------------------------------------------------------------------------
# StreamingManager.stop — data-preparation failure falls back to empty CSV
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_data_prep_failure_sends_empty_csv(mock_register, mock_finish):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {}

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()

    # uploaded_uris is empty → stop() falls to _read_all_csv() path
    # Make _read_all_csv raise to trigger the fallback (lines 206-208)
    with patch.object(mgr, "_read_all_csv", side_effect=IOError("disk failure")):
        mgr.stop(exit_code=1, run_status=RunStatus.finished)

    mock_finish.assert_called_once()
    assert mock_finish.call_args[1]["data_source"] == DataSource.inline
    assert mock_finish.call_args[1]["data_csv"] == ""


# ---------------------------------------------------------------------------
# StreamingManager._upload_batch
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.register_run")
def test_upload_batch_uploads_gzipped_csv(mock_register, mock_put, tmp_path):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_put.side_effect = lambda **kw: kw["s3_uri"]

    csv_file = tmp_path / "combined.csv"
    csv_file.write_text(COMBINED_CSV_HEADER + COMBINED_CSV_ROW1 + COMBINED_CSV_ROW2)

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
    )
    mgr.start()

    # Manually trigger an upload
    mgr._upload_batch()

    assert mock_put.call_count == 1
    put_kwargs = mock_put.call_args[1]
    assert put_kwargs["s3_uri"].endswith("0001.csv.gz")
    assert put_kwargs["access_key"] == "AKIA..."
    # body should be gzipped
    import gzip

    decompressed = gzip.decompress(put_kwargs["body"])
    assert b"timestamp" in decompressed
    assert b"system_cpu_usage" in decompressed
    assert b"process_cpu_usage" in decompressed

    assert len(mgr.uploaded_uris) == 1
    assert mgr.uploaded_uris[0].endswith("0001.csv.gz")

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.register_run")
def test_upload_batch_includes_header_in_subsequent_batches(
    mock_register, mock_put, tmp_path
):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_put.side_effect = lambda **kw: kw["s3_uri"]

    csv_file = tmp_path / "combined.csv"
    csv_file.write_text(COMBINED_CSV_HEADER + COMBINED_CSV_ROW1)

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
    )
    mgr.start()

    # First batch
    mgr._upload_batch()
    assert mock_put.call_count == 1

    # Append more data
    with open(str(csv_file), "a") as fh:
        fh.write(COMBINED_CSV_ROW2 + COMBINED_CSV_ROW3)

    # Second batch — should prepend the header
    mgr._upload_batch()
    assert mock_put.call_count == 2

    import gzip

    second_body = mock_put.call_args_list[1][1]["body"]
    decompressed = gzip.decompress(second_body)
    lines = decompressed.decode().strip().split("\n")
    assert "timestamp" in lines[0]  # header included
    assert "1774468572" in lines[1]

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.register_run")
def test_upload_batch_no_data_no_upload(mock_register, mock_put, tmp_path):
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    csv_file = tmp_path / "empty.csv"
    csv_file.write_bytes(b"")

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
    )
    mgr.start()

    mgr._upload_batch()

    mock_put.assert_not_called()
    assert len(mgr.uploaded_uris) == 0

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.register_run")
def test_upload_batch_failed_does_not_advance_offset(mock_register, mock_put, tmp_path):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_put.side_effect = RuntimeError("network error")

    csv_file = tmp_path / "combined.csv"
    csv_file.write_text(COMBINED_CSV_HEADER + COMBINED_CSV_ROW1)

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
    )
    mgr.start()

    mgr._upload_batch()  # should fail but not crash

    assert len(mgr.uploaded_uris) == 0
    assert mgr._csv_offset == 0  # not advanced
    assert mgr._seq == 0  # rolled back

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# StreamingManager._set_credentials — missing expires_at
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_set_credentials_missing_expires_at(mock_register):
    mock_register.return_value = {
        "run_id": FAKE_RUN_ID,
        "upload_uri_prefix": FAKE_URI_PREFIX,
        "upload_credentials": {
            "access_key": "AKIA",
            "secret_key": "secret",
            "session_token": "token",
            # expires_at deliberately omitted
        },
    }

    mgr = StreamingManager(token=FAKE_TOKEN)
    with pytest.raises(KeyError, match="expires_at"):
        mgr.start()


# ---------------------------------------------------------------------------
# StreamingManager._upload_batch — csv_update_fn paths
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_upload_batch_csv_update_fn_is_called(mock_register, tmp_path):
    """csv_update_fn is invoked before each batch (lines 317-318)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    called = []

    def update_fn():
        called.append(True)

    csv_file = tmp_path / "combined.csv"
    csv_file.write_bytes(b"")  # empty — batch will return early after calling fn

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
        csv_update_fn=update_fn,
    )
    mgr.start()
    mgr._upload_batch()

    assert called, "csv_update_fn should have been called"

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.register_run")
def test_upload_batch_csv_update_fn_failure_continues(mock_register, tmp_path):
    """A failing csv_update_fn is logged and the batch proceeds (lines 319-320)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    def failing_fn():
        raise RuntimeError("disk full")

    csv_file = tmp_path / "combined.csv"
    csv_file.write_bytes(b"")

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
        csv_update_fn=failing_fn,
    )
    mgr.start()
    mgr._upload_batch()  # must not raise

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# StreamingManager._upload_batch — early return when csv_path is None
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_upload_batch_no_csv_path_returns_early(mock_register):
    """_upload_batch returns immediately when csv_path is None (line 324)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    mgr = StreamingManager(token=FAKE_TOKEN)  # csv_path defaults to None
    mgr.start()
    mgr._upload_batch()  # should be a no-op

    assert len(mgr.uploaded_uris) == 0

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# StreamingManager._upload_batch — no header line raises ValueError
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_upload_batch_raises_when_no_header_line(mock_register, tmp_path):
    """ValueError is raised when the CSV has data but no newline (line 337)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    csv_file = tmp_path / "bad.csv"
    csv_file.write_bytes(b"x" * 512)  # no newline → no header boundary

    mgr = StreamingManager(
        token=FAKE_TOKEN, csv_path=str(csv_file), upload_interval=9999
    )
    mgr.start()

    with pytest.raises(ValueError, match="no header line"):
        mgr._upload_batch()

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# StreamingManager._read_all_csv — csv_update_fn paths
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_read_all_csv_calls_update_fn(mock_register, tmp_path):
    """_read_all_csv invokes csv_update_fn before reading (lines 374-375)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("some,content\n")

    called = []

    def update_fn():
        called.append(True)

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
        csv_update_fn=update_fn,
    )
    mgr.start()
    result = mgr._read_all_csv()

    assert called
    assert result == "some,content\n"

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.register_run")
def test_read_all_csv_update_fn_failure_continues(mock_register, tmp_path):
    """A failing csv_update_fn is swallowed and the file is still read (lines 376-377)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("content\n")

    def failing_fn():
        raise RuntimeError("oops")

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
        csv_update_fn=failing_fn,
    )
    mgr.start()
    result = mgr._read_all_csv()  # must not raise

    assert result == "content\n"

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# StreamingManager._read_all_csv — file not found returns empty string
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_read_all_csv_file_not_found_returns_empty(mock_register):
    """_read_all_csv returns '' when csv_path points to a non-existent file (lines 384-385)."""
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    mgr = StreamingManager(
        token=FAKE_TOKEN, csv_path="/nonexistent/path.csv", upload_interval=9999
    )
    mgr.start()
    result = mgr._read_all_csv()

    assert result == ""

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# StreamingManager._streaming_loop — normal cycle (refresh + upload)
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.refresh_credentials")
@patch("resource_tracker.streaming.register_run")
def test_streaming_loop_runs_normal_cycle(mock_register, mock_refresh, mock_put, tmp_path):
    """The streaming loop refreshes credentials and uploads in one controlled cycle."""
    from datetime import datetime, timezone

    # Credentials expiring in 100 s → within the 300 s threshold
    # → time_until_refresh = 0 → Event.wait(timeout=0.1 s) → loop body runs quickly
    near_expiry = time_module.time() + 100
    near_expiry_iso = datetime.fromtimestamp(near_expiry, tz=timezone.utc).isoformat()
    register_resp = {
        "run_id": FAKE_RUN_ID,
        "upload_uri_prefix": FAKE_URI_PREFIX,
        "upload_credentials": {
            "access_key": "AKIA...",
            "secret_key": "secret...",
            "session_token": "token...",
            "expires_at": near_expiry_iso,
            "region": "us-east-1",
        },
    }
    mock_register.return_value = register_resp

    new_expiry_iso = datetime.fromtimestamp(
        time_module.time() + 3600, tz=timezone.utc
    ).isoformat()
    mock_refresh.return_value = {
        "upload_credentials": {
            "access_key": "AKIA-NEW",
            "secret_key": "secret-new",
            "session_token": "token-new",
            "expires_at": new_expiry_iso,
            "region": "us-east-1",
        }
    }
    mock_put.side_effect = lambda **kw: kw["s3_uri"]

    csv_file = tmp_path / "combined.csv"
    csv_file.write_text(COMBINED_CSV_HEADER + COMBINED_CSV_ROW1)

    mgr = StreamingManager(
        token=FAKE_TOKEN, csv_path=str(csv_file), upload_interval=1
    )
    mgr.start()

    # Stop after two loop ticks (≈0.2 s) to cover the loop body (lines 304-309)
    mgr._stop_event.wait(timeout=0.3)
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)

    assert mock_refresh.call_count >= 1
    assert mock_put.call_count >= 1


# ---------------------------------------------------------------------------
# StreamingManager._streaming_loop — upload exception is caught (line 311)
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.refresh_credentials")
@patch("resource_tracker.streaming.register_run")
def test_streaming_loop_catches_upload_exception(mock_register, mock_refresh, tmp_path):
    """The loop catches exceptions raised by _upload_batch and logs a warning (line 311)."""
    from datetime import datetime, timezone

    near_expiry = time_module.time() + 100
    near_expiry_iso = datetime.fromtimestamp(near_expiry, tz=timezone.utc).isoformat()
    register_resp = {
        "run_id": FAKE_RUN_ID,
        "upload_uri_prefix": FAKE_URI_PREFIX,
        "upload_credentials": {
            "access_key": "AKIA...",
            "secret_key": "secret...",
            "session_token": "token...",
            "expires_at": near_expiry_iso,
            "region": "us-east-1",
        },
    }
    mock_register.return_value = register_resp
    mock_refresh.return_value = {"upload_credentials": register_resp["upload_credentials"]}

    # CSV with no newline → ValueError("no header line") propagates from _upload_batch
    csv_file = tmp_path / "bad.csv"
    csv_file.write_bytes(b"x" * 512)

    mgr = StreamingManager(
        token=FAKE_TOKEN, csv_path=str(csv_file), upload_interval=1
    )
    mgr.start()

    # Wait for the loop to run at least two iterations without crashing
    mgr._stop_event.wait(timeout=0.5)
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)

    assert not mgr._thread.is_alive(), "streaming thread should have exited cleanly"


# ---------------------------------------------------------------------------
# _read_new_bytes — until delimiter
# ---------------------------------------------------------------------------


def test_read_new_bytes_with_until_delimiter(tmp_path):
    """_read_new_bytes reads up to (and including) the first newline when until=b'\\n'."""
    f = tmp_path / "data.csv"
    f.write_bytes(b"header\nrow1\nrow2\n")

    data, offset = _read_new_bytes(str(f), 0, until=b"\n")

    assert data == b"header\n"
    assert offset == len(b"header\n")


def test_read_new_bytes_until_delimiter_not_found(tmp_path):
    """_read_new_bytes raises ValueError when the delimiter is absent."""
    f = tmp_path / "data.csv"
    f.write_bytes(b"no newline here at all")

    with pytest.raises(ValueError, match="not found"):
        _read_new_bytes(str(f), 0, until=b"\n")
