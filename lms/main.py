"""
Melo v2 LMS entry point.

Connects cameras, starts HLS pipelines, privacy filters, thumbnails, R2 uploaders,
and delegates heartbeat + cleanup to dedicated manager threads.
"""
from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path

import boto3
from dotenv import load_dotenv

from lms.config import load_config
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


def main() -> None:
    load_dotenv()
    cfg = load_config()

    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )

    db = MeloDB(cfg.supabase_url, cfg.supabase_service_role_key)

    kms_client: KMSClient | None = None
    if not cfg.local_dev:
        kms_client = KMSClient(
            cfg.gcp_project_id, cfg.kms_location, cfg.kms_key_ring, cfg.kms_key_name
        )

    s3 = boto3.client(
        "s3",
        endpoint_url=cfg.r2_endpoint,
        aws_access_key_id=cfg.r2_access_key_id,
        aws_secret_access_key=cfg.r2_secret_access_key,
    )

    cameras = db.get_cameras_for_shelter(cfg.shelter_id)
    logger.info("Found %d camera(s) for shelter %s", len(cameras), cfg.shelter_id)

    heartbeat = HeartbeatManager(db, interval=cfg.heartbeat_interval)
    cleanup = SegmentCleanup()

    pipelines: list[HLSPipeline] = []
    uploaders: list[R2Uploader] = []
    privacy_filters: list[PrivacyFilter] = []
    thumbnails: list[ThumbnailCapture] = []
    stream_ids: list[str] = []

    for cam_row in cameras:
        cam_uuid = cam_row["id"]
        stream_id = cam_row.get("stream_id") or cam_uuid

        # Decrypt credentials
        encrypted = cam_row.get("encrypted_secret")
        username = cam_row.get("username", "admin")
        if encrypted and kms_client:
            password = kms_client.decrypt(encrypted)
        elif cfg.local_dev:
            password = cam_row.get("password", "")
        else:
            logger.warning("No encrypted secret for camera %s, skipping", cam_uuid)
            continue

        # Use explicit rtsp_url if set, otherwise discover via ONVIF
        if cam_row.get("rtsp_url"):
            rtsp_url = cam_row["rtsp_url"]
            del password
        else:
            try:
                rtsp_url = get_stream_uri(
                    cam_row["ip_address"], cam_row.get("onvif_port", 80), username, password
                )
            except Exception:
                logger.exception("ONVIF failed for camera %s", cam_uuid)
                continue
            finally:
                del password

        registry.upsert(Camera(
            uuid=cam_uuid,
            ip_address=cam_row["ip_address"],
            onvif_port=cam_row.get("onvif_port", 80),
            status=CameraStatus.CONNECTED,
            stream_id=stream_id,
        ))

        output_dir = cfg.hls_output_dir / stream_id
        cleanup.register(output_dir)

        # Privacy filter (optional — disabled if model fails to load)
        privacy_filter: PrivacyFilter | None = None
        if cfg.privacy_filter_enabled:
            privacy_filter = PrivacyFilter(
                stream_id=stream_id,
                rtsp_url=rtsp_url,
                confidence_threshold=cfg.privacy_confidence_threshold,
                segment_duration=cfg.hls_segment_duration,
            )
            privacy_filter.start()
            privacy_filters.append(privacy_filter)

        pipeline = HLSPipeline(
            stream_id=stream_id,
            rtsp_url=rtsp_url,
            output_dir=output_dir,
            segment_duration=cfg.hls_segment_duration,
            playlist_size=cfg.hls_playlist_size,
        )
        uploader = R2Uploader(
            bucket=cfg.r2_bucket,
            endpoint=cfg.r2_endpoint,
            access_key_id=cfg.r2_access_key_id,
            secret_access_key=cfg.r2_secret_access_key,
            stream_id=stream_id,
            segment_dir=output_dir,
            privacy_filter=privacy_filter,
        )

        pipeline.start()
        uploader.start()

        # Build HLS URL from R2 public base if configured
        hls_url: str | None = None
        if cfg.r2_public_base:
            hls_url = f"{cfg.r2_public_base.rstrip('/')}/live-segments/{stream_id}/stream.m3u8"

        db.set_stream_status(stream_id, "live")
        if hls_url:
            from supabase import Client
            db.client.table("streams").update({"hls_url": hls_url}).eq("id", stream_id).execute()

        heartbeat.register(stream_id, pipeline, uploader)

        if cfg.r2_public_base:
            thumb = ThumbnailCapture(
                stream_id=stream_id,
                rtsp_url=rtsp_url,
                db=db,
                s3_client=s3,
                bucket=cfg.r2_bucket,
                r2_public_base=cfg.r2_public_base,
                privacy_filter=privacy_filter,
                interval=cfg.thumbnail_interval,
            )
            thumb.start()
            thumbnails.append(thumb)

        pipelines.append(pipeline)
        uploaders.append(uploader)
        stream_ids.append(stream_id)

    heartbeat.start()
    cleanup.start()

    # Block until signal
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    logger.info("LMS running — %d pipeline(s) active", len(pipelines))
    stop.wait()

    # Graceful shutdown
    logger.info("Shutting down...")
    heartbeat.stop()
    cleanup.stop()
    for pf in privacy_filters:
        pf.stop()
    for thumb in thumbnails:
        thumb.stop()
    for pipeline in pipelines:
        pipeline.stop()
    for uploader in uploaders:
        uploader.stop()
    for sid in stream_ids:
        db.set_stream_status(sid, "offline")
