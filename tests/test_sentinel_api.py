"""Tests for the Sentinel API client (sentinel_api.py)."""

from io import BytesIO
from json import dumps as json_dumps
from unittest.mock import MagicMock, patch

import pytest

from resource_tracker.sentinel_api import (
    DEFAULT_SENTINEL_URL,
    SentinelAPIError,
    _get_base_url,
    _request,
    finish_run,
    get_token,
    refresh_credentials,
    register_run,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_TOKEN = "test-token-abc123"
FAKE_RUN_ID = "run-00000000-0000-0000-0000-000000000001"


def _mock_response(body: dict, status: int = 200) -> MagicMock:
    """Build a mock that behaves like ``urlopen(...)`` return value."""
    raw = json_dumps(body).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------


def test_get_token_when_set(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_TOKEN", "my-secret")
    assert get_token() == "my-secret"


def test_get_token_when_unset(monkeypatch):
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    assert get_token() is None


# ---------------------------------------------------------------------------
# _get_base_url
# ---------------------------------------------------------------------------


def test_base_url_default(monkeypatch):
    monkeypatch.delenv("SENTINEL_API_URL", raising=False)
    assert _get_base_url() == DEFAULT_SENTINEL_URL


def test_base_url_override(monkeypatch):
    monkeypatch.setenv("SENTINEL_API_URL", "https://custom.example.com")
    assert _get_base_url() == "https://custom.example.com"


# ---------------------------------------------------------------------------
# _request (low-level)
# ---------------------------------------------------------------------------


@patch("resource_tracker.sentinel_api.urlopen")
def test_request_sends_correct_headers(mock_urlopen):
    mock_urlopen.return_value = _mock_response({"ok": True})

    result = _request(
        "POST", "/test", token=FAKE_TOKEN, payload={"a": 1}, base_url="https://api.test"
    )

    assert result == {"ok": True}

    # inspect the Request object passed to urlopen
    req = mock_urlopen.call_args[0][0]
    assert req.get_method() == "POST"
    assert req.full_url == "https://api.test/test"
    assert req.get_header("Authorization") == f"Bearer {FAKE_TOKEN}"
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("Accept") == "application/json"
    assert req.data == json_dumps({"a": 1}).encode("utf-8")


@patch("resource_tracker.sentinel_api.urlopen")
def test_request_no_payload(mock_urlopen):
    mock_urlopen.return_value = _mock_response({})

    _request("POST", "/test", token=FAKE_TOKEN, base_url="https://api.test")

    req = mock_urlopen.call_args[0][0]
    assert req.data is None


@patch("resource_tracker.sentinel_api.urlopen")
def test_request_raises_sentinel_api_error(mock_urlopen):
    from urllib.error import HTTPError

    mock_urlopen.side_effect = HTTPError(
        url="https://api.test/fail",
        code=422,
        msg="Unprocessable Entity",
        hdrs={},
        fp=BytesIO(b'{"detail": "bad input"}'),
    )

    with pytest.raises(SentinelAPIError) as exc_info:
        _request("POST", "/fail", token=FAKE_TOKEN, base_url="https://api.test")

    assert exc_info.value.status_code == 422
    assert "bad input" in exc_info.value.body


@patch("resource_tracker.sentinel_api.urlopen")
def test_request_timeout_forwarded(mock_urlopen):
    mock_urlopen.return_value = _mock_response({})

    _request("POST", "/t", token=FAKE_TOKEN, base_url="https://api.test", timeout=7)

    assert mock_urlopen.call_args[1]["timeout"] == 7


# ---------------------------------------------------------------------------
# register_run
# ---------------------------------------------------------------------------

REGISTER_RESPONSE = {
    "run_id": FAKE_RUN_ID,
    "upload_uri_prefix": "s3://bucket/prefix/run-001",
    "upload_credentials": {
        "access_key": "AKIA...",
        "secret_key": "secret...",
        "session_token": "token...",
        "expiration": "2026-03-27T00:00:00Z",
        "region": "us-east-1",
    },
}


@patch("resource_tracker.sentinel_api.urlopen")
def test_register_run_minimal(mock_urlopen, monkeypatch):
    mock_urlopen.return_value = _mock_response(REGISTER_RESPONSE)
    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    result = register_run(FAKE_TOKEN)

    assert result["run_id"] == FAKE_RUN_ID
    assert result["upload_uri_prefix"].startswith("s3://")
    assert "access_key" in result["upload_credentials"]

    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://api.test/runs"
    assert req.get_method() == "POST"


@patch("resource_tracker.sentinel_api.urlopen")
def test_register_run_with_metadata(mock_urlopen, monkeypatch):
    mock_urlopen.return_value = _mock_response(REGISTER_RESPONSE)
    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    metadata = {
        "project_name": "my-project",
        "job_name": "train",
        "language": "python",
        "tags": {"env": "staging"},
        "ignored_none_field": None,
    }
    register_run(FAKE_TOKEN, metadata=metadata)

    req = mock_urlopen.call_args[0][0]
    import json

    sent_payload = json.loads(req.data.decode("utf-8"))
    assert sent_payload["project_name"] == "my-project"
    assert sent_payload["language"] == "python"
    assert sent_payload["tags"] == {"env": "staging"}
    # None values should be filtered out
    assert "ignored_none_field" not in sent_payload


# ---------------------------------------------------------------------------
# refresh_credentials
# ---------------------------------------------------------------------------

REFRESH_RESPONSE = {
    "upload_credentials": {
        "access_key": "AKIA-NEW...",
        "secret_key": "secret-new...",
        "session_token": "token-new...",
        "expiration": "2026-03-28T00:00:00Z",
        "region": "us-east-1",
    },
}


@patch("resource_tracker.sentinel_api.urlopen")
def test_refresh_credentials(mock_urlopen, monkeypatch):
    mock_urlopen.return_value = _mock_response(REFRESH_RESPONSE)
    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    result = refresh_credentials(FAKE_TOKEN, FAKE_RUN_ID)

    assert result["upload_credentials"]["access_key"] == "AKIA-NEW..."

    req = mock_urlopen.call_args[0][0]
    assert req.full_url == f"https://api.test/runs/{FAKE_RUN_ID}/refresh-credentials"
    assert req.get_method() == "POST"


# ---------------------------------------------------------------------------
# finish_run
# ---------------------------------------------------------------------------


@patch("resource_tracker.sentinel_api.urlopen")
def test_finish_run_with_s3_uris(mock_urlopen, monkeypatch):
    mock_urlopen.return_value = _mock_response({"stats": {"cpu_mean": 1.5}})
    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    uris = [
        "s3://bucket/prefix/process_0001.csv.gz",
        "s3://bucket/prefix/system_0001.csv.gz",
    ]
    result = finish_run(
        FAKE_TOKEN,
        FAKE_RUN_ID,
        exit_code=0,
        run_status="success",
        data_source="s3",
        data_uris=uris,
    )

    assert "stats" in result

    req = mock_urlopen.call_args[0][0]
    assert req.full_url == f"https://api.test/runs/{FAKE_RUN_ID}/finish"

    import json

    sent = json.loads(req.data.decode("utf-8"))
    assert sent["exit_code"] == 0
    assert sent["run_status"] == "success"
    assert sent["data_source"] == "s3"
    assert sent["data_uris"] == uris
    assert "data_csv" not in sent


@patch("resource_tracker.sentinel_api.urlopen")
def test_finish_run_with_inline_csv(mock_urlopen, monkeypatch):
    mock_urlopen.return_value = _mock_response({"stats": {}})
    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    import gzip
    from base64 import b64encode

    csv_content = b"timestamp,cpu_usage\n1.0,0.5\n2.0,0.8\n"
    gzipped = gzip.compress(csv_content)
    finish_run(
        FAKE_TOKEN,
        FAKE_RUN_ID,
        exit_code=1,
        run_status="failure",
        data_source="inline",
        data_csv=gzipped,
    )

    import json

    req = mock_urlopen.call_args[0][0]
    sent = json.loads(req.data.decode("utf-8"))
    assert sent["data_source"] == "inline"
    assert sent["data_csv"] == b64encode(gzipped).decode("ascii")
    assert sent["exit_code"] == 1
    assert sent["run_status"] == "failure"
    assert "data_uris" not in sent


@patch("resource_tracker.sentinel_api.urlopen")
def test_register_run_with_host_and_cloud_info(mock_urlopen, monkeypatch):
    mock_urlopen.return_value = _mock_response(REGISTER_RESPONSE)
    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    host = {"host_vcpus": 4, "host_memory_mib": 8192, "host_gpu_count": None}
    cloud = {"cloud_vendor_id": "aws", "cloud_region_id": "us-east-1"}

    register_run(
        FAKE_TOKEN,
        metadata={"project_name": "proj"},
        host_info=host,
        cloud_info=cloud,
    )

    import json

    req = mock_urlopen.call_args[0][0]
    sent = json.loads(req.data.decode("utf-8"))
    assert sent["project_name"] == "proj"
    assert sent["host_vcpus"] == 4
    assert sent["host_memory_mib"] == 8192
    # None values in host_info should be filtered out
    assert "host_gpu_count" not in sent
    assert sent["cloud_vendor_id"] == "aws"
    assert sent["cloud_region_id"] == "us-east-1"


@patch("resource_tracker.sentinel_api.urlopen")
def test_finish_run_api_error(mock_urlopen, monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setenv("SENTINEL_API_URL", "https://api.test")

    mock_urlopen.side_effect = HTTPError(
        url="https://api.test/runs/x/finish",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=BytesIO(b"server broke"),
    )

    with pytest.raises(SentinelAPIError) as exc_info:
        finish_run(FAKE_TOKEN, "x", data_source="s3", data_uris=[])

    assert exc_info.value.status_code == 500
    assert "server broke" in exc_info.value.body
