# API Specification

Base URL: `http://localhost:8000`. Interactive OpenAPI docs: `/docs`.

## POST /documents

Upload a document for asynchronous ingestion. Multipart form field `file`.
Accepts PDF, Markdown, text and code files.

Response `202 Accepted`:

```json
{
  "id": "0c1f...",
  "filename": "Source_Code_Sample (2).py",
  "source_type": "code",
  "status": "pending",
  "message": "Document accepted for asynchronous processing."
}
```

Errors: `400` (missing filename), `413` (file too large).

## GET /documents/{id}

Fetch processing status and metadata.

```json
{
  "id": "0c1f...",
  "filename": "Source_Code_Sample (2).py",
  "source_type": "code",
  "status": "completed",
  "error": null,
  "metadata": {"chunk_count": 7, "segment_count": 1, "size_bytes": 7366},
  "chunk_count": 7,
  "created_at": "2026-07-04T00:00:00Z",
  "updated_at": "2026-07-04T00:00:05Z"
}
```

`status` is one of `pending | processing | completed | failed`.

## GET /documents

List documents. Query params: `status`, `source_type`, `include_deleted`
(bool), `limit` (<=200), `offset`.

```json
{ "total": 2, "items": [ { "id": "...", "status": "completed", ... } ] }
```

## POST /query

Semantic search.

Request:

```json
{
  "query": "how does proxy recovery work?",
  "top_k": 3,
  "filters": {"source_type": "code"}
}
```

`filters` supports `source_type`, `document_id`, and any chunk metadata key
(e.g. `symbol`, `page`, `language`) as equality filters.

Response:

```json
{
  "query": "how does proxy recovery work?",
  "top_k": 3,
  "count": 3,
  "latency_ms": 24,
  "results": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "filename": "Source_Code_Sample (2).py",
      "source_type": "code",
      "content": "def _calculate_current_score(self, stats): ...",
      "score": 0.71,
      "metadata": {"symbol": "DecayProxyRotator._calculate_current_score", "kind": "method"}
    }
  ]
}
```

`score` is cosine similarity in `[0, 1]` (higher is more relevant).

## DELETE /documents/{id}

Delete a document. Query param `hard` (default `false`).

- Soft (default): excluded from search, `deleted_at` set, recoverable.
- Hard (`?hard=true`): file, row, chunks and embeddings permanently removed.

```json
{ "id": "...", "deleted": true, "mode": "soft", "chunks_removed": 0,
  "message": "Document soft-deleted and excluded from search." }
```

## POST /gateway/chat

Centralized LLM access with optional RAG grounding.

Request:

```json
{ "message": "How is a proxy penalized on failure?", "use_rag": true, "top_k": 4,
  "filters": {"source_type": "code"} }
```

Response (no LLM configured - context only):

```json
{
  "answer": null,
  "provider": "none",
  "used_rag": true,
  "context": [ { "chunk_id": "...", "content": "...", "score": 0.68, ... } ],
  "note": "No LLM provider configured; returning retrieved context only."
}
```

When `LLM_PROVIDER=ollama`, `answer` contains the grounded completion.

## GET /health, GET /readiness

- `/health` -> `{"status": "ok"}` (liveness).
- `/readiness` -> checks database and Redis connectivity.
