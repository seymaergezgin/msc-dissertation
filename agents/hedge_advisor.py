"""
Hedge Advisor Agent.

Answers questions about the company's fuel price hedging position: hedge
ratios, hedged vs unhedged dollar exposure, whether current coverage is
sufficient, and which vessels carry the largest hedging gaps.

Architecture — RAG+ pattern (same as RiskExplainerAgent, see agents/risk_explainer.py
for the full rationale):

  1. LIVE PORTFOLIO DATA — hedge ratios and hedged/unhedged exposure per
     vessel, loaded from data/synthetic/risk_metrics.json. This agent's
     context formatter emphasises the hedging fields of that same snapshot
     (hedge_ratio_pct, hedged_exposure_usd, unhedged_exposure_usd) rather
     than the VaR/CVaR fields the Risk Explainer emphasises — same source
     file, different lens.

  2. DOMAIN KNOWLEDGE — chunks retrieved from the ChromaDB "hedging"
     collection (Kavussanos, Sun, Bai, Han maritime hedging papers).
     Explains hedging instruments, strategy, and market context.

Usage:
    from agents.hedge_advisor import HedgeAdvisorAgent

    agent = HedgeAdvisorAgent()
    result = agent.answer("Is our 48% average hedge ratio sufficient?")
    print(result["answer"])
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config.settings import DATA_DIR
from prompts.system_prompts import HEDGE_ADVISOR_SYSTEM_PROMPT
from src.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)

RISK_METRICS_PATH = DATA_DIR / "synthetic" / "risk_metrics.json"


class HedgeAdvisorAgent(BaseAgent):
    """
    Advises on maritime fuel hedging positions and strategy in plain English.

    How it works:
    1. On init: loads the same portfolio risk snapshot as RiskExplainerAgent.
    2. On answer(): retrieves the top-5 most relevant chunks from the
       "hedging" ChromaDB collection.
    3. Prepends the live hedge-ratio and exposure data as "CURRENT PORTFOLIO
       DATA" before the retrieved hedging-strategy literature.
    4. Calls the LLM with the HEDGE_ADVISOR_SYSTEM_PROMPT persona.
    5. Returns the answer with source citations and a snapshot summary.

    Args:
        pipeline: Pre-initialised RAGPipeline. If None, one is created
                  using collection="hedging".
    """

    name = "Hedge Advisor"
    collection = "hedging"

    def __init__(self, pipeline: Optional[RAGPipeline] = None) -> None:
        super().__init__(pipeline=pipeline or RAGPipeline(collection=self.collection))
        self._risk_snapshot = self._load_risk_snapshot()
        if self._risk_snapshot:
            ps = self._risk_snapshot.get("portfolio_summary", {})
            logger.info(
                "Risk snapshot loaded: %d vessels | average hedge ratio %s%%",
                len(self._risk_snapshot.get("vessels", [])),
                ps.get("average_hedge_ratio_pct", "N/A"),
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
        Answer a hedging-related query using live portfolio data + RAG context.

        Args:
            query: Natural language question about hedge positions or strategy.

        Returns:
            Dict with keys:
              - "answer" (str): Plain-English response in structured format
              - "sources" (list[dict]): Retrieved chunk citations
              - "context_used" (str): Full context block shown to the LLM
              - "retrieval_count" (int): Number of chunks retrieved
              - "query" (str): Original question
              - "agent" (str): "Hedge Advisor"
              - "portfolio_snapshot" (dict): Key hedging figures summary
              - "response_time_s" (float): Time to generate the response
        """
        start_time = time.time()

        # Step 1: Retrieve relevant hedging literature from ChromaDB
        context_docs = self.pipeline.vs.query(
            query, collection=self.collection, k=5
        )

        # Step 2: Build combined context — hedging data first, then retrieved docs
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
                query_summary=f"[HedgeAgent] {query[:70]}",
            )
        except Exception as cost_err:
            logger.warning("Cost tracking failed (non-fatal): %s", cost_err)

        logger.info(
            "HedgeAdvisorAgent: '%s...' answered in %.2fs | provider: %s | %d chunks retrieved",
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
        return HEDGE_ADVISOR_SYSTEM_PROMPT

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
        hedging figures rather than VaR/CVaR.

        Uses the same underlying risk_metrics.json as RiskExplainerAgent, but
        surfaces hedge_ratio_pct, hedged_exposure_usd, and unhedged_exposure_usd
        per vessel, since those are the figures this agent's audience
        (treasury/risk team) needs to reason about hedging strategy.

        Returns:
            Formatted multi-line string, or empty string if no snapshot loaded.
        """
        if not self._risk_snapshot:
            return ""

        snap = self._risk_snapshot
        ps = snap.get("portfolio_summary", {})
        vessels = snap.get("vessels", [])

        total_hedged = sum(v.get("hedged_exposure_usd", 0) for v in vessels)
        total_unhedged = sum(v.get("unhedged_exposure_usd", 0) for v in vessels)

        lines = [
            f"[CURRENT PORTFOLIO DATA — snapshot date: {snap.get('snapshot_date', 'N/A')}]",
            "",
            "FLEET-WIDE HEDGING POSITION:",
            f"  Total annual fuel cost:                      ${ps.get('total_annual_fuel_cost_usd', 0):>15,.0f}",
            f"  Average hedge ratio across fleet:            {ps.get('average_hedge_ratio_pct', 0):>14}%",
            f"  Total hedged exposure (fleet):                ${total_hedged:>15,.0f}",
            f"  Total unhedged exposure (fleet):              ${total_unhedged:>15,.0f}",
            "",
            "VESSEL-LEVEL HEDGING BREAKDOWN:",
        ]

        for v in vessels:
            lines.append(
                f"  {v['vessel_name']} | {v['vessel_type']} | Fuel: {v['fuel_type']} | "
                f"Hedge ratio: {v['hedge_ratio_pct']}% | "
                f"Hedged: ${v.get('hedged_exposure_usd', 0):,.0f} | "
                f"Unhedged: ${v.get('unhedged_exposure_usd', 0):,.0f}"
            )

        return "\n".join(lines)

    def _get_snapshot_summary(self) -> dict:
        """
        Return a concise hedging-focused summary dict for API responses and UI display.
        """
        if not self._risk_snapshot:
            return {}
        ps = self._risk_snapshot.get("portfolio_summary", {})
        vessels = self._risk_snapshot.get("vessels", [])
        return {
            "snapshot_date": self._risk_snapshot.get("snapshot_date"),
            "total_vessels": ps.get("total_vessels"),
            "average_hedge_ratio_pct": ps.get("average_hedge_ratio_pct"),
            "total_hedged_exposure_usd": sum(v.get("hedged_exposure_usd", 0) for v in vessels),
            "total_unhedged_exposure_usd": sum(v.get("unhedged_exposure_usd", 0) for v in vessels),
        }
