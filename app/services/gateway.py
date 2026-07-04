"""Centralized AI Gateway: a provider-agnostic interface to LLMs.

Keeps model access in one place so callers never talk to a provider directly.
Currently supports a local Ollama backend and degrades gracefully when no
provider is configured (returning retrieved context only).
"""
from __future__ import annotations

from app.config import get_settings

settings = get_settings()


class GatewayError(RuntimeError):
    pass


def provider_available() -> bool:
    return settings.llm_provider not in ("none", "", None)


def generate(prompt: str, system: str | None = None) -> str:
    """Generate a completion via the configured provider."""
    provider = settings.llm_provider
    if provider == "ollama":
        return _ollama_generate(prompt, system)
    raise GatewayError(f"No LLM provider configured (llm_provider={provider!r}).")


def _ollama_generate(prompt: str, system: str | None) -> str:
    import httpx

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        response = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:  # network / provider failure
        raise GatewayError(f"Ollama request failed: {exc}") from exc

    return response.json().get("response", "").strip()


def build_rag_prompt(question: str, contexts: list[str]) -> str:
    """Assemble a grounded prompt from retrieved context chunks."""
    joined = "\n\n---\n\n".join(f"[Source {i + 1}]\n{c}" for i, c in enumerate(contexts))
    return (
        "Answer the question using ONLY the context below. "
        "If the answer is not in the context, say you don't know.\n\n"
        f"Context:\n{joined}\n\nQuestion: {question}\n\nAnswer:"
    )
