"""
ChromaDB vector store operations.

Provides a thin wrapper around ChromaDB that:
  - Uses persistent storage (data/embeddings/chroma_store/) so the index
    survives restarts without re-ingesting all documents
  - Maintains separate named collections per document category
    (risk_metrics, hedging, maritime) so agents can query only
    the relevant subset
  - Exposes a simple interface: add_documents(), query(), list_collections()

Usage:
    from src.vector_store import VectorStore

    vs = VectorStore()
    vs.add_documents(docs, collection="hedging")
    results = vs.query("How do I hedge VLSFO exposure?", collection="hedging")
"""

import logging
from pathlib import Path
from typing import Optional

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config.settings import CHROMA_PERSIST_DIR
from src.embeddings import get_embedding_function

logger = logging.getLogger(__name__)

# Ollama crashes when embedding too many chunks in a single API call.
# Sending more than ~50 chunks at once causes the internal tokenizer to
# run out of memory and reset the connection (HTTP 400, "connection reset by peer").
# This batch size keeps each request well within Ollama's limits.
EMBED_BATCH_SIZE = 50

# Named collections — one per document category
COLLECTIONS = {
    "risk_metrics": "maritime_risk_metrics",
    "hedging": "maritime_hedging",
    "maritime": "maritime_domain",
    "all": "maritime_all",
}


class VectorStore:
    """
    Persistent ChromaDB vector store with per-category collections.

    How it works:
    1. On initialisation, creates (or reopens) a PersistentClient pointing at
       CHROMA_PERSIST_DIR. The directory is created automatically if missing.
    2. Each document category gets its own named collection. Queries can target
       a specific collection or the merged "all" collection.
    3. The LangChain Chroma wrapper handles embedding → storage → retrieval,
       so agents interact only with LangChain Document objects — not raw vectors.

    Args:
        persist_dir: Override the persistence directory (default from settings.py).
        embedding_provider: Override the embedding provider (default from .env).
    """

    def __init__(
        self,
        persist_dir: str | None = None,
        embedding_provider: str | None = None,
    ) -> None:
        self.persist_dir = Path(persist_dir or CHROMA_PERSIST_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self.embed_fn = get_embedding_function(embedding_provider)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))

        # Cache of open LangChain Chroma wrappers, keyed by collection name
        self._stores: dict[str, Chroma] = {}

        logger.info("VectorStore initialised at: %s", self.persist_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_documents(
        self,
        documents: list[Document],
        collection: str = "all",
    ) -> int:
        """
        Embed and store a list of LangChain Documents in the named collection.

        Documents are deduplicated by source path + chunk index so re-running
        the loader does not create duplicate entries.

        Args:
            documents: List of LangChain Document objects (with page_content
                       and metadata).
            collection: One of "risk_metrics", "hedging", "maritime", "all".

        Returns:
            Number of documents actually added (after deduplication).

        Raises:
            ValueError: If the collection name is not recognised.
        """
        store = self._get_or_create_store(collection)
        collection_name = COLLECTIONS.get(collection, collection)

        # Build globally unique IDs: source path + chunk_index + enumerate position
        # The enumerate position (::i) guarantees uniqueness within a batch even when
        # multiple chunks share the same source/chunk_index (e.g., test fixtures).
        ids = [
            (
                f"{doc.metadata.get('source', doc.metadata.get('source_file', 'unknown'))}"
                f"::{doc.metadata.get('chunk_index', i)}::{i}"
            )
            for i, doc in enumerate(documents)
        ]

        # Check which IDs already exist and skip them
        existing = set(self._client.get_collection(collection_name).get()["ids"])
        new_docs = [doc for doc, id_ in zip(documents, ids) if id_ not in existing]
        new_ids = [id_ for id_ in ids if id_ not in existing]

        if not new_docs:
            logger.info("All %d documents already in collection '%s'.", len(documents), collection)
            return 0

        # Process in small batches to prevent Ollama's tokenizer from crashing
        # on large document sets (e.g., Stopford 840-page textbook).
        added_count = 0
        for batch_start in range(0, len(new_docs), EMBED_BATCH_SIZE):
            batch_docs = new_docs[batch_start:batch_start + EMBED_BATCH_SIZE]
            batch_ids = new_ids[batch_start:batch_start + EMBED_BATCH_SIZE]
            store.add_documents(batch_docs, ids=batch_ids)
            added_count += len(batch_docs)
            logger.debug(
                "  Embedded batch %d–%d / %d for '%s'",
                batch_start + 1, batch_start + len(batch_docs), len(new_docs), collection,
            )

        logger.info("Added %d/%d documents to collection '%s'.", added_count, len(documents), collection)
        return added_count

    def query(
        self,
        query_text: str,
        collection: str = "all",
        k: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[Document]:
        """
        Retrieve the k most semantically similar documents for a query.

        Args:
            query_text: The user's natural language question.
            collection: Which collection to search. Defaults to "all".
            k: Number of results to return. Default 5.
            filter_metadata: Optional ChromaDB where-clause to filter by
                             metadata fields (e.g., {"category": "hedging"}).

        Returns:
            List of Document objects, sorted by relevance (most relevant first).
        """
        store = self._get_or_create_store(collection)
        search_kwargs = {"k": k}
        if filter_metadata:
            search_kwargs["filter"] = filter_metadata

        retriever = store.as_retriever(search_kwargs=search_kwargs)
        results = retriever.invoke(query_text)

        logger.debug(
            "Query '%s...' returned %d results from '%s'.",
            query_text[:50], len(results), collection,
        )
        return results

    def query_with_scores(
        self,
        query_text: str,
        collection: str = "all",
        k: int = 5,
    ) -> list[tuple[Document, float]]:
        """
        Retrieve documents with their cosine similarity scores.

        Returns:
            List of (Document, score) tuples. Score is in [0, 1] where
            1.0 means identical. Used in evaluation to assess retrieval quality.
        """
        store = self._get_or_create_store(collection)
        return store.similarity_search_with_score(query_text, k=k)

    def list_collections(self) -> dict[str, int]:
        """
        Return each collection name and the number of documents it contains.

        Useful for verifying that documents were loaded correctly.
        """
        result = {}
        for short_name, full_name in COLLECTIONS.items():
            try:
                col = self._client.get_collection(full_name)
                result[short_name] = col.count()
            except Exception:
                result[short_name] = 0
        return result

    def delete_collection(self, collection: str) -> None:
        """
        Delete a collection and all its embeddings.

        Use this when you want to re-ingest a category from scratch
        (e.g., after updating documents).

        Args:
            collection: Short name ("risk_metrics", "hedging", "maritime", "all").
        """
        full_name = COLLECTIONS.get(collection, collection)
        try:
            self._client.delete_collection(full_name)
            self._stores.pop(collection, None)
            logger.info("Deleted collection: %s", full_name)
        except Exception as e:
            logger.warning("Could not delete collection '%s': %s", full_name, e)

    def get_retriever(self, collection: str = "all", k: int = 5):
        """
        Return a LangChain retriever for use in LCEL chains.

        This is what the RAG pipeline uses to plug the vector store into
        a LangChain chain.

        Args:
            collection: Collection to retrieve from.
            k: Number of documents to return per query.

        Returns:
            A LangChain VectorStoreRetriever.
        """
        store = self._get_or_create_store(collection)
        return store.as_retriever(search_kwargs={"k": k})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_store(self, collection: str) -> Chroma:
        """
        Return a cached LangChain Chroma wrapper for the named collection.

        Creates the ChromaDB collection on first access; returns the cached
        wrapper on subsequent calls. This avoids recreating the embedding
        model on every query.
        """
        if collection not in self._stores:
            full_name = COLLECTIONS.get(collection)
            if not full_name:
                raise ValueError(
                    f"Unknown collection '{collection}'. "
                    f"Choose from: {list(COLLECTIONS.keys())}"
                )
            self._stores[collection] = Chroma(
                client=self._client,
                collection_name=full_name,
                embedding_function=self.embed_fn,
            )
        return self._stores[collection]
