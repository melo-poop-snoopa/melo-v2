"""Tests for PrivacyFilter."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from lms.privacy_filter import PrivacyFilter


# ── is_human_detected flag ────────────────────────────────────────────────────

def test_human_not_detected_by_default():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    assert pf.is_human_detected() is False


def test_detection_flag_set_on_person_above_threshold():
    pf = PrivacyFilter("s1", "rtsp://localhost/test", confidence_threshold=0.5)
    with pf._lock:
        pf._human_detected = True
    assert pf.is_human_detected() is True


def test_detection_flag_cleared_after_person_leaves():
    pf = PrivacyFilter("s1", "rtsp://localhost/test", confidence_threshold=0.5)
    with pf._lock:
        pf._human_detected = True
    assert pf.is_human_detected() is True
    with pf._lock:
        pf._human_detected = False
    assert pf.is_human_detected() is False


# ── confidence threshold filtering ───────────────────────────────────────────

def test_confidence_below_threshold_not_detected():
    """Person box with conf=0.3 should not trigger when threshold=0.5."""
    pf = PrivacyFilter("s1", "rtsp://localhost/test", confidence_threshold=0.5)

    mock_box = MagicMock()
    mock_box.conf = 0.3

    mock_result = MagicMock()
    mock_result.boxes = [mock_box]

    detected = any(
        float(box.conf) >= pf._confidence_threshold
        for r in [mock_result]
        for box in r.boxes
    )
    assert detected is False


def test_confidence_at_threshold_is_detected():
    """Exactly at threshold should count as detected."""
    pf = PrivacyFilter("s1", "rtsp://localhost/test", confidence_threshold=0.5)

    mock_box = MagicMock()
    mock_box.conf = 0.5

    mock_result = MagicMock()
    mock_result.boxes = [mock_box]

    detected = any(
        float(box.conf) >= pf._confidence_threshold
        for r in [mock_result]
        for box in r.boxes
    )
    assert detected is True


# ── stop/start lifecycle ──────────────────────────────────────────────────────

def test_stop_before_start_is_safe():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    pf.stop()  # should not raise


def test_detection_loop_exits_on_stop():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    pf._model = MagicMock()

    with patch.object(pf, "_run_detection", side_effect=Exception("connection failed")):
        pf._stop_event.clear()
        t = threading.Thread(target=pf._detection_loop)
        t.start()
        pf._stop_event.set()
        t.join(timeout=2)
        assert not t.is_alive()
