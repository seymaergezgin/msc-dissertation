"""
Embedding generation with support for multiple providers.

Three embedding backends are available, controlled by EMBEDDING_PROVIDER in .env:
  - "ollama"               : nomic-embed-text via local Ollama (free, 768-dim)
  - "openai"               : text-embedding-3-small via OpenAI API (1536-dim)
  - "sentence-transformers": all-MiniLM-L6-v2 running locally (free, 384-dim)

All three return the same interface: a list of float vectors.

Usage:
    from src.embeddings import get_embedding_function

    embed_fn = get_embedding_function()           # Uses .env default
    vectors = embed_fn.embed_documents(["text1", "text2"])
    query_vec = embed_fn.embed_query("explain VaR")
"""

import logging
import os
from typing import Any

from config.llm_config import get_embedding_config
from src.llm_provider import is_ollama_available

logger = logging.getLogger(__name__)


def get_embedding_function(provider: str | None = None) -> Any:
    """
    Factory: return a LangChain-compatible embedding object for the given provider.

    LangChain's ChromaDB integration requires an object with .embed_documents()
    and .embed_query() methods. All three implementations provide this interface.

    Args:
        provider: One of "ollama", "openai", "sentence-transformers".
                  Defaults to EMBEDDING_PROVIDER from .env.

    Returns:
        A LangChain embedding object ready to use with ChromaDB.

    Raises:
        RuntimeError: If no embedding provider is available.
    """
    config = get_embedding_config(provider)
    name = config["provider"]

    if name == "ollama":
        return _get_ollama_embeddings(config)
    elif name == "openai":
        return _get_openai_embeddings(config)
    elif name == "sentence-transformers":
        return _get_sentence_transformer_embeddings(config)
    else:
        raise ValueError(f"Unknown embedding provider: {name}")


def _get_ollama_embeddings(config: dict[str, Any]) -> Any:
    """
    Return an OllamaEmbeddings instance.

    Falls back to sentence-transformers if Ollama is not running, so the
    system can still generate embeddings during offline development without
    any API costs.
    """
    base_url = config.get("base_url", "http://localhost:11434")

    if not is_ollama_available(base_url):
        logger.warning(
            "Ollama not running — falling back to sentence-transformers for embeddings. "
            "Start Ollama with 'ollama serve' to use nomic-embed-text."
        )
        return _get_sentence_transformer_embeddings(
            {"model": "all-MiniLM-L6-v2", "provider": "sentence-transformers"}
        )

    from langchain_ollama import OllamaEmbeddings

    model = config.get("model", "nomic-embed-text")
    logger.info("Using Ollama embeddings: %s @ %s", model, base_url)
    return OllamaEmbeddings(model=model, base_url=base_url)


def _get_openai_embeddings(config: dict[str, Any]) -> Any:
    """Return an OpenAIEmbeddings instance (requires OPENAI_API_KEY)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Add it to .env or switch to "
            "EMBEDDING_PROVIDER=ollama or EMBEDDING_PROVIDER=sentence-transformers."
        )

    from langchain_openai import OpenAIEmbeddings

    model = config.get("model", "text-embedding-3-small")
    logger.info("Using OpenAI embeddings: %s", model)
    return OpenAIEmbeddings(model=model, openai_api_key=api_key)


def _get_sentence_transformer_embeddings(config: dict[str, Any]) -> Any:
    """
    Return a HuggingFaceEmbeddings instance using sentence-transformers.

    Runs entirely locally — no API key, no cost, no internet required.
    Produces 384-dimensional vectors (all-MiniLM-L6-v2).

    Note: first call downloads ~90MB model from HuggingFace. Subsequent
    calls use the cached model.
    """
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        from langchain_community.embeddings import HuggingFaceEmbeddings  # type: ignore[no-redef]

    model = config.get("model", "all-MiniLM-L6-v2")
    logger.info("Using sentence-transformers embeddings: %s (local, free)", model)
    return HuggingFaceEmbeddings(
        model_name=model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def get_embedding_dimension(provider: str | None = None) -> int:
    """
    Return the vector dimension for the active embedding provider.

    ChromaDB needs consistent dimensions — mixing providers will break
    an existing collection. This is used in vector_store.py to validate
    consistency when loading an existing store.
    """
    config = get_embedding_config(provider)
    return config.get("dimension", 768)
