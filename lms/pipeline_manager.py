"""
PipelineManager: starts and stops per-camera streaming pipelines.

Used by main() for initial cameras and by the setup API to hot-add
cameras without restarting the LMS.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import boto3

from lms.config import Config
from lms.database import MeloDB
from lms.heartbeat_manager import HeartbeatManager
from lms.hls_pipeline import HLSPipeline
from lms.kms import KMSClient
from lms.onvif_client import get_stream_uri
from lms.privacy_filter import PrivacyFilter
from lms.r2_uploader import R2Uploader
from lms.registry import Camera, CameraStatus, registry
from lms.segment_cleanup import SegmentCleanup
from lms.thumbnail_capture import ThumbnailCapture

logger = logging.getLogger(__name__)


class PipelineManager:
    def __init__(
        self,
        cfg: Config,
        db: MeloDB,
        s3,
        kms_client: KMSClient | None,
        heartbeat: HeartbeatManager,
        cleanup: SegmentCleanup,
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._s3 = s3
        self._kms = kms_client
        self._heartbeat = heartbeat
        self._cleanup = cleanup
        self._lock = threading.Lock()
        self._active: dict[str, _CameraPipeline] = {}

    def start_camera(self, cam_row: dict, rtsp_url: str | None = None) -> bool:
        """Start streaming for a camera row from Supabase.

        If rtsp_url is provided (e.g. from a just-completed ONVIF test),
        it's used directly. Otherwise the RTSP URL is discovered via ONVIF
        or read from the rtsp_url column.

        Returns True if the pipeline started successfully.
        """
        cfg = self._cfg
        cam_uuid = cam_row["id"]
        stream_id = cam_row.get("stream_id") or cam_uuid

        with self._lock:
            if stream_id in self._active:
                logger.info("Stream %s already active, skipping", stream_id)
                return True

        if not rtsp_url:
            rtsp_url = self._resolve_rtsp_url(cam_row)
        if not rtsp_url:
            return False

        registry.upsert(Camera(
            uuid=cam_uuid,
            ip_address=cam_row.get("ip_address", ""),
            onvif_port=cam_row.get("onvif_port", 80),
            status=CameraStatus.CONNECTED,
            stream_id=stream_id,
        ))

        output_dir = cfg.hls_output_dir / stream_id
        self._cleanup.register(output_dir)

        privacy_filter: PrivacyFilter | None = None
        if cfg.privacy_filter_enabled:
            privacy_filter = PrivacyFilter(
                stream_id=stream_id,
                rtsp_url=rtsp_url,
                confidence_threshold=cfg.privacy_confidence_threshold,
            )
            privacy_filter.start()

        pipeline = HLSPipeline(
            stream_id=stream_id,
            rtsp_url=rtsp_url,
            output_dir=output_dir,
            segment_duration=cfg.hls_segment_duration,
            playlist_size=cfg.hls_playlist_size,
            video_codec=cfg.hls_video_codec,
            preset=cfg.hls_preset,
            fps=cfg.hls_fps,
        )
        uploader = R2Uploader(
            bucket=cfg.r2_bucket,
            endpoint=cfg.r2_endpoint,
            access_key_id=cfg.r2_access_key_id,
            secret_access_key=cfg.r2_secret_access_key,
            stream_id=stream_id,
            segment_dir=output_dir,
        )

        pipeline.start()
        uploader.start()

        hls_url: str | None = None
        if cfg.r2_public_base:
            hls_url = f"{cfg.r2_public_base.rstrip('/')}/live-segments/{stream_id}/stream.m3u8"

        if hls_url:
            self._db.client.table("streams").update({"hls_url": hls_url}).eq("id", stream_id).execute()

        self._heartbeat.register(stream_id, pipeline, uploader, privacy_filter)

        thumb: ThumbnailCapture | None = None
        if cfg.r2_public_base:
            thumb = ThumbnailCapture(
                stream_id=stream_id,
                rtsp_url=rtsp_url,
                db=self._db,
                s3_client=self._s3,
                bucket=cfg.r2_bucket,
                r2_public_base=cfg.r2_public_base,
                privacy_filter=privacy_filter,
                interval=cfg.thumbnail_interval,
            )
            thumb.start()

        with self._lock:
            self._active[stream_id] = _CameraPipeline(
                pipeline=pipeline,
                uploader=uploader,
                privacy_filter=privacy_filter,
                thumbnail=thumb,
            )

        logger.info("Started pipeline for stream %s (camera %s)", stream_id, cam_uuid)
        return True

    def stop_camera(self, stream_id: str) -> None:
        with self._lock:
            cam_pipeline = self._active.pop(stream_id, None)
        if not cam_pipeline:
            return
        cam_pipeline.stop()
        self._db.set_stream_status(stream_id, "offline")
        logger.info("Stopped pipeline for stream %s", stream_id)

    def stop_all(self) -> None:
        with self._lock:
            stream_ids = list(self._active.keys())
        for sid in stream_ids:
            self.stop_camera(sid)

    def _resolve_rtsp_url(self, cam_row: dict) -> str | None:
        cfg = self._cfg

        if cam_row.get("rtsp_url"):
            return cam_row["rtsp_url"]

        encrypted = cam_row.get("encrypted_secret")
        username = cam_row.get("username", "admin")
        if encrypted and self._kms:
            password = self._kms.decrypt(encrypted)
        elif cfg.local_dev:
            if encrypted and isinstance(encrypted, str) and encrypted.startswith("\\x"):
                password = bytes.fromhex(encrypted[2:]).decode("utf-8")
            elif encrypted:
                password = str(encrypted)
            else:
                password = ""
        else:
            logger.warning("No encrypted secret for camera %s, skipping", cam_row["id"])
            return None

        try:
            url = get_stream_uri(
                cam_row["ip_address"], cam_row.get("onvif_port", 80), username, password
            )
            del password
            return url
        except Exception:
            logger.exception("ONVIF failed for camera %s", cam_row["id"])
            del password
            return None


class _CameraPipeline:
    __slots__ = ("pipeline", "uploader", "privacy_filter", "thumbnail")

    def __init__(
        self,
        pipeline: HLSPipeline,
        uploader: R2Uploader,
        privacy_filter: PrivacyFilter | None,
        thumbnail: ThumbnailCapture | None,
    ) -> None:
        self.pipeline = pipeline
        self.uploader = uploader
        self.privacy_filter = privacy_filter
        self.thumbnail = thumbnail

    def stop(self) -> None:
        if self.privacy_filter:
            self.privacy_filter.stop()
        if self.thumbnail:
            self.thumbnail.stop()
        self.pipeline.stop()
        self.uploader.stop()
