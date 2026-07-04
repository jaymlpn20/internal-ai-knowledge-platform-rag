"""Semantic retrieval: embed query, vector similarity search, metadata filtering, ranking."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.services.embeddings import embed_text

# Metadata keys handled at the document level rather than the chunk JSONB blob.
_DOCUMENT_FILTERS = {"source_type", "document_id"}


@dataclass
class SearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    source_type: str
    content: str
    score: float
    metadata: dict


def search(
    db: Session,
    query: str,
    top_k: int = 5,
    filters: dict | None = None,
) -> list[SearchResult]:
    """Run a cosine-similarity vector search with optional metadata filtering."""
    query_vector = embed_text(query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(Chunk, distance, Document.filename, Document.source_type)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.deleted_at.is_(None))
    )

    stmt = _apply_filters(stmt, filters or {})
    stmt = stmt.order_by(distance.asc()).limit(top_k)

    results: list[SearchResult] = []
    for chunk, dist, filename, source_type in db.execute(stmt).all():
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                source_type=source_type,
                content=chunk.content,
                # cosine_distance = 1 - cosine_similarity -> convert back to a [0,1] score
                score=round(1.0 - float(dist), 6),
                metadata=chunk.chunk_metadata or {},
            )
        )
    return results


def _apply_filters(stmt, filters: dict):
    for key, value in filters.items():
        if value is None:
            continue
        if key == "source_type":
            stmt = stmt.where(Document.source_type == value)
        elif key == "document_id":
            stmt = stmt.where(Document.id == value)
        else:
            # Generic equality against the chunk JSONB metadata.
            stmt = stmt.where(Chunk.chunk_metadata[key].astext == str(value))
    return stmt
