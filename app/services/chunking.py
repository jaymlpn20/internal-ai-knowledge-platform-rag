"""Chunking strategies: token-aware text splitting and AST-based code splitting."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import lru_cache

from app.config import get_settings
from app.services.extraction import ExtractedSegment

settings = get_settings()


@dataclass
class ChunkData:
    content: str
    metadata: dict = field(default_factory=dict)


@lru_cache
def _encoder():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def chunk_text(
    text: str,
    base_metadata: dict | None = None,
    size: int | None = None,
    overlap: int | None = None,
) -> list[ChunkData]:
    """Split text into overlapping token windows.

    Overlap preserves context across boundaries so a concept spanning two
    windows is still retrievable.
    """
    base_metadata = base_metadata or {}
    size = size or settings.chunk_size_tokens
    overlap = overlap if overlap is not None else settings.chunk_overlap_tokens
    if overlap >= size:
        overlap = size // 4

    enc = _encoder()
    tokens = enc.encode(text)
    if not tokens:
        return []

    # Preserve an explicit chunk_type (e.g. a code fallback) if the caller set one.
    chunk_type = base_metadata.get("chunk_type", "text")

    chunks: list[ChunkData] = []
    start = 0
    while start < len(tokens):
        end = min(start + size, len(tokens))
        piece = enc.decode(tokens[start:end]).strip()
        if piece:
            chunks.append(ChunkData(content=piece, metadata={**base_metadata, "chunk_type": chunk_type}))
        if end >= len(tokens):
            break
        start = end - overlap
    return chunks


def chunk_code(source: str, base_metadata: dict | None = None) -> list[ChunkData]:
    """Split source code by top-level classes/functions using the Python AST.

    Classes are further split into a header chunk plus one chunk per method so
    each retrievable unit maps to a meaningful symbol. Falls back to token
    chunking for non-Python or unparseable sources.
    """
    base_metadata = base_metadata or {}
    language = base_metadata.get("language", "unknown")
    if language != "python":
        return chunk_text(source, {**base_metadata, "chunk_type": "code"})

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return chunk_text(source, {**base_metadata, "chunk_type": "code"})

    lines = source.splitlines()
    chunks: list[ChunkData] = []
    covered_start = None

    # Capture leading module-level code (imports, constants) before the first def/class.
    body_defs = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if body_defs:
        first_line = min(n.lineno for n in body_defs)
        header = "\n".join(lines[: first_line - 1]).strip()
        if header:
            chunks.append(
                ChunkData(
                    content=header,
                    metadata={**base_metadata, "chunk_type": "code", "symbol": "<module>", "kind": "module"},
                )
            )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            chunks.extend(_class_chunks(node, lines, base_metadata))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.append(_symbol_chunk(node, node.name, "function", lines, base_metadata))

    if not chunks:
        return chunk_text(source, {**base_metadata, "chunk_type": "code"})
    return chunks


def _symbol_chunk(node, name: str, kind: str, lines: list[str], base_metadata: dict) -> ChunkData:
    start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno)
    segment = "\n".join(lines[start:end])
    return ChunkData(
        content=segment,
        metadata={
            **base_metadata,
            "chunk_type": "code",
            "symbol": name,
            "kind": kind,
            "start_line": node.lineno,
            "end_line": end,
        },
    )


def _class_chunks(node: ast.ClassDef, lines: list[str], base_metadata: dict) -> list[ChunkData]:
    method_nodes = [
        n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    chunks: list[ChunkData] = []

    header_end = method_nodes[0].lineno - 1 if method_nodes else getattr(node, "end_lineno", node.lineno)
    header = "\n".join(lines[node.lineno - 1 : header_end]).strip()
    if header:
        chunks.append(
            ChunkData(
                content=header,
                metadata={
                    **base_metadata,
                    "chunk_type": "code",
                    "symbol": node.name,
                    "kind": "class",
                    "start_line": node.lineno,
                    "end_line": header_end,
                },
            )
        )

    for method in method_nodes:
        chunks.append(
            _symbol_chunk(method, f"{node.name}.{method.name}", "method", lines, base_metadata)
        )
    return chunks


def build_chunks(segments: list[ExtractedSegment], source_type: str) -> list[ChunkData]:
    """Turn extracted segments into chunks based on source type."""
    result: list[ChunkData] = []
    for segment in segments:
        if source_type == "code":
            result.extend(chunk_code(segment.text, segment.metadata))
        else:
            result.extend(chunk_text(segment.text, segment.metadata))
    return result
