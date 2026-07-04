"""AI Gateway API: centralized, provider-agnostic access to LLMs with optional RAG."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.schemas.documents import GatewayRequest, GatewayResponse, QueryResultItem
from app.services import gateway as gateway_service
from app.services.retrieval import search

router = APIRouter(prefix="/gateway", tags=["gateway"])
settings = get_settings()


@router.post("/chat", response_model=GatewayResponse)
def gateway_chat(payload: GatewayRequest, db: Session = Depends(get_db)) -> GatewayResponse:
    """Chat through the centralized gateway, optionally grounded on retrieved chunks."""
    context_items: list[QueryResultItem] = []
    contexts: list[str] = []

    if payload.use_rag:
        top_k = min(payload.top_k or settings.default_top_k, settings.max_top_k)
        results = search(db, payload.message, top_k=top_k, filters=payload.filters)
        for r in results:
            context_items.append(
                QueryResultItem(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    filename=r.filename,
                    source_type=r.source_type,
                    content=r.content,
                    score=r.score,
                    metadata=r.metadata,
                )
            )
            contexts.append(r.content)

    # If no provider is configured, degrade gracefully: return retrieved context.
    if not gateway_service.provider_available():
        return GatewayResponse(
            answer=None,
            provider=settings.llm_provider,
            used_rag=payload.use_rag,
            context=context_items,
            note="No LLM provider configured; returning retrieved context only.",
        )

    prompt = (
        gateway_service.build_rag_prompt(payload.message, contexts)
        if payload.use_rag and contexts
        else payload.message
    )

    try:
        answer = gateway_service.generate(prompt)
        note = None
    except gateway_service.GatewayError as exc:
        answer = None
        note = f"LLM generation failed: {exc}"

    return GatewayResponse(
        answer=answer,
        provider=settings.llm_provider,
        used_rag=payload.use_rag,
        context=context_items,
        note=note,
    )
