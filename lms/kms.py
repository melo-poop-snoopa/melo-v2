"""
GCP Cloud KMS wrapper for decrypting camera credentials.

The LMS service account must have the cloudkms.cryptoKeyDecrypter IAM role.
Authentication is handled automatically via GOOGLE_APPLICATION_CREDENTIALS.
"""
from __future__ import annotations

import base64
import logging

from google.cloud import kms

logger = logging.getLogger(__name__)


class KMSClient:
    def __init__(
        self,
        project_id: str,
        location: str,
        key_ring: str,
        key_name: str,
    ) -> None:
        self._client = kms.KeyManagementServiceClient()
        self._key_path = self._client.crypto_key_path(
            project_id, location, key_ring, key_name
        )

    def decrypt(self, ciphertext: str | bytes) -> str:
        """
        Decrypt a GCP KMS ciphertext blob and return the plaintext password.

        Accepts either:
        - A base64-encoded string (as returned by Supabase REST for BYTEA columns)
        - Raw bytes
        """
        if isinstance(ciphertext, str):
            if ciphertext.startswith("\\x"):
                # PostgreSQL hex-escape format (e.g. \xdeadbeef) returned by
                # some PostgREST versions for BYTEA columns.
                ciphertext_bytes = bytes.fromhex(ciphertext[2:])
            else:
                # Standard PostgREST base64 encoding (no padding); add it back.
                padding = 4 - len(ciphertext) % 4
                if padding != 4:
                    ciphertext += "=" * padding
                ciphertext_bytes = base64.b64decode(ciphertext)
        else:
            ciphertext_bytes = ciphertext

        response = self._client.decrypt(
            request={
                "name": self._key_path,
                "ciphertext": ciphertext_bytes,
            }
        )

        plaintext = response.plaintext.decode("utf-8").rstrip("\n")
        logger.debug("KMS decryption successful for key %s", self._key_path)
        return plaintext
