# System Architecture

## Overview

The platform is a RAG (Retrieval-Augmented Generation) backend split into a
synchronous **API tier** and an asynchronous **processing tier**, backed by a
single PostgreSQL database (with `pgvector`) that stores documents, chunks,
embeddings and query logs.

```mermaid
flowchart TB
  subgraph client [Clients]
    Dev[Internal developer / service]
  end

  subgraph api [API tier - FastAPI]
    Upload[POST /documents]
    QueryEp[POST /query]
    DeleteEp[DELETE /documents/id]
    GatewayEp[POST /gateway/chat]
    Health[GET /health, /readiness]
  end

  subgraph async [Async tier]
    Broker[(Redis broker)]
    Worker[Celery worker]
  end

  subgraph ml [ML services]
    Embed[sentence-transformers]
    OCR[Tesseract OCR + PyMuPDF]
    LLM[(Ollama / LLM)]
  end

  subgraph data [Storage]
    PG[(PostgreSQL + pgvector)]
    Files[(Uploaded files volume)]
  end

  Dev --> Upload --> Files
  Upload --> PG
  Upload --> Broker --> Worker
  Worker --> OCR
  Worker --> Embed
  Worker --> PG
  Dev --> QueryEp --> Embed
  QueryEp --> PG
  Dev --> DeleteEp --> PG
  Dev --> GatewayEp --> Embed
  GatewayEp --> PG
  GatewayEp --> LLM
```

## Ingestion flow (async)

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant DB as Postgres
    participant Q as Redis
    participant W as Worker
    C->>A: POST /documents (file)
    A->>DB: insert document (status=pending)
    A->>Q: enqueue process_document(id)
    A-->>C: 202 Accepted {id, status: pending}
    W->>DB: status=processing
    W->>W: extract (text or OCR)
    W->>W: chunk (text windows / code AST)
    W->>W: embed chunks (batched)
    W->>DB: bulk insert chunks + vectors
    W->>DB: status=completed (chunk_count)
    C->>A: GET /documents/{id}
    A-->>C: {status: completed, chunk_count}
```

## Query flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant E as Embedder
    participant DB as Postgres
    C->>A: POST /query {query, top_k, filters}
    A->>E: embed(query)
    E-->>A: query vector
    A->>DB: SELECT ... ORDER BY embedding <=> qvec LIMIT k (+ filters)
    DB-->>A: ranked chunks
    A->>DB: insert query_log
    A-->>C: ranked results + scores
```

## Components

- **API tier (FastAPI)** - stateless; can be scaled horizontally behind a load
  balancer. Handles validation, persistence of metadata, enqueuing jobs, and
  synchronous read paths (query, gateway).
- **Async tier (Celery + Redis)** - decouples slow work (OCR, embedding) from
  the request path. Workers scale independently based on ingestion volume.
- **ML services** - embedding model loaded once per worker/process; OCR via
  Tesseract; optional LLM via the gateway abstraction.
- **PostgreSQL + pgvector** - single source of truth. Chosen so metadata,
  full-text content and vectors live together (transactional consistency,
  simpler ops, joins between chunks and document metadata for filtering).

## Design principles

- **Async-first ingestion** so uploads return immediately and large/slow files
  (e.g. a 22-page scanned PDF) don't block clients.
- **Provider abstraction** for both embeddings and LLMs, keeping model choice a
  configuration concern.
- **Graceful degradation** - the gateway returns retrieved context even when no
  LLM is configured; query logging never fails a request.
- **Idempotent, observable processing** - document status transitions
  (`pending -> processing -> completed/failed`) with stored error messages.
