"""S3-backed model artifact store.

Manages upload, download, and versioning of ML model artifacts in S3.
"""

import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".trustshield" / "cache"


class S3ArtifactStore:
    """Manage ML model artifacts in S3."""

    def __init__(self, bucket: str, client=None):
        self._bucket = bucket
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from app.config import settings
            kwargs = {}
            if settings.aws_access_key_id:
                kwargs["aws_access_key_id"] = settings.aws_access_key_id
            if settings.aws_secret_access_key:
                kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            self._client = boto3.client("s3", region_name=settings.kms_region, **kwargs)
        except ImportError:
            raise RuntimeError("boto3 is required for S3ArtifactStore")
        return self._client

    def upload(self, version: str, local_dir: str) -> dict:
        """Upload a local directory of artifacts to S3.

        Returns a manifest with file hashes and metadata.
        """
        client = self._get_client()
        local_path = Path(local_dir)
        manifest: Dict[str, Any] = {
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": {},
        }

        # Get git SHA if in a repo
        try:
            manifest["git_sha"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            manifest["git_sha"] = "unknown"

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                rel_key = str(file_path.relative_to(local_path))
                s3_key = f"models/{version}/{rel_key}"

                # Compute SHA-256
                sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
                manifest["files"][rel_key] = sha

                # Upload
                client.upload_file(str(file_path), self._bucket, s3_key)
                logger.info("Uploaded %s -> s3://%s/%s", rel_key, self._bucket, s3_key)

        # Upload manifest
        manifest_key = f"models/{version}/manifest.json"
        client.put_object(
            Bucket=self._bucket,
            Key=manifest_key,
            Body=json.dumps(manifest, indent=2),
            ContentType="application/json",
        )

        return manifest

    def download(self, version: str, dest_dir: str) -> Path:
        """Download artifacts for a version from S3 to a local directory."""
        client = self._get_client()
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)

        # List all objects for this version
        prefix = f"models/{version}/"
        response = client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)

        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith("manifest.json"):
                continue
            rel_key = key[len(prefix):]
            local_file = dest / rel_key
            local_file.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(self._bucket, key, str(local_file))
            logger.info("Downloaded s3://%s/%s -> %s", self._bucket, key, local_file)

        return dest

    def resolve(self, version: str) -> str:
        """Return the S3 key prefix for a version."""
        return f"models/{version}"

    def list_versions(self) -> List[str]:
        """List all available artifact versions."""
        client = self._get_client()
        versions = set()
        response = client.list_objects_v2(Bucket=self._bucket, Prefix="models/")

        for obj in response.get("Contents", []):
            key = obj["Key"]
            parts = key.split("/")
            if len(parts) >= 2:
                versions.add(parts[1])

        return sorted(versions)
