"""Document APIs: upload (async), status, list and delete (soft/hard)."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, Document
from app.db.session import get_db
from app.schemas.documents import (
    DeleteResponse,
    DocumentAccepted,
    DocumentListResponse,
    DocumentResponse,
)
from app.services.extraction import detect_source_type
from app.workers.tasks import process_document

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()


def _chunk_count(db: Session, document_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == document_id)) or 0


def _to_response(db: Session, document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        content_type=document.content_type,
        source_type=document.source_type,
        status=document.status,
        error=document.error,
        metadata=document.doc_metadata or {},
        chunk_count=_chunk_count(db, document.id),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentAccepted)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentAccepted:
    """Accept a document, persist it, and enqueue asynchronous processing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB > {settings.max_upload_mb} MB).",
        )

    source_type = detect_source_type(file.filename)

    os.makedirs(settings.upload_dir, exist_ok=True)
    document_id = uuid.uuid4()
    stored_name = f"{document_id}{os.path.splitext(file.filename)[1].lower()}"
    file_path = os.path.join(settings.upload_dir, stored_name)
    with open(file_path, "wb") as fh:
        fh.write(contents)

    document = Document(
        id=document_id,
        filename=file.filename,
        content_type=file.content_type,
        source_type=source_type,
        status="pending",
        file_path=file_path,
        doc_metadata={"size_bytes": len(contents)},
    )
    db.add(document)
    db.commit()

    # Hand off to the worker. Processing happens out of the request path.
    process_document.delay(str(document_id))

    return DocumentAccepted(
        id=document_id,
        filename=file.filename,
        source_type=source_type,
        status="pending",
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    conditions = []
    if not include_deleted:
        conditions.append(Document.deleted_at.is_(None))
    if status_filter:
        conditions.append(Document.status == status_filter)
    if source_type:
        conditions.append(Document.source_type == source_type)

    total = db.scalar(select(func.count(Document.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(Document)
        .where(*conditions)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return DocumentListResponse(total=total, items=[_to_response(db, d) for d in rows])


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentResponse:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _to_response(db, document)


@router.delete("/{document_id}", response_model=DeleteResponse)
def delete_document(
    document_id: uuid.UUID,
    hard: bool = Query(default=False, description="Permanently remove data when true."),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    """Delete a document.

    Soft delete (default) marks ``deleted_at`` so the document is excluded from
    search and listings while remaining auditable/recoverable. Hard delete
    removes the chunks/embeddings, the stored file, and the row. Partial
    failures (e.g. the file already gone) are handled gracefully.
    """
    document = db.get(Document, document_id)
    if document is None or (document.deleted_at is not None and not hard):
        raise HTTPException(status_code=404, detail="Document not found.")

    if not hard:
        document.deleted_at = func.now()
        document.status = "deleted"
        db.commit()
        return DeleteResponse(
            id=document_id,
            deleted=True,
            mode="soft",
            message="Document soft-deleted and excluded from search.",
        )

    chunks_removed = _chunk_count(db, document_id)
    warnings: list[str] = []

    # Remove the stored file first; missing file should not block DB cleanup.
    if document.file_path and os.path.exists(document.file_path):
        try:
            os.remove(document.file_path)
        except OSError as exc:
            warnings.append(f"file removal failed: {exc}")

    # Chunks are removed via ON DELETE CASCADE when the document row is deleted.
    db.delete(document)
    db.commit()

    message = "Document and embeddings permanently deleted."
    if warnings:
        message += " Warnings: " + "; ".join(warnings)
    return DeleteResponse(
        id=document_id,
        deleted=True,
        mode="hard",
        chunks_removed=chunks_removed,
        message=message,
    )
