"""Query API: natural-language semantic search over ingested knowledge."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import QueryLog
from app.db.session import get_db
from app.schemas.documents import QueryRequest, QueryResponse, QueryResultItem
from app.services.retrieval import search

router = APIRouter(tags=["query"])
settings = get_settings()


@router.post("/query", response_model=QueryResponse)
def query_documents(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    top_k = min(payload.top_k or settings.default_top_k, settings.max_top_k)

    started = time.perf_counter()
    results = search(db, payload.query, top_k=top_k, filters=payload.filters)
    latency_ms = int((time.perf_counter() - started) * 1000)

    items = [
        QueryResultItem(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            filename=r.filename,
            source_type=r.source_type,
            content=r.content,
            score=r.score,
            metadata=r.metadata,
        )
        for r in results
    ]

    # Best-effort query logging; never fail the request because logging failed.
    try:
        db.add(
            QueryLog(
                query_text=payload.query,
                top_k=top_k,
                filters=payload.filters or {},
                result_chunk_ids=[str(r.chunk_id) for r in results],
                latency_ms=latency_ms,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return QueryResponse(
        query=payload.query,
        top_k=top_k,
        count=len(items),
        latency_ms=latency_ms,
        results=items,
    )
