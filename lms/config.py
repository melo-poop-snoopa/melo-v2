from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    supabase_url: str
    supabase_service_role_key: str
    gcp_project_id: str
    kms_location: str
    kms_key_ring: str
    kms_key_name: str

    # Cloudflare R2
    r2_bucket: str = ""
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    # Shelter identity
    shelter_id: str = ""

    # HLS
    hls_segment_duration: int = 1
    hls_playlist_size: int = 8
    hls_output_dir: Path = field(default_factory=lambda: Path("./segments"))
    hls_video_codec: str = "copy"
    hls_preset: str = "ultrafast"
    hls_fps: int = 30
    hls_video_bitrate: str = "1500k"

    # Heartbeat
    heartbeat_interval: int = 15

    # Privacy filter
    privacy_filter_enabled: bool = True
    privacy_confidence_threshold: float = 0.39

    # Thumbnail
    thumbnail_interval: int = 30
    r2_public_base: str = ""

    # General
    log_level: str = "INFO"
    local_dev: bool = False


def load_config() -> Config:
    required = {
        "SUPABASE_URL": "Supabase project URL",
        "SUPABASE_SERVICE_ROLE_KEY": "Supabase service role key",
        "GCP_PROJECT_ID": "GCP project ID",
        "KMS_LOCATION": "GCP KMS location (e.g. us-central1)",
        "KMS_KEY_RING": "GCP KMS key ring name",
        "KMS_KEY_NAME": "GCP KMS key name",
        "R2_BUCKET": "Cloudflare R2 bucket name",
        "R2_ENDPOINT": "Cloudflare R2 endpoint URL",
        "R2_ACCESS_KEY_ID": "Cloudflare R2 access key ID",
        "R2_SECRET_ACCESS_KEY": "Cloudflare R2 secret access key",
        "SHELTER_ID": "Shelter UUID for this LMS instance",
    }

    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        lines = "\n".join(f"  {k}: {required[k]}" for k in missing)
        raise EnvironmentError(f"Missing required environment variables:\n{lines}")

    return Config(
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_service_role_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        gcp_project_id=os.environ["GCP_PROJECT_ID"],
        kms_location=os.environ["KMS_LOCATION"],
        kms_key_ring=os.environ["KMS_KEY_RING"],
        kms_key_name=os.environ["KMS_KEY_NAME"],
        r2_bucket=os.environ["R2_BUCKET"],
        r2_endpoint=os.environ["R2_ENDPOINT"],
        r2_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        r2_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        shelter_id=os.environ["SHELTER_ID"],
        hls_segment_duration=int(os.environ.get("HLS_SEGMENT_DURATION", "1")),
        hls_playlist_size=int(os.environ.get("HLS_PLAYLIST_SIZE", "8")),
        hls_output_dir=Path(os.environ.get("HLS_OUTPUT_DIR", "./segments")),
        hls_video_codec=os.environ.get("HLS_VIDEO_CODEC", "copy"),
        hls_preset=os.environ.get("HLS_PRESET", "ultrafast"),
        hls_fps=int(os.environ.get("HLS_FPS", "30")),
        hls_video_bitrate=os.environ.get("HLS_VIDEO_BITRATE", "1500k"),
        heartbeat_interval=int(os.environ.get("HEARTBEAT_INTERVAL", "15")),
        privacy_filter_enabled=os.environ.get("PRIVACY_FILTER_ENABLED", "true").lower() not in ("0", "false", "no"),
        privacy_confidence_threshold=float(os.environ.get("PRIVACY_CONFIDENCE_THRESHOLD", "0.35")),
        thumbnail_interval=int(os.environ.get("THUMBNAIL_INTERVAL", "30")),
        r2_public_base=os.environ.get("R2_PUBLIC_BASE", ""),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        local_dev=os.environ.get("LOCAL_DEV", "").lower() in ("1", "true", "yes"),
    )
