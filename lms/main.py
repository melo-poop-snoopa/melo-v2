"""
Melo v2 LMS entry point.

Connects cameras, starts HLS pipelines + R2 uploaders, and runs a heartbeat loop.
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from lms.config import load_config
from lms.database import MeloDB
from lms.hls_pipeline import HLSPipeline
from lms.kms import KMSClient
from lms.onvif_client import get_stream_uri
from lms.r2_uploader import R2Uploader
from lms.registry import Camera, CameraStatus, registry

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

    cameras = db.get_cameras_for_shelter(cfg.shelter_id)
    logger.info("Found %d camera(s) for shelter %s", len(cameras), cfg.shelter_id)

    pipelines: list[HLSPipeline] = []
    uploaders: list[R2Uploader] = []
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

        # Get RTSP URI via ONVIF
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
        )

        pipeline.start()
        uploader.start()
        db.set_stream_status(stream_id, "live")

        pipelines.append(pipeline)
        uploaders.append(uploader)
        stream_ids.append(stream_id)

    # Heartbeat loop
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    logger.info("LMS running — %d pipeline(s) active", len(pipelines))

    while not stop.is_set():
        for pipeline, uploader, sid in zip(pipelines, uploaders, stream_ids):
            alive = pipeline.is_alive()
            recent_upload = (time.time() - uploader.last_upload_time) < 30

            if alive and recent_upload:
                db.update_heartbeat(sid)
            else:
                db.set_stream_status(sid, "offline")

        stop.wait(cfg.heartbeat_interval)

    # Graceful shutdown
    logger.info("Shutting down...")
    for pipeline in pipelines:
        pipeline.stop()
    for uploader in uploaders:
        uploader.stop()
    for sid in stream_ids:
        db.set_stream_status(sid, "offline")
