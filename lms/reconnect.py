"""
Reconnection logic with exponential backoff for HLS pipeline crashes.

When FFmpeg exits unexpectedly the watchdog calls reconnect() to get a fresh
RTSP URL (ONVIF may return a different token each time) and restart the
pipeline. Backoff: 2s base, doubles each attempt, caps at 30s.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_BASE_DELAY = 2.0
_MAX_DELAY = 60.0
_MAX_ATTEMPTS = 0  # 0 = unlimited; retries until stop_event is set


def reconnect_with_backoff(
    stream_id: str,
    attempt_fn: Callable[[], bool],
    stop_fn: Callable[[], bool],
    on_failure: Callable[[], None] | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    """
    Call attempt_fn() repeatedly with exponential backoff until it returns True
    (success) or stop_fn() returns True (shutdown requested).

    Retries indefinitely (stop_event / stop_fn is the only exit).
    """
    delay = _BASE_DELAY
    attempt = 0
    while True:
        attempt += 1
        if stop_fn():
            logger.info("Stream %s: reconnect aborted (shutdown)", stream_id)
            return

        logger.info(
            "Stream %s: reconnect attempt %d (delay=%.0fs)",
            stream_id, attempt, delay,
        )

        try:
            if attempt_fn():
                logger.info("Stream %s: reconnected after %d attempt(s)", stream_id, attempt)
                return
        except Exception:
            logger.exception("Stream %s: reconnect attempt %d raised", stream_id, attempt)

        if stop_fn():
            return

        if stop_event:
            stop_event.wait(delay)
        else:
            import time
            time.sleep(delay)
        delay = min(delay * 2, _MAX_DELAY)
