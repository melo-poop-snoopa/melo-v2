from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lms.config import Config


@pytest.fixture
def tmp_segments(tmp_path: Path) -> Path:
    seg_dir = tmp_path / "segments" / "test-stream"
    seg_dir.mkdir(parents=True)
    return seg_dir


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        supabase_url="http://localhost:54321",
        supabase_service_role_key="test-key",
        gcp_project_id="test-project",
        kms_location="us-central1",
        kms_key_ring="test-ring",
        kms_key_name="test-key",
        r2_bucket="test-bucket",
        r2_endpoint="https://test.r2.cloudflarestorage.com",
        r2_access_key_id="test-access-key",
        r2_secret_access_key="test-secret-key",
        shelter_id="test-shelter-id",
        hls_output_dir=tmp_path / "segments",
    )


@pytest.fixture
def mock_s3_client() -> MagicMock:
    return MagicMock()
