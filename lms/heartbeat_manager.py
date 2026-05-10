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

from lms.database import MeloDB
from lms.hls_pipeline import HLSPipeline
from lms.r2_uploader import R2Uploader

logger = logging.getLogger(__name__)

_UPLOAD_STALE_THRESHOLD = 30  # seconds


class HeartbeatManager:
    def __init__(self, db: MeloDB, interval: int = 15) -> None:
        self._db = db
        self._interval = interval
        self._streams: dict[str, tuple[HLSPipeline, R2Uploader]] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, stream_id: str, pipeline: HLSPipeline, uploader: R2Uploader) -> None:
        self._streams[stream_id] = (pipeline, uploader)

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
            for stream_id, (pipeline, uploader) in list(self._streams.items()):
                try:
                    self._tick(stream_id, pipeline, uploader)
                except Exception:
                    logger.exception("Heartbeat error for stream %s", stream_id)
            self._stop_event.wait(self._interval)

    def _tick(self, stream_id: str, pipeline: HLSPipeline, uploader: R2Uploader) -> None:
        alive = pipeline.is_alive()
        recent_upload = (time.time() - uploader.last_upload_time) < _UPLOAD_STALE_THRESHOLD

        if alive and recent_upload:
            self._db.update_heartbeat(stream_id)
        else:
            logger.warning(
                "Stream %s unhealthy (alive=%s recent_upload=%s) → offline",
                stream_id, alive, recent_upload,
            )
            self._db.set_stream_status(stream_id, "offline")
