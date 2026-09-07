"""
Model Monitor Agent.

Answers questions about the health of the VaR model itself: whether its
assumptions still hold, signs of drift, and when recalibration is needed.
This agent reviews the *model*, not the portfolio's risk exposure — its
audience is the quant team and risk committee, not business stakeholders.

Architecture — RAG+ pattern (same as RiskExplainerAgent, see agents/risk_explainer.py
for the full rationale):

  1. LIVE PORTFOLIO DATA — the VaR methodology block from
     data/synthetic/risk_metrics.json (method name, confidence levels,
     time horizon, volatility basis, correlation assumption). This agent's
     context formatter foregrounds these calibration parameters — the
     inputs a model reviewer needs — rather than the resulting VaR/CVaR
     dollar figures the Risk Explainer emphasises.

  2. DOMAIN KNOWLEDGE — chunks retrieved from the ChromaDB "risk_metrics"
     collection (same collection as Risk Explainer — both agents reason
     about VaR methodology, just for different audiences and purposes).

Usage:
    from agents.model_monitor import ModelMonitorAgent

    agent = ModelMonitorAgent()
    result = agent.answer("Are our VaR model assumptions still valid?")
    print(result["answer"])
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config.settings import DATA_DIR
from prompts.system_prompts import MODEL_MONITOR_SYSTEM_PROMPT
from src.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)

RISK_METRICS_PATH = DATA_DIR / "synthetic" / "risk_metrics.json"


class ModelMonitorAgent(BaseAgent):
    """
    Reviews VaR model health: assumptions, drift indicators, recalibration needs.

    How it works:
    1. On init: loads the same portfolio risk snapshot as the other agents.
    2. On answer(): retrieves the top-5 most relevant chunks from the
       "risk_metrics" ChromaDB collection.
    3. Prepends the live methodology block ("CURRENT PORTFOLIO DATA") before
       the retrieved methodology literature.
    4. Calls the LLM with the MODEL_MONITOR_SYSTEM_PROMPT persona.
    5. Returns the answer with source citations and a methodology summary.

    Args:
        pipeline: Pre-initialised RAGPipeline. If None, one is created
                  using collection="risk_metrics".
    """

    name = "Model Monitor"
    collection = "risk_metrics"

    def __init__(self, pipeline: Optional[RAGPipeline] = None) -> None:
        super().__init__(pipeline=pipeline or RAGPipeline(collection=self.collection))
        self._risk_snapshot = self._load_risk_snapshot()
        if self._risk_snapshot:
            method = self._risk_snapshot.get("methodology", {})
            logger.info(
                "Risk snapshot loaded: VaR method '%s' | window: %s",
                method.get("var_method", "N/A"),
                method.get("volatility_basis", "N/A"),
            )
        else:
            logger.warning(
                "Risk snapshot not found at %s — agent will answer from knowledge base only.",
                RISK_METRICS_PATH,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer(self, query: str) -> dict:
        """
        Answer a model-methodology query using live calibration data + RAG context.

        Args:
            query: Natural language question about model assumptions or drift.

        Returns:
            Dict with keys:
              - "answer" (str): Plain-English response in structured format
              - "sources" (list[dict]): Retrieved chunk citations
              - "context_used" (str): Full context block shown to the LLM
              - "retrieval_count" (int): Number of chunks retrieved
              - "query" (str): Original question
              - "agent" (str): "Model Monitor"
              - "portfolio_snapshot" (dict): Key methodology figures summary
              - "response_time_s" (float): Time to generate the response
        """
        start_time = time.time()

        # Step 1: Retrieve relevant methodology literature from ChromaDB
        context_docs = self.pipeline.vs.query(
            query, collection=self.collection, k=5
        )

        # Step 2: Build combined context — methodology data first, then retrieved docs
        portfolio_context = self._format_portfolio_as_context()
        docs_context = self.pipeline._format_context(context_docs)

        if portfolio_context:
            full_context = f"{portfolio_context}\n\n---\n\n{docs_context}"
        else:
            full_context = docs_context

        # Step 3: Build the augmented prompt and call the LLM
        prompt = self.pipeline._build_prompt(query, full_context)
        answer_text = self.pipeline.llm.invoke(prompt, system_prompt=self.system_prompt)

        elapsed = time.time() - start_time

        # Step 4: Log cost (non-fatal if tracker fails)
        tokens = self.pipeline.llm.get_token_counts(prompt, answer_text)
        try:
            self.pipeline.tracker.log_usage(
                provider=self.pipeline.llm.get_provider_name(),
                model=self.pipeline.llm.model,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                query_summary=f"[ModelMonitor] {query[:70]}",
            )
        except Exception as cost_err:
            logger.warning("Cost tracking failed (non-fatal): %s", cost_err)

        logger.info(
            "ModelMonitorAgent: '%s...' answered in %.2fs | provider: %s | %d chunks retrieved",
            query[:50], elapsed, self.pipeline.llm.get_provider_name(), len(context_docs),
        )

        return {
            "answer": answer_text,
            "sources": self.pipeline._format_sources(context_docs),
            "context_used": full_context,
            "retrieval_count": len(context_docs),
            "query": query,
            "agent": self.name,
            "portfolio_snapshot": self._get_snapshot_summary(),
            "response_time_s": round(elapsed, 2),
        }

    @property
    def system_prompt(self) -> str:
        return MODEL_MONITOR_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_risk_snapshot(self) -> dict:
        """
        Load the portfolio risk snapshot from the synthetic data file.

        Returns an empty dict if the file does not exist, allowing the
        agent to degrade gracefully to knowledge-base-only responses.
        """
        if not RISK_METRICS_PATH.exists():
            return {}
        with open(RISK_METRICS_PATH) as f:
            return json.load(f)

    def _format_portfolio_as_context(self) -> str:
        """
        Format the risk snapshot as a plain-text context block, emphasising
        VaR model calibration parameters rather than resulting dollar figures.

        Uses the same underlying risk_metrics.json as the other agents, but
        surfaces the "methodology" block plus the daily/annualised volatility
        observed across the fleet — the inputs a model reviewer checks for
        drift, rather than the output VaR/CVaR figures.

        Returns:
            Formatted multi-line string, or empty string if no snapshot loaded.
        """
        if not self._risk_snapshot:
            return ""

        snap = self._risk_snapshot
        method = snap.get("methodology", {})
        vessels = snap.get("vessels", [])

        lines = [
            f"[CURRENT PORTFOLIO DATA — snapshot date: {snap.get('snapshot_date', 'N/A')}]",
            "",
            "VaR MODEL CONFIGURATION:",
            f"  Method:                  {method.get('var_method', 'N/A')}",
            f"  Confidence levels:       {', '.join(method.get('confidence_levels', []))}",
            f"  Time horizon:            {method.get('time_horizon', 'N/A')}",
            f"  Volatility basis:        {method.get('volatility_basis', 'N/A')}",
            f"  Correlation assumption:  {method.get('correlation_assumption', 'N/A')}",
            "",
            "OBSERVED VOLATILITY (per vessel, current calibration):",
        ]

        for v in vessels:
            rm = v.get("risk_metrics", {})
            lines.append(
                f"  {v['vessel_name']} | Daily vol: {rm.get('daily_volatility_pct', 0)}% | "
                f"Annualised vol: {rm.get('annualised_volatility_pct', 0)}%"
            )

        return "\n".join(lines)

    def _get_snapshot_summary(self) -> dict:
        """
        Return a concise methodology-focused summary dict for API responses and UI display.
        """
        if not self._risk_snapshot:
            return {}
        method = self._risk_snapshot.get("methodology", {})
        return {
            "snapshot_date": self._risk_snapshot.get("snapshot_date"),
            "var_method": method.get("var_method"),
            "confidence_levels": method.get("confidence_levels"),
            "time_horizon": method.get("time_horizon"),
            "volatility_basis": method.get("volatility_basis"),
            "correlation_assumption": method.get("correlation_assumption"),
        }
