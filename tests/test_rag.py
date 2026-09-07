"""
Unit tests for the RAG pipeline.

LLM calls are mocked so tests run instantly without Ollama or API keys.
The vector store uses sentence-transformers (local, free) in a temp directory.

Run with: pytest tests/test_rag.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.rag_pipeline import RAGPipeline
from src.vector_store import VectorStore


@pytest.fixture
def mock_llm():
    """
    A mock LLM provider that returns a fixed response.

    Mocking the LLM lets us test the pipeline's retrieval and prompt
    assembly logic without making real LLM calls. All tests run offline.
    """
    llm = MagicMock()
    llm.invoke.return_value = (
        "At 95% confidence level, the portfolio VaR over 10 days is $376,329. "
        "This means there is a 5% probability of losing more than this amount."
    )
    llm.get_provider_name.return_value = "mock"
    llm.model = "mock-model"
    llm.get_token_counts.return_value = {"input_tokens": 100, "output_tokens": 50}
    return llm


@pytest.fixture
def mock_tracker():
    """A mock cost tracker that does nothing (avoids CSV writes in tests)."""
    tracker = MagicMock()
    tracker.log_usage.return_value = 0.0
    return tracker


@pytest.fixture
def tmp_store_with_docs(tmp_path):
    """VectorStore pre-loaded with sample maritime risk documents."""
    store = VectorStore(
        persist_dir=str(tmp_path / "rag_test_chroma"),
        embedding_provider="sentence-transformers",
    )
    docs = [
        Document(
            page_content=(
                "The portfolio 10-day VaR at 95% confidence is $376,329. "
                "This represents the maximum expected loss over 10 trading days "
                "at the 95% confidence level using the variance-covariance method."
            ),
            metadata={"source_file": "risk_metrics.json", "category": "risk_metrics", "chunk_index": 0},
        ),
        Document(
            page_content=(
                "CVaR (Conditional Value at Risk), also known as Expected Shortfall, "
                "is $481,701. This is the average loss expected in the worst 5% of scenarios, "
                "providing a more complete picture of tail risk than VaR alone."
            ),
            metadata={"source_file": "risk_metrics.json", "category": "risk_metrics", "chunk_index": 1},
        ),
        Document(
            page_content=(
                "The current VLSFO price is $470.73 per metric ton. The hedge ratio "
                "for the fleet averages 48%, meaning 48% of anticipated fuel consumption "
                "is covered by derivative instruments."
            ),
            metadata={"source_file": "risk_metrics.json", "category": "hedging", "chunk_index": 2},
        ),
    ]
    store.add_documents(docs, collection="all")
    return store


class TestRAGPipelineSetup:
    def test_initialises_with_defaults(self, tmp_path, mock_llm, mock_tracker):
        """RAGPipeline should initialise without error using injected components."""
        store = VectorStore(
            persist_dir=str(tmp_path / "init_test"),
            embedding_provider="sentence-transformers",
        )
        pipeline = RAGPipeline(
            vector_store=store,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        assert pipeline is not None
        assert pipeline.default_collection == "all"
        assert pipeline.default_k == 5


class TestRAGPipelineQuery:
    def test_query_returns_expected_keys(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """query() should return a dict with all required keys."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        result = pipeline.query("What is the portfolio VaR?")
        assert set(result.keys()) == {"answer", "sources", "context_used", "retrieval_count", "query"}

    def test_query_calls_llm_once(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """The LLM should be called exactly once per query."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        pipeline.query("What is CVaR?")
        assert mock_llm.invoke.call_count == 1

    def test_query_returns_non_empty_answer(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """answer field should be the LLM's response string."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        result = pipeline.query("Explain VaR")
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_query_retrieves_context_documents(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """retrieval_count should be > 0 when documents are in the store."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        result = pipeline.query("VaR risk metrics")
        assert result["retrieval_count"] > 0

    def test_query_includes_context_in_prompt(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """The LLM should be called with a prompt that contains the retrieved context."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        pipeline.query("VaR 95%")
        # The first positional argument to llm.invoke should be the augmented prompt
        call_args = mock_llm.invoke.call_args
        prompt_used = call_args[0][0]
        assert "CONTEXT DOCUMENTS" in prompt_used
        assert "USER QUESTION" in prompt_used

    def test_query_sources_list_has_correct_structure(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """sources should be a list of dicts with 'file' and 'preview' keys."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        result = pipeline.query("fuel price hedge ratio")
        for source in result["sources"]:
            assert "file" in source
            assert "preview" in source

    def test_query_logs_cost(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """log_usage should be called on the cost tracker after each query."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        pipeline.query("VaR question")
        mock_tracker.log_usage.assert_called_once()

    def test_query_without_rag_returns_empty_sources(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """query_without_rag should return empty sources and context."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        result = pipeline.query_without_rag("What is VaR?")
        assert result["sources"] == []
        assert result["context_used"] == ""
        assert result["retrieval_count"] == 0

    def test_query_with_custom_system_prompt(self, tmp_store_with_docs, mock_llm, mock_tracker):
        """A custom system prompt should be passed through to the LLM."""
        pipeline = RAGPipeline(
            vector_store=tmp_store_with_docs,
            llm_provider=mock_llm,
            cost_tracker=mock_tracker,
        )
        custom_prompt = "You are a specialist in maritime law."
        pipeline.query("Explain sulphur cap", system_prompt=custom_prompt)
        call_kwargs = mock_llm.invoke.call_args[1]
        assert call_kwargs.get("system_prompt") == custom_prompt
