"""Vector store for session context embeddings.

Provides deterministic hash-based pseudo-embeddings with pgvector-backed
persistence.  In production, replace _pseudo_embed with a real embedding
model (e.g. sentence-transformers all-MiniLM-L6-v2 → 384-d, or
multilingual-e5-small → 768-d).
"""

import hashlib
import struct
from datetime import datetime, timezone

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

EMBEDDING_DIM = 768


class SessionEmbedding(Base):
    """Stores embeddings for session text."""

    __tablename__ = "session_embeddings"

    session_id = Column(String(100), primary_key=True)
    embedding = Column(Vector(EMBEDDING_DIM))
    content_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _compute_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pseudo_embed(text: str) -> list[float]:
    """Deterministic pseudo-embedding derived from content hash.

    Production should replace this with a real encoder.
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    seed = struct.unpack("<I", h[:4])[0]
    rng = np.random.RandomState(int(seed))
    vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


async def embed_session(
    session_id: str, text: str, db: AsyncSession
) -> None:
    """Embed *text* for *session_id* and upsert into session_embeddings.

    Skips re-embedding when the content hash is unchanged.
    """
    content_hash = _compute_content_hash(text)

    result = await db.execute(
        select(SessionEmbedding).filter(
            SessionEmbedding.session_id == session_id
        )
    )
    existing = result.scalars().first()

    if existing and existing.content_hash == content_hash:
        return

    embedding = _pseudo_embed(text)

    if existing:
        existing.embedding = embedding
        existing.content_hash = content_hash
    else:
        db.add(
            SessionEmbedding(
                session_id=session_id,
                embedding=embedding,
                content_hash=content_hash,
            )
        )
    await db.flush()


async def find_similar_sessions(
    session_id: str, db: AsyncSession, top_k: int = 5
) -> list[dict]:
    """Return *top_k* most similar sessions via cosine distance.

    Each result dict has keys ``session_id`` and ``similarity`` (0–1).
    """
    result = await db.execute(
        select(SessionEmbedding).filter(
            SessionEmbedding.session_id == session_id
        )
    )
    query_emb = result.scalars().first()

    if not query_emb or query_emb.embedding is None:
        return []

    distance_col = SessionEmbedding.embedding.cosine_distance(
        query_emb.embedding
    ).label("distance")

    stmt = (
        select(SessionEmbedding.session_id, distance_col)
        .filter(SessionEmbedding.session_id != session_id)
        .order_by(distance_col)
        .limit(top_k)
    )

    rows = (await db.execute(stmt)).all()
    return [
        {"session_id": row.session_id, "similarity": 1.0 - row.distance}
        for row in rows
    ]
