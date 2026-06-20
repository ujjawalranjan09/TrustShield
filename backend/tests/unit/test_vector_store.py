"""Unit tests for session vector store."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.explain.vector_store import (
    EMBEDDING_DIM,
    SessionEmbedding,
    _compute_content_hash,
    _pseudo_embed,
    embed_session,
    find_similar_sessions,
)


# ------------------------------------------------------------------
# Pure-function tests
# ------------------------------------------------------------------

class TestComputeContentHash:
    def test_deterministic(self):
        h1 = _compute_content_hash("hello world")
        h2 = _compute_content_hash("hello world")
        assert h1 == h2

    def test_different_inputs(self):
        assert _compute_content_hash("a") != _compute_content_hash("b")

    def test_hex_length(self):
        assert len(_compute_content_hash("x")) == 64


class TestPseudoEmbed:
    def test_deterministic(self):
        v1 = _pseudo_embed("test text")
        v2 = _pseudo_embed("test text")
        assert v1 == v2

    def test_dimension(self):
        assert len(_pseudo_embed("any text")) == EMBEDDING_DIM

    def test_normalized(self):
        import math
        vec = _pseudo_embed("normalize me")
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-5

    def test_different_inputs_different_vectors(self):
        assert _pseudo_embed("alpha") != _pseudo_embed("beta")


# ------------------------------------------------------------------
# Async DB-backed tests
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_session_stores_embedding():
    db = AsyncMock()
    db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_result

    await embed_session("s1", "test content", db)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert isinstance(added, SessionEmbedding)
    assert added.session_id == "s1"
    assert added.content_hash == _compute_content_hash("test content")
    assert len(added.embedding) == EMBEDDING_DIM
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_embed_session_unchanged_skips_reembed():
    db = AsyncMock()
    existing = MagicMock(spec=SessionEmbedding)
    existing.content_hash = _compute_content_hash("same content")
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing
    db.execute.return_value = mock_result

    await embed_session("s1", "same content", db)

    db.add.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_embed_session_changed_updates():
    db = AsyncMock()
    existing = MagicMock(spec=SessionEmbedding)
    existing.content_hash = "old_hash"
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing
    db.execute.return_value = mock_result

    await embed_session("s1", "new content", db)

    assert existing.content_hash == _compute_content_hash("new content")
    assert len(existing.embedding) == EMBEDDING_DIM
    db.add.assert_not_called()
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_find_similar_returns_nearest():
    db = AsyncMock()
    query_emb = MagicMock(spec=SessionEmbedding)
    query_emb.embedding = [0.1] * EMBEDDING_DIM
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = query_emb
    db.execute.return_value = mock_result

    row1 = MagicMock()
    row1.session_id = "s2"
    row1.distance = 0.1
    row2 = MagicMock()
    row2.session_id = "s3"
    row2.distance = 0.3

    similar_result = MagicMock()
    similar_result.all.return_value = [row1, row2]
    db.execute.side_effect = [mock_result, similar_result]

    results = await find_similar_sessions("s1", db, top_k=2)

    assert len(results) == 2
    assert results[0]["session_id"] == "s2"
    assert results[0]["similarity"] == pytest.approx(0.9)
    assert results[1]["session_id"] == "s3"
    assert results[1]["similarity"] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_find_similar_no_embedding_returns_empty():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    db.execute.return_value = mock_result

    results = await find_similar_sessions("missing", db, top_k=5)
    assert results == []
