"""Pydantic schemas for the document, query and gateway APIs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: Optional[str] = None
    source_type: str
    status: str
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    chunk_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DocumentAccepted(BaseModel):
    id: uuid.UUID
    filename: str
    source_type: str
    status: str
    message: str = "Document accepted for asynchronous processing."


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentResponse]


class DeleteResponse(BaseModel):
    id: uuid.UUID
    deleted: bool
    mode: str  # soft | hard
    chunks_removed: int = 0
    message: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: Optional[int] = None
    filters: dict[str, Any] = Field(default_factory=dict)


class QueryResultItem(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    source_type: str
    content: str
    score: float
    metadata: dict = Field(default_factory=dict)


class QueryResponse(BaseModel):
    query: str
    top_k: int
    count: int
    latency_ms: int
    results: list[QueryResultItem]


class GatewayRequest(BaseModel):
    message: str = Field(..., min_length=1)
    use_rag: bool = True
    top_k: Optional[int] = None
    filters: dict[str, Any] = Field(default_factory=dict)


class GatewayResponse(BaseModel):
    answer: Optional[str] = None
    provider: str
    used_rag: bool
    context: list[QueryResultItem] = Field(default_factory=list)
    note: Optional[str] = None
