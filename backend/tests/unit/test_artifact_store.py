"""Unit tests for S3 artifact store."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestArtifactStore:
    def test_upload_download_roundtrip(self):
        from app.services.ml.artifact_store import S3ArtifactStore

        mock_client = MagicMock()
        store = S3ArtifactStore(bucket="test-bucket", client=mock_client)

        # Create a temp directory with files
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "model.onnx").write_bytes(b"fake model data")
            (Path(tmpdir) / "config.json").write_text('{"version": "1.0"}')

            manifest = store.upload("v1.0", tmpdir)

        assert manifest["version"] == "v1.0"
        assert "model.onnx" in manifest["files"]
        assert "config.json" in manifest["files"]
        assert "created_at" in manifest

        # Verify S3 upload was called
        assert mock_client.upload_file.call_count == 2
        mock_client.put_object.assert_called_once()

    def test_resolve_returns_key(self):
        from app.services.ml.artifact_store import S3ArtifactStore

        mock_client = MagicMock()
        store = S3ArtifactStore(bucket="test-bucket", client=mock_client)

        key = store.resolve("v1.0")
        assert key == "models/v1.0"

    def test_list_versions(self):
        from app.services.ml.artifact_store import S3ArtifactStore

        mock_client = MagicMock()
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "models/v1.0/model.onnx"},
                {"Key": "models/v1.0/config.json"},
                {"Key": "models/v2.0/model.onnx"},
            ]
        }

        store = S3ArtifactStore(bucket="test-bucket", client=mock_client)
        versions = store.list_versions()

        assert "v1.0" in versions
        assert "v2.0" in versions
        assert len(versions) == 2

    def test_download_calls_s3(self):
        from app.services.ml.artifact_store import S3ArtifactStore

        mock_client = MagicMock()
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "models/v1.0/model.onnx"},
                {"Key": "models/v1.0/manifest.json"},
            ]
        }

        store = S3ArtifactStore(bucket="test-bucket", client=mock_client)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = store.download("v1.0", tmpdir)
            assert result.exists()
            # Should download model.onnx but skip manifest.json
            assert mock_client.download_file.call_count == 1
