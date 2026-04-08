"""HTTP client for the Spare Cores Sentinel metrics ingestion API."""

from __future__ import annotations

import gzip
import os
from enum import Enum
from json import dumps as json_dumps
from json import loads as json_loads
from logging import getLogger
from shlex import split as shlex_split
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

logger = getLogger(__name__)

DEFAULT_SENTINEL_URL = "https://api.sentinel.sparecores.net"
DEFAULT_TIMEOUT = 30  # seconds


class RunStatus(Enum):
    finished = "finished"
    failed = "failed"


class DataSource(Enum):
    s3 = "s3"
    inline = "inline"


class SentinelAPIError(Exception):
    """Raised when the Sentinel API returns a non-2xx response.

    Attributes:
        status_code: The HTTP status code.
        body: The decoded response body (best-effort).
    """

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Sentinel API error {status_code}: {body}")


def _get_base_url() -> str:
    """Return the Sentinel API base URL from env or the default."""
    return os.environ.get("SENTINEL_API_URL", DEFAULT_SENTINEL_URL)


def _request(
    method: str,
    path: str,
    *,
    token: str,
    payload: Optional[dict] = None,
    base_url: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    compress: bool = False,
) -> dict:
    """Send a JSON request to the Sentinel API and return the parsed response.

    Args:
        method: HTTP method (e.g. ``POST``).
        path: URL path relative to the base URL (e.g. ``/runs``).
        token: Bearer token for authentication.
        payload: Optional JSON-serializable body.
        base_url: Override the base URL (defaults to env / built-in default).
        timeout: Request timeout in seconds.
        compress: If ``True``, gzip-compress the request body and set the
            ``Content-Encoding: gzip`` header.

    Returns:
        The JSON-decoded response body as a dictionary.

    Raises:
        SentinelAPIError: On non-2xx HTTP responses.
    """
    url = urljoin(base_url or _get_base_url(), path)
    body = json_dumps(payload).encode("utf-8") if payload is not None else None
    if compress and body is not None:
        body = gzip.compress(body)

    req = Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if compress and body is not None:
        req.add_header("Content-Encoding", "gzip")

    logger.debug("Sentinel API %s %s", method, url)

    try:
        with urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            return json_loads(resp_body) if resp_body else {}
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise SentinelAPIError(exc.code, error_body) from exc


def register_run(
    token: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    host_info: Optional[Dict[str, Any]] = None,
    cloud_info: Optional[Dict[str, Any]] = None,
) -> dict:
    """Register the start of a new Run with the Sentinel API.

    Args:
        token: Bearer token for authentication.
        metadata: Optional run metadata. Recognised keys include
            ``project_name``, ``job_name``, ``stage_name``, ``task_name``,
            ``external_run_id``, ``pid``, ``container_image``,
            ``command`` (a ``List[str]`` JSON array, e.g.
            ``["python", "train.py", "--epochs", "10"]``; a plain ``str``
            is automatically split with :func:`shlex.split` for backward
            compatibility),
            ``env``, ``language``, ``orchestrator``, ``executor``, ``team``,
            and ``tags`` (an arbitrary key-value dict).
        host_info: Optional dict of ``host_*`` fields (e.g. ``host_vcpus``,
            ``host_memory_mib``, ``host_gpu_model``, etc.).
        cloud_info: Optional dict of ``cloud_*`` fields (e.g.
            ``cloud_vendor_id``, ``cloud_region_id``,
            ``cloud_instance_type``, etc.).

    Returns:
        A dict containing at least:

        - ``run_id`` (str): Unique identifier for this run.
        - ``upload_uri_prefix`` (str): S3 URI prefix for uploading metric files.
        - ``upload_credentials`` (dict): Temporary AWS STS credentials with keys
          ``access_key``, ``secret_key``, ``session_token``, ``expiration``,
          and ``region``.

    Raises:
        SentinelAPIError: On non-2xx responses.
    """
    payload = {k: v for k, v in (metadata or {}).items() if v is not None}
    if host_info:
        payload.update({k: v for k, v in host_info.items() if v is not None})
    if cloud_info:
        payload.update({k: v for k, v in cloud_info.items() if v is not None})
    if isinstance(payload.get("command"), str):
        payload["command"] = shlex_split(payload["command"])
    logger.info("Registering run with Sentinel API")
    return _request("POST", "/runs", token=token, payload=payload)


def refresh_credentials(
    token: str,
    run_id: str,
) -> dict:
    """Refresh the temporary upload credentials for an existing run.

    Args:
        token: Bearer token for authentication.
        run_id: The run identifier returned by :func:`register_run`.

    Returns:
        A dict with refreshed ``upload_credentials`` (same structure as in
        :func:`register_run`).

    Raises:
        SentinelAPIError: On non-2xx responses.
    """
    logger.info("Refreshing credentials for run %s", run_id)
    return _request(
        "POST",
        f"/runs/{run_id}/refresh-credentials",
        token=token,
    )


def finish_run(
    token: str,
    run_id: str,
    *,
    exit_code: int = 0,
    run_status: RunStatus = RunStatus.finished,
    data_source: DataSource = DataSource.s3,
    data_uris: Optional[List[str]] = None,
    data_csv: Optional[str] = None,
) -> dict:
    """Signal that a run has finished and submit final data.

    Args:
        token: Bearer token for authentication.
        run_id: The run identifier returned by :func:`register_run`.
        exit_code: The exit code of the monitored process.
        run_status: Run outcome, either ``"finished"`` or ``"failed"``.
        data_source: Either ``"s3"`` (uploaded CSV objects) or ``"inline"``
            (plain CSV string sent inline; the request body is gzip-compressed
            by :func:`_request` so no pre-encoding is needed).
        data_uris: List of S3 URIs of uploaded gzipped CSV files.
            Required when ``data_source="s3"``.
        data_csv: Plain CSV string to submit inline.
            Required when ``data_source="inline"``.

    Returns:
        A dict with backend-computed statistics for the run.

    Raises:
        SentinelAPIError: On non-2xx responses.
    """
    payload: Dict[str, Any] = {
        "exit_code": exit_code,
        "run_status": run_status.value,
        "data_source": data_source.value,
    }

    if not data_uris and not data_csv:
        raise ValueError(
            "Either 'data_uris' (for data_source='s3') or 'data_csv' (for data_source='inline') must be provided."
        )

    if data_source == DataSource.s3:
        payload["data_uris"] = data_uris
    else:
        payload["data_csv"] = data_csv

    logger.info(
        "Finishing run %s (status=%s, exit_code=%d)", run_id, run_status, exit_code
    )
    return _request(
        "POST",
        f"/runs/{run_id}/finish",
        token=token,
        payload=payload,
        compress=data_source == DataSource.inline,
    )
