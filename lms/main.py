"""
Melo v2 LMS entry point.

Connects cameras, starts HLS pipelines, privacy filters, thumbnails, R2 uploaders,
and delegates heartbeat + cleanup to dedicated manager threads.

Also runs a local setup API (FastAPI on port 8000) for camera discovery
and configuration from the admin dashboard.
"""
from __future__ import annotations

import datetime
import logging
import logging.handlers
import os
import resource
import signal
import sys
import threading
import time
from pathlib import Path

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


def _start_setup_api(
    cfg,
    db,
    pipeline_mgr: PipelineManager,
    heartbeat: HeartbeatManager,
    cleanup: SegmentCleanup,
    file_handler: logging.FileHandler | None,
    session_log_path: str | None,
) -> threading.Thread:
    """Start the setup API server in a background thread."""
    from setup.app import app, _state

    _state["cfg"] = cfg
    _state["db"] = db
    _state["pipeline_manager"] = pipeline_mgr
    _state["heartbeat"] = heartbeat
    _state["cleanup"] = cleanup
    _state["file_handler"] = file_handler
    _state["session_log_path"] = session_log_path

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

    log_format = "%(asctime)s %(levelname)-8s %(name)s  %(message)s"
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format=log_format,
    )

    # Session file logging
    file_handler: logging.FileHandler | None = None
    session_log_path: str | None = None
    try:
        log_dir = Path("/var/log/melo")
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        session_log_path = str(log_dir / f"session_{ts}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            session_log_path, maxBytes=50 * 1024 * 1024, backupCount=3,
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)
        logger.info("Session log: %s", session_log_path)
    except PermissionError:
        logger.warning("Cannot write to /var/log/melo/ — session logs disabled")

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
    _start_setup_api(
        cfg, db, pipeline_mgr, heartbeat, cleanup, file_handler, session_log_path,
    )

    cameras = db.get_cameras_for_shelter(cfg.shelter_id)
    logger.info("Found %d camera(s) for shelter %s", len(cameras), cfg.shelter_id)

    for cam_row in cameras:
        stream_id = cam_row.get("stream_id") or cam_row["id"]
        if not pipeline_mgr.start_camera(cam_row):
            db.set_stream_status(stream_id, "offline")

    heartbeat.start()
    cleanup.start()

    # Block until signal or API-triggered shutdown
    stop = threading.Event()

    # Share with setup API so the shutdown endpoint can unblock us
    from setup.app import _state as api_state
    api_state["stop_event"] = stop

    def _shutdown(*_):
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    process_start = time.time()

    def _get_current_rss_mb() -> float:
        if sys.platform == "linux":
            try:
                with open("/proc/self/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            return int(line.split()[1]) / 1024
            except (FileNotFoundError, ValueError):
                pass
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "linux":
            return rusage.ru_maxrss / 1024
        return rusage.ru_maxrss / (1024 * 1024)

    def _sd_notify(state: str) -> None:
        """Send a notification to systemd (no-op if not running under systemd)."""
        addr = os.environ.get("NOTIFY_SOCKET")
        if not addr:
            return
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            if addr.startswith("@"):
                addr = "\0" + addr[1:]
            sock.connect(addr)
            sock.sendall(state.encode())
        finally:
            sock.close()

    _sd_notify("READY=1")

    def _process_heartbeat():
        while not stop.is_set():
            stop.wait(60)
            if stop.is_set():
                break
            try:
                _sd_notify("WATCHDOG=1")
                rss_mb = _get_current_rss_mb()
                logger.info(
                    "[process] pid=%d rss_mb=%.1f threads=%d uptime_min=%.0f",
                    os.getpid(), rss_mb, threading.active_count(),
                    (time.time() - process_start) / 60,
                )
            except Exception:
                logger.exception("[process] heartbeat failed")

    threading.Thread(target=_process_heartbeat, daemon=True, name="process-heartbeat").start()

    def _roaming_scan():
        """Periodically retry cameras that aren't currently streaming."""
        while not stop.is_set():
            stop.wait(60)
            if stop.is_set():
                break
            try:
                all_cameras = db.get_cameras_for_shelter(cfg.shelter_id)
                for cam_row in all_cameras:
                    stream_id = cam_row.get("stream_id") or cam_row["id"]
                    if pipeline_mgr.is_active(stream_id):
                        continue
                    logger.info("[roaming] Retrying camera %s...", cam_row["id"])
                    if pipeline_mgr.start_camera(cam_row):
                        logger.info("[roaming] Camera %s is now live", cam_row["id"])
                    else:
                        db.set_stream_status(stream_id, "offline")
            except Exception:
                logger.exception("[roaming] Scan error")

    threading.Thread(target=_roaming_scan, daemon=True, name="roaming-scan").start()

    logger.info("LMS running — setup API on :8000")
    stop.wait()

    # Graceful shutdown — managers may already be stopped by the API endpoint,
    # but these calls are safe to repeat (they're idempotent).
    logger.info("Shutting down...")
    heartbeat.stop()
    cleanup.stop()
    pipeline_mgr.stop_all()
    logger.info("LMS process exiting.")

    # Force exit — uvicorn's daemon thread would otherwise keep the process alive
    os._exit(0)
