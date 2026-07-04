"""Unit tests for the AI gateway helpers."""
from app.services import gateway


def test_build_rag_prompt_includes_context_and_question():
    prompt = gateway.build_rag_prompt("What is X?", ["ctx one", "ctx two"])
    assert "What is X?" in prompt
    assert "ctx one" in prompt
    assert "ctx two" in prompt
    assert "Source 1" in prompt


def test_provider_available_reflects_config(monkeypatch):
    monkeypatch.setattr(gateway.settings, "llm_provider", "none")
    assert gateway.provider_available() is False
    monkeypatch.setattr(gateway.settings, "llm_provider", "ollama")
    assert gateway.provider_available() is True
