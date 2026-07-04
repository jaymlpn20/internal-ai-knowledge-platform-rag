"""Initial schema: pgvector extension, documents, chunks, query_logs.

Revision ID: 0001_init
Revises:
Create Date: 2026-07-04
"""
from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

# Must match app.config.Settings.embedding_dim (all-MiniLM-L6-v2 -> 384).
EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE documents (
            id UUID PRIMARY KEY,
            filename VARCHAR(512) NOT NULL,
            content_type VARCHAR(128),
            source_type VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            error TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            file_path VARCHAR(1024),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX ix_documents_status ON documents (status)")
    op.execute("CREATE INDEX ix_documents_source_type ON documents (source_type)")
    op.execute("CREATE INDEX ix_documents_deleted_at ON documents (deleted_at)")

    op.execute(
        f"""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            embedding vector({EMBEDDING_DIM}),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_chunks_document_id ON chunks (document_id)")
    op.execute("CREATE INDEX ix_chunks_metadata ON chunks USING gin (metadata)")
    # HNSW index for approximate nearest-neighbour cosine search (pgvector >= 0.5).
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.execute(
        """
        CREATE TABLE query_logs (
            id UUID PRIMARY KEY,
            query_text TEXT NOT NULL,
            top_k INTEGER NOT NULL,
            filters JSONB NOT NULL DEFAULT '{}'::jsonb,
            result_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_query_logs_created_at ON query_logs (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS query_logs")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
