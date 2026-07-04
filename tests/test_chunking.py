"""Unit tests for the chunking strategies (no DB or model required)."""
from app.services.chunking import chunk_code, chunk_text, count_tokens

SAMPLE_CODE = '''
import os

CONST = 42

class Rotator:
    """A rotator."""

    def __init__(self, items):
        self.items = items

    def pick(self):
        return self.items[0]


def run():
    return Rotator([1, 2, 3]).pick()
'''


def test_chunk_code_splits_by_symbol():
    chunks = chunk_code(SAMPLE_CODE, {"language": "python"})
    symbols = {c.metadata.get("symbol") for c in chunks}

    # Module header, class header, its methods, and the top-level function.
    assert "<module>" in symbols
    assert "Rotator" in symbols
    assert "Rotator.__init__" in symbols
    assert "Rotator.pick" in symbols
    assert "run" in symbols

    for c in chunks:
        assert c.metadata["chunk_type"] == "code"


def test_chunk_code_records_line_numbers():
    chunks = chunk_code(SAMPLE_CODE, {"language": "python"})
    pick = next(c for c in chunks if c.metadata.get("symbol") == "Rotator.pick")
    assert pick.metadata["start_line"] <= pick.metadata["end_line"]
    assert "def pick" in pick.content


def test_chunk_code_non_python_falls_back_to_text():
    chunks = chunk_code("console.log('hi')", {"language": "javascript"})
    assert len(chunks) >= 1
    assert chunks[0].metadata["chunk_type"] == "code"


def test_chunk_text_produces_overlapping_windows():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(text, {"page": 1}, size=100, overlap=20)
    assert len(chunks) > 1
    assert all(c.metadata["page"] == 1 for c in chunks)
    assert all(c.metadata["chunk_type"] == "text" for c in chunks)


def test_count_tokens_positive():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0
