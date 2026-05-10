"""
Reconnection logic with exponential backoff for HLS pipeline crashes.

When FFmpeg exits unexpectedly the watchdog calls reconnect() to get a fresh
RTSP URL (ONVIF may return a different token each time) and restart the
pipeline. Backoff: 2s base, doubles each attempt, caps at 30s.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

_BASE_DELAY = 2.0
_MAX_DELAY = 30.0
_MAX_ATTEMPTS = 20


def reconnect_with_backoff(
    stream_id: str,
    attempt_fn: Callable[[], bool],
    stop_fn: Callable[[], bool],
    on_failure: Callable[[], None] | None = None,
) -> None:
    """
    Call attempt_fn() repeatedly with exponential backoff until it returns True
    (success) or stop_fn() returns True (shutdown requested).

    attempt_fn: returns True on successful reconnect, False to retry
    stop_fn:    returns True when the caller wants to abort (e.g. shutdown)
    on_failure: called once after MAX_ATTEMPTS exhausted without success
    """
    delay = _BASE_DELAY
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if stop_fn():
            logger.info("Stream %s: reconnect aborted (shutdown)", stream_id)
            return

        logger.info(
            "Stream %s: reconnect attempt %d/%d (delay=%.0fs)",
            stream_id, attempt, _MAX_ATTEMPTS, delay,
        )

        try:
            if attempt_fn():
                logger.info("Stream %s: reconnected after %d attempt(s)", stream_id, attempt)
                return
        except Exception:
            logger.exception("Stream %s: reconnect attempt %d raised", stream_id, attempt)

        if stop_fn():
            return

        time.sleep(delay)
        delay = min(delay * 2, _MAX_DELAY)

    logger.error("Stream %s: exhausted %d reconnect attempts", stream_id, _MAX_ATTEMPTS)
    if on_failure:
        on_failure()
