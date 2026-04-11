"""Tests for the S3 upload module (s3_upload.py)."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from resource_tracker.s3_upload import (
    _derive_signing_key,
    _hmac_sha256,
    _parse_s3_uri,
    _sha256_hex,
    put_bytes_with_sts,
    put_object_with_sts,
)

# ---------------------------------------------------------------------------
# _parse_s3_uri
# ---------------------------------------------------------------------------


def test_parse_s3_uri_valid():
    bucket, key = _parse_s3_uri("s3://my-bucket/path/to/object.csv.gz")
    assert bucket == "my-bucket"
    assert key == "path/to/object.csv.gz"


def test_parse_s3_uri_single_key():
    bucket, key = _parse_s3_uri("s3://bucket/file.txt")
    assert bucket == "bucket"
    assert key == "file.txt"


def test_parse_s3_uri_missing_scheme():
    with pytest.raises(ValueError, match="Expected s3 URI"):
        _parse_s3_uri("https://bucket/key")


def test_parse_s3_uri_missing_bucket():
    with pytest.raises(ValueError, match="Expected s3 URI"):
        _parse_s3_uri("s3:///key")


def test_parse_s3_uri_missing_key():
    with pytest.raises(ValueError, match="Expected s3 URI"):
        _parse_s3_uri("s3://bucket/")


def test_parse_s3_uri_empty():
    with pytest.raises(ValueError, match="Expected s3 URI"):
        _parse_s3_uri("")


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def test_sha256_hex():
    # Known SHA-256 of empty bytes
    assert (
        _sha256_hex(b"")
        == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    # Known SHA-256 of "hello"
    assert (
        _sha256_hex(b"hello")
        == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_hmac_sha256():
    result = _hmac_sha256(b"key", "message")
    assert isinstance(result, bytes)
    assert len(result) == 32  # SHA-256 produces 32 bytes


def test_derive_signing_key():
    key = _derive_signing_key(
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "20260326", "us-east-1"
    )
    assert isinstance(key, bytes)
    assert len(key) == 32


# ---------------------------------------------------------------------------
# put_bytes_with_sts
# ---------------------------------------------------------------------------

STS_KWARGS = {
    "access_key": "AKIAIOSFODNN7EXAMPLE",
    "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "session_token": "FwoGZXIvYXdzEBYaDHqa0ABC123/session-token",
    "region": "us-east-1",
}


@patch("resource_tracker.s3_upload.urlopen")
def test_put_bytes_with_sts_returns_uri(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    result = put_bytes_with_sts(
        s3_uri="s3://my-bucket/metrics/0001.csv.gz",
        body=b"timestamp,cpu\n1.0,0.5\n",
        **STS_KWARGS,
    )

    assert result == "s3://my-bucket/metrics/0001.csv.gz"


@patch("resource_tracker.s3_upload.urlopen")
def test_put_bytes_with_sts_sends_correct_request(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    body = b"test payload"
    put_bytes_with_sts(
        s3_uri="s3://bucket/key/file.gz",
        body=body,
        **STS_KWARGS,
    )

    # Inspect the Request
    req = mock_urlopen.call_args[0][0]
    assert req.get_method() == "PUT"
    assert "bucket.s3.us-east-1.amazonaws.com" in req.full_url
    assert "/key/file.gz" in req.full_url
    assert req.data == body
    assert req.get_header("Content-length") == str(len(body))
    assert "AWS4-HMAC-SHA256" in req.get_header("Authorization")
    assert req.get_header("X-amz-security-token") == STS_KWARGS["session_token"]
    assert req.get_header("X-amz-content-sha256") == _sha256_hex(body)


@patch("resource_tracker.s3_upload.urlopen")
def test_put_bytes_with_sts_timeout_forwarded(mock_urlopen):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    put_bytes_with_sts(
        s3_uri="s3://b/k",
        body=b"x",
        timeout=42,
        **STS_KWARGS,
    )

    assert mock_urlopen.call_args[1]["timeout"] == 42


@patch("resource_tracker.s3_upload.urlopen")
def test_put_bytes_with_sts_raises_on_http_error(mock_urlopen):
    from urllib.error import HTTPError

    mock_urlopen.side_effect = HTTPError(
        url="https://bucket.s3.us-east-1.amazonaws.com/key",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=BytesIO(b"<Error><Code>AccessDenied</Code></Error>"),
    )

    with pytest.raises(RuntimeError, match="403"):
        put_bytes_with_sts(
            s3_uri="s3://bucket/key",
            body=b"data",
            **STS_KWARGS,
        )


@patch("resource_tracker.s3_upload.urlopen")
def test_put_bytes_with_sts_raises_on_unexpected_status(mock_urlopen):
    resp = MagicMock()
    resp.status = 500
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    with pytest.raises(RuntimeError, match="500"):
        put_bytes_with_sts(
            s3_uri="s3://bucket/key",
            body=b"data",
            **STS_KWARGS,
        )


# ---------------------------------------------------------------------------
# put_object_with_sts
# ---------------------------------------------------------------------------


@patch("resource_tracker.s3_upload.urlopen")
def test_put_object_with_sts_reads_file_and_delegates(mock_urlopen, tmp_path):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    file = tmp_path / "data.csv"
    file_content = b"timestamp,value\n1.0,42\n"
    file.write_bytes(file_content)

    result = put_object_with_sts(
        s3_uri="s3://bucket/upload/data.csv",
        file_path=file,
        **STS_KWARGS,
    )

    assert result == "s3://bucket/upload/data.csv"

    # Verify the file content was sent as the request body
    req = mock_urlopen.call_args[0][0]
    assert req.data == file_content


@patch("resource_tracker.s3_upload.urlopen")
def test_put_object_with_sts_passes_timeout(mock_urlopen, tmp_path):
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    file = tmp_path / "data.csv"
    file.write_bytes(b"x")

    put_object_with_sts(
        s3_uri="s3://b/k",
        file_path=file,
        timeout=99,
        **STS_KWARGS,
    )

    assert mock_urlopen.call_args[1]["timeout"] == 99
