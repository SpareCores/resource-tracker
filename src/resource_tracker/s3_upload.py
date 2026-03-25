"""Upload a local file to S3 using temporary STS credentials.

This is a minimal, no-dependencies, POC implementation of a client utilizing the
API's STS credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Expected s3 URI like s3://bucket/path/to/object")
    return parsed.netloc, parsed.path.lstrip("/")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def put_object_with_sts(
    *,
    s3_uri: str,
    file_path: Path,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
) -> None:
    bucket, key = _parse_s3_uri(s3_uri)
    body = file_path.read_bytes()
    payload_hash = _sha256_hex(body)

    now = datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    host = f"{bucket}.s3.{region}.amazonaws.com"
    canonical_uri = "/" + key
    endpoint = f"https://{host}{canonical_uri}"

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

    try:
        with urlopen(req) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"S3 upload failed with status {resp.status}")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"S3 upload failed with status {exc.code}: {error_body}"
        ) from exc


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
    put_object_with_sts(
        s3_uri=args.s3_uri,
        file_path=args.file,
        access_key=args.access_key,
        secret_key=args.secret_key,
        session_token=args.session_token,
        region=args.region,
    )
    print(f"Uploaded {args.file} to {args.s3_uri}")
