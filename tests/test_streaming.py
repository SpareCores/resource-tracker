"""Tests for the streaming manager (streaming.py)."""

from __future__ import annotations

import time as time_module
from unittest.mock import patch

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
# StreamingManager.stop — with S3 uploads
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.register_run")
def test_stop_with_uploads_sends_data_uris(
    mock_register, mock_put, mock_finish, tmp_path
):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_put.side_effect = lambda **kw: kw["s3_uri"]
    mock_finish.return_value = {"stats": {"cpu_mean": 1.5}}

    csv_file = tmp_path / "combined.csv"
    csv_file.write_text(COMBINED_CSV_HEADER + COMBINED_CSV_ROW1)

    mgr = StreamingManager(
        token=FAKE_TOKEN,
        csv_path=str(csv_file),
        upload_interval=9999,
    )
    mgr.start()
    mgr._upload_batch()  # produces one upload

    result = mgr.stop(exit_code=0, run_status=RunStatus.finished)

    mock_finish.assert_called_once()
    finish_kwargs = mock_finish.call_args[1]
    assert finish_kwargs["data_source"] == DataSource.s3
    # Should have URIs from the manual batch + final flush
    assert len(finish_kwargs["data_uris"]) >= 1
    assert result["stats"]["cpu_mean"] == 1.5


# ---------------------------------------------------------------------------
# StreamingManager.stop — interrupted
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.finish_run")
@patch("resource_tracker.streaming.register_run")
def test_stop_interrupted(mock_register, mock_finish, tmp_path):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_finish.return_value = {}

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()

    mgr.stop(exit_code=130, run_status="interrupted")

    mock_finish.assert_called_once()
    assert mock_finish.call_args[1]["exit_code"] == 130
    assert mock_finish.call_args[1]["run_status"] == "interrupted"


# ---------------------------------------------------------------------------
# Credential refresh — static threshold
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.refresh_credentials")
@patch("resource_tracker.streaming.register_run")
def test_refresh_credentials_called_when_within_threshold(mock_register, mock_refresh):
    # Credentials that expire in 4 minutes (< 5 min threshold) → should refresh
    from datetime import datetime, timezone

    expiry = time_module.time() + 240  # 4 minutes
    expiry_iso = datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat()

    register_resp = {
        "run_id": FAKE_RUN_ID,
        "upload_uri_prefix": FAKE_URI_PREFIX,
        "upload_credentials": {
            "access_key": "AKIA-OLD",
            "secret_key": "secret-old",
            "session_token": "token-old",
            "expires_at": expiry_iso,
            "region": "us-east-1",
        },
    }
    mock_register.return_value = register_resp

    new_expiry = time_module.time() + 3600
    new_expiry_iso = datetime.fromtimestamp(new_expiry, tz=timezone.utc).isoformat()
    mock_refresh.return_value = {
        "upload_credentials": {
            "access_key": "AKIA-NEW",
            "secret_key": "secret-new",
            "session_token": "token-new",
            "expires_at": new_expiry_iso,
            "region": "us-east-1",
        },
    }

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()

    # With 4 min left, should be within the 5-min threshold
    assert mgr._should_refresh_credentials() is True
    mgr._refresh_credentials()

    mock_refresh.assert_called_once_with(
        FAKE_TOKEN,
        FAKE_RUN_ID,
    )
    assert mgr._credentials["access_key"] == "AKIA-NEW"

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.register_run")
def test_no_refresh_when_credentials_far_from_expiry(mock_register):
    # Credentials that expire in 1 hour → should NOT refresh (well above 5-min threshold)
    from datetime import datetime, timezone

    expiry = time_module.time() + 3600  # 1 hour
    expiry_iso = datetime.fromtimestamp(expiry, tz=timezone.utc).isoformat()

    register_resp = {
        "run_id": FAKE_RUN_ID,
        "upload_uri_prefix": FAKE_URI_PREFIX,
        "upload_credentials": {
            "access_key": "AKIA-OLD",
            "secret_key": "secret-old",
            "session_token": "token-old",
            "expires_at": expiry_iso,
            "region": "us-east-1",
        },
    }
    mock_register.return_value = register_resp

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()

    assert mgr._should_refresh_credentials() is False

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.refresh_credentials")
@patch("resource_tracker.streaming.register_run")
def test_refresh_credentials_retries_once(mock_register, mock_refresh):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_refresh.side_effect = [RuntimeError("fail 1"), FAKE_REFRESH_RESPONSE]

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()

    with patch("resource_tracker.streaming.sleep"):  # skip the 10s delay
        mgr._refresh_credentials()

    assert mock_refresh.call_count == 2
    assert mgr._credentials["access_key"] == "AKIA-NEW..."

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


@patch("resource_tracker.streaming.refresh_credentials")
@patch("resource_tracker.streaming.register_run")
def test_refresh_credentials_both_attempts_fail(mock_register, mock_refresh):
    mock_register.return_value = FAKE_REGISTER_RESPONSE
    mock_refresh.side_effect = RuntimeError("always fails")

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    mgr.start()
    original_creds = mgr._credentials

    with patch("resource_tracker.streaming.sleep"):
        mgr._refresh_credentials()

    # Credentials should remain unchanged
    assert mgr._credentials == original_creds
    assert mock_refresh.call_count == 2

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Sequence numbering
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.put_bytes_with_sts")
@patch("resource_tracker.streaming.register_run")
def test_sequence_numbers_increment(mock_register, mock_put, tmp_path):
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

    mgr._upload_batch()

    # One combined file uploaded with seq 1
    assert mgr._seq == 1
    uris = mgr.uploaded_uris
    assert any("0001" in u for u in uris)

    # Append more and upload again
    with open(str(csv_file), "a") as fh:
        fh.write(COMBINED_CSV_ROW2)

    mgr._upload_batch()
    assert mgr._seq == 2
    assert any("0002" in u for u in mgr.uploaded_uris)

    # Cleanup
    mgr._stop_event.set()
    mgr._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# is_alive property
# ---------------------------------------------------------------------------


@patch("resource_tracker.streaming.register_run")
def test_is_alive(mock_register):
    mock_register.return_value = FAKE_REGISTER_RESPONSE

    mgr = StreamingManager(token=FAKE_TOKEN, upload_interval=9999)
    assert mgr.is_alive is False

    mgr.start()
    assert mgr.is_alive is True

    mgr._stop_event.set()
    mgr._thread.join(timeout=5)
    assert mgr.is_alive is False
