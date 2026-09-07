"""
LLM provider configuration.

Defines supported providers and their parameters. The active provider is
controlled by the LLM_PROVIDER environment variable — changing that one
variable is all that is needed to switch between Ollama, OpenAI, and Anthropic.
No code changes required.
"""

import os
from typing import Any

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

LLM_PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "temperature": 0.1,      # Low temperature for factual risk reporting
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    "openai": {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "fallback_model": "gpt-3.5-turbo",
        "temperature": 0.1,
        "cost_per_1k_input": 0.00015,   # USD, as of 2024
        "cost_per_1k_output": 0.00060,
    },
    "anthropic": {
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        "temperature": 0.1,
        # Introductory pricing through 2026-08-31 ($2/$10 per 1M tokens);
        # rises to $3/$15 per 1M after that — update if still in use then.
        "cost_per_1k_input": 0.002,
        "cost_per_1k_output": 0.010,
    },
}

# ---------------------------------------------------------------------------
# Embedding provider definitions
# ---------------------------------------------------------------------------

EMBEDDING_PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "model": os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "dimension": 768,
        "cost_per_1k_tokens": 0.0,
    },
    "openai": {
        "model": "text-embedding-3-small",
        "dimension": 1536,
        "cost_per_1k_tokens": 0.00002,
    },
    "sentence-transformers": {
        "model": "all-MiniLM-L6-v2",
        "dimension": 384,
        "cost_per_1k_tokens": 0.0,   # Runs locally
    },
}

# ---------------------------------------------------------------------------
# Active provider selection (set via .env)
# ---------------------------------------------------------------------------

DEFAULT_LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
DEFAULT_EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "ollama")


def get_llm_config(provider: str | None = None) -> dict[str, Any]:
    """
    Return configuration dict for the specified LLM provider.

    Args:
        provider: One of "ollama", "openai", "anthropic". Defaults to
                  DEFAULT_LLM_PROVIDER (from .env).

    Returns:
        Configuration dictionary for the provider.

    Raises:
        ValueError: If the provider name is not recognised.
    """
    name = provider or DEFAULT_LLM_PROVIDER
    if name not in LLM_PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider '{name}'. "
            f"Choose from: {list(LLM_PROVIDERS.keys())}"
        )
    return {"provider": name, **LLM_PROVIDERS[name]}


def get_embedding_config(provider: str | None = None) -> dict[str, Any]:
    """
    Return configuration dict for the specified embedding provider.

    Args:
        provider: One of "ollama", "openai", "sentence-transformers".
                  Defaults to DEFAULT_EMBEDDING_PROVIDER.

    Returns:
        Configuration dictionary for the provider.

    Raises:
        ValueError: If the provider name is not recognised.
    """
    name = provider or DEFAULT_EMBEDDING_PROVIDER
    if name not in EMBEDDING_PROVIDERS:
        raise ValueError(
            f"Unknown embedding provider '{name}'. "
            f"Choose from: {list(EMBEDDING_PROVIDERS.keys())}"
        )
    return {"provider": name, **EMBEDDING_PROVIDERS[name]}
