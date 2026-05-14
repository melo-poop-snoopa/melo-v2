"""
Supabase CRUD operations for melo v2 tables (shelters, streams, cats, shelter_cameras).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class MeloDB:
    def __init__(self, url: str, service_role_key: str) -> None:
        self._client: Client = create_client(url, service_role_key)

    @property
    def client(self) -> Client:
        return self._client

    # ── Shelters ──────────────────────────────────────────────────────────────

    def get_shelter(self, shelter_id: str) -> dict | None:
        result = self._client.table("shelters").select("*").eq("id", shelter_id).execute()
        rows = result.data
        return rows[0] if rows else None

    def set_lms_url(self, shelter_id: str, lms_url: str) -> None:
        self._client.table("shelters").update(
            {"lms_url": lms_url}
        ).eq("id", shelter_id).execute()
        logger.info("Registered LMS URL for shelter %s: %s", shelter_id, lms_url)

    # ── Cameras ───────────────────────────────────────────────────────────────

    def get_cameras_for_shelter(self, shelter_id: str) -> list[dict]:
        result = (
            self._client.table("shelter_cameras")
            .select("*")
            .eq("shelter_id", shelter_id)
            .execute()
        )
        return result.data or []

    # ── Streams ───────────────────────────────────────────────────────────────

    def get_stream(self, stream_id: str) -> dict | None:
        result = self._client.table("streams").select("*").eq("id", stream_id).execute()
        rows = result.data
        return rows[0] if rows else None

    def upsert_stream(self, stream_id: str, data: dict) -> None:
        data["id"] = stream_id
        self._client.table("streams").upsert(data).execute()
        logger.info("Upserted stream %s", stream_id)

    def update_heartbeat(self, stream_id: str) -> None:
        self._client.table("streams").update(
            {"last_heartbeat": datetime.now(timezone.utc).isoformat(), "status": "live"}
        ).eq("id", stream_id).execute()

    def set_stream_status(self, stream_id: str, status: str) -> None:
        self._client.table("streams").update(
            {"status": status}
        ).eq("id", stream_id).execute()
        logger.info("Stream %s → %s", stream_id, status)

    def update_thumbnail_url(self, stream_id: str, url: str) -> None:
        self._client.table("streams").update(
            {"thumbnail_url": url}
        ).eq("id", stream_id).execute()

    # ── Cats ──────────────────────────────────────────────────────────────────

    def get_cats_for_stream(self, stream_id: str) -> list[dict]:
        result = (
            self._client.table("cats")
            .select("*")
            .eq("stream_id", stream_id)
            .execute()
        )
        return result.data or []
