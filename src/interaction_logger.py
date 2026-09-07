"""
Interaction logger — persists every question/answer exchange for
dissertation evidence, supervisor review, and Phase 6 evaluation scoring.

Why this exists: prior to Phase 6, only `src/cost_tracker.py` persisted
anything about live queries, and it only tracks cost accounting (tokens,
$ spent, and a query string truncated to ~80 characters). There was no
record of the full question, the full answer, which agent handled it,
its sources, or how long it took — the only place that information ever
existed was scattered across terminal output and hand-written markdown
test-result docs. This module gives every interaction a permanent,
structured, queryable record.

Format: one JSON object per line (JSONL) at
data/interaction_logs/interactions.jsonl. JSONL (not CSV) because answers
are long free text and sources are a nested list — both awkward to
represent as CSV cells, natural as JSON.

Integration point: `src/orchestrator.py` calls `log_interaction()` once
per `Orchestrator.answer()` call — this is the single choke point for
both live UI usage (ui/app.py always goes through the orchestrator) and
Phase 6's routing-accuracy evaluation run. The Phase 6 ablation run
(RAG+ vs RAG vs LLM-only), which calls agents/pipelines directly and
bypasses the orchestrator, calls `log_interaction()` itself so those
interactions are captured too — see `evaluation/run_evaluation.py`.

Usage:
    from src.interaction_logger import log_interaction, read_interactions

    log_interaction(
        query="What is our current VaR?",
        answer="**SUMMARY** ...",
        agent="Risk Explainer",
        routed_to="Risk Explainer",
        routing_reason="Matched keyword(s) ['var'] -> routed to Risk Explainer",
        confidence="high",
        collection="risk_metrics",
        sources=[{"file": "Value_at_risk.pdf", "page": 3}],
        retrieval_count=5,
        response_time_s=4.2,
        provider="openai",
        model="gpt-4o-mini",
        cost_usd=0.0004,
    )

    all_rows = read_interactions()  # -> list[dict], most recent last
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

INTERACTION_LOG_FILE: Path = DATA_DIR / "interaction_logs" / "interactions.jsonl"


def log_interaction(
    query: str,
    answer: str,
    agent: str,
    *,
    routed_to: Optional[str] = None,
    routing_reason: Optional[str] = None,
    confidence: Optional[str] = None,
    collection: Optional[str] = None,
    sources: Optional[list[dict]] = None,
    retrieval_count: Optional[int] = None,
    response_time_s: Optional[float] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    cost_usd: Optional[float] = None,
    eval_metadata: Optional[dict] = None,
    log_file: Optional[Path] = None,
) -> None:
    """
    Append one interaction to the JSONL log.

    Args:
        query: The original user question (full text, not truncated).
        answer: The agent's full response text.
        agent: Name of the agent that generated the answer (e.g. "Risk Explainer").
        routed_to: Which agent the orchestrator routed to, if called via
            Orchestrator.answer(). None for direct agent/pipeline calls
            (e.g. the Phase 6 ablation run).
        routing_reason: Why that agent was chosen (orchestrator calls only).
        confidence: Routing confidence — "high"/"medium"/"low" (orchestrator
            calls only).
        collection: The ChromaDB collection actually queried for this answer.
        sources: List of source citation dicts (file, page, etc.).
        retrieval_count: Number of chunks retrieved.
        response_time_s: Time taken to generate the response, in seconds.
        provider: LLM provider used ("openai", "ollama", "anthropic").
        model: Model identifier string (e.g. "gpt-4o-mini").
        cost_usd: Cost of this specific call in USD.
        eval_metadata: Optional dict for Phase 6 evaluation runs — e.g.
            {"query_id": "Q001", "category": "factual", "difficulty": "easy",
             "expected_agent": "risk_explainer", "mode": "rag_plus"}.
            None for ordinary live/UI usage.
        log_file: Override the log file path (tests use this to avoid
            writing into the real project log).

    This function is intentionally non-fatal: a logging failure (disk full,
    permissions, a non-JSON-serialisable value) must never break a live
    query. Failures are caught and logged as a WARNING.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "answer": answer,
        "agent": agent,
        "routed_to": routed_to,
        "routing_reason": routing_reason,
        "confidence": confidence,
        "collection": collection,
        "sources": sources or [],
        "retrieval_count": retrieval_count,
        "response_time_s": response_time_s,
        "provider": provider,
        "model": model,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
    }
    if eval_metadata:
        entry["eval_metadata"] = eval_metadata

    path = log_file or INTERACTION_LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Interaction logging failed (non-fatal): %s", exc)


def read_interactions(log_file: Optional[Path] = None) -> list[dict]:
    """
    Read all logged interactions back as a list of dicts, oldest first.

    Returns an empty list if the log file does not exist yet, so callers
    (e.g. a future dashboard or evaluation report) don't need to special-case
    a fresh install.
    """
    path = log_file or INTERACTION_LOG_FILE
    if not path.exists():
        return []

    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
