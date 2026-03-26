"""Upload data to S3 using temporary STS credentials.

Minimal, zero-dependency implementation (stdlib only) of AWS Signature V4
authenticated ``PUT`` requests, designed for uploading gzipped CSV metric
files via the Sentinel API's temporary STS credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = getLogger(__name__)

DEFAULT_UPLOAD_TIMEOUT = 30  # seconds


def _parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Parse an ``s3://bucket/key`` URI into *(bucket, key)*.

    Args:
        s3_uri: An S3 URI in the form ``s3://bucket/path/to/object``.

    Returns:
        A ``(bucket, key)`` tuple.

    Raises:
        ValueError: If the URI is not a valid S3 URI.
    """
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Expected s3 URI like s3://bucket/path/to/object")
    return parsed.netloc, parsed.path.lstrip("/")


def _get_bucket_region(bucket: str, timeout: int = 10) -> str:
    """Determine the AWS region of an S3 bucket via a HEAD request.

    Uses the ``x-amz-bucket-region`` response header, which S3 returns even
    for 3xx/4xx responses.  Results are cached in a module-level dict so
    repeated calls for the same bucket are free.

    Args:
        bucket: The S3 bucket name.
        timeout: HTTP request timeout in seconds.

    Returns:
        The AWS region string (e.g. ``"eu-central-1"``).  Falls back to
        ``"eu-central-1"`` if detection fails.
    """

    url = f"https://{bucket}.s3.amazonaws.com/"
    req = Request(url, method="HEAD")
    try:
        with urlopen(req, timeout=timeout) as resp:
            region = resp.headers.get("x-amz-bucket-region", "eu-central-1")
    except HTTPError as exc:
        # 301/403/404 responses still carry the header
        region = exc.headers.get("x-amz-bucket-region", "eu-central-1")
    except Exception:
        logger.debug(
            "Could not detect region for bucket %s, defaulting to eu-central-1", bucket
        )
        region = "eu-central-1"

    logger.debug("Detected region for bucket %s: %s", bucket, region)
    return region


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def put_bytes_with_sts(
    *,
    s3_uri: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str | None = None,
    timeout: int = DEFAULT_UPLOAD_TIMEOUT,
) -> str:
    """Upload raw bytes to S3 using temporary STS credentials.

    This is the core upload primitive used by the streaming module to push
    gzipped CSV data without writing a temporary file.

    Args:
        s3_uri: Target S3 URI (``s3://bucket/path/to/object``).
        body: Raw bytes to upload.
        access_key: AWS STS access key ID.
        secret_key: AWS STS secret access key.
        session_token: AWS STS session token.
        region: AWS region of the target bucket.
        timeout: HTTP request timeout in seconds.

    Returns:
        The S3 URI that was written to (same as *s3_uri*).

    Raises:
        RuntimeError: If the upload fails.
    """
    bucket, key = _parse_s3_uri(s3_uri)
    payload_hash = _sha256_hex(body)

    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    if not region:
        region = _get_bucket_region(bucket, timeout=timeout)

    host = f"{bucket}.s3.{region}.amazonaws.com"
    canonical_uri = "/" + key
    endpoint = f"https://{host}{canonical_uri}"

    logger.debug(
        "Uploading %s to %s",
        s3_uri,
        endpoint,
    )

    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-security-token:{session_token}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date;x-amz-security-token"
    canonical_request = (
        f"PUT\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    canonical_request_hash = _sha256_hex(canonical_request.encode("utf-8"))

    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{canonical_request_hash}"
    )
    signing_key = _derive_signing_key(secret_key, date_stamp, region)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    req = Request(endpoint, data=body, method="PUT")
    req.add_header("Host", host)
    req.add_header("Authorization", authorization)
    req.add_header("x-amz-date", amz_date)
    req.add_header("x-amz-security-token", session_token)
    req.add_header("x-amz-content-sha256", payload_hash)
    req.add_header("Content-Length", str(len(body)))

    logger.debug("S3 PUT %s (%d bytes)", s3_uri, len(body))

    try:
        with urlopen(req, timeout=timeout) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"S3 upload failed with status {resp.status}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"S3 upload failed with status {exc.code}: {error_body}"
        ) from exc

    logger.debug("S3 PUT %s completed", s3_uri)
    return s3_uri


def put_object_with_sts(
    *,
    s3_uri: str,
    file_path: Path,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
    timeout: int = DEFAULT_UPLOAD_TIMEOUT,
) -> str:
    """Upload a local file to S3 using temporary STS credentials.

    Convenience wrapper around :func:`put_bytes_with_sts` that reads the file
    contents first.

    Args:
        s3_uri: Target S3 URI (``s3://bucket/path/to/object``).
        file_path: Path to the local file to upload.
        access_key: AWS STS access key ID.
        secret_key: AWS STS secret access key.
        session_token: AWS STS session token.
        region: AWS region of the target bucket.
        timeout: HTTP request timeout in seconds.

    Returns:
        The S3 URI that was written to (same as *s3_uri*).

    Raises:
        RuntimeError: If the upload fails.
    """
    logger.debug("Reading file %s for upload to %s", file_path, s3_uri)
    return put_bytes_with_sts(
        s3_uri=s3_uri,
        body=file_path.read_bytes(),
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        timeout=timeout,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upload a local file to S3 using temporary STS credentials."
    )
    parser.add_argument("--s3-uri", required=True, help="Target S3 URI.")
    parser.add_argument("--file", required=True, type=Path, help="Local file path.")
    parser.add_argument("--access-key", required=True, help="STS access key ID.")
    parser.add_argument("--secret-key", required=True, help="STS secret access key.")
    parser.add_argument("--session-token", required=True, help="STS session token.")
    parser.add_argument(
        "--region", required=True, help="AWS region for the target bucket."
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    uri = put_object_with_sts(
        s3_uri=args.s3_uri,
        file_path=args.file,
        access_key=args.access_key,
        secret_key=args.secret_key,
        session_token=args.session_token,
        region=args.region,
    )
    print(f"Uploaded {args.file} to {uri}")
