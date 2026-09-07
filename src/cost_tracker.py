"""
API cost tracker.

Tracks token usage and API costs across all LLM calls, writes a running log
to CSV, and raises warnings when the monthly budget threshold is approached.

For Ollama (local, free), costs are recorded as $0.00 so the log still
captures token usage for the dissertation's resource analysis section.

Usage:
    from src.cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.log_usage(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=150,
        output_tokens=320,
        query_summary="Explain VaR exposure",
    )
    print(tracker.get_report())
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.budget_config import (
    BUDGET_ALERT_THRESHOLD,
    COST_LOG_COLUMNS,
    COST_LOG_FILE,
    MONTHLY_BUDGET_USD,
)
from config.llm_config import LLM_PROVIDERS

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when a query would push spend over the monthly budget."""


class CostTracker:
    """
    Tracks cumulative API spend and logs each call to a CSV file.

    How it works:
    1. On initialisation, reads existing CSV log to restore cumulative spend
       so tracking survives restarts.
    2. Each call to log_usage() calculates cost, appends a row to the CSV,
       and checks whether the budget threshold has been breached.
    3. get_report() returns a summary dict suitable for displaying in the UI
       or logging to the dissertation appendix.

    Args:
        monthly_budget: Override the monthly budget (default from budget_config.py).
        log_file: Override the CSV log path (default from budget_config.py).
    """

    def __init__(
        self,
        monthly_budget: float = MONTHLY_BUDGET_USD,
        log_file: Path = COST_LOG_FILE,
    ) -> None:
        self.monthly_budget = monthly_budget
        self.alert_threshold = BUDGET_ALERT_THRESHOLD
        self.log_file = Path(log_file)
        self.current_spend: float = 0.0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0

        self._ensure_log_file()
        self._restore_from_log()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        query_summary: str = "",
    ) -> float:
        """
        Record one LLM API call and return the cost for that call.

        Args:
            provider: Provider name ("ollama", "openai", "anthropic").
            model: Model identifier string.
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.
            query_summary: Short description for the log (first 80 chars of query).

        Returns:
            Cost in USD for this single call.

        Raises:
            BudgetExceededError: If this call would exceed the monthly budget.
        """
        cost = self._calculate_cost(provider, input_tokens, output_tokens)

        if self.current_spend + cost > self.monthly_budget:
            raise BudgetExceededError(
                f"Monthly budget of ${self.monthly_budget:.2f} would be exceeded. "
                f"Current spend: ${self.current_spend:.4f}. "
                f"This call cost: ${cost:.4f}. "
                "Switch to Ollama (free) or increase MONTHLY_BUDGET_USD in .env."
            )

        self.current_spend += cost
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.call_count += 1

        self._write_row(provider, model, input_tokens, output_tokens, cost, query_summary)
        self._check_alert_threshold()

        logger.debug(
            "Cost logged: provider=%s model=%s in=%d out=%d cost=$%.6f cumulative=$%.4f",
            provider, model, input_tokens, output_tokens, cost, self.current_spend,
        )
        return cost

    def check_budget(self) -> bool:
        """
        Return True if spending is still within budget, False if exceeded.

        Useful for pre-flight checks before running expensive evaluation runs.
        """
        return self.current_spend < self.monthly_budget

    def get_report(self) -> dict:
        """
        Return a summary of current usage and budget status.

        Returns:
            Dict with keys: current_spend, monthly_budget, remaining_budget,
            budget_used_pct, total_input_tokens, total_output_tokens,
            call_count, alert_threshold_pct, is_over_alert.
        """
        budget_used_pct = (self.current_spend / self.monthly_budget * 100
                           if self.monthly_budget > 0 else 0.0)
        remaining = max(0.0, self.monthly_budget - self.current_spend)

        return {
            "current_spend_usd": round(self.current_spend, 4),
            "monthly_budget_usd": self.monthly_budget,
            "remaining_budget_usd": round(remaining, 4),
            "budget_used_pct": round(budget_used_pct, 1),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "call_count": self.call_count,
            "alert_threshold_pct": self.alert_threshold * 100,
            "is_over_alert": budget_used_pct >= self.alert_threshold * 100,
            "log_file": str(self.log_file),
        }

    def reset_month(self) -> None:
        """
        Reset the cumulative spend counter for a new billing month.

        Does NOT clear the CSV log — the log is cumulative for the full project.
        Only resets the in-memory counter so budget checks restart from zero.
        """
        logger.info(
            "Monthly reset: clearing $%.4f spend counter.", self.current_spend
        )
        self.current_spend = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_cost(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        """Look up per-token rates from llm_config and compute total cost."""
        cfg = LLM_PROVIDERS.get(provider, {})
        rate_in = cfg.get("cost_per_1k_input", 0.0)
        rate_out = cfg.get("cost_per_1k_output", 0.0)
        return (input_tokens / 1000 * rate_in) + (output_tokens / 1000 * rate_out)

    def _ensure_log_file(self) -> None:
        """Create the CSV log file with headers if it does not exist."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            with open(self.log_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=COST_LOG_COLUMNS)
                writer.writeheader()
            logger.info("Created cost log: %s", self.log_file)

    def _restore_from_log(self) -> None:
        """
        Re-read the CSV log to restore in-memory spend counter.

        This ensures the budget check is accurate even if the process restarts
        mid-session. Only reads the current calendar month's rows.
        """
        current_month = datetime.now().strftime("%Y-%m")
        try:
            with open(self.log_file, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("timestamp", "").startswith(current_month):
                        self.current_spend += float(row.get("cost_usd", 0))
                        self.total_input_tokens += int(row.get("input_tokens", 0))
                        self.total_output_tokens += int(row.get("output_tokens", 0))
                        self.call_count += 1
        except (FileNotFoundError, KeyError):
            pass  # New log file — nothing to restore

        if self.current_spend > 0:
            logger.info(
                "Restored $%.4f spend from log (%d calls this month).",
                self.current_spend, self.call_count,
            )

    def _write_row(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        query_summary: str,
    ) -> None:
        """Append a single row to the CSV log."""
        row = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": f"{cost:.6f}",
            "cumulative_cost_usd": f"{self.current_spend:.6f}",
            "query_summary": query_summary[:80],
        }
        with open(self.log_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COST_LOG_COLUMNS)
            writer.writerow(row)

    def _check_alert_threshold(self) -> None:
        """Log a warning if spend crosses the alert threshold."""
        if self.monthly_budget > 0:
            pct = self.current_spend / self.monthly_budget
            if pct >= self.alert_threshold:
                logger.warning(
                    "BUDGET ALERT: %.1f%% of $%.2f monthly budget used ($%.4f spent). "
                    "Consider switching to Ollama (free) for remaining development.",
                    pct * 100, self.monthly_budget, self.current_spend,
                )
