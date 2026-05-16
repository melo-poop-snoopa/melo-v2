from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lms.hls_pipeline import HLSPipeline


@pytest.fixture
def pipeline(tmp_segments: Path) -> HLSPipeline:
    return HLSPipeline(
        stream_id="test-stream",
        rtsp_url="rtsp://admin:pass@192.168.1.10/stream",
        output_dir=tmp_segments,
        segment_duration=4,
        playlist_size=5,
    )


def test_build_ffmpeg_cmd(pipeline: HLSPipeline) -> None:
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        cmd = pipeline._build_ffmpeg_cmd()

    assert cmd[0] == "/usr/bin/ffmpeg"
    assert "-rtsp_transport" in cmd
    assert "tcp" in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-an" in cmd
    assert "-f" in cmd
    assert "hls" in cmd
    assert "-hls_time" in cmd
    assert "4" in cmd
    assert "-hls_list_size" in cmd
    assert "5" in cmd
    assert "-hls_flags" in cmd
    assert "append_list+delete_segments" in cmd

    assert cmd[-1].endswith("stream.m3u8")
    seg_idx = cmd.index("-hls_segment_filename") + 1
    assert "seg_%05d.ts" in cmd[seg_idx]


def test_build_ffmpeg_cmd_missing_ffmpeg(pipeline: HLSPipeline) -> None:
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="FFmpeg not found"):
            pipeline._build_ffmpeg_cmd()


@patch("lms.hls_pipeline.HLSPipeline._build_ffmpeg_cmd")
@patch("subprocess.Popen")
def test_start_spawns_process(
    mock_popen: MagicMock, mock_cmd: MagicMock, pipeline: HLSPipeline
) -> None:
    mock_cmd.return_value = ["ffmpeg", "-i", "test"]
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.side_effect = lambda **_kw: time.sleep(10)
    mock_popen.return_value = mock_proc

    pipeline.start()

    mock_popen.assert_called_once()
    assert pipeline.is_alive()

    pipeline.stop()


@patch("lms.hls_pipeline.HLSPipeline._build_ffmpeg_cmd")
@patch("subprocess.Popen")
def test_stop_terminates_process(
    mock_popen: MagicMock, mock_cmd: MagicMock, pipeline: HLSPipeline
) -> None:
    mock_cmd.return_value = ["ffmpeg", "-i", "test"]
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.wait.side_effect = [None, None]
    mock_popen.return_value = mock_proc

    pipeline.start()
    pipeline.stop()

    mock_proc.terminate.assert_called_once()


def test_is_alive_no_process(pipeline: HLSPipeline) -> None:
    assert not pipeline.is_alive()


def test_last_segment_time_empty(pipeline: HLSPipeline) -> None:
    assert pipeline.last_segment_time is None


def test_last_segment_time_with_files(pipeline: HLSPipeline, tmp_segments: Path) -> None:
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00")
    time.sleep(0.05)
    (tmp_segments / "seg_00002.ts").write_bytes(b"\x00")

    result = pipeline.last_segment_time
    assert result is not None
    assert result == (tmp_segments / "seg_00002.ts").stat().st_mtime
