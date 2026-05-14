from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import botocore.exceptions
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
    initial_time = uploader.last_upload_time
    assert initial_time > 0

    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    uploader._upload_new_files()

    assert uploader.last_upload_time > initial_time


def test_upload_skips_vanished_file(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """File deleted between iterdir() and upload_file() should not crash."""
    seg = tmp_segments / "seg_00001.ts"
    seg.write_bytes(b"\x00" * 100)

    def delete_then_raise(*args, **kwargs):
        seg.unlink(missing_ok=True)
        raise FileNotFoundError(str(seg))

    mock_s3_client.upload_file.side_effect = delete_then_raise

    uploader._upload_new_files()  # should not raise


def test_upload_handles_unseekable_stream_error(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """boto3 wraps FileNotFoundError as UnseekableStreamError during retries."""
    seg = tmp_segments / "seg_00001.ts"
    seg.write_bytes(b"\x00" * 100)

    mock_s3_client.upload_file.side_effect = botocore.exceptions.UnseekableStreamError(
        stream_object="fake-stream"
    )

    uploader._upload_new_files()  # should not raise


def test_upload_skips_file_deleted_before_upload(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """File gone before upload_file() is called — caught by exists() check."""
    seg = tmp_segments / "seg_00001.ts"
    seg.write_bytes(b"\x00" * 100)
    seg.unlink()

    uploader._upload_new_files()

    mock_s3_client.upload_file.assert_not_called()
