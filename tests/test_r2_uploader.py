from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lms.r2_uploader import R2Uploader


@pytest.fixture
def uploader(tmp_segments: Path, mock_s3_client: MagicMock) -> R2Uploader:
    with patch("boto3.client", return_value=mock_s3_client):
        up = R2Uploader(
            bucket="test-bucket",
            endpoint="https://test.r2.cloudflarestorage.com",
            access_key_id="test-key",
            secret_access_key="test-secret",
            stream_id="test-stream",
            segment_dir=tmp_segments,
        )
    return up


def test_upload_new_segments(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)

    uploader._upload_new_files()

    mock_s3_client.upload_file.assert_called_once_with(
        str(tmp_segments / "seg_00001.ts"),
        "test-bucket",
        "live-segments/test-stream/seg_00001.ts",
        ExtraArgs={"ContentType": "video/MP2T"},
    )
    assert uploader.last_upload_time > 0


def test_no_duplicate_uploads(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)

    uploader._upload_new_files()
    mock_s3_client.upload_file.reset_mock()

    uploader._upload_new_files()
    # .ts should not be re-uploaded
    ts_calls = [
        c for c in mock_s3_client.upload_file.call_args_list
        if c[0][2].endswith(".ts")
    ]
    assert len(ts_calls) == 0


def test_m3u8_always_reuploaded(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    (tmp_segments / "stream.m3u8").write_text("#EXTM3U\n")

    uploader._upload_new_files()
    mock_s3_client.upload_file.reset_mock()

    uploader._upload_new_files()
    m3u8_calls = [
        c for c in mock_s3_client.upload_file.call_args_list
        if c[0][2].endswith(".m3u8")
    ]
    assert len(m3u8_calls) == 1


def test_cleanup_old_segments(uploader: R2Uploader, tmp_segments: Path) -> None:
    old_file = tmp_segments / "seg_00001.ts"
    old_file.write_bytes(b"\x00" * 100)

    import os
    old_time = time.time() - 600
    os.utime(old_file, (old_time, old_time))

    uploader._cleanup_old_segments()

    assert not old_file.exists()


def test_cleanup_keeps_recent_segments(uploader: R2Uploader, tmp_segments: Path) -> None:
    recent_file = tmp_segments / "seg_00002.ts"
    recent_file.write_bytes(b"\x00" * 100)

    uploader._cleanup_old_segments()

    assert recent_file.exists()


def test_content_type_ts(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)

    uploader._upload_new_files()

    call_args = mock_s3_client.upload_file.call_args
    assert call_args[1]["ExtraArgs"]["ContentType"] == "video/MP2T"


def test_content_type_m3u8(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    (tmp_segments / "stream.m3u8").write_text("#EXTM3U\n")

    uploader._upload_new_files()

    call_args = mock_s3_client.upload_file.call_args
    assert call_args[1]["ExtraArgs"]["ContentType"] == "application/vnd.apple.mpegurl"


def test_last_upload_time_updated(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    assert uploader.last_upload_time == 0.0

    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    uploader._upload_new_files()

    assert uploader.last_upload_time > 0
