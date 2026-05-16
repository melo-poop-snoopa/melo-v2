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
        ExtraArgs={"ContentType": "video/MP2T", "CacheControl": "public, max-age=60"},
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
    mock_s3_client.put_object.reset_mock()

    uploader._upload_new_files()
    m3u8_calls = [
        c for c in mock_s3_client.put_object.call_args_list
        if str(c).find(".m3u8") != -1
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

    call_args = mock_s3_client.put_object.call_args
    assert call_args[1]["ContentType"] == "application/vnd.apple.mpegurl"


def test_last_upload_time_updated(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    initial_time = uploader.last_upload_time
    assert initial_time == 0.0

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


def test_playlist_deferred_when_segments_pending_on_disk(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """Playlist should NOT be uploaded if it references segments on disk but not yet uploaded."""
    m3u8_content = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
        "#EXTINF:2.0,\nseg_00003.ts\n"
    )
    (tmp_segments / "stream.m3u8").write_text(m3u8_content)
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    (tmp_segments / "seg_00002.ts").write_bytes(b"\x00" * 100)
    (tmp_segments / "seg_00003.ts").write_bytes(b"\x00" * 100)

    # Simulate only seg_00001 being discovered by making upload_file fail for 2 and 3
    original_upload = mock_s3_client.upload_file
    call_count = {"n": 0}

    def fail_after_first(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise FileNotFoundError("simulated")
        return original_upload(*args, **kwargs)

    mock_s3_client.upload_file.side_effect = fail_after_first

    uploader._upload_new_files()

    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 0


def test_playlist_uploaded_when_all_segments_present(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """Playlist should be uploaded once all referenced segments have been uploaded."""
    m3u8_content = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
    )
    (tmp_segments / "stream.m3u8").write_text(m3u8_content)
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    (tmp_segments / "seg_00002.ts").write_bytes(b"\x00" * 100)

    uploader._upload_new_files()

    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 1


def test_playlist_deferred_then_uploaded_next_cycle(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """Simulate the race: first cycle defers (segment on disk), second cycle uploads."""
    m3u8_content = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
    )
    (tmp_segments / "stream.m3u8").write_text(m3u8_content)
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    # seg_00002 exists on disk but upload fails — simulates pending segment
    (tmp_segments / "seg_00002.ts").write_bytes(b"\x00" * 100)

    original_upload = mock_s3_client.upload_file
    call_count = {"n": 0}

    def fail_after_first(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise FileNotFoundError("simulated")
        return original_upload(*args, **kwargs)

    mock_s3_client.upload_file.side_effect = fail_after_first

    uploader._upload_new_files()
    assert all("m3u8" not in str(c) for c in mock_s3_client.put_object.call_args_list)

    mock_s3_client.upload_file.side_effect = None
    mock_s3_client.put_object.reset_mock()

    uploader._upload_new_files()
    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 1


def test_parse_m3u8_segments() -> None:
    m3u8 = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
        "#EXTINF:2.0,\nseg_00003.ts\n"
    )
    result = R2Uploader._parse_m3u8_segments(m3u8)
    assert result == {"seg_00001.ts", "seg_00002.ts", "seg_00003.ts"}


def test_parse_m3u8_segments_empty() -> None:
    assert R2Uploader._parse_m3u8_segments("#EXTM3U\n") == set()


def test_upload_skips_file_deleted_before_upload(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """File gone before upload_file() is called — caught by exists() check."""
    seg = tmp_segments / "seg_00001.ts"
    seg.write_bytes(b"\x00" * 100)
    seg.unlink()

    uploader._upload_new_files()

    mock_s3_client.upload_file.assert_not_called()


def test_playlist_uploaded_when_segments_lost_from_disk(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """Playlist should be uploaded if missing segments are gone from disk (lost)."""
    m3u8_content = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
    )
    (tmp_segments / "stream.m3u8").write_text(m3u8_content)
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    # seg_00002.ts intentionally NOT on disk — simulates FFmpeg deleting it

    uploader._upload_new_files()

    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 1
    assert "seg_00002.ts" in uploader._lost_segments


def test_lost_segments_tracked_across_cycles(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """Lost segments should not block subsequent playlist uploads."""
    m3u8_content = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
    )
    (tmp_segments / "stream.m3u8").write_text(m3u8_content)
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)

    uploader._upload_new_files()
    assert "seg_00002.ts" in uploader._lost_segments

    mock_s3_client.put_object.reset_mock()

    # Second cycle: same playlist, lost segment already tracked
    uploader._upload_new_files()

    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 1


def test_playlist_deferred_with_mix_of_pending_and_lost(
    uploader: R2Uploader, tmp_segments: Path, mock_s3_client: MagicMock
) -> None:
    """Playlist deferred if any segment is pending on disk, even if others are lost."""
    m3u8_content = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXTINF:2.0,\nseg_00001.ts\n#EXTINF:2.0,\nseg_00002.ts\n"
        "#EXTINF:2.0,\nseg_00003.ts\n"
    )
    (tmp_segments / "stream.m3u8").write_text(m3u8_content)
    (tmp_segments / "seg_00001.ts").write_bytes(b"\x00" * 100)
    # seg_00002.ts on disk but not uploaded (pending)
    (tmp_segments / "seg_00002.ts").write_bytes(b"\x00" * 100)
    # seg_00003.ts NOT on disk (lost)

    # Only upload seg_00001 by making upload_file fail for seg_00002
    original_upload = mock_s3_client.upload_file
    call_count = {"n": 0}

    def fail_after_first(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise FileNotFoundError("simulated")
        return original_upload(*args, **kwargs)

    mock_s3_client.upload_file.side_effect = fail_after_first

    uploader._upload_new_files()

    # seg_00003 is lost, seg_00002 is pending → playlist deferred
    assert "seg_00003.ts" in uploader._lost_segments
    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 0

    # Now upload seg_00002 successfully
    mock_s3_client.upload_file.side_effect = None
    mock_s3_client.put_object.reset_mock()

    uploader._upload_new_files()

    m3u8_puts = [
        c for c in mock_s3_client.put_object.call_args_list
        if "m3u8" in str(c)
    ]
    assert len(m3u8_puts) == 1
