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

_POLL_INTERVAL = 0.5
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
        self._brb_segments: set[str] = set()
        self._lost_segments: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_upload_time: float = 0.0
        self._upload_count: int = 0
        self._privacy_filter = privacy_filter

    def start(self) -> None:
        self._clear_remote()
        self._uploaded.clear()
        self._brb_segments.clear()
        self._lost_segments.clear()
        self._upload_count = 0
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

    @property
    def upload_count(self) -> int:
        return self._upload_count

    def _clear_remote(self) -> None:
        try:
            resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=f"{self._prefix}/")
            objects = [{"Key": obj["Key"]} for obj in resp.get("Contents", [])]
            if objects:
                self._s3.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
                logger.info("Cleared %d stale R2 objects for stream %s", len(objects), self._stream_id)
        except Exception:
            logger.exception("Failed to clear remote segments for stream %s", self._stream_id)

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

        segments: list[Path] = []
        playlists: list[Path] = []
        for path in self._segment_dir.iterdir():
            if path.suffix == ".ts" and path.name not in self._uploaded:
                segments.append(path)
            elif path.suffix == ".m3u8":
                playlists.append(path)

        for path in segments:
            self._upload_segment(path)

        for path in playlists:
            self._upload_playlist(path)

    def _upload_segment(self, path: Path) -> None:
        content_type = _CONTENT_TYPES[".ts"]
        key = f"{self._prefix}/{path.name}"

        if self._privacy_filter and self._privacy_filter.is_human_detected():
            brb = self._privacy_filter.brb_segment
            if brb:
                self._s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=brb,
                    ContentType=content_type,
                )
                self._uploaded.add(path.name)
                self._brb_segments.add(path.name)
                self._upload_count += 1
                self._last_upload_time = time.time()
                logger.debug("Uploaded BRB segment in place of %s", path.name)
                return

        if not self._put_file(path):
            return
        self._uploaded.add(path.name)
        self._brb_segments.discard(path.name)
        self._upload_count += 1
        self._last_upload_time = time.time()
        logger.info("Uploaded %s → %s", path.name, key)

    @staticmethod
    def _parse_m3u8_segments(m3u8_text: str) -> set[str]:
        return {
            line.strip()
            for line in m3u8_text.splitlines()
            if line.strip() and not line.startswith("#") and line.strip().endswith(".ts")
        }

    def _upload_playlist(self, path: Path) -> None:
        try:
            raw = path.read_text()
        except (FileNotFoundError, OSError):
            logger.debug("Playlist %s vanished before upload", path.name)
            return

        referenced = self._parse_m3u8_segments(raw)
        not_uploaded = referenced - self._uploaded - self._lost_segments
        if not_uploaded:
            pending = {s for s in not_uploaded if (self._segment_dir / s).exists()}
            lost = not_uploaded - pending

            if lost:
                logger.warning(
                    "Lost %d segment(s) for %s (deleted before upload): %s",
                    len(lost), self._stream_id, ", ".join(sorted(lost)),
                )
                self._lost_segments.update(lost)

            if pending:
                logger.debug(
                    "Deferring playlist %s: %d segment(s) pending upload: %s",
                    path.name, len(pending), ", ".join(sorted(pending)),
                )
                return

        key = f"{self._prefix}/{path.name}"

        m3u8_cache = "no-cache, no-store"

        if not self._brb_segments:
            try:
                self._s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=raw.encode("utf-8"),
                    ContentType=_CONTENT_TYPES[".m3u8"],
                    CacheControl=m3u8_cache,
                )
            except Exception:
                logger.exception("Failed to upload playlist %s", path.name)
            return

        lines = raw.splitlines()
        output: list[str] = []
        prev_was_brb: bool | None = None
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("#EXTINF") and i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                seg_name = lines[i + 1].strip()
                is_brb = seg_name in self._brb_segments
                if prev_was_brb is not None and is_brb != prev_was_brb:
                    output.append("#EXT-X-DISCONTINUITY")
                prev_was_brb = is_brb
                output.append(line)
                output.append(lines[i + 1])
                i += 2
                continue
            output.append(line)
            i += 1

        modified = "\n".join(output) + "\n"
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=modified.encode("utf-8"),
                ContentType=_CONTENT_TYPES[".m3u8"],
                CacheControl=m3u8_cache,
            )
        except Exception:
            logger.exception("Failed to upload playlist %s", path.name)

    def _put_file(self, path: Path) -> bool:
        if not path.exists():
            logger.debug("File %s vanished before upload", path.name)
            return False

        content_type = _CONTENT_TYPES[path.suffix]
        key = f"{self._prefix}/{path.name}"

        try:
            self._s3.upload_file(
                str(path),
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
            return True
        except (FileNotFoundError, OSError, botocore.exceptions.UnseekableStreamError):
            logger.debug("File %s vanished during upload", path.name)
            return False

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
                self._brb_segments.discard(path.name)
                logger.info("Deleted stale local segment %s", path.name)
