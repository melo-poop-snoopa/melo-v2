"""
Thread-safe in-memory registry of active Camera objects.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum


class CameraStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    AUTH_FAILED = "auth_failed"


@dataclass
class Camera:
    uuid: str
    ip_address: str
    onvif_port: int
    status: CameraStatus
    stream_id: str = ""


class CameraRegistry:
    """Thread-safe in-memory store for Camera objects."""

    def __init__(self) -> None:
        self._cameras: dict[str, Camera] = {}
        self._lock = threading.RLock()

    def get(self, uuid: str) -> Camera | None:
        with self._lock:
            return self._cameras.get(uuid)

    def upsert(self, camera: Camera) -> None:
        with self._lock:
            self._cameras[camera.uuid] = camera

    def set_status(self, uuid: str, status: CameraStatus) -> Camera | None:
        with self._lock:
            cam = self._cameras.get(uuid)
            if cam is None:
                return None
            cam.status = status
            return cam

    def update_ip(self, uuid: str, ip_address: str, onvif_port: int) -> None:
        with self._lock:
            cam = self._cameras.get(uuid)
            if cam is not None:
                cam.ip_address = ip_address
                cam.onvif_port = onvif_port

    def remove(self, uuid: str) -> None:
        with self._lock:
            self._cameras.pop(uuid, None)

    def get_all(self) -> list[Camera]:
        with self._lock:
            return list(self._cameras.values())


registry = CameraRegistry()
