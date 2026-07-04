"""Asynchronous ingestion pipeline: extract -> chunk -> embed -> persist."""
from __future__ import annotations

import logging

from app.db.models import Chunk, Document
from app.db.session import SessionLocal
from app.services.chunking import build_chunks, count_tokens
from app.services.embeddings import embed_texts
from app.services.extraction import extract
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="process_document", bind=True, max_retries=2, default_retry_delay=10)
def process_document(self, document_id: str) -> dict:
    """Process a single uploaded document end to end.

    On any failure the document is marked ``failed`` with the error message so
    the API can surface it; the task is also retried a couple of times for
    transient errors (e.g. the embedding model still warming up).
    """
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("process_document: document %s not found", document_id)
            return {"document_id": document_id, "status": "missing"}

        if document.deleted_at is not None:
            return {"document_id": document_id, "status": "deleted"}

        document.status = "processing"
        db.commit()

        segments = extract(document.file_path, document.source_type)
        chunks = build_chunks(segments, document.source_type)

        if not chunks:
            document.status = "failed"
            document.error = "No content could be extracted from the document."
            db.commit()
            return {"document_id": document_id, "status": "failed", "chunks": 0}

        vectors = embed_texts([c.content for c in chunks])

        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            db.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk.content,
                    token_count=count_tokens(chunk.content),
                    chunk_metadata=chunk.metadata,
                    embedding=vector,
                )
            )

        document.status = "completed"
        document.error = None
        document.doc_metadata = {
            **(document.doc_metadata or {}),
            "chunk_count": len(chunks),
            "segment_count": len(segments),
        }
        db.commit()
        logger.info("process_document: %s completed with %d chunks", document_id, len(chunks))
        return {"document_id": document_id, "status": "completed", "chunks": len(chunks)}

    except Exception as exc:  # noqa: BLE001 - we want to record any failure
        logger.exception("process_document failed for %s", document_id)
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.status = "failed"
            document.error = str(exc)[:2000]
            db.commit()
        raise
    finally:
        db.close()
