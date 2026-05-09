"""
ONVIF client for retrieving an authenticated RTSP stream URI.

Uses onvif-zeep-async to call GetStreamUri on the camera's media service,
then injects credentials into the returned RTSP URL so that FFmpeg
can handle the Digest Authentication handshake natively.
"""
from __future__ import annotations

import asyncio
import importlib.resources
import logging
from urllib.parse import urlparse, urlunparse

from onvif.client import ONVIFCamera

logger = logging.getLogger(__name__)

_WSDL_DIR = str(importlib.resources.files("onvif") / "wsdl")


def get_stream_uri(ip: str, port: int, username: str, password: str) -> str:
    """
    Connect to the ONVIF device at ip:port, authenticate, and return
    an RTSP URL with credentials embedded for use with FFmpeg.

    Selects the first available media profile.
    """
    return asyncio.run(_get_stream_uri_async(ip, port, username, password))


async def _get_stream_uri_async(ip: str, port: int, username: str, password: str) -> str:
    cam = ONVIFCamera(ip, port, username, password, wsdl_dir=_WSDL_DIR)
    try:
        await cam.update_xaddrs()
        media = await cam.create_media_service()

        profiles = await media.GetProfiles()
        if not profiles:
            raise RuntimeError(f"Camera {ip} returned no media profiles")

        token = profiles[0].token
        uri_response = await media.GetStreamUri(
            {
                "StreamSetup": {
                    "Stream": "RTP-Unicast",
                    "Transport": {"Protocol": "RTSP"},
                },
                "ProfileToken": token,
            }
        )

        rtsp_url = uri_response.Uri
        logger.debug("GetStreamUri for %s: %s", ip, rtsp_url)

        return inject_credentials(rtsp_url, username, password)
    finally:
        await cam.close()


def inject_credentials(rtsp_url: str, username: str, password: str) -> str:
    """
    Embed username:password into an RTSP URL so FFmpeg handles
    Digest Authentication automatically.

    e.g. rtsp://192.168.1.10/stream → rtsp://admin:secret@192.168.1.10/stream
    """
    parts = urlparse(rtsp_url)
    netloc = f"{username}:{password}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunparse(parts._replace(netloc=netloc))
