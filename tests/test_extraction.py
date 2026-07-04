"""Unit tests for source-type detection and text/code extraction."""
import os

from app.services.extraction import detect_source_type, extract


def test_detect_source_type():
    assert detect_source_type("a.pdf") == "pdf"
    assert detect_source_type("README.md") == "markdown"
    assert detect_source_type("main.py") == "code"
    assert detect_source_type("notes.txt") == "text"
    assert detect_source_type("weird.xyz") == "text"


def test_extract_code_file(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    segments = extract(str(path), "code")
    assert len(segments) == 1
    assert "def hello" in segments[0].text
    assert segments[0].metadata["language"] == "python"


def test_extract_text_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("some plain text content", encoding="utf-8")

    segments = extract(str(path), "text")
    assert len(segments) == 1
    assert "plain text" in segments[0].text


def test_extract_empty_file_returns_nothing(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert extract(str(path), "text") == []
