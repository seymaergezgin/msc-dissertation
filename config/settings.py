"""
General application settings.

Loads all configuration from environment variables (via .env file).
This is the single source of truth for runtime configuration — no
values should be hardcoded in other modules.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Project Identity
# ---------------------------------------------------------------------------
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Maritime Risk Narrative System")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
COST_LOGS_DIR = DATA_DIR / "cost_logs"

# Ensure runtime directories exist
for _dir in [DATA_DIR, DOCUMENTS_DIR, SYNTHETIC_DIR, EMBEDDINGS_DIR, COST_LOGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)
logger.info("Settings loaded. Project root: %s", PROJECT_ROOT)

# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR: str = os.getenv(
    "CHROMA_PERSIST_DIR",
    str(EMBEDDINGS_DIR / "chroma_store"),
)
