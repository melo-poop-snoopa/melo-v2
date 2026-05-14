"""
Melo Setup API — camera discovery and configuration endpoints.

Embedded in the LMS process. The LMS starts this as a background thread
on port 8000. The admin dashboard calls these endpoints for camera
discovery, ONVIF testing, and saving camera configs to Supabase.

Can also run standalone with `uv run melo-setup` for development.
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from setup.discovery import discover_onvif_cameras

logger = logging.getLogger(__name__)

app = FastAPI(title="Melo Setup API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared state — populated by the LMS on startup, or by standalone mode
_state: dict = {}


def _get_supabase():
    """Get a Supabase client, either from LMS shared state or standalone."""
    db = _state.get("db")
    if db:
        return db.client

    from supabase import create_client
    from dotenv import load_dotenv
    load_dotenv()
    url = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54331")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        raise HTTPException(500, "SUPABASE_SERVICE_ROLE_KEY not configured")
    return create_client(url, key)


def _get_config():
    """Get config, either from LMS shared state or env vars."""
    cfg = _state.get("cfg")
    if cfg:
        return cfg
    return None


# ── Models ───────────────────────────────────────────────────────────────────


class DiscoverResponse(BaseModel):
    cameras: list[dict]


class TestCameraRequest(BaseModel):
    host: str
    port: int = 80
    username: str = ""
    password: str = ""


class TestCameraResponse(BaseModel):
    success: bool
    rtsp_url: str | None = None
    error: str | None = None


class SaveCameraRequest(BaseModel):
    shelter_id: str
    host: str
    port: int = 80
    username: str = ""
    password: str = ""
    stream_name: str = "Camera"


class SaveCameraResponse(BaseModel):
    camera_id: str
    stream_id: str


class DeleteCameraRequest(BaseModel):
    camera_id: str
    stream_id: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/discover", response_model=DiscoverResponse)
async def discover_cameras(timeout: float = 3.0):
    """Run WS-Discovery probe on the local network."""
    cameras = await asyncio.to_thread(discover_onvif_cameras, timeout)
    return DiscoverResponse(
        cameras=[
            {
                "host": c.host,
                "port": c.port,
                "xaddrs": c.xaddrs,
                "device_uuid": c.device_uuid,
            }
            for c in cameras
        ]
    )


@app.post("/api/test", response_model=TestCameraResponse)
async def test_camera(req: TestCameraRequest):
    """Test ONVIF connection — GetProfiles + GetStreamUri."""
    try:
        from lms.onvif_client import _get_stream_uri_async

        rtsp_url = await _get_stream_uri_async(
            req.host, req.port, req.username, req.password
        )
        return TestCameraResponse(success=True, rtsp_url=rtsp_url)
    except Exception as exc:
        logger.warning("ONVIF test failed for %s:%d: %s", req.host, req.port, exc)
        return TestCameraResponse(success=False, error=str(exc))


@app.post("/api/cameras", response_model=SaveCameraResponse)
async def save_camera(req: SaveCameraRequest):
    """Save a camera to Supabase: creates a stream + shelter_camera record."""
    client = _get_supabase()
    cfg = _get_config()
    local_dev = cfg.local_dev if cfg else os.environ.get("LOCAL_DEV", "").lower() in ("1", "true", "yes")

    # Encrypt password
    if local_dev:
        encrypted_secret = "\\x" + req.password.encode("utf-8").hex()
    else:
        from lms.kms import KMSClient

        kms = KMSClient(
            os.environ["GCP_PROJECT_ID"],
            os.environ["KMS_LOCATION"],
            os.environ["KMS_KEY_RING"],
            os.environ["KMS_KEY_NAME"],
        )
        encrypted_secret = kms.encrypt(req.password.encode("utf-8"))

    # Create stream record
    stream_result = (
        client.table("streams")
        .insert({
            "shelter_id": req.shelter_id,
            "name": req.stream_name,
            "status": "offline",
        })
        .execute()
    )
    stream = stream_result.data[0]
    stream_id = stream["id"]

    # Create shelter_camera record
    camera_result = (
        client.table("shelter_cameras")
        .insert({
            "shelter_id": req.shelter_id,
            "stream_id": stream_id,
            "ip_address": req.host,
            "onvif_port": req.port,
            "username": req.username,
            "encrypted_secret": encrypted_secret,
        })
        .execute()
    )
    camera = camera_result.data[0]

    logger.info(
        "Saved camera %s → stream %s for shelter %s",
        camera["id"], stream_id, req.shelter_id,
    )

    # Hot-add: start streaming immediately if the LMS pipeline manager is available
    pipeline_mgr = _state.get("pipeline_manager")
    if pipeline_mgr:
        try:
            # Re-read the camera row so the pipeline manager has the full record
            cam_row = client.table("shelter_cameras").select("*").eq("id", camera["id"]).single().execute().data
            # Use the RTSP URL from the test step if available
            test_result = await test_camera(TestCameraRequest(
                host=req.host, port=req.port, username=req.username, password=req.password,
            ))
            rtsp_url = test_result.rtsp_url if test_result.success else None
            pipeline_mgr.start_camera(cam_row, rtsp_url=rtsp_url)
        except Exception:
            logger.warning("Hot-add failed for camera %s — will start on next LMS restart", camera["id"], exc_info=True)

    return SaveCameraResponse(camera_id=camera["id"], stream_id=stream_id)


@app.delete("/api/cameras")
async def delete_camera(req: DeleteCameraRequest):
    """Delete a camera and stop its pipeline (no LMS restart needed)."""
    client = _get_supabase()

    pipeline_mgr = _state.get("pipeline_manager")
    if pipeline_mgr and req.stream_id:
        pipeline_mgr.stop_camera(req.stream_id)

    client.table("shelter_cameras").delete().eq("id", req.camera_id).execute()

    if req.stream_id:
        client.table("streams").delete().eq("id", req.stream_id).execute()

    logger.info("Deleted camera %s", req.camera_id)
    return {"status": "ok"}


# ── Standalone entry point ───────────────────────────────────────────────────


def main() -> None:
    """Run standalone (for development without the full LMS)."""
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )
    logger.info("Starting Melo Setup Tool (standalone) on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
