"""
Unit tests for VectorStore.

Tests use a temporary directory so they never touch the production ChromaDB
in data/embeddings/. The temporary directory is cleaned up after each test.

Run with: pytest tests/test_vector_store.py -v
"""

import tempfile
from pathlib import Path

import pytest
from langchain_core.documents import Document

from src.vector_store import VectorStore


@pytest.fixture
def tmp_store(tmp_path):
    """
    Return a VectorStore backed by a temporary ChromaDB directory.

    Uses sentence-transformers (local, no API key, no Ollama needed) so
    tests run in any environment. The tmp_path fixture is provided by
    pytest and cleaned up automatically after each test.
    """
    return VectorStore(
        persist_dir=str(tmp_path / "test_chroma"),
        embedding_provider="sentence-transformers",
    )


@pytest.fixture
def sample_docs():
    """A small set of test Documents simulating maritime risk content."""
    return [
        Document(
            page_content=(
                "Value at Risk (VaR) is a statistical technique used to measure "
                "the level of financial risk within a portfolio over a specific time frame. "
                "At 95% confidence level, VaR answers: what is the maximum loss we "
                "should not expect to exceed 95% of the time?"
            ),
            metadata={"source_file": "test_var.pdf", "category": "risk_metrics", "chunk_index": 0},
        ),
        Document(
            page_content=(
                "Maritime bunker fuel hedging involves using derivative instruments "
                "such as fuel oil futures, swaps, or options to lock in fuel prices "
                "and reduce exposure to price volatility. Shipping companies may hedge "
                "30-70% of their anticipated fuel consumption."
            ),
            metadata={"source_file": "test_hedging.pdf", "category": "hedging", "chunk_index": 0},
        ),
        Document(
            page_content=(
                "The IMO 2020 regulation requires vessels to use fuel oil with a "
                "maximum sulphur content of 0.5% m/m globally, down from the previous "
                "3.5% limit. Vessels may comply by switching to VLSFO or fitting scrubbers."
            ),
            metadata={"source_file": "test_imo.pdf", "category": "maritime", "chunk_index": 0},
        ),
    ]


class TestVectorStoreBasicOperations:
    def test_initialises_without_error(self, tmp_store):
        """VectorStore should initialise and create persistence directory."""
        assert tmp_store.persist_dir.exists()

    def test_list_collections_empty_on_init(self, tmp_store):
        """All collections should return 0 before any documents are added."""
        counts = tmp_store.list_collections()
        assert all(count == 0 for count in counts.values())

    def test_add_documents_returns_count(self, tmp_store, sample_docs):
        """add_documents should return the number of documents actually inserted."""
        added = tmp_store.add_documents([sample_docs[0]], collection="risk_metrics")
        assert added == 1

    def test_add_documents_updates_collection_count(self, tmp_store, sample_docs):
        """Collection count should reflect inserted documents."""
        tmp_store.add_documents(sample_docs, collection="all")
        counts = tmp_store.list_collections()
        assert counts["all"] == len(sample_docs)

    def test_add_duplicate_documents_not_counted(self, tmp_store, sample_docs):
        """Re-adding the same documents should not increase the count."""
        tmp_store.add_documents([sample_docs[0]], collection="risk_metrics")
        second_add = tmp_store.add_documents([sample_docs[0]], collection="risk_metrics")
        assert second_add == 0

    def test_delete_collection(self, tmp_store, sample_docs):
        """Deleting a collection should reset its count to 0."""
        tmp_store.add_documents(sample_docs, collection="all")
        tmp_store.delete_collection("all")
        counts = tmp_store.list_collections()
        assert counts["all"] == 0


class TestVectorStoreRetrieval:
    def test_query_returns_documents(self, tmp_store, sample_docs):
        """query() should return Document objects."""
        tmp_store.add_documents(sample_docs, collection="all")
        results = tmp_store.query("what is Value at Risk", collection="all", k=2)
        assert len(results) > 0
        assert all(hasattr(doc, "page_content") for doc in results)

    def test_query_most_relevant_first(self, tmp_store, sample_docs):
        """The most relevant document should be ranked first."""
        tmp_store.add_documents(sample_docs, collection="all")
        results = tmp_store.query("maritime bunker fuel hedging", collection="all", k=3)
        # The hedging doc should rank highest for this query
        top_content = results[0].page_content.lower()
        assert "hedging" in top_content or "bunker" in top_content

    def test_query_respects_k_limit(self, tmp_store, sample_docs):
        """query() should return at most k documents."""
        tmp_store.add_documents(sample_docs, collection="all")
        results = tmp_store.query("fuel", collection="all", k=1)
        assert len(results) <= 1

    def test_query_with_scores_returns_tuples(self, tmp_store, sample_docs):
        """query_with_scores() should return (Document, float) tuples."""
        tmp_store.add_documents(sample_docs, collection="all")
        results = tmp_store.query_with_scores("VaR risk", collection="all", k=2)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        assert all(isinstance(score, float) for _, score in results)

    def test_get_retriever_is_callable(self, tmp_store, sample_docs):
        """get_retriever() should return an object that can invoke queries."""
        tmp_store.add_documents(sample_docs, collection="all")
        retriever = tmp_store.get_retriever(collection="all", k=2)
        results = retriever.invoke("sulphur regulation")
        assert isinstance(results, list)

    def test_unknown_collection_raises(self, tmp_store):
        """Querying an unknown collection should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown collection"):
            tmp_store.query("test", collection="nonexistent_collection")
