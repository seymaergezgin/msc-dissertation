"""
RAG (Retrieval-Augmented Generation) pipeline.

Combines the vector store retriever with the LLM provider to answer
natural language questions about maritime fuel risk.

Pipeline flow:
  1. Query arrives as a natural language string.
  2. The retriever fetches the top-k most relevant document chunks from ChromaDB.
  3. The chunks are formatted into a context block.
  4. The LLM is called with: system prompt + context + user query.
  5. The response and source citations are returned together.

Usage:
    from src.rag_pipeline import RAGPipeline

    pipeline = RAGPipeline()
    result = pipeline.query("What is VaR at 95% confidence?")
    print(result["answer"])
    print(result["sources"])
"""

import logging
import time
from typing import Optional

from langchain_core.documents import Document

from src.cost_tracker import CostTracker
from src.llm_provider import BaseLLMProvider, get_llm_provider
from src.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Default system prompt — agents override this with their own
DEFAULT_SYSTEM_PROMPT = """You are a maritime fuel risk analyst assistant.
Your role is to explain maritime fuel price risk metrics in clear, accessible language
for business stakeholders who may not have a quantitative background.

Guidelines:
- Base your answer ONLY on the provided context documents
- If the context does not contain enough information, say so explicitly — do not speculate
- Use plain English, avoiding unnecessary jargon
- When citing a number (e.g., VaR figure), state the source document
- Structure longer answers with a brief summary followed by detail
- Mention relevant caveats or limitations where appropriate"""


class RAGPipeline:
    """
    End-to-end RAG pipeline: retrieve relevant context, then generate a response.

    How it works:
    1. __init__: Initialises the vector store, LLM provider, and cost tracker.
       All are lazily reused across multiple queries.
    2. query(): The main method. Retrieves context, builds a prompt, calls the LLM,
       and returns both the answer and the source documents for citation.
    3. Cost is logged after every query so the budget tracker stays up to date.

    Args:
        vector_store: Pre-initialised VectorStore. Created fresh if not provided.
        llm_provider: Pre-initialised LLM provider. Created from .env if not provided.
        cost_tracker: Pre-initialised CostTracker. Created fresh if not provided.
        collection: Default ChromaDB collection to query. Can be overridden per call.
        k: Default number of context chunks to retrieve. Can be overridden per call.
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        cost_tracker: Optional[CostTracker] = None,
        collection: str = "all",
        k: int = 5,
    ) -> None:
        self.vs = vector_store or VectorStore()
        self.llm = llm_provider or get_llm_provider()
        self.tracker = cost_tracker or CostTracker()
        self.default_collection = collection
        self.default_k = k

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(
        self,
        question: str,
        collection: Optional[str] = None,
        k: Optional[int] = None,
        system_prompt: Optional[str] = None,
        log_query_summary: bool = True,
    ) -> dict:
        """
        Answer a maritime risk question using retrieved context.

        Args:
            question: The user's natural language question.
            collection: ChromaDB collection to search. Defaults to self.default_collection.
            k: Number of context chunks to retrieve. Defaults to self.default_k.
            system_prompt: Override the default system prompt (agents use this).
            log_query_summary: Whether to log this call to the cost CSV.

        Returns:
            Dict with keys:
              - "answer" (str): The LLM's response
              - "sources" (list[dict]): Citation info for each retrieved chunk
              - "context_used" (str): The raw context block shown to the LLM
              - "retrieval_count" (int): Number of chunks retrieved
              - "query" (str): The original question (for evaluation logging)
        """
        start_time = time.time()
        col = collection or self.default_collection
        num_results = k or self.default_k

        # Step 1: Retrieve relevant context
        context_docs = self.vs.query(question, collection=col, k=num_results)
        context_block = self._format_context(context_docs)

        # Step 2: Build the full prompt
        augmented_prompt = self._build_prompt(question, context_block)
        sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        # Step 3: Call the LLM
        answer = self.llm.invoke(augmented_prompt, system_prompt=sys_prompt)

        elapsed = time.time() - start_time

        # Step 4: Log cost
        if log_query_summary:
            tokens = self.llm.get_token_counts(augmented_prompt, answer)
            try:
                self.tracker.log_usage(
                    provider=self.llm.get_provider_name(),
                    model=self.llm.model,
                    input_tokens=tokens["input_tokens"],
                    output_tokens=tokens["output_tokens"],
                    query_summary=question[:80],
                )
            except Exception as e:
                logger.warning("Cost tracking failed (non-fatal): %s", e)

        logger.info(
            "RAG query answered in %.2fs | %d context chunks | provider: %s",
            elapsed, len(context_docs), self.llm.get_provider_name(),
        )

        return {
            "answer": answer,
            "sources": self._format_sources(context_docs),
            "context_used": context_block,
            "retrieval_count": len(context_docs),
            "query": question,
        }

    def query_without_rag(self, question: str, system_prompt: Optional[str] = None) -> dict:
        """
        Answer a question using only the LLM, without retrieval.

        Used in evaluation to compare RAG vs. non-RAG performance.
        Also useful as a fallback if the vector store has no relevant documents.

        Returns:
            Same dict structure as query(), but with empty sources and context.
        """
        sys_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        answer = self.llm.invoke(question, system_prompt=sys_prompt)

        tokens = self.llm.get_token_counts(question, answer)
        try:
            self.tracker.log_usage(
                provider=self.llm.get_provider_name(),
                model=self.llm.model,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                query_summary=f"[NO-RAG] {question[:70]}",
            )
        except Exception as e:
            logger.warning("Cost tracking failed (non-fatal): %s", e)

        return {
            "answer": answer,
            "sources": [],
            "context_used": "",
            "retrieval_count": 0,
            "query": question,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_context(self, docs: list[Document]) -> str:
        """
        Format retrieved document chunks into a single context block.

        Each chunk is prefixed with its source file and page number so the
        LLM can attribute claims to specific documents in its response.
        """
        if not docs:
            return "No relevant context found in the knowledge base."

        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source_file", "Unknown source")
            page = doc.metadata.get("page", "")
            page_str = f", page {page}" if page != "" else ""
            parts.append(
                f"[Context {i} — {source}{page_str}]\n{doc.page_content.strip()}"
            )
        return "\n\n---\n\n".join(parts)

    def _build_prompt(self, question: str, context: str) -> str:
        """
        Assemble the augmented prompt that is sent to the LLM.

        Structure:
          CONTEXT DOCUMENTS
          ---
          USER QUESTION
          ---
          Instruction to answer from context

        This structure is well-established in RAG literature for
        keeping context and question clearly separated.
        """
        return f"""CONTEXT DOCUMENTS:
{context}

---

USER QUESTION:
{question}

---

Please answer the question based on the context documents provided above.
If the context documents do not contain sufficient information to answer
the question accurately, state this clearly rather than speculating."""

    def _format_sources(self, docs: list[Document]) -> list[dict]:
        """
        Extract citation metadata from retrieved documents.

        Returns a list of dicts that the UI displays as source citations.
        """
        sources = []
        seen = set()
        for doc in docs:
            source_file = doc.metadata.get("source_file", "Unknown")
            page = doc.metadata.get("page", "")
            key = f"{source_file}::{page}"
            if key not in seen:
                seen.add(key)
                sources.append({
                    "file": source_file,
                    "page": page,
                    "category": doc.metadata.get("category", ""),
                    "preview": doc.page_content[:200].strip() + "...",
                })
        return sources
