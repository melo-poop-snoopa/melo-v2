"""
Background uploader: watches a segment directory and pushes new .ts/.m3u8 files to Cloudflare R2.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import boto3
import botocore.exceptions

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.0
_CLEANUP_AGE = 300  # 5 minutes

_CONTENT_TYPES = {
    ".ts": "video/MP2T",
    ".m3u8": "application/vnd.apple.mpegurl",
}


class R2Uploader:
    def __init__(
        self,
        bucket: str,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        stream_id: str,
        segment_dir: Path,
        privacy_filter=None,
    ) -> None:
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        self._bucket = bucket
        self._stream_id = stream_id
        self._segment_dir = segment_dir
        self._prefix = f"live-segments/{stream_id}"
        self._uploaded: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_upload_time: float = time.time()
        self._privacy_filter = privacy_filter

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._upload_loop, daemon=True, name=f"r2-upload-{self._stream_id}"
        )
        self._thread.start()
        logger.info("R2 uploader started for stream %s", self._stream_id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("R2 uploader stopped for stream %s", self._stream_id)

    @property
    def last_upload_time(self) -> float:
        return self._last_upload_time

    def _upload_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._upload_new_files()
                self._cleanup_old_segments()
            except Exception:
                logger.exception("R2 upload error for stream %s", self._stream_id)
            self._stop_event.wait(_POLL_INTERVAL)

    def _upload_new_files(self) -> None:
        if not self._segment_dir.exists():
            return

        for path in self._segment_dir.iterdir():
            if path.suffix not in _CONTENT_TYPES:
                continue

            # .m3u8 playlist changes every cycle — always re-upload
            if path.suffix == ".ts" and path.name in self._uploaded:
                continue

            content_type = _CONTENT_TYPES[path.suffix]
            key = f"{self._prefix}/{path.name}"

            if path.suffix == ".ts" and self._privacy_filter and self._privacy_filter.is_human_detected():
                brb = self._privacy_filter.brb_segment
                if brb:
                    self._s3.put_object(
                        Bucket=self._bucket,
                        Key=key,
                        Body=brb,
                        ContentType=content_type,
                    )
                    self._uploaded.add(path.name)
                    self._last_upload_time = time.time()
                    logger.debug("Uploaded BRB segment in place of %s", path.name)
                    continue

            if not path.exists():
                logger.debug("Segment %s vanished before upload", path.name)
                continue

            try:
                self._s3.upload_file(
                    str(path),
                    self._bucket,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )
            except (FileNotFoundError, OSError, botocore.exceptions.UnseekableStreamError):
                logger.debug("Segment %s vanished during upload", path.name)
                continue

            if path.suffix == ".ts":
                self._uploaded.add(path.name)
                logger.info("Uploaded %s → %s", path.name, key)

            self._last_upload_time = time.time()

    def _cleanup_old_segments(self) -> None:
        if not self._segment_dir.exists():
            return

        now = time.time()
        for path in self._segment_dir.iterdir():
            try:
                stale = path.suffix == ".ts" and (now - path.stat().st_mtime) > _CLEANUP_AGE
            except FileNotFoundError:
                continue
            if stale:
                path.unlink(missing_ok=True)
                self._uploaded.discard(path.name)
