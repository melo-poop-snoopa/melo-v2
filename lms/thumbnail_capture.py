"""
ThumbnailCapture: decodes one frame from an RTSP sub-stream every N seconds,
uploads it as a JPEG to R2, and updates streams.thumbnail_url in Supabase.

Skips capture when the privacy filter reports a human in frame — retaining
the last clean thumbnail instead of exposing a volunteer's face.
"""
from __future__ import annotations

import io
import logging
import threading
import time

import boto3

from lms.database import MeloDB
from lms.privacy_filter import PrivacyFilter

logger = logging.getLogger(__name__)

_JPEG_QUALITY = 85


class ThumbnailCapture:
    def __init__(
        self,
        stream_id: str,
        rtsp_url: str,
        db: MeloDB,
        s3_client,
        bucket: str,
        r2_public_base: str,
        privacy_filter: PrivacyFilter | None = None,
        interval: int = 30,
    ) -> None:
        self._stream_id = stream_id
        self._rtsp_url = rtsp_url
        self._db = db
        self._s3 = s3_client
        self._bucket = bucket
        self._key = f"thumbnails/{stream_id}/thumb.jpg"
        self._public_url = f"{r2_public_base.rstrip('/')}/thumbnails/{stream_id}/thumb.jpg"
        self._privacy_filter = privacy_filter
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"thumbnail-{self._stream_id}",
        )
        self._thread.start()
        logger.info("ThumbnailCapture started for stream %s", self._stream_id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 5)

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._privacy_filter and self._privacy_filter.is_human_detected():
                logger.debug("Stream %s: skipping thumbnail (human detected)", self._stream_id)
            else:
                try:
                    self._capture_and_upload()
                except Exception:
                    logger.exception("Thumbnail capture failed for stream %s", self._stream_id)
            self._stop_event.wait(self._interval)

    def _capture_and_upload(self) -> None:
        import av

        container = av.open(
            self._rtsp_url,
            options={"rtsp_transport": "tcp", "stimeout": "5000000"},
        )
        try:
            for frame in container.decode(video=0):
                img = frame.to_image()
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
                jpeg_bytes = buf.getvalue()
                break
        finally:
            container.close()

        self._s3.put_object(
            Bucket=self._bucket,
            Key=self._key,
            Body=jpeg_bytes,
            ContentType="image/jpeg",
        )

        self._db.update_thumbnail_url(self._stream_id, self._public_url)
        logger.debug("Thumbnail uploaded for stream %s (%d bytes)", self._stream_id, len(jpeg_bytes))
