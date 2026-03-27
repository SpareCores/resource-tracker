"""Streaming manager that uploads resource-tracker CSV data to S3 in the background.

Orchestrates the Sentinel API client (:mod:`sentinel_api`) and S3 upload
(:mod:`s3_upload`) to periodically push gzipped CSV batches while
automatically refreshing temporary AWS STS credentials.
"""

from __future__ import annotations

from datetime import datetime
from gzip import compress as gzip_compress
from logging import getLogger
from threading import Event, Thread
from time import sleep, time
from typing import Any, Callable, Dict, List, Optional

from .s3_upload import put_bytes_with_sts
from .sentinel_api import (
    DataSource,
    RunStatus,
    finish_run,
    refresh_credentials,
    register_run,
)

logger = getLogger(__name__)

# How long (seconds) before credential expiry to trigger a refresh.
_CREDENTIAL_REFRESH_THRESHOLD = 300  # 5 minutes

# Retry delay (seconds) when a credential refresh fails the first time.
_CREDENTIAL_REFRESH_RETRY_DELAY = 10


def _parse_expires_at(expires_at: str) -> float:
    """Parse an ISO-8601 expires_at string into a UNIX timestamp.

    Handles both ``Z`` suffix and ``+00:00`` offset.
    """
    # normalise "Z" → "+00:00" so fromisoformat works on Python < 3.11
    if expires_at.endswith("Z"):
        expires_at = expires_at[:-1] + "+00:00"
    return datetime.fromisoformat(expires_at).timestamp()


def _read_new_bytes(filepath: str, offset: int) -> tuple[bytes, int]:
    """Read new bytes from *filepath* starting at *offset*.

    Returns:
        A ``(new_bytes, new_offset)`` tuple.  *new_bytes* may be empty if
        nothing was written since last read.
    """
    try:
        with open(filepath, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
            return data, offset + len(data)
    except FileNotFoundError:
        return b"", offset


class StreamingManager:
    """Manages the lifecycle of streaming resource metrics to the Sentinel API.

    This class is meant to be used **internally** by
    :class:`~resource_tracker.tracker.ResourceTracker`.  It runs a single
    daemon thread that:

    * Periodically reads new CSV rows from the combined tracker CSV file.
    * Gzip-compresses and uploads them as S3 objects.
    * Refreshes AWS STS credentials before they expire.

    Args:
        token: Sentinel API bearer token.
        csv_path: Path to the combined CSV temp file (or ``None``).
        upload_interval: Seconds between upload cycles (default 60).
        metadata: Optional run metadata forwarded to :func:`register_run`.
        host_info: Optional ``host_*`` fields forwarded to :func:`register_run`.
        cloud_info: Optional ``cloud_*`` fields forwarded to :func:`register_run`.
        csv_update_fn: Optional callable invoked before each upload cycle to
            refresh the combined CSV file (e.g. append new rows).
    """

    def __init__(
        self,
        token: str,
        csv_path: Optional[str] = None,
        upload_interval: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
        host_info: Optional[Dict[str, Any]] = None,
        cloud_info: Optional[Dict[str, Any]] = None,
        csv_update_fn: Optional[Callable[[], None]] = None,
    ):
        self._token = token
        self._csv_path = csv_path
        self._upload_interval = max(1, upload_interval)
        self._metadata = metadata
        self._host_info = host_info
        self._cloud_info = cloud_info
        self._csv_update_fn = csv_update_fn

        # Set after start()
        self._run_id: Optional[str] = None
        self._upload_uri_prefix: Optional[str] = None
        self._credentials: Optional[dict] = None
        self._credential_expiry: float = 0.0  # UNIX ts

        # Upload bookkeeping
        self._uploaded_uris: List[str] = []
        self._seq: int = 0  # sequence counter for S3 keys
        self._csv_offset: int = 0

        # Thread control
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def start(self) -> None:
        """Register the run with the Sentinel API and start the upload thread."""
        resp = register_run(
            self._token,
            metadata=self._metadata,
            host_info=self._host_info,
            cloud_info=self._cloud_info,
        )
        self._run_id = resp.get("run_id")
        if not self._run_id:
            raise KeyError("register_run response missing 'run_id'")
        self._upload_uri_prefix = resp["upload_uri_prefix"]
        self._set_credentials(resp["upload_credentials"])

        logger.info(
            "Streaming started for run %s (upload every %ds)",
            self._run_id,
            self._upload_interval,
        )

        self._thread = Thread(
            target=self._streaming_loop, daemon=True, name="streaming-upload"
        )
        self._thread.start()

    def stop(
        self,
        exit_code: int = 0,
        run_status: RunStatus = RunStatus.finished,
    ) -> dict:
        """Stop the upload thread, flush remaining data, and finish the run.

        Args:
            exit_code: Exit code of the monitored process.
            run_status: Run outcome (e.g. ``"started"``, ``"finished"``, ``"failed"``, or ``"stale"``).

        Returns:
            The response dict from the Sentinel ``finish_run`` endpoint.
        """
        # Signal the loop to stop and wait for the thread to exit
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=30)

        # Final flush — upload whatever is left
        try:
            self._upload_batch()
        except Exception as e:
            logger.warning("Final upload batch failed: %s", e)

        # Decide data delivery mode — wrapped so finish_run is always attempted
        data_kwargs: Dict[str, Any] = {}
        try:
            if self._uploaded_uris:
                data_kwargs = {
                    "data_source": DataSource.s3,
                    "data_uris": list(self._uploaded_uris),
                }
            else:
                # Short run — no S3 uploads happened yet; send inline CSV
                data_kwargs = {
                    "data_source": DataSource.inline,
                    "data_csv": self._read_all_csv(),
                }
        except Exception as e:
            logger.warning("Failed to prepare data for finish_run: %s", e)
            # Fall back to inline with empty gzipped CSV so finish_run still fires
            data_kwargs = {
                "data_source": DataSource.inline,
                "data_csv": gzip_compress(b""),
            }

        result = finish_run(
            self._token,
            self._run_id,
            exit_code=exit_code,
            run_status=run_status,
            **data_kwargs,
        )

        logger.info(
            "Run %s finished (status=%s, uploads=%d)",
            self._run_id,
            run_status,
            len(self._uploaded_uris),
        )
        return result

    @property
    def is_alive(self) -> bool:
        """Whether the upload thread is still running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def run_id(self) -> Optional[str]:
        """The Sentinel run ID (set after :meth:`start`)."""
        return self._run_id

    @property
    def uploaded_uris(self) -> List[str]:
        """S3 URIs of all successfully uploaded objects so far."""
        return list(self._uploaded_uris)

    def _set_credentials(self, creds: dict) -> None:
        """Store credentials and compute the expiry timestamp."""
        self._credentials = creds
        expiry_str = creds.get("expires_at")
        if not expiry_str:
            raise KeyError("credentials missing 'expires_at'")
        self._credential_expiry = _parse_expires_at(expiry_str)
        remaining = self._credential_expiry - time()
        logger.debug(
            "Credentials set, expiry in %.0fs, refresh threshold %ds",
            remaining,
            _CREDENTIAL_REFRESH_THRESHOLD,
        )

    def _should_refresh_credentials(self) -> bool:
        """Return True if credentials will expire within the static threshold."""
        return (self._credential_expiry - time()) <= _CREDENTIAL_REFRESH_THRESHOLD

    def _refresh_credentials(self) -> None:
        """Hit the refresh endpoint, retrying once on failure."""
        for attempt in range(2):
            try:
                resp = refresh_credentials(
                    self._token,
                    self._run_id,
                )
                self._set_credentials(resp["upload_credentials"])
                return
            except Exception as e:
                if attempt == 0:
                    logger.warning(
                        "Credential refresh failed (attempt 1/2), retrying in %ds: %s",
                        _CREDENTIAL_REFRESH_RETRY_DELAY,
                        e,
                    )
                    sleep(_CREDENTIAL_REFRESH_RETRY_DELAY)
                else:
                    logger.warning(
                        "Credential refresh failed (attempt 2/2), "
                        "continuing with existing credentials: %s",
                        e,
                    )

    def _seconds_until_expiry(self) -> float:
        """Seconds until credentials expire."""
        return max(0.0, self._credential_expiry - time())

    def _streaming_loop(self) -> None:
        """Background loop: upload batches and refresh credentials."""
        while not self._stop_event.is_set():
            # Sleep for the shorter of upload_interval or time-until-refresh-needed
            time_until_refresh = max(
                0.0, self._seconds_until_expiry() - _CREDENTIAL_REFRESH_THRESHOLD
            )
            wait_secs = min(float(self._upload_interval), time_until_refresh)
            # Use the event's wait() so we can be woken early by stop()
            if self._stop_event.wait(timeout=max(0.1, wait_secs)):
                break  # stop requested

            # Refresh credentials if needed
            if self._should_refresh_credentials():
                self._refresh_credentials()

            # Upload a batch
            try:
                self._upload_batch()
            except Exception as e:
                logger.warning("Upload batch failed: %s", e)

    def _upload_batch(self) -> None:
        """Read new CSV data from the combined CSV file and upload as a gzipped S3 object."""
        # Refresh the combined CSV before reading (e.g. append new tracker rows)
        if self._csv_update_fn is not None:
            try:
                self._csv_update_fn()
            except Exception as e:
                logger.debug("CSV update function failed: %s", e)

        creds = self._credentials
        if creds is None or self._csv_path is None:
            return

        current_offset = self._csv_offset
        new_data, new_offset = _read_new_bytes(self._csv_path, current_offset)

        if not new_data:
            return

        # If this is not the first batch, prepend the CSV header so every
        # uploaded object is a self-contained CSV.
        if current_offset > 0:
            header, _ = _read_new_bytes(self._csv_path, 0)
            # header is everything up to (and including) the first newline
            header_end = header.find(b"\n")
            if header_end >= 0:
                header_line = header[: header_end + 1]
                new_data = header_line + new_data

        compressed = gzip_compress(new_data)
        self._seq += 1
        s3_key = f"{self._upload_uri_prefix}/{self._seq:04d}.csv.gz"

        try:
            uri = put_bytes_with_sts(
                s3_uri=s3_key,
                body=compressed,
                access_key=creds["access_key"],
                secret_key=creds["secret_key"],
                session_token=creds["session_token"],
            )
            self._uploaded_uris.append(uri)
            self._csv_offset = new_offset
            logger.debug(
                "Uploaded %s (%d bytes raw, %d bytes gzipped)",
                uri,
                len(new_data),
                len(compressed),
            )
        except Exception as e:
            # Don't advance offset — we'll retry next cycle
            self._seq -= 1
            logger.warning("Failed to upload %s: %s", s3_key, e)

    def _read_all_csv(self) -> bytes:
        """Read the full contents of the combined CSV file as gzipped bytes.

        Used for short runs where no S3 uploads have happened.
        """
        # Refresh the combined CSV before reading
        if self._csv_update_fn is not None:
            try:
                self._csv_update_fn()
            except Exception as e:
                logger.debug("CSV update function failed: %s", e)

        if self._csv_path is None:
            return gzip_compress(b"")
        try:
            with open(self._csv_path, "rb") as fh:
                return gzip_compress(fh.read())
        except FileNotFoundError:
            return gzip_compress(b"")
