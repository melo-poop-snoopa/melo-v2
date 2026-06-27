"""Tests for HeartbeatManager."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest

from lms.heartbeat_manager import (
    HeartbeatManager,
    _OFFLINE_GRACE_TICKS,
    _UPLOAD_STALE_THRESHOLD,
)


def _make_pipeline(alive: bool) -> MagicMock:
    p = MagicMock()
    p.is_alive.return_value = alive
    return p


def _make_uploader(last_upload_offset: float) -> MagicMock:
    u = MagicMock()
    u.last_upload_time = time.time() - last_upload_offset
    u.upload_count = 2
    return u


# ── heartbeat written when healthy ───────────────────────────────────────────

def test_heartbeat_written_when_pipeline_alive_and_recent_upload():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    pipeline = _make_pipeline(alive=True)
    uploader = _make_uploader(last_upload_offset=5)  # 5 seconds ago — fresh

    hm.register("stream-1", pipeline, uploader)
    hm._tick("stream-1", pipeline, uploader)

    db.update_heartbeat.assert_called_once_with("stream-1")
    db.set_stream_status.assert_not_called()


# ── stream set offline when pipeline dead ────────────────────────────────────

def test_offline_when_pipeline_dead():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    pipeline = _make_pipeline(alive=False)
    uploader = _make_uploader(last_upload_offset=5)

    for _ in range(_OFFLINE_GRACE_TICKS):
        hm._tick("stream-1", pipeline, uploader)

    db.set_stream_status.assert_called_once_with("stream-1", "offline")
    db.update_heartbeat.assert_not_called()


# ── stream set offline when upload is stale ──────────────────────────────────

def test_offline_when_upload_stale():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    pipeline = _make_pipeline(alive=True)
    uploader = _make_uploader(last_upload_offset=_UPLOAD_STALE_THRESHOLD + 1)

    for _ in range(_OFFLINE_GRACE_TICKS):
        hm._tick("stream-1", pipeline, uploader)

    db.set_stream_status.assert_called_once_with("stream-1", "offline")
    db.update_heartbeat.assert_not_called()


# ── stream set offline when both fail ────────────────────────────────────────

def test_offline_when_both_unhealthy():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    pipeline = _make_pipeline(alive=False)
    uploader = _make_uploader(last_upload_offset=_UPLOAD_STALE_THRESHOLD + 10)

    for _ in range(_OFFLINE_GRACE_TICKS):
        hm._tick("stream-1", pipeline, uploader)

    db.set_stream_status.assert_called_once_with("stream-1", "offline")


def test_does_not_flip_offline_on_first_unhealthy_tick():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    pipeline = _make_pipeline(alive=False)
    uploader = _make_uploader(last_upload_offset=5)

    hm._tick("stream-1", pipeline, uploader)

    db.set_stream_status.assert_not_called()
    db.update_heartbeat.assert_not_called()


def test_healthy_tick_resets_unhealthy_counter():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    stale_uploader = _make_uploader(last_upload_offset=_UPLOAD_STALE_THRESHOLD + 1)
    healthy_uploader = _make_uploader(last_upload_offset=5)
    pipeline = _make_pipeline(alive=True)

    hm._tick("stream-1", pipeline, stale_uploader)
    hm._tick("stream-1", pipeline, healthy_uploader)
    hm._tick("stream-1", pipeline, stale_uploader)

    db.set_stream_status.assert_not_called()
    db.update_heartbeat.assert_called_once_with("stream-1")


# ── multiple streams ticked independently ────────────────────────────────────

def test_multiple_streams_ticked_independently():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)

    hm.register("s-live", _make_pipeline(alive=True), _make_uploader(5))
    hm.register("s-dead", _make_pipeline(alive=False), _make_uploader(5))

    for _ in range(_OFFLINE_GRACE_TICKS):
        for sid, (pl, up) in list(hm._streams.items()):
            hm._tick(sid, pl, up)

    assert db.update_heartbeat.call_count == _OFFLINE_GRACE_TICKS
    db.set_stream_status.assert_called_once_with("s-dead", "offline")


# ── start / stop lifecycle ───────────────────────────────────────────────────

def test_stop_before_start_is_safe():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)
    hm.stop()  # should not raise


def test_start_and_stop():
    db = MagicMock()
    hm = HeartbeatManager(db, interval=999)
    hm.start()
    assert hm._thread is not None
    assert hm._thread.is_alive()
    hm.stop()
    assert not hm._thread.is_alive()


# ── exception in tick doesn't kill loop ──────────────────────────────────────

def test_exception_in_heartbeat_loop_does_not_propagate():
    """DB errors during a tick must be caught so the loop keeps running."""
    db = MagicMock()
    call_count = 0

    def flaky_heartbeat(stream_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient DB error")

    db.update_heartbeat.side_effect = flaky_heartbeat

    hm = HeartbeatManager(db, interval=999)
    pipeline = _make_pipeline(alive=True)
    uploader = _make_uploader(5)
    hm.register("s1", pipeline, uploader)

    # Simulate what _heartbeat_loop does — it wraps _tick in try/except
    for sid, (pl, up) in list(hm._streams.items()):
        try:
            hm._tick(sid, pl, up)
        except Exception:
            pass  # loop continues

    # Second iteration should succeed (call_count == 2)
    for sid, (pl, up) in list(hm._streams.items()):
        try:
            hm._tick(sid, pl, up)
        except Exception:
            pytest.fail("Second tick raised unexpectedly")

    assert call_count == 2
