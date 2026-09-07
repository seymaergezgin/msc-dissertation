"""
Budget and cost tracking configuration.

Centralises all cost-related settings so they can be adjusted in one place.
These values are read by CostTracker in src/cost_tracker.py.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Budget limits
# ---------------------------------------------------------------------------

MONTHLY_BUDGET_USD: float = float(os.getenv("MONTHLY_BUDGET_USD", "10.00"))
BUDGET_ALERT_THRESHOLD: float = float(os.getenv("BUDGET_ALERT_THRESHOLD", "0.80"))

# ---------------------------------------------------------------------------
# Log file location
# ---------------------------------------------------------------------------

_project_root = Path(__file__).resolve().parent.parent
COST_LOG_FILE: Path = _project_root / "data" / "cost_logs" / "api_costs.csv"

# CSV column names — used by CostTracker to write headers
COST_LOG_COLUMNS: list[str] = [
    "timestamp",
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "cumulative_cost_usd",
    "query_summary",
]
