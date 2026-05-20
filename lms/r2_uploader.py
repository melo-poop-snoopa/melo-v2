"""
Background uploader: watches a segment directory and pushes new .ts/.m3u8 files to Cloudflare R2.

Uses inotify on Linux (Raspberry Pi) for instant segment detection, falls back to
polling on other platforms (macOS dev).
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import botocore.config
import botocore.exceptions

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.3  # fallback polling (macOS only)
_DEFAULT_CLEANUP_AGE = 300  # 5 minutes

try:
    if sys.platform == "linux":
        from inotify_simple import INotify, flags as inotify_flags
        _HAS_INOTIFY = True
    else:
        _HAS_INOTIFY = False
except ImportError:
    _HAS_INOTIFY = False

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
        cleanup_age: int = _DEFAULT_CLEANUP_AGE,
    ) -> None:
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=botocore.config.Config(
                connect_timeout=5,
                read_timeout=10,
                retries={"max_attempts": 2},
            ),
        )
        self._bucket = bucket
        self._stream_id = stream_id
        self._segment_dir = segment_dir
        self._prefix = f"live-segments/{stream_id}"
        self._cleanup_age = cleanup_age
        self._uploaded: set[str] = set()
        self._pending_r2_deletes: list[str] = []
        self._lost_segments: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_upload_time: float = 0.0
        self._upload_count: int = 0
        self._start_time: float = 0.0
        self._last_summary_time: float = 0.0
        self._uploads_since_summary: int = 0
        self._errors_since_summary: int = 0
        self._upload_pool = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix=f"r2-worker-{stream_id}"
        )

    def start(self) -> None:
        self._clear_remote()
        self._uploaded.clear()
        self._pending_r2_deletes.clear()
        self._lost_segments.clear()
        self._upload_count = 0
        self._start_time = time.time()
        self._last_summary_time = time.time()
        self._uploads_since_summary = 0
        self._errors_since_summary = 0
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
        self._upload_pool.shutdown(wait=False)
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
        if _HAS_INOTIFY:
            self._upload_loop_inotify()
        else:
            self._upload_loop_poll()

    def _upload_loop_inotify(self) -> None:
        inotify = INotify()
        watch_flags = inotify_flags.CLOSE_WRITE | inotify_flags.MOVED_TO
        self._segment_dir.mkdir(parents=True, exist_ok=True)
        wd = inotify.add_watch(str(self._segment_dir), watch_flags)
        logger.info("Using inotify for segment detection (stream %s)", self._stream_id)

        try:
            while not self._stop_event.is_set():
                events = inotify.read(timeout=1000)
                if self._stop_event.is_set():
                    break
                if events:
                    try:
                        self._upload_new_files()
                        self._cleanup_old_segments()
                    except Exception:
                        self._errors_since_summary += 1
                        logger.exception("R2 upload error for stream %s", self._stream_id)
        finally:
            inotify.close()

    def _upload_loop_poll(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._upload_new_files()
                self._cleanup_old_segments()
            except Exception:
                self._errors_since_summary += 1
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

        if segments:
            futures = [self._upload_pool.submit(self._upload_segment, p) for p in segments]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    self._errors_since_summary += 1
                    logger.exception("Segment upload failed for stream %s", self._stream_id)

        for path in playlists:
            self._upload_playlist(path)

    def _upload_segment(self, path: Path) -> None:
        if not self._put_file(path):
            return
        self._uploaded.add(path.name)
        self._upload_count += 1
        self._uploads_since_summary += 1
        self._last_upload_time = time.time()
        logger.debug("Uploaded %s → %s/%s", path.name, self._prefix, path.name)
        self._maybe_emit_summary()

    def _maybe_emit_summary(self) -> None:
        now = time.time()
        if now - self._last_summary_time < 300:
            return
        self._last_summary_time = now
        upload_ago = now - self._last_upload_time if self._last_upload_time else -1
        logger.info(
            "[summary] stream=%s total_uploaded=%d since_last_summary=%d errors=%d "
            "uptime=%.0fm last_upload_ago=%.0fs",
            self._stream_id, self._upload_count, self._uploads_since_summary,
            self._errors_since_summary,
            (now - self._start_time) / 60, upload_ago,
        )
        self._uploads_since_summary = 0
        self._errors_since_summary = 0

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

        trimmed = self._trim_playlist_to_uploaded(raw)
        if trimmed is None:
            logger.debug("Playlist %s: no uploaded segments yet, skipping", path.name)
            return

        key = f"{self._prefix}/{path.name}"
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=trimmed.encode("utf-8"),
                ContentType=_CONTENT_TYPES[".m3u8"],
                CacheControl="no-cache, no-store",
            )
        except Exception:
            logger.exception("Failed to upload playlist %s", path.name)

    def _trim_playlist_to_uploaded(self, raw: str) -> str | None:
        """Rewrite the playlist to only reference segments already uploaded to R2.

        Truncates at the first non-uploaded segment, so the browser never gets
        a 404 for a segment that hasn't been pushed yet. Returns None if no
        segments are uploaded yet.
        """
        lines = raw.splitlines()
        output: list[str] = []
        pending_extinf: str | None = None
        segment_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#EXTINF"):
                pending_extinf = line
                continue
            if stripped.endswith(".ts"):
                if stripped in self._uploaded:
                    if pending_extinf is not None:
                        output.append(pending_extinf)
                    output.append(line)
                    pending_extinf = None
                    segment_count += 1
                else:
                    break
            else:
                output.append(line)

        if segment_count == 0:
            return None
        return "\n".join(output) + "\n"

    def _put_file(self, path: Path) -> bool:
        if not path.exists():
            logger.debug("File %s vanished before upload", path.name)
            return False

        content_type = _CONTENT_TYPES[path.suffix]
        key = f"{self._prefix}/{path.name}"
        extra_args: dict = {"ContentType": content_type}
        if path.suffix == ".ts":
            extra_args["CacheControl"] = "public, max-age=60"

        try:
            self._s3.upload_file(
                str(path),
                self._bucket,
                key,
                ExtraArgs=extra_args,
            )
            return True
        except (FileNotFoundError, OSError, botocore.exceptions.UnseekableStreamError):
            logger.debug("File %s vanished during upload", path.name)
            return False

    def _cleanup_old_segments(self) -> None:
        if not self._segment_dir.exists():
            return

        now = time.time()
        current_files: set[str] = set()
        for path in self._segment_dir.iterdir():
            current_files.add(path.name)
            try:
                stale = path.suffix == ".ts" and (now - path.stat().st_mtime) > self._cleanup_age
            except FileNotFoundError:
                continue
            if stale:
                path.unlink(missing_ok=True)
                if path.name in self._uploaded:
                    self._uploaded.discard(path.name)
                    self._pending_r2_deletes.append(path.name)
                logger.info("Deleted stale local segment %s", path.name)

        stale_names = self._uploaded - current_files
        if stale_names:
            self._pending_r2_deletes.extend(stale_names)
            self._uploaded -= stale_names

        self._flush_r2_deletes()

    def _flush_r2_deletes(self) -> None:
        if not self._pending_r2_deletes:
            return
        keys = [f"{self._prefix}/{name}" for name in self._pending_r2_deletes]
        self._pending_r2_deletes.clear()
        self._upload_pool.submit(self._delete_r2_objects, keys)

    def _delete_r2_objects(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            batch = keys[i : i + 1000]
            try:
                self._s3.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": k} for k in batch]},
                )
                logger.info(
                    "Deleted %d R2 segment(s) for stream %s",
                    len(batch),
                    self._stream_id,
                )
            except Exception:
                logger.exception(
                    "Failed to delete %d R2 segment(s) for stream %s",
                    len(batch),
                    self._stream_id,
                )
