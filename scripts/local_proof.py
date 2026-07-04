"""Standalone, infra-free proof of the RAG pipeline.

Runs the *real* services (extraction -> chunking -> embeddings -> cosine
retrieval) in-process against the two task files, without Postgres/Redis/Docker.
The retrieval math is identical to the pgvector cosine path; only the storage
layer differs. Useful as a quick, reproducible demonstration.

Usage:
    python scripts/local_proof.py
"""
from __future__ import annotations

import glob
import sys

import numpy as np

from app.services.chunking import build_chunks
from app.services.embeddings import embed_text, embed_texts
from app.services.extraction import detect_source_type, extract


def ingest(path: str):
    source_type = detect_source_type(path)
    segments = extract(path, source_type)
    chunks = build_chunks(segments, source_type)
    matrix = np.array(embed_texts([c.content for c in chunks])) if chunks else np.zeros((0, 384))
    return source_type, chunks, matrix


def search(query: str, chunks, matrix, top_k: int = 3):
    if len(chunks) == 0:
        return []
    q = np.array(embed_text(query))
    sims = matrix @ q  # vectors are L2-normalized -> dot product == cosine similarity
    order = np.argsort(sims)[::-1][:top_k]
    return [(float(sims[i]), chunks[i]) for i in order]


def show(query: str, chunks, matrix, top_k: int = 3):
    print(f"\nQ: {query}")
    hits = search(query, chunks, matrix, top_k)
    if not hits:
        print("  (no chunks available)")
        return
    for rank, (score, chunk) in enumerate(hits, start=1):
        symbol = chunk.metadata.get("symbol")
        page = chunk.metadata.get("page")
        loc = f" symbol={symbol}" if symbol else (f" page={page}" if page else "")
        snippet = " ".join(chunk.content.split())[:160]
        print(f"  {rank}. score={score:.3f}{loc}")
        print(f"     {snippet}")


def _discover(pattern: str) -> str | None:
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


def main() -> int:
    code_path = _discover("Source_Code_Sample*.py")
    pdf_path = _discover("Knowledge_Base_Sample*.pdf")

    print("=" * 70)
    print("LOCAL RAG PIPELINE PROOF (no Docker / no DB)")
    print("=" * 70)

    if code_path:
        print(f"\n### Ingesting code file: {code_path}")
        st, chunks, matrix = ingest(code_path)
        print(f"  source_type={st}, chunks={len(chunks)}")
        print("  symbols: " + ", ".join(str(c.metadata.get('symbol')) for c in chunks))
        show("How does the proxy score recover over time and how are failures penalized?", chunks, matrix)
        show("How is a user agent selected and burned when used?", chunks, matrix)
        show("Where is the proxy list loaded from disk?", chunks, matrix)
    else:
        print("Code sample not found.")

    if pdf_path:
        print(f"\n### Ingesting PDF (scanned -> OCR): {pdf_path}")
        try:
            st, chunks, matrix = ingest(pdf_path)
            print(f"  source_type={st}, chunks={len(chunks)}")
            show("Summarize the main topic of the knowledge base document.", chunks, matrix)
            show("What are the key concepts or definitions described?", chunks, matrix)
        except Exception as exc:  # OCR binary missing locally, etc.
            print(f"  PDF ingest skipped: {exc}")
            print("  (OCR requires the Tesseract binary; it is bundled in the Docker image.)")
    else:
        print("PDF sample not found.")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
