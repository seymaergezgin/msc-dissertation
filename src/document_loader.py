"""
Document loader: reads files from data/documents/ and loads them into ChromaDB.

Supports:
  - PDF files (via langchain's PyPDFLoader)
  - Markdown / plain text files
  - Selective loading by category (risk_metrics, hedging, maritime)

Chunking strategy:
  - Chunk size: 800 tokens (~600 words) — large enough for a full paragraph,
    small enough that each chunk focuses on one concept.
  - Overlap: 100 tokens — avoids cutting a sentence mid-thought at chunk boundaries.
  - Metadata attached to every chunk: source file, category, page number, chunk index.
    This metadata is returned with every RAG result so the UI can show citations.

Usage:
    from src.document_loader import DocumentLoader
    from src.vector_store import VectorStore

    vs = VectorStore()
    loader = DocumentLoader(vs)

    # Load all documents
    loader.load_all()

    # Or load a specific category
    loader.load_category("hedging")

    # Check what's been loaded
    print(vs.list_collections())
"""

import logging
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import DOCUMENTS_DIR
from src.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Chunking parameters — tuned for maritime finance prose
CHUNK_SIZE = 800        # characters (not tokens — simpler, no tokeniser dependency)
CHUNK_OVERLAP = 100     # characters

# Chunks with more than this fraction of non-ASCII characters are mostly corrupted
# mathematical notation from PDF extraction (e.g., "Q1¡c p var[±V] = e¢±§ e¢").
# These chunks degrade retrieval quality and are skipped.
MAX_NON_ASCII_RATIO = 0.15

# Map directory names to collection names
CATEGORY_MAP = {
    "risk_metrics": "risk_metrics",
    "hedging": "hedging",
    "maritime": "maritime",
}


class DocumentLoader:
    """
    Loads documents from data/documents/ into the vector store.

    How it works:
    1. Scans each category subdirectory for supported files (PDF, MD, TXT).
    2. Loads each file's text using the appropriate LangChain loader.
    3. Splits text into overlapping chunks using RecursiveCharacterTextSplitter.
    4. Attaches metadata (source, category, page, chunk_index) to every chunk.
    5. Calls VectorStore.add_documents() which handles deduplication.

    Large files (e.g., Stopford Maritime Economics, 840 pages) are handled
    gracefully — they take time on first load but are cached in ChromaDB
    for all subsequent queries.

    Args:
        vector_store: An initialised VectorStore instance.
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self.vs = vector_store
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_all(self, force_reload: bool = False) -> dict[str, int]:
        """
        Load all document categories into their respective collections.

        Args:
            force_reload: If True, delete existing collections and reload from scratch.
                          Use when documents have been updated or added.

        Returns:
            Dict of {category: number_of_chunks_added}.
        """
        totals = {}
        for category in CATEGORY_MAP:
            totals[category] = self.load_category(category, force_reload=force_reload)
        logger.info("Total chunks loaded: %d", sum(totals.values()))
        return totals

    def load_category(
        self, category: str, force_reload: bool = False
    ) -> int:
        """
        Load all documents in one category directory.

        Args:
            category: "risk_metrics", "hedging", or "maritime".
            force_reload: Delete existing collection before loading.

        Returns:
            Total number of chunks added to the collection.
        """
        if category not in CATEGORY_MAP:
            raise ValueError(
                f"Unknown category '{category}'. "
                f"Choose from: {list(CATEGORY_MAP.keys())}"
            )

        category_dir = DOCUMENTS_DIR / category
        if not category_dir.exists():
            logger.warning("Category directory not found: %s", category_dir)
            return 0

        if force_reload:
            self.vs.delete_collection(category)
            logger.info("Deleted collection '%s' for reload.", category)

        files = list(category_dir.glob("*.pdf")) + \
                list(category_dir.glob("*.md")) + \
                list(category_dir.glob("*.txt"))

        if not files:
            logger.warning("No documents found in %s", category_dir)
            return 0

        logger.info("Loading %d files from %s...", len(files), category_dir)
        total_added = 0

        for file_path in files:
            try:
                chunks = self._load_file(file_path, category)
                if chunks:
                    added = self.vs.add_documents(chunks, collection=category)
                    # Also add to the merged "all" collection
                    self.vs.add_documents(chunks, collection="all")
                    total_added += added
                    logger.info(
                        "  %s → %d chunks (%d new)", file_path.name, len(chunks), added
                    )
            except Exception as e:
                logger.error("Failed to load %s: %s", file_path.name, e)

        return total_added

    def load_file(self, file_path: str | Path, category: str) -> int:
        """
        Load a single file into the named category collection.

        Useful for adding individual documents without re-loading the entire category.
        """
        path = Path(file_path)
        chunks = self._load_file(path, category)
        if not chunks:
            return 0
        added = self.vs.add_documents(chunks, collection=category)
        self.vs.add_documents(chunks, collection="all")
        return added

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file(self, file_path: Path, category: str) -> list[Document]:
        """
        Load one file and return chunked Document objects with metadata.

        Dispatches to the correct loader based on file extension.
        """
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            raw_docs = self._load_pdf(file_path)
        elif suffix in {".md", ".txt"}:
            raw_docs = self._load_text(file_path)
        else:
            logger.warning("Unsupported file type: %s — skipping.", file_path.name)
            return []

        if not raw_docs:
            return []

        # Split into chunks
        all_chunks = self.splitter.split_documents(raw_docs)

        # Filter out corrupted chunks (pages dominated by PDF math encoding artifacts)
        chunks = [c for c in all_chunks if self._is_quality_chunk(c.page_content)]
        skipped = len(all_chunks) - len(chunks)
        if skipped:
            logger.debug(
                "  Skipped %d/%d chunks from %s (>%.0f%% non-ASCII characters — likely formula pages).",
                skipped, len(all_chunks), file_path.name, MAX_NON_ASCII_RATIO * 100,
            )

        # Attach category and chunk index metadata to every chunk
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                "category": category,
                "chunk_index": i,
                "source_file": file_path.name,
                "source": str(file_path),
                "total_chunks": len(chunks),
            })

        return chunks

    def _load_pdf(self, file_path: Path) -> list[Document]:
        """
        Load a PDF using PyPDFLoader (page-by-page).

        PyPDF is already installed (we added it for the data evaluation step).
        Each page becomes one Document with 'page' metadata.
        """
        try:
            from langchain_community.document_loaders import PyPDFLoader

            loader = PyPDFLoader(str(file_path))
            docs = loader.load()
            logger.debug("  PDF loaded: %s (%d pages)", file_path.name, len(docs))
            return docs
        except ImportError:
            # Fallback: use pypdf directly if langchain_community loader fails
            import pypdf

            reader = pypdf.PdfReader(str(file_path))
            docs = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={"source": str(file_path), "page": i},
                        )
                    )
            return docs

    def _is_quality_chunk(self, text: str) -> bool:
        """
        Return False for chunks that are mostly corrupted PDF extraction artifacts.

        Why this exists:
        Mathematical textbooks (e.g., the Deutsch VaR textbook) have pages dense
        with LaTeX formulas. PyPDF extracts these as garbled character sequences
        such as "Q1¡c p var[±V] = e¢±§ e¢", where special characters are
        mangled. These chunks cannot be understood by an LLM and degrade retrieval
        quality by matching formula-heavy queries with garbage context.

        The heuristic: if more than MAX_NON_ASCII_RATIO (15%) of characters in a
        chunk are non-ASCII, the chunk is likely dominated by formula artifacts.
        Plain English prose from financial/regulatory documents typically has <3%.
        """
        if len(text.strip()) < 50:
            return False
        non_ascii = sum(1 for c in text if ord(c) > 127)
        return (non_ascii / len(text)) < MAX_NON_ASCII_RATIO

    def _load_text(self, file_path: Path) -> list[Document]:
        """Load a Markdown or plain text file as a single Document."""
        from langchain_community.document_loaders import TextLoader

        loader = TextLoader(str(file_path), encoding="utf-8")
        return loader.load()

    def get_loading_summary(self) -> str:
        """Return a human-readable summary of what is currently in the vector store."""
        collections = self.vs.list_collections()
        lines = ["Vector Store Summary:"]
        for name, count in collections.items():
            lines.append(f"  {name:20s}: {count:>5d} chunks")
        return "\n".join(lines)
