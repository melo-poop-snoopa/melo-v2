"""
SegmentCleanup: periodic local .ts file deletion to prevent disk exhaustion.

Single thread walks all registered segment directories every N seconds and
deletes .ts files older than max_age seconds. Prevents the Pi's SD card
from filling up with stale segments that R2Uploader already uploaded.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MAX_AGE = 300   # 5 minutes
_DEFAULT_INTERVAL = 60   # 1 minute


class SegmentCleanup:
    def __init__(self, max_age: int = _DEFAULT_MAX_AGE, interval: int = _DEFAULT_INTERVAL) -> None:
        self._max_age = max_age
        self._interval = interval
        self._dirs: list[Path] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, segment_dir: Path) -> None:
        with self._lock:
            self._dirs.append(segment_dir)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="segment-cleanup"
        )
        self._thread.start()
        logger.info("SegmentCleanup started (max_age=%ds, interval=%ds)", self._max_age, self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 5)

    def _cleanup_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                dirs = list(self._dirs)
            for d in dirs:
                try:
                    self._clean_dir(d)
                except Exception:
                    logger.exception("Cleanup error for %s", d)
            self._stop_event.wait(self._interval)

    def _clean_dir(self, segment_dir: Path) -> None:
        if not segment_dir.exists():
            return
        now = time.time()
        deleted = 0
        for path in segment_dir.iterdir():
            if path.suffix == ".ts" and (now - path.stat().st_mtime) > self._max_age:
                path.unlink(missing_ok=True)
                deleted += 1
        if deleted:
            logger.info("Cleaned %d stale segment(s) from %s", deleted, segment_dir)
