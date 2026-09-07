#!/usr/bin/env python3
"""
Phase 6/7 Evaluation Runner.

Runs the full evaluation set (prompts/risk_prompts.py — 38 queries as of
Phase 7) in two parts and writes a combined report to
docs/test_results/phase6_evaluation_report.md.

Part A — Routing accuracy: every query is answered via the real Orchestrator,
so we measure whether the keyword router actually sends each query to its
expected_agent (Section "Phase 6 addition" in prompts/risk_prompts.py). This
is the systematic evidence for RQ3 that Phase 3/4 only had one anecdote for.

Part B — RAG+ / RAG-only / LLM-only ablation: extends the Phase 3 comparative
test (which only covered the Risk Explainer) to a representative subset of
queries spanning all three agents' domains, using each query's correct
agent/collection/system-prompt combination.

Every response in both parts is:
  1. Logged via src.interaction_logger.log_interaction() (Phase 6) — full
     query, answer, routing info, sources, timing, cost.
  2. Checked against its expected_elements (automated substring match, same
     method Phase 3 used).
  3. Scored by evaluation.judge.judge_response() (LLM-as-judge, Phase 6) —
     automates what Phase 3 left blank for manual entry.

The generated report still includes a blank "supervisor override" column
next to every automated score, exactly as Phase 3's report did — this
automates the first pass, it does not replace human review.

Usage:
    # Estimate cost without spending anything
    python3 evaluation/run_evaluation.py --estimate-only

    # Run both parts (this is what actually costs money)
    python3 evaluation/run_evaluation.py --part all

    # Run just one part
    python3 evaluation/run_evaluation.py --part routing
    python3 evaluation/run_evaluation.py --part ablation
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.hedge_advisor import HedgeAdvisorAgent
from agents.model_monitor import ModelMonitorAgent
from agents.risk_explainer import RiskExplainerAgent
from evaluation.judge import judge_response
from evaluation.statistics import paired_significance_test, wilson_score_interval
from prompts.risk_prompts import RISK_EVALUATION_QUERIES
from src.interaction_logger import log_interaction
from prompts.system_prompts import (
    HEDGE_ADVISOR_SYSTEM_PROMPT,
    MODEL_MONITOR_SYSTEM_PROMPT,
    RISK_EXPLAINER_SYSTEM_PROMPT,
)
from src.cost_tracker import CostTracker
from src.llm_provider import get_llm_provider
from src.orchestrator import Orchestrator
from src.rag_pipeline import RAGPipeline
from src.vector_store import VectorStore

# Model used for the optional cross-family judge check (Phase 7). Deliberately
# a different provider family (Anthropic, not OpenAI) from the gpt-4o-mini
# used for both generation and the primary judge — an external dissertation
# review noted that a same-family judge (gpt-4o-mini judging gpt-4o-mini) risks
# self-family scoring bias, a documented phenomenon in the LLM-as-judge
# literature. This is deliberately NOT run as part of `--part all` — it costs
# more per call than the rest of the evaluation combined (Claude Sonnet is
# roughly 20x gpt-4o-mini's per-token price) and needs its own cost approval,
# via the separate `--cross-judge` flag.
CROSS_JUDGE_PROVIDER = "anthropic"

OUTPUT_FILE = PROJECT_ROOT / "docs" / "test_results" / "phase6_evaluation_report.md"

# Representative subset for the 3-way ablation. Phase 6 extended Phase 3's
# 8 Risk Explainer queries with just 1 Hedge Advisor and 1 Model Monitor
# query — an external dissertation review correctly noted this left those
# two agents with essentially a single ablation data point each. Phase 7
# adds 2 more of each, plus Q038 (designed to show RAG+ combining both
# context sources, not just one masking the other's absence — see
# PROJECT_DOC_v1.1.md Section 3.3).
ABLATION_QUERY_IDS = [
    "Q001", "Q002", "Q006", "Q007", "Q011", "Q017", "Q019", "Q025",  # Phase 3 set (Risk Explainer)
    "Q038",  # Risk Explainer — RAG+ combined-value demonstration (Phase 7)
    "Q014", "Q026", "Q028",  # Hedge Advisor (Phase 7 adds Q026, Q028)
    "Q023", "Q031", "Q033",  # Model Monitor (Phase 7 adds Q031, Q033)
]

AGENT_CLASSES = {
    "risk_explainer": (RiskExplainerAgent, RISK_EXPLAINER_SYSTEM_PROMPT, "risk_metrics"),
    "hedge_advisor": (HedgeAdvisorAgent, HEDGE_ADVISOR_SYSTEM_PROMPT, "hedging"),
    "model_monitor": (ModelMonitorAgent, MODEL_MONITOR_SYSTEM_PROMPT, "risk_metrics"),
}


def check_expected(answer: str, expected: list[str]) -> tuple[list[str], list[str]]:
    """Return (found_list, missing_list) for expected elements in the answer — same method as Phase 3."""
    found = [e for e in expected if e.lower() in answer.lower()]
    missing = [e for e in expected if e.lower() not in answer.lower()]
    return found, missing


def estimate_cost() -> dict:
    """
    Rough cost estimate, printed before any live run so the student can
    approve it first (per this project's budget-approval convention).

    The cross-judge check (Phase 7) is deliberately estimated separately —
    it is not part of the `--part all` run and needs its own approval,
    since Claude Sonnet costs roughly 20x gpt-4o-mini per token.
    """
    n_routing = len(RISK_EVALUATION_QUERIES)
    n_ablation_queries = len(ABLATION_QUERY_IDS)
    n_ablation_calls = n_ablation_queries * 3  # RAG+, RAG-only, LLM-only

    n_generation_calls = n_routing + n_ablation_calls
    n_judge_calls = n_generation_calls  # every response gets judged once

    # ~$0.0004/call observed average across Phase 3-6 live tests (see cost_logs)
    est_per_call = 0.0005
    est_generation_cost = n_generation_calls * est_per_call
    est_judge_cost = n_judge_calls * est_per_call * 1.3  # judge prompts are a little longer
    est_total = est_generation_cost + est_judge_cost

    # Cross-judge: one Claude call per ablation RAG+ response (run_cross_judge_check
    # runs it on that subset — n_ablation_queries responses, not calls). Rates
    # read from config/llm_config.py rather than hardcoded here, so this estimate
    # doesn't silently go stale if the model/pricing changes (as it did once
    # already — see PROJECT_DOC_v1.1.md Section 3.4 for the model-ID lesson).
    # Judge prompts run roughly 700 input / 100 output tokens.
    from config.llm_config import get_llm_config
    cross_judge_cfg = get_llm_config(CROSS_JUDGE_PROVIDER)
    est_cross_judge_per_call = (
        700 / 1000 * cross_judge_cfg["cost_per_1k_input"]
        + 100 / 1000 * cross_judge_cfg["cost_per_1k_output"]
    )
    est_cross_judge_total = n_ablation_queries * est_cross_judge_per_call

    return {
        "n_routing_calls": n_routing,
        "n_ablation_calls": n_ablation_calls,
        "n_generation_calls": n_generation_calls,
        "n_judge_calls": n_judge_calls,
        "n_total_calls": n_generation_calls + n_judge_calls,
        "est_total_usd": round(est_total, 4),
        "n_cross_judge_calls": n_ablation_queries,
        "est_cross_judge_usd": round(est_cross_judge_total, 4),
    }


# ---------------------------------------------------------------------------
# Part A — Routing accuracy
# ---------------------------------------------------------------------------

def run_routing_accuracy(orchestrator: Orchestrator, judge_llm, judge_tracker: CostTracker) -> list[dict]:
    """Answer all 25 queries via the real Orchestrator and score routing + content quality."""
    rows = []
    n = len(RISK_EVALUATION_QUERIES)

    print(f"\n{'='*65}")
    print(f"  PART A — Routing accuracy ({n} queries via Orchestrator)")
    print(f"{'='*65}\n")

    for i, q in enumerate(RISK_EVALUATION_QUERIES, 1):
        print(f"[{i}/{n}] {q['id']} (expects {q['expected_agent']}) — {q['query'][:60]}...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = orchestrator.answer(
                q["query"],
                eval_metadata={
                    "query_id": q["id"],
                    "category": q["category"],
                    "difficulty": q["difficulty"],
                    "expected_agent": q["expected_agent"],
                    "mode": "orchestrator",
                },
            )
        except Exception as e:
            print(f"ERROR: {e}")
            rows.append({"query": q, "error": str(e)})
            continue
        elapsed = time.time() - t0

        actual_agent_key = {
            "Risk Explainer": "risk_explainer",
            "Hedge Advisor": "hedge_advisor",
            "Model Monitor": "model_monitor",
        }.get(result["routed_to"], result["routed_to"])
        routing_correct = actual_agent_key == q["expected_agent"]

        found, missing = check_expected(result["answer"], q["expected_elements"])
        judge = judge_response(
            query=q["query"], answer=result["answer"], expected_elements=q["expected_elements"],
            llm=judge_llm, cost_tracker=judge_tracker, query_id=q["id"],
        )

        print(f"-> {result['routed_to']} ({'OK' if routing_correct else 'MISROUTED'})  {elapsed:.1f}s  judge={judge['total']}/12")

        rows.append({
            "query": q,
            "result": result,
            "routing_correct": routing_correct,
            "found": found,
            "missing": missing,
            "judge": judge,
            "elapsed": elapsed,
        })

    return rows


# ---------------------------------------------------------------------------
# Part B — RAG+ / RAG-only / LLM-only ablation
# ---------------------------------------------------------------------------

def run_ablation(vs: VectorStore, judge_llm, judge_tracker: CostTracker) -> list[dict]:
    """Run the representative query subset in 3 modes each, across all 3 agent domains."""
    from prompts.risk_prompts import QUERIES_BY_ID

    ablation_queries = [QUERIES_BY_ID[qid] for qid in ABLATION_QUERY_IDS]
    n = len(ablation_queries)

    print(f"\n{'='*65}")
    print(f"  PART B — RAG+/RAG/LLM-only ablation ({n} queries x 3 modes)")
    print(f"{'='*65}\n")

    llm = get_llm_provider("openai")
    rows = []

    for i, q in enumerate(ablation_queries, 1):
        agent_key = q["expected_agent"]
        agent_cls, system_prompt, default_collection = AGENT_CLASSES[agent_key]
        collection = "maritime" if q["category"] == "maritime_context" else default_collection

        pipeline = RAGPipeline(vector_store=vs, llm_provider=llm, collection=collection)
        agent = agent_cls(pipeline=pipeline)

        print(f"[{i}/{n}] {q['id']} ({agent_key}, collection={collection}) — {q['query'][:55]}...")

        query_rows = {"query": q, "agent_key": agent_key, "collection": collection, "modes": {}}
        eval_meta_base = {
            "query_id": q["id"], "category": q["category"], "difficulty": q["difficulty"],
            "expected_agent": q["expected_agent"],
        }

        # Mode 1: RAG+ (full agent, with maritime override where applicable)
        print("        [1/3] RAG+ ...", end=" ", flush=True)
        try:
            cost_before = pipeline.tracker.current_spend
            t0 = time.time()
            if collection != default_collection:
                r = agent.answer(q["query"], collection_override=collection)
            else:
                r = agent.answer(q["query"])
            elapsed = time.time() - t0
            cost_of_call = pipeline.tracker.current_spend - cost_before
            found, missing = check_expected(r["answer"], q["expected_elements"])
            judge = judge_response(q["query"], r["answer"], q["expected_elements"], judge_llm, judge_tracker, q["id"])
            print(f"OK {elapsed:.1f}s judge={judge['total']}/12")
            query_rows["modes"]["rag_plus"] = {"result": r, "found": found, "missing": missing, "judge": judge, "elapsed": elapsed}
            log_interaction(
                query=q["query"], answer=r["answer"], agent=agent.name, collection=collection,
                sources=r.get("sources"), retrieval_count=r.get("retrieval_count"), response_time_s=round(elapsed, 2),
                provider=llm.get_provider_name(), model=llm.model, cost_usd=cost_of_call,
                eval_metadata={**eval_meta_base, "mode": "rag_plus"},
            )
        except Exception as e:
            print(f"ERROR: {e}")
            query_rows["modes"]["rag_plus"] = {"error": str(e)}

        # Mode 2: RAG only (retrieved docs + LLM, no portfolio injection)
        print("        [2/3] RAG only ...", end=" ", flush=True)
        try:
            cost_before = pipeline.tracker.current_spend
            t0 = time.time()
            r = pipeline.query(q["query"], collection=collection, system_prompt=system_prompt)
            elapsed = time.time() - t0
            cost_of_call = pipeline.tracker.current_spend - cost_before
            found, missing = check_expected(r["answer"], q["expected_elements"])
            judge = judge_response(q["query"], r["answer"], q["expected_elements"], judge_llm, judge_tracker, q["id"])
            print(f"OK {elapsed:.1f}s judge={judge['total']}/12")
            query_rows["modes"]["rag_only"] = {"result": r, "found": found, "missing": missing, "judge": judge, "elapsed": elapsed}
            log_interaction(
                query=q["query"], answer=r["answer"], agent=f"{agent_cls.name} (RAG only, no portfolio injection)",
                collection=collection, sources=r.get("sources"), retrieval_count=r.get("retrieval_count"),
                response_time_s=round(elapsed, 2), provider=llm.get_provider_name(), model=llm.model,
                cost_usd=cost_of_call, eval_metadata={**eval_meta_base, "mode": "rag_only"},
            )
        except Exception as e:
            print(f"ERROR: {e}")
            query_rows["modes"]["rag_only"] = {"error": str(e)}

        # Mode 3: LLM only (bare model, no context)
        print("        [3/3] LLM only ...", end=" ", flush=True)
        try:
            cost_before = pipeline.tracker.current_spend
            t0 = time.time()
            r = pipeline.query_without_rag(q["query"], system_prompt=system_prompt)
            elapsed = time.time() - t0
            cost_of_call = pipeline.tracker.current_spend - cost_before
            found, missing = check_expected(r["answer"], q["expected_elements"])
            judge = judge_response(q["query"], r["answer"], q["expected_elements"], judge_llm, judge_tracker, q["id"])
            print(f"OK {elapsed:.1f}s judge={judge['total']}/12")
            query_rows["modes"]["llm_only"] = {"result": r, "found": found, "missing": missing, "judge": judge, "elapsed": elapsed}
            log_interaction(
                query=q["query"], answer=r["answer"], agent=f"{agent_cls.name} (LLM only, no context)",
                collection=None, sources=r.get("sources"), retrieval_count=r.get("retrieval_count"),
                response_time_s=round(elapsed, 2), provider=llm.get_provider_name(), model=llm.model,
                cost_usd=cost_of_call, eval_metadata={**eval_meta_base, "mode": "llm_only"},
            )
        except Exception as e:
            print(f"ERROR: {e}")
            query_rows["modes"]["llm_only"] = {"error": str(e)}

        rows.append(query_rows)
        print()

    return rows


# ---------------------------------------------------------------------------
# Cross-family judge check (Phase 7) — mitigates same-family judge bias
# ---------------------------------------------------------------------------

def run_cross_judge_check(ablation_rows: list[dict]) -> list[dict]:
    """
    Re-score each ablation query's RAG+ response with a second judge from a
    different model family (Claude, not gpt-4o-mini), to check whether the
    primary judge's scores are inflated by scoring its own model family's
    output — a documented risk in the LLM-as-judge literature that an
    external dissertation review specifically flagged.

    Only re-judges the RAG+ mode response per ablation query (not RAG-only/
    LLM-only) to keep the cost bounded to roughly one Claude call per
    ablation query, not three — the goal is a same-family-bias check, not
    a full re-run.

    Args:
        ablation_rows: The rows returned by run_ablation(), already containing
            the RAG+ response and the primary (gpt-4o-mini) judge's scores.

    Returns:
        List of dicts, one per successfully-judged ablation query, each with
        "query_id", "agent_key", "primary_total", "cross_total", and the full
        primary/cross judge score breakdowns. Queries whose RAG+ mode errored
        out are skipped (nothing to re-judge).
    """
    cross_llm = get_llm_provider(CROSS_JUDGE_PROVIDER)
    cross_tracker = CostTracker()
    rows = []

    n = len(ablation_rows)
    print(f"\n{'='*65}")
    print(f"  CROSS-JUDGE CHECK — {n} RAG+ responses re-scored by {CROSS_JUDGE_PROVIDER}")
    print(f"{'='*65}\n")

    for i, qr in enumerate(ablation_rows, 1):
        q = qr["query"]
        rag_plus = qr["modes"].get("rag_plus", {})
        if "error" in rag_plus or "result" not in rag_plus:
            print(f"[{i}/{n}] {q['id']} — skipped (RAG+ mode errored, nothing to re-judge)")
            continue

        answer_text = rag_plus["result"]["answer"]
        primary_judge = rag_plus["judge"]

        print(f"[{i}/{n}] {q['id']} ({qr['agent_key']}) ...", end=" ", flush=True)
        try:
            cross_judge = judge_response(
                query=q["query"], answer=answer_text, expected_elements=q["expected_elements"],
                llm=cross_llm, cost_tracker=cross_tracker, query_id=q["id"],
            )
        except Exception as e:
            # One failing call (e.g. an auth error) must not abort the whole
            # batch and, critically, must not propagate up into main() and
            # prevent write_report() from running — see the module docstring
            # note on this exact failure mode, found the hard way in Phase 7.
            print(f"ERROR: {e}")
            continue
        print(f"primary={primary_judge['total']}/12  cross={cross_judge['total']}/12")

        log_interaction(
            query=q["query"], answer=answer_text, agent=f"{qr['agent_key']} (cross-judge re-score)",
            provider=cross_llm.get_provider_name(), model=cross_llm.model,
            eval_metadata={
                "query_id": q["id"], "expected_agent": qr["agent_key"], "mode": "cross_judge",
                "primary_judge_total": primary_judge["total"], "cross_judge_total": cross_judge["total"],
            },
        )

        rows.append({
            "query_id": q["id"],
            "agent_key": qr["agent_key"],
            "primary_total": primary_judge["total"],
            "cross_total": cross_judge["total"],
            "primary_judge": primary_judge,
            "cross_judge": cross_judge,
        })

    return rows


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _judge_cell(judge: dict) -> str:
    if judge.get("total") is None:
        return "parse error"
    return f"{judge['total']}/12 (A{judge['accuracy']}/S{judge['structure']}/P{judge['plain_english']}/C{judge['completeness']})"


def write_header(f) -> None:
    f.write("# Phase 6 Evaluation Report\n\n")
    f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write("**Project**: Maritime Fuel Risk Narrative System — MSc Dissertation, University of Greenwich\n")
    f.write("**Author**: Seymanur Ergezgin | Supervisor: Dr. Mike Sharp\n\n---\n\n")


def write_part_a(f, routing_rows: list[dict]) -> None:
    f.write(f"## Part A — Routing Accuracy (all {len(routing_rows)} queries, via Orchestrator)\n\n")
    n_correct = sum(1 for r in routing_rows if r.get("routing_correct"))
    n_total = len(routing_rows)
    overall_ci = wilson_score_interval(n_correct, n_total)
    f.write(
        f"**Routing accuracy: {n_correct}/{n_total} ({overall_ci['point_estimate']:.1%}, "
        f"95% Wilson CI: {overall_ci['lower']:.1%}-{overall_ci['upper']:.1%})**\n\n"
    )
    f.write(
        "*The interval above is wide because n is modest — report both the point estimate "
        "and the interval together, not the percentage alone (see PROJECT_DOC_v1.1.md Section 3.2).*\n\n"
    )

    f.write("### Per-Agent Breakdown\n\n")
    f.write("| Expected Agent | Correct / Total | Accuracy | 95% Wilson CI |\n")
    f.write("|----------------|------------------|----------|----------------|\n")
    per_agent: dict[str, list[bool]] = {}
    for r in routing_rows:
        if "result" not in r:
            continue
        per_agent.setdefault(r["query"]["expected_agent"], []).append(r["routing_correct"])
    for agent_key, outcomes in sorted(per_agent.items()):
        correct = sum(outcomes)
        total = len(outcomes)
        ci = wilson_score_interval(correct, total)
        f.write(
            f"| {agent_key} | {correct}/{total} | {ci['point_estimate']:.1%} | "
            f"{ci['lower']:.1%}-{ci['upper']:.1%} |\n"
        )
    f.write("\n---\n\n")

    f.write("### Full Results\n\n")
    f.write("| Query | Category | Expected Agent | Routed To | Correct? | Confidence | Elements Found | Judge Score |\n")
    f.write("|-------|----------|-----------------|-----------|----------|------------|-----------------|-------------|\n")
    for r in routing_rows:
        q = r["query"]
        if "error" in r and "result" not in r:
            f.write(f"| {q['id']} | {q['category']} | {q['expected_agent']} | ERROR | - | - | - | - |\n")
            continue
        res = r["result"]
        correct_mark = "✅" if r["routing_correct"] else "❌"
        elements = f"{len(r['found'])}/{len(r['found']) + len(r['missing'])}"
        f.write(
            f"| {q['id']} | {q['category']} | {q['expected_agent']} | {res['routed_to']} | "
            f"{correct_mark} | {res['confidence']} | {elements} | {_judge_cell(r['judge'])} |\n"
        )
    f.write("\n**Supervisor override** *(optional — record disagreement with any automated score here)*:\n\n")
    f.write("| Query | Supervisor Score | Notes |\n|-------|------------------|-------|\n")
    for r in routing_rows:
        f.write(f"| {r['query']['id']} | | |\n")
    f.write("\n---\n\n")


def write_part_b(f, ablation_rows: list[dict]) -> None:
    f.write("## Part B — RAG+ / RAG-only / LLM-only Ablation\n\n")
    f.write("Extends the Phase 3 comparative test to all three agent domains.\n\n")

    mode_labels = {"rag_plus": "RAG+", "rag_only": "RAG only", "llm_only": "LLM only"}
    for qr in ablation_rows:
        q = qr["query"]
        f.write(f"### {q['id']} — {q['category'].title()} / {q['difficulty'].title()} ({qr['agent_key']})\n\n")
        f.write(f"**Query**: \"{q['query']}\"\n\n")
        f.write(f"**Expected elements**: {' | '.join(q['expected_elements'])}\n\n")
        f.write("| Mode | Elements Found | Judge Score | Response Time |\n")
        f.write("|------|-----------------|-------------|----------------|\n")
        for mode_key, label in mode_labels.items():
            m = qr["modes"].get(mode_key, {})
            if "error" in m:
                f.write(f"| {label} | ERROR | - | - |\n")
                continue
            elements = f"{len(m['found'])}/{len(m['found']) + len(m['missing'])}"
            f.write(f"| {label} | {elements} | {_judge_cell(m['judge'])} | {m['elapsed']:.2f}s |\n")
        f.write("\n")
        for mode_key, label in mode_labels.items():
            m = qr["modes"].get(mode_key, {})
            if "error" in m:
                continue
            f.write(f"**{label} response:**\n\n")
            for line in m["result"]["answer"].split("\n"):
                f.write(f"> {line}\n")
            f.write("\n")
        f.write("---\n\n")


def write_ablation_statistics(f, ablation_rows: list[dict]) -> None:
    """
    Wilcoxon signed-rank tests comparing RAG+/RAG-only/LLM-only judge totals,
    paired on the same queries. Added in response to an external dissertation
    review noting that mean-score comparisons alone (e.g. "11.6 vs 7.4 vs 8.6")
    don't establish whether the difference is likely real given the small
    ablation sample (n=9-15 per condition) — see PROJECT_DOC_v1.1.md Section 3.1.
    """
    f.write("## Ablation Significance Testing\n\n")
    f.write(
        "Wilcoxon signed-rank test (non-parametric, paired — chosen because judge "
        "totals are bounded/ordinal and the sample is small) on the same queries "
        "scored under each pair of conditions.\n\n"
    )

    modes = {}
    for qr in ablation_rows:
        for mode_key in ("rag_plus", "rag_only", "llm_only"):
            m = qr["modes"].get(mode_key, {})
            if "judge" in m and m["judge"].get("total") is not None:
                modes.setdefault(mode_key, []).append(m["judge"]["total"])

    # Only compare queries where ALL THREE modes succeeded, so the test stays paired.
    complete_queries = [
        qr for qr in ablation_rows
        if all(
            "judge" in qr["modes"].get(mk, {}) and qr["modes"][mk]["judge"].get("total") is not None
            for mk in ("rag_plus", "rag_only", "llm_only")
        )
    ]
    rag_plus_scores = [qr["modes"]["rag_plus"]["judge"]["total"] for qr in complete_queries]
    rag_only_scores = [qr["modes"]["rag_only"]["judge"]["total"] for qr in complete_queries]
    llm_only_scores = [qr["modes"]["llm_only"]["judge"]["total"] for qr in complete_queries]

    f.write(f"*n = {len(complete_queries)} queries with complete data across all 3 modes.*\n\n")
    f.write("| Comparison | Mean A | Mean B | Wilcoxon statistic | p-value | Significant (p<0.05)? |\n")
    f.write("|------------|--------|--------|---------------------|---------|------------------------|\n")

    if len(complete_queries) >= 1:
        for label_a, scores_a, label_b, scores_b in [
            ("RAG+", rag_plus_scores, "RAG-only", rag_only_scores),
            ("RAG+", rag_plus_scores, "LLM-only", llm_only_scores),
            ("RAG-only", rag_only_scores, "LLM-only", llm_only_scores),
        ]:
            result = paired_significance_test(scores_a, scores_b, label_a, label_b)
            mean_a = sum(scores_a) / len(scores_a)
            mean_b = sum(scores_b) / len(scores_b)
            sig_mark = "Yes" if result["significant"] else "No"
            f.write(
                f"| {label_a} vs {label_b} | {mean_a:.1f}/12 | {mean_b:.1f}/12 | "
                f"{result['statistic']:.1f} | {result['p_value']:.4f} | {sig_mark} |\n"
            )
    f.write(
        "\n*A small or non-significant p-value with this sample size should be read as "
        "suggestive, not confirmatory — see PROJECT_DOC_v1.1.md Section 3.1 for the "
        "honest interpretation of what n=9-15 per condition can and cannot support.*\n\n"
    )
    f.write("---\n\n")


def write_cross_judge_section(f, cross_judge_rows: list[dict]) -> None:
    """
    Reports agreement between the primary judge (gpt-4o-mini) and the
    cross-family judge (Claude) on the same RAG+ responses — added to check
    for same-family judge bias, per external dissertation review Section 3.4.
    """
    f.write("## Cross-Family Judge Check (Phase 7)\n\n")
    if not cross_judge_rows:
        f.write("*Not run in this evaluation pass — run with `--cross-judge` to include it.*\n\n---\n\n")
        return

    f.write(
        f"The primary judge (gpt-4o-mini) is the same model family used for generation. "
        f"To check for same-family scoring bias, {len(cross_judge_rows)} RAG+ responses "
        f"were independently re-scored by a different model family (Claude, via "
        f"Anthropic).\n\n"
    )

    diffs = [row["cross_total"] - row["primary_total"] for row in cross_judge_rows]
    mean_diff = sum(diffs) / len(diffs)
    mean_abs_diff = sum(abs(d) for d in diffs) / len(diffs)
    exact_matches = sum(1 for d in diffs if d == 0)

    primary_scores = [row["primary_total"] for row in cross_judge_rows]
    cross_scores = [row["cross_total"] for row in cross_judge_rows]
    correlation_computable = len(set(primary_scores)) > 1 and len(set(cross_scores)) > 1
    if correlation_computable:
        import numpy as np
        correlation = float(np.corrcoef(primary_scores, cross_scores)[0, 1])

    if mean_diff > 0:
        diff_interpretation = "positive means Claude scored higher on average (opposite of same-family inflation)"
    elif mean_diff < 0:
        diff_interpretation = "negative means gpt-4o-mini scored itself higher on average — consistent with same-family bias"
    else:
        diff_interpretation = "no average difference"

    f.write(f"- **Mean signed difference** (cross − primary): {mean_diff:+.2f} points\n")
    f.write(f"  — {diff_interpretation}\n")
    f.write(f"- **Mean absolute difference**: {mean_abs_diff:.2f} points (out of 12)\n")
    f.write(f"- **Exact agreement rate**: {exact_matches}/{len(cross_judge_rows)} ({exact_matches/len(cross_judge_rows):.0%})\n")
    if correlation_computable:
        f.write(f"- **Correlation** (primary vs cross-judge totals): {correlation:.2f}\n\n")
    else:
        f.write("- **Correlation**: not computable (one judge gave identical scores to everything)\n\n")

    f.write("| Query | Agent | Primary (gpt-4o-mini) | Cross (Claude) | Difference |\n")
    f.write("|-------|-------|------------------------|-----------------|------------|\n")
    for row in cross_judge_rows:
        diff = row["cross_total"] - row["primary_total"]
        f.write(f"| {row['query_id']} | {row['agent_key']} | {row['primary_total']}/12 | {row['cross_total']}/12 | {diff:+d} |\n")
    f.write("\n---\n\n")


def write_key_findings(f) -> None:
    f.write("## Key Findings *(fill in after review)*\n\n")
    f.write("**Routing accuracy**: Which query types (if any) were misrouted, and why?\n\n> *Your observation here*\n\n")
    f.write("**RAG+ vs RAG vs LLM-only**: Consistent with Phase 3's findings across all three agent domains?\n\n> *Your observation here*\n\n")
    f.write("**Judge vs manual scoring**: Do you agree with the automated judge's scores? Note any disagreements above.\n\n> *Your observation here*\n\n")
    f.write("**Cross-judge agreement**: If the cross-judge check was run, does the agreement level change your confidence in the primary judge's scores?\n\n> *Your observation here*\n\n")


def write_report(
    routing_rows: list[dict],
    ablation_rows: list[dict],
    cross_judge_rows: list[dict] | None = None,
) -> None:
    """Write the full report from scratch (both parts, plus stats and optional cross-judge). Used by `--part all`."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        write_header(f)
        write_part_a(f, routing_rows)
        write_part_b(f, ablation_rows)
        write_ablation_statistics(f, ablation_rows)
        write_cross_judge_section(f, cross_judge_rows or [])
        write_key_findings(f)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6/7 evaluation runner")
    parser.add_argument("--part", choices=["routing", "ablation", "all"], default="all")
    parser.add_argument("--estimate-only", action="store_true", help="Print cost estimate and exit, no API calls")
    parser.add_argument(
        "--cross-judge", action="store_true",
        help="Also run the Phase 7 cross-family judge check (Claude) on ablation RAG+ responses. "
             "Costs more per call than the rest of the evaluation combined — see the printed "
             "estimate. Requires --part ablation or --part all in the same run.",
    )
    args = parser.parse_args()

    est = estimate_cost()
    print(f"\n{'='*65}")
    print("  Phase 6/7 Evaluation — Cost Estimate")
    print(f"{'='*65}")
    print(f"  Routing accuracy calls : {est['n_routing_calls']}")
    print(f"  Ablation calls         : {est['n_ablation_calls']}")
    print(f"  Judge calls            : {est['n_judge_calls']}")
    print(f"  Total API calls        : {est['n_total_calls']}")
    print(f"  Estimated cost         : ~${est['est_total_usd']}")
    if args.cross_judge:
        print(f"  Cross-judge calls      : {est['n_cross_judge_calls']} (Claude Sonnet, separate from above)")
        print(f"  Cross-judge est. cost  : ~${est['est_cross_judge_usd']}")
    print(f"{'='*65}\n")

    if args.estimate_only:
        return

    print("Initialising VectorStore (Ollama embeddings)...", end=" ", flush=True)
    vs = VectorStore()
    print("done.")

    judge_llm = get_llm_provider("openai")
    judge_tracker = CostTracker()

    routing_rows: list[dict] = []
    ablation_rows: list[dict] = []
    cross_judge_rows: list[dict] = []

    if args.part in ("routing", "all"):
        orchestrator = Orchestrator(agents={
            "risk_explainer": RiskExplainerAgent(pipeline=RAGPipeline(vector_store=vs, llm_provider=get_llm_provider("openai"), collection="risk_metrics")),
            "hedge_advisor": HedgeAdvisorAgent(pipeline=RAGPipeline(vector_store=vs, llm_provider=get_llm_provider("openai"), collection="hedging")),
            "model_monitor": ModelMonitorAgent(pipeline=RAGPipeline(vector_store=vs, llm_provider=get_llm_provider("openai"), collection="risk_metrics")),
        })
        routing_rows = run_routing_accuracy(orchestrator, judge_llm, judge_tracker)

    if args.part in ("ablation", "all"):
        ablation_rows = run_ablation(vs, judge_llm, judge_tracker)

    # Write the report NOW, before attempting the optional cross-judge step.
    # A prior run lost a full evaluation pass (166 real API calls, routing +
    # ablation both completed successfully) because write_report() was only
    # called once, at the very end — when the cross-judge step crashed
    # (an invalid Anthropic key), the crash propagated up and the report was
    # never written at all, despite all the expensive work having succeeded.
    # Writing here guarantees the core results are saved regardless of what
    # happens next; if cross-judge succeeds, the report is simply re-written
    # with that section filled in.
    write_report(routing_rows, ablation_rows, cross_judge_rows)

    if args.cross_judge:
        if not ablation_rows:
            print("WARNING: --cross-judge requires ablation rows (use --part ablation or --part all). Skipping.")
        else:
            try:
                cross_judge_rows = run_cross_judge_check(ablation_rows)
                write_report(routing_rows, ablation_rows, cross_judge_rows)
            except Exception as e:
                print(f"WARNING: cross-judge check failed ({e}) — the report above (without cross-judge) is still saved.")

    print(f"\n{'='*65}")
    print("  Evaluation complete.")
    print(f"  Report: {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"  Interaction log: data/interaction_logs/interactions.jsonl")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
