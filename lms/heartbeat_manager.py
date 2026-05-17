"""
HeartbeatManager: writes stream liveness to Supabase every N seconds.

Only marks a stream live when both the HLS pipeline process is running AND
the R2 uploader successfully pushed a segment within the last 30 seconds.
If either check fails, the stream is set offline immediately.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from lms.database import MeloDB
from lms.hls_pipeline import HLSPipeline
from lms.r2_uploader import R2Uploader

if TYPE_CHECKING:
    from lms.privacy_filter import PrivacyFilter

logger = logging.getLogger(__name__)

_UPLOAD_STALE_THRESHOLD = 30  # seconds
_MIN_SEGMENTS_FOR_LIVE = 2


class HeartbeatManager:
    def __init__(self, db: MeloDB, interval: int = 15) -> None:
        self._db = db
        self._interval = interval
        self._streams: dict[str, tuple[HLSPipeline, R2Uploader, PrivacyFilter | None]] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick_count: int = 0
        self._last_status: dict[str, bool] = {}
        self._start_time: float = time.time()
        self._summary_interval_ticks: int = max(1, 300 // interval)

    def register(
        self,
        stream_id: str,
        pipeline: HLSPipeline,
        uploader: R2Uploader,
        privacy_filter: PrivacyFilter | None = None,
    ) -> None:
        self._streams[stream_id] = (pipeline, uploader, privacy_filter)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="heartbeat-manager"
        )
        self._thread.start()
        logger.info("HeartbeatManager started (%d stream(s))", len(self._streams))

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 5)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            for stream_id, (pipeline, uploader, pf) in list(self._streams.items()):
                try:
                    self._tick(stream_id, pipeline, uploader, pf)
                except Exception:
                    logger.exception("Heartbeat error for stream %s", stream_id)
            self._stop_event.wait(self._interval)

    def _tick(
        self,
        stream_id: str,
        pipeline: HLSPipeline,
        uploader: R2Uploader,
        privacy_filter: PrivacyFilter | None,
    ) -> None:
        alive = pipeline.is_alive()
        recent_upload = (time.time() - uploader.last_upload_time) < _UPLOAD_STALE_THRESHOLD
        enough_segments = uploader.upload_count >= _MIN_SEGMENTS_FOR_LIVE
        healthy = alive and recent_upload and enough_segments

        was_healthy = self._last_status.get(stream_id)
        if was_healthy is not None and healthy != was_healthy:
            logger.warning(
                "[transition] stream=%s %s → %s (alive=%s upload_recent=%s segments=%d)",
                stream_id,
                "healthy" if was_healthy else "unhealthy",
                "healthy" if healthy else "unhealthy",
                alive, recent_upload, uploader.upload_count,
            )
        self._last_status[stream_id] = healthy

        if healthy:
            privacy_active = bool(privacy_filter and privacy_filter.is_human_detected())
            self._db.update_heartbeat(stream_id, privacy_active=privacy_active)
        else:
            logger.warning(
                "Stream %s unhealthy (alive=%s recent_upload=%s segments=%d) → offline",
                stream_id, alive, recent_upload, uploader.upload_count,
            )
            self._db.set_stream_status(stream_id, "offline")

        self._tick_count += 1
        if self._tick_count % self._summary_interval_ticks == 0:
            upload_ago = time.time() - uploader.last_upload_time if uploader.last_upload_time else -1
            logger.info(
                "[summary] stream=%s uptime=%.0fm healthy=%s segments=%d last_upload_ago=%.0fs",
                stream_id,
                (time.time() - self._start_time) / 60,
                healthy,
                uploader.upload_count,
                upload_ago,
            )
