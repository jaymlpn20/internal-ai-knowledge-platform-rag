# Scaling Strategy & Trade-offs

Target scale: ~100 internal developers. The design is deliberately simple at
this scale while leaving clear, low-risk paths to grow.

## Chunking strategy

- **Text/PDF**: token-aware sliding windows (~500 tokens, ~50 overlap using
  `tiktoken`). Overlap preserves cross-boundary context; page numbers are kept in
  metadata for citations.
- **Code**: AST-based splitting (Python) into module header, class header, and
  per-method chunks, each tagged with `symbol` and line range. This aligns
  retrievable units with how developers think about code, dramatically improving
  code search relevance vs. naive line windows. Non-Python/unparseable files
  fall back to token windows.
- **Trade-off**: smaller chunks improve precision but increase row count and can
  fragment context; the overlap + symbol-aware code splitting balances this.

## Embedding lifecycle

- Generated in the worker at ingest time, batched for throughput, L2-normalized
  for cosine similarity, stored inline on `chunks.embedding`.
- Model is a configuration value (`EMBEDDING_MODEL`/`EMBEDDING_DIM`). Changing
  models requires re-embedding; a background "reindex" job would iterate
  documents and recompute vectors into a new column/table, then swap.
- **Trade-off**: local models (no API cost, reproducible, private) vs. hosted
  models (higher quality, network dependency). The abstraction keeps this a swap.

## Similarity search approach

- `pgvector` HNSW index with cosine distance (`<=>`), top-K via `ORDER BY ...
  LIMIT k`. HNSW gives strong recall/latency and supports incremental inserts.
- Metadata filters are applied in the same SQL statement (document-level columns
  + GIN-indexed JSONB), so filtering and ranking happen in one pass.

## Vector database choice

Postgres + `pgvector` was chosen over a dedicated vector DB (Pinecone, Weaviate,
Milvus, Qdrant) because at this scale it offers:

- One system for metadata, content and vectors (transactional consistency, joins
  for filtering, simpler ops/backups).
- No extra infrastructure or vendor lock-in; runs anywhere.

**Trade-off**: dedicated vector DBs scale to billions of vectors and offer
advanced ANN tuning. Migration path: the retrieval layer is isolated in
`services/retrieval.py`, so swapping the backend is contained.

## Ranking / reranking strategy

- Baseline: cosine similarity ranking from the vector index.
- Optional improvements (documented, not all enabled): score normalization,
  metadata boosts (e.g. prefer code symbols for code queries), and a
  cross-encoder reranker over the top-N candidates for higher precision at the
  cost of extra latency. Hybrid search (BM25 + vector) via Postgres full-text is
  a natural addition.

## Failure handling

- **Ingestion**: status machine (`pending -> processing -> completed/failed`)
  with stored error text; Celery retries transient failures; OCR failures on a
  page don't abort the whole document.
- **Query**: query logging is best-effort and never fails the request.
- **Gateway**: graceful degradation to retrieved context when the LLM is
  unavailable; provider errors are surfaced in `note`, not thrown to the client.
- **Delete**: hard delete tolerates a missing file and still cleans the DB.

## Scaling paths

| Dimension | Now | Next |
| --- | --- | --- |
| API | Single container | Horizontal replicas behind a load balancer (stateless) |
| Ingestion throughput | 1 worker (concurrency 2) | More Celery workers / dedicated GPU embedding workers |
| Vector volume | Single Postgres + HNSW | Partition `chunks`; read replicas; or dedicated vector DB |
| Query latency | Direct DB search | Redis result cache for hot queries |
| Storage | Local volume | Object storage (S3) for uploaded files |
| Embeddings | CPU model | Batched GPU inference / hosted embedding API |

## Key assumptions & trade-offs summary

- Local-first for reproducibility and zero external dependencies during review.
- Single Postgres instance is sufficient and operationally simplest at ~100
  users; the code isolates retrieval/embeddings so scaling out is incremental.
- Async processing prioritizes responsive uploads over immediate availability of
  search results (eventual consistency between upload and queryability).
