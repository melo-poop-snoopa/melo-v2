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
from setup.discovery import discover_onvif_cameras

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
            video_bitrate=cfg.hls_video_bitrate,
        )
        uploader = R2Uploader(
            bucket=cfg.r2_bucket,
            endpoint=cfg.r2_endpoint,
            access_key_id=cfg.r2_access_key_id,
            secret_access_key=cfg.r2_secret_access_key,
            stream_id=stream_id,
            segment_dir=output_dir,
            cleanup_age=cfg.r2_segment_retention,
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
                segment_dir=output_dir,
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

    def is_active(self, stream_id: str) -> bool:
        with self._lock:
            return stream_id in self._active

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

        password = self._decrypt_password(cam_row)
        if password is None:
            return None

        username = cam_row.get("username", "admin")
        ip = cam_row["ip_address"]
        port = cam_row.get("onvif_port", 80)

        try:
            url = get_stream_uri(ip, port, username, password)
            return url
        except Exception as exc:
            logger.warning(
                "Camera %s not reachable at %s:%d — %s. Attempting auto-rediscovery...",
                cam_row["id"], ip, port, type(exc).__name__,
            )

        new_ip = self._rediscover_by_uuid(cam_row)
        if not new_ip or new_ip == ip:
            logger.error(
                "Camera %s not detected on the network. "
                "Ensure the camera is powered on and connected to the same LAN as this device.",
                cam_row["id"],
            )
            del password
            return None

        try:
            url = get_stream_uri(new_ip, port, username, password)
            self._db.client.table("shelter_cameras").update(
                {"ip_address": new_ip}
            ).eq("id", cam_row["id"]).execute()
            logger.info(
                "Camera %s found at new IP %s (was %s) — reconnected successfully.",
                cam_row["id"], new_ip, ip,
            )
            return url
        except Exception as exc:
            logger.error(
                "Camera %s found at %s but connection failed — %s: %s",
                cam_row["id"], new_ip, type(exc).__name__, exc,
            )
            return None
        finally:
            del password

    def _decrypt_password(self, cam_row: dict) -> str | None:
        cfg = self._cfg
        encrypted = cam_row.get("encrypted_secret")
        if encrypted and self._kms:
            return self._kms.decrypt(encrypted)
        if cfg.local_dev:
            if encrypted and isinstance(encrypted, str) and encrypted.startswith("\\x"):
                return bytes.fromhex(encrypted[2:]).decode("utf-8")
            if encrypted:
                return str(encrypted)
            return ""
        logger.warning("No encrypted secret for camera %s, skipping", cam_row["id"])
        return None

    def _rediscover_by_uuid(self, cam_row: dict) -> str | None:
        """Run WS-Discovery and match by device_uuid to find a camera's new IP."""
        device_uuid = cam_row.get("device_uuid")
        if not device_uuid:
            logger.warning(
                "Camera %s has no device_uuid stored — cannot auto-rediscover. "
                "Re-add the camera via the setup page to enable auto-rediscovery.",
                cam_row["id"],
            )
            return None

        logger.info("Scanning network for camera %s...", cam_row["id"])
        cameras = discover_onvif_cameras(timeout=5.0)

        for cam in cameras:
            if cam.device_uuid and cam.device_uuid == device_uuid:
                logger.info("Camera %s found at %s (auto-rediscovered)", cam_row["id"], cam.host)
                return cam.host

        if cameras:
            logger.warning(
                "Found %d camera(s) on the network but none matched camera %s. "
                "The camera may be offline or on a different subnet.",
                len(cameras), cam_row["id"],
            )
        else:
            logger.warning(
                "No cameras found on the network. "
                "Check that the camera is powered on and connected via Ethernet/WiFi.",
            )
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
