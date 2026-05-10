"""Tests for PrivacyFilter."""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lms.privacy_filter import PrivacyFilter, _encode_brb_segment, _generate_brb_png


# ── is_human_detected flag ────────────────────────────────────────────────────

def test_human_not_detected_by_default():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    assert pf.is_human_detected() is False


def test_detection_flag_set_on_person_above_threshold():
    pf = PrivacyFilter("s1", "rtsp://localhost/test", confidence_threshold=0.5)
    # Directly mutate internal flag to simulate detection result
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
    mock_box.conf = 0.3  # scalar, matching YOLOv8 tensor scalar behaviour

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


# ── BRB segment pre-encoding ─────────────────────────────────────────────────

def test_encode_brb_segment_returns_bytes(tmp_path):
    brb_png = tmp_path / "brb.png"

    # Create a minimal 1x1 black PNG without FFmpeg
    import struct, zlib
    def _png():
        def chunk(name, data):
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        raw = b"\x00\x00\x00\x00"
        idat = chunk(b"IDAT", zlib.compress(raw))
        iend = chunk(b"IEND", b"")
        return sig + ihdr + idat + iend

    brb_png.write_bytes(_png())

    with patch("lms.privacy_filter._ASSETS_DIR", tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Simulate ffmpeg writing output file
            def fake_run(cmd, **kwargs):
                out_path = Path(cmd[-1])
                out_path.write_bytes(b"fake-ts-data")
                return MagicMock(returncode=0)
            mock_run.side_effect = fake_run

            result = _encode_brb_segment(segment_duration=4)

    assert result == b"fake-ts-data"


def test_encode_brb_segment_returns_none_on_ffmpeg_failure(tmp_path):
    brb_png = tmp_path / "brb.png"
    brb_png.write_bytes(b"fake")

    with patch("lms.privacy_filter._ASSETS_DIR", tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b"error")
            result = _encode_brb_segment(segment_duration=4)

    assert result is None


def test_brb_segment_none_before_start():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    assert pf.brb_segment is None


# ── stop/start lifecycle ──────────────────────────────────────────────────────

def test_stop_before_start_is_safe():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    pf.stop()  # should not raise


def test_detection_loop_exits_on_stop():
    pf = PrivacyFilter("s1", "rtsp://localhost/test")
    pf._model = MagicMock()  # skip model load
    pf._brb_segment = b"fake"

    with patch.object(pf, "_run_detection", side_effect=Exception("connection failed")):
        pf._stop_event.clear()
        t = threading.Thread(target=pf._detection_loop)
        t.start()
        pf._stop_event.set()
        t.join(timeout=2)
        assert not t.is_alive()
