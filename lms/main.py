"""
Melo v2 LMS entry point.

Connects cameras, starts HLS pipelines, privacy filters, thumbnails, R2 uploaders,
and delegates heartbeat + cleanup to dedicated manager threads.

Also runs a local setup API (FastAPI on port 8000) for camera discovery
and configuration from the admin dashboard.
"""
from __future__ import annotations

import logging
import signal
import threading

import boto3
from dotenv import load_dotenv

from lms.config import load_config
from lms.database import MeloDB
from lms.heartbeat_manager import HeartbeatManager
from lms.kms import KMSClient
from lms.pipeline_manager import PipelineManager
from lms.segment_cleanup import SegmentCleanup

logger = logging.getLogger(__name__)


def _get_local_ip() -> str:
    """Get the machine's LAN IP address."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _start_setup_api(cfg, db, pipeline_mgr: PipelineManager) -> threading.Thread:
    """Start the setup API server in a background thread."""
    from setup.app import app, _state

    _state["cfg"] = cfg
    _state["db"] = db
    _state["pipeline_manager"] = pipeline_mgr

    def run():
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

    t = threading.Thread(target=run, daemon=True, name="setup-api")
    t.start()

    local_ip = _get_local_ip()
    lms_url = f"http://{local_ip}:8000"
    db.set_lms_url(cfg.shelter_id, lms_url)
    logger.info("Setup API running on %s", lms_url)

    return t


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

    heartbeat = HeartbeatManager(db, interval=cfg.heartbeat_interval)
    cleanup = SegmentCleanup()

    pipeline_mgr = PipelineManager(
        cfg=cfg, db=db, s3=s3, kms_client=kms_client,
        heartbeat=heartbeat, cleanup=cleanup,
    )

    # Start the setup API for camera discovery/configuration
    _start_setup_api(cfg, db, pipeline_mgr)

    cameras = db.get_cameras_for_shelter(cfg.shelter_id)
    logger.info("Found %d camera(s) for shelter %s", len(cameras), cfg.shelter_id)

    for cam_row in cameras:
        pipeline_mgr.start_camera(cam_row)

    heartbeat.start()
    cleanup.start()

    # Block until signal
    stop = threading.Event()

    def _shutdown(*_):
        for pipeline in pipelines:
            pipeline.request_stop()
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("LMS running — setup API on :8000")
    stop.wait()

    # Graceful shutdown
    logger.info("Shutting down...")
    heartbeat.stop()
    cleanup.stop()
    pipeline_mgr.stop_all()
