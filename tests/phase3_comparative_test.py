#!/usr/bin/env python3
"""
Phase 3 Comparative Test — Risk Explainer Agent

Runs 8 representative queries in 3 modes to compare:
  - RAG+ mode    : live portfolio data + retrieved chunks + LLM  (full system)
  - RAG only     : retrieved chunks + LLM, no portfolio injection (ablation 1)
  - LLM only     : bare LLM, no context at all                   (ablation 2)

Providers tested:
  - OpenAI gpt-4o-mini  : all 8 queries × 3 modes  (~$0.015, ~3 min)
  - Ollama llama3.1:8b  : 3 queries × RAG+ only    ($0.00,  ~45-90 min on CPU)

Results are written to docs/test_results/phase3_comparative_test.md
as they arrive — safe to interrupt at any time.

Usage:
    # OpenAI only (recommended first run — fast)
    python3 tests/phase3_comparative_test.py --provider openai

    # Ollama only (run separately, ideally when machine is free)
    python3 tests/phase3_comparative_test.py --provider ollama

    # Both: OpenAI first, then prompts before starting Ollama
    python3 tests/phase3_comparative_test.py --provider all
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Project root on sys.path so imports work regardless of cwd
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.vector_store import VectorStore
from src.rag_pipeline import RAGPipeline
from src.llm_provider import get_llm_provider
from agents.risk_explainer import RiskExplainerAgent
from prompts.system_prompts import RISK_EXPLAINER_SYSTEM_PROMPT

OUTPUT_DIR = PROJECT_ROOT / "docs" / "test_results"
OUTPUT_FILE = OUTPUT_DIR / "phase3_comparative_test.md"

# ---------------------------------------------------------------------------
# The 8 test queries — a representative cross-section of the 25-query set
# ---------------------------------------------------------------------------

TEST_QUERIES = [
    {
        "id": "Q001",
        "query": "What is our current portfolio VaR at 95% confidence?",
        "category": "factual",
        "difficulty": "easy",
        "expected_elements": ["$376,329", "95%", "10 trading days", "5% chance"],
        "why_included": "Baseline factual test — answer is a direct portfolio lookup.",
    },
    {
        "id": "Q002",
        "query": "What is the CVaR (Expected Shortfall) for our total fleet?",
        "category": "factual",
        "difficulty": "easy",
        "expected_elements": ["$481,701", "95%", "average loss"],
        "why_included": "Tests CVaR figure retrieval alongside VaR.",
    },
    {
        "id": "Q006",
        "query": "Explain what Value at Risk means for a maritime shipping company in plain English.",
        "category": "conceptual",
        "difficulty": "medium",
        "expected_elements": ["maximum loss", "confidence level", "time horizon", "probability"],
        "why_included": "Pure knowledge retrieval — no portfolio data needed. Isolates RAG quality.",
    },
    {
        "id": "Q007",
        "query": "What is the difference between VaR and CVaR, and which one should management focus on?",
        "category": "conceptual",
        "difficulty": "medium",
        "expected_elements": ["VaR", "CVaR", "Expected Shortfall", "tail risk"],
        "why_included": "Tests ability to compare related concepts and give a recommendation.",
    },
    {
        "id": "Q011",
        "query": "Which vessel in our fleet carries the highest fuel price risk and why?",
        "category": "comparative",
        "difficulty": "medium",
        "expected_elements": ["MV Iron Maiden", "VLCC", "largest fuel cost", "lowest hedge ratio"],
        "why_included": "Requires reasoning across all 5 vessel records — multi-step retrieval.",
    },
    {
        "id": "Q017",
        "query": "Why does MV Iron Maiden use HSFO instead of VLSFO, and what are the cost implications?",
        "category": "maritime_context",
        "difficulty": "hard",
        "expected_elements": ["HSFO", "scrubber", "VLSFO", "sulphur", "IMO 2020"],
        "why_included": "Requires domain knowledge from Stopford/IMO docs AND portfolio data.",
    },
    {
        "id": "Q019",
        "query": "Is our current VaR level of $376,329 acceptable, or should the risk committee be concerned?",
        "category": "actionable",
        "difficulty": "hard",
        "expected_elements": ["$376,329", "percentage of fuel cost", "recommendation"],
        "why_included": "Hardest test — requires combining portfolio figures with judgment.",
    },
    {
        "id": "Q025",
        "query": "Provide a concise summary of our overall fuel risk position suitable for presenting to the board of directors.",
        "category": "summary",
        "difficulty": "hard",
        "expected_elements": ["portfolio VaR", "CVaR", "hedge ratio", "recommendation"],
        "why_included": "Holistic quality test — all information must be synthesised into one narrative.",
    },
]

# Ollama only runs these 3 (others would take 3+ hours on CPU)
OLLAMA_QUERY_IDS = {"Q001", "Q006", "Q025"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_agent(provider_name: str, vs: VectorStore) -> RiskExplainerAgent:
    """Create a RiskExplainerAgent with the specified LLM provider."""
    llm = get_llm_provider(provider_name)
    pipeline = RAGPipeline(vector_store=vs, llm_provider=llm, collection="risk_metrics")
    return RiskExplainerAgent(pipeline=pipeline)


def make_pipeline(provider_name: str, vs: VectorStore) -> RAGPipeline:
    """Create a plain RAGPipeline with the specified LLM provider."""
    llm = get_llm_provider(provider_name)
    return RAGPipeline(vector_store=vs, llm_provider=llm, collection="risk_metrics")


def check_expected(answer: str, expected: list[str]) -> tuple[list[str], list[str]]:
    """Return (found_list, missing_list) for expected elements in the answer."""
    found = [e for e in expected if e.lower() in answer.lower()]
    missing = [e for e in expected if e.lower() not in answer.lower()]
    return found, missing


def format_sources(sources: list[dict]) -> str:
    if not sources:
        return "None"
    parts = []
    for s in sources[:4]:
        page = f" p.{s['page']}" if s.get("page") != "" else ""
        parts.append(f"{s['file']}{page}")
    return " | ".join(parts)


def write_line(f, text: str = "") -> None:
    """Write a line and flush immediately so results are never lost on crash."""
    f.write(text + "\n")
    f.flush()


def write_result_section(
    f,
    query: dict,
    mode: str,
    provider: str,
    model: str,
    result: dict,
    elapsed: float,
) -> None:
    """Write one query-result section to the markdown file."""
    mode_titles = {
        "rag_plus": "RAG+ Mode — Portfolio data + Retrieved docs + LLM",
        "rag_only": "RAG Only — Retrieved docs + LLM (no portfolio injection)",
        "llm_only": "LLM Only — Bare model, no context at all",
    }

    answer = result.get("answer", "ERROR — see terminal output")
    sources = result.get("sources", [])
    chunks = result.get("retrieval_count", 0)
    found, missing = check_expected(answer, query["expected_elements"])

    if provider == "openai":
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output — rough estimate
        est_cost = f"~${(1400 * 0.15 / 1_000_000) + (500 * 0.60 / 1_000_000):.5f}"
    else:
        est_cost = "$0.00 (local model)"

    write_line(f, f"### {provider.upper()} {model} — {mode_titles[mode]}")
    write_line(f)
    write_line(f, f"| Metric | Value |")
    write_line(f, f"|--------|-------|")
    write_line(f, f"| Response time | {elapsed:.2f}s |")
    write_line(f, f"| Chunks retrieved | {chunks} |")
    write_line(f, f"| Sources | {format_sources(sources)} |")
    write_line(f, f"| Estimated cost | {est_cost} |")
    write_line(f, f"| Expected elements found | {len(found)}/{len(query['expected_elements'])} |")
    if missing:
        write_line(f, f"| Missing elements | {', '.join(missing)} |")
    write_line(f)
    write_line(f, "**Full response:**")
    write_line(f)
    for line in answer.split("\n"):
        write_line(f, f"> {line}")
    write_line(f)
    write_line(f, "**Manual scoring** *(fill in after reading the response above)*:")
    write_line(f)
    write_line(f, "| Criterion | Score (0–3) | Notes |")
    write_line(f, "|-----------|------------|-------|")
    write_line(f, "| **Accuracy** — correct figures cited | | |")
    write_line(f, "| **Structure** — follows SUMMARY/EXPLANATION/IMPLICATIONS/CAVEATS | | |")
    write_line(f, "| **Plain English** — clear for a non-technical reader | | |")
    write_line(f, "| **Completeness** — covers all expected elements | | |")
    write_line(f, "| **Total** | **/12** | |")
    write_line(f)
    write_line(f, "---")
    write_line(f)


# ---------------------------------------------------------------------------
# OpenAI test runner
# ---------------------------------------------------------------------------

def run_openai_tests(vs: VectorStore) -> None:
    queries_n = len(TEST_QUERIES)
    calls_n = queries_n * 3
    print(f"\n{'='*65}")
    print(f"  OPENAI TESTS — {queries_n} queries × 3 modes = {calls_n} API calls")
    print(f"  Estimated cost : ~$0.015 | Estimated time : ~3–5 minutes")
    print(f"  Output file    : {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"{'='*65}\n")

    agent = make_agent("openai", vs)
    pipeline = make_pipeline("openai", vs)
    model = "gpt-4o-mini"

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        write_line(f, "---")
        write_line(f)
        write_line(f, "## OpenAI gpt-4o-mini — All Modes")
        write_line(f)
        write_line(f, f"*Run at {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        write_line(f)

        for i, q in enumerate(TEST_QUERIES, 1):
            print(f"[{i}/{queries_n}] {q['id']} — {q['category'].upper()} / {q['difficulty'].upper()}")
            print(f"        Query: {q['query'][:65]}...")

            write_line(f, f"## {q['id']} — {q['category'].title()} / {q['difficulty'].title()}")
            write_line(f)
            write_line(f, f"**Query**: \"{q['query']}\"")
            write_line(f)
            write_line(f, f"**Expected elements**: {' | '.join(q['expected_elements'])}")
            write_line(f)
            write_line(f, f"*Why included*: {q['why_included']}*")
            write_line(f)

            # ── Mode 1: RAG+ ──────────────────────────────────────────
            print(f"        [1/3] RAG+ ...", end=" ", flush=True)
            try:
                t0 = time.time()
                r = agent.answer(q["query"])
                elapsed = time.time() - t0
                print(f"✓  {elapsed:.1f}s")
                write_result_section(f, q, "rag_plus", "openai", model, r, elapsed)
            except Exception as e:
                print(f"ERROR: {e}")
                write_line(f, f"### OPENAI RAG+ — ERROR\n\n```\n{e}\n```\n\n---\n")

            # ── Mode 2: RAG only ──────────────────────────────────────
            print(f"        [2/3] RAG only ...", end=" ", flush=True)
            try:
                t0 = time.time()
                r = pipeline.query(q["query"], system_prompt=RISK_EXPLAINER_SYSTEM_PROMPT)
                elapsed = time.time() - t0
                r["response_time_s"] = round(elapsed, 2)
                print(f"✓  {elapsed:.1f}s")
                write_result_section(f, q, "rag_only", "openai", model, r, elapsed)
            except Exception as e:
                print(f"ERROR: {e}")
                write_line(f, f"### OPENAI RAG ONLY — ERROR\n\n```\n{e}\n```\n\n---\n")

            # ── Mode 3: LLM only ──────────────────────────────────────
            print(f"        [3/3] LLM only ...", end=" ", flush=True)
            try:
                t0 = time.time()
                r = pipeline.query_without_rag(q["query"], system_prompt=RISK_EXPLAINER_SYSTEM_PROMPT)
                elapsed = time.time() - t0
                r["response_time_s"] = round(elapsed, 2)
                print(f"✓  {elapsed:.1f}s")
                write_result_section(f, q, "llm_only", "openai", model, r, elapsed)
            except Exception as e:
                print(f"ERROR: {e}")
                write_line(f, f"### OPENAI LLM ONLY — ERROR\n\n```\n{e}\n```\n\n---\n")

            print()  # blank line between queries

    print(f"\n  OpenAI tests done. Results saved to: {OUTPUT_FILE.relative_to(PROJECT_ROOT)}\n")


# ---------------------------------------------------------------------------
# Ollama test runner
# ---------------------------------------------------------------------------

def run_ollama_tests(vs: VectorStore) -> None:
    ollama_queries = [q for q in TEST_QUERIES if q["id"] in OLLAMA_QUERY_IDS]
    n = len(ollama_queries)

    print(f"\n{'='*65}")
    print(f"  OLLAMA TESTS — {n} queries × RAG+ mode only")
    print(f"  Model          : llama3.1:8b on CPU")
    print(f"  Estimated time : 15–30 min per query ({n * 15}–{n * 30} min total)")
    print(f"  Cost           : $0.00 (local)")
    print(f"  Queries        : Q001 (factual), Q006 (conceptual), Q025 (summary)")
    print(f"  Output file    : {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")
    print(f"{'='*65}")
    print(f"\n  You can interrupt at any time with Ctrl+C — results are saved")
    print(f"  as each query completes.\n")

    try:
        input("  Press Enter to start Ollama tests (Ctrl+C to skip entirely)...")
    except KeyboardInterrupt:
        print("\n  Ollama tests skipped.")
        return

    print()
    agent = make_agent("ollama", vs)
    model = "llama3.1:8b"

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        write_line(f, "---")
        write_line(f)
        write_line(f, "## Ollama llama3.1:8b — RAG+ Mode Only")
        write_line(f)
        write_line(f, f"*Run at {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        write_line(f)
        write_line(f, "> **Note**: Ollama runs locally on CPU (llama3.1:8b). Response times")
        write_line(f, "> are 15–30 min per query. Only 3 representative queries are included.")
        write_line(f, "> No cost — fully local. Results below are RAG+ mode only.")
        write_line(f)

        for i, q in enumerate(ollama_queries, 1):
            print(f"[{i}/{n}] {q['id']} — {q['category'].upper()} / {q['difficulty'].upper()}")
            print(f"       Query: {q['query'][:65]}...")
            print(f"       Running RAG+ ... (this will take several minutes)", flush=True)

            write_line(f, f"## {q['id']} — {q['category'].title()} / {q['difficulty'].title()} (Ollama)")
            write_line(f)
            write_line(f, f"**Query**: \"{q['query']}\"")
            write_line(f)
            write_line(f, f"**Expected elements**: {' | '.join(q['expected_elements'])}")
            write_line(f)

            try:
                t0 = time.time()
                r = agent.answer(q["query"])
                elapsed = time.time() - t0
                print(f"       ✓  Done in {elapsed:.0f}s ({elapsed/60:.1f} min)")
                write_result_section(f, q, "rag_plus", "ollama", model, r, elapsed)
            except KeyboardInterrupt:
                print("\n\n  Interrupted — results saved so far.")
                write_line(f, "*[Test interrupted by user — query not completed]*")
                write_line(f)
                write_line(f, "---")
                write_line(f)
                return
            except Exception as e:
                print(f"       ERROR: {e}")
                write_line(f, f"### OLLAMA RAG+ — ERROR\n\n```\n{e}\n```\n\n---\n")

            print()

    print(f"\n  Ollama tests done. Results saved to: {OUTPUT_FILE.relative_to(PROJECT_ROOT)}\n")


# ---------------------------------------------------------------------------
# Scoring summary template
# ---------------------------------------------------------------------------

def write_scoring_summary(providers_run: list[str]) -> None:
    """Append an empty scoring summary table for the user to fill in."""
    has_ollama = "ollama" in providers_run

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        write_line(f, "---")
        write_line(f)
        write_line(f, "## Scoring Summary")
        write_line(f)
        write_line(f, "*Fill in after reading all responses above. Score each criterion 0–3.*")
        write_line(f, "*0=wrong/missing, 1=partial, 2=good, 3=excellent.*")
        write_line(f)

        if has_ollama:
            header = "| Query | Category | Diff | OpenAI RAG+ | OpenAI RAG | OpenAI LLM | Ollama RAG+ |"
            sep    = "|-------|----------|------|------------|------------|------------|-------------|"
            row_template = "| {id} | {cat} | {diff} | /12 | /12 | /12 | /12 |"
        else:
            header = "| Query | Category | Diff | OpenAI RAG+ | OpenAI RAG | OpenAI LLM |"
            sep    = "|-------|----------|------|------------|------------|------------|"
            row_template = "| {id} | {cat} | {diff} | /12 | /12 | /12 |"

        write_line(f, header)
        write_line(f, sep)
        for q in TEST_QUERIES:
            if not has_ollama or q["id"] not in OLLAMA_QUERY_IDS:
                row = row_template.format(
                    id=q["id"], cat=q["category"], diff=q["difficulty"]
                )
                # For ollama column in non-ollama-query rows, mark N/A
                if has_ollama and q["id"] not in OLLAMA_QUERY_IDS:
                    row = row.replace("| /12 |", "| /12 |", 3) + ""
                    row = f"| {q['id']} | {q['category']} | {q['difficulty']} | /12 | /12 | /12 | N/A |"
                write_line(f, row)
            else:
                write_line(f, f"| {q['id']} | {q['category']} | {q['difficulty']} | /12 | /12 | /12 | /12 |")

        write_line(f)
        write_line(f, "### Key Findings (fill in after scoring)")
        write_line(f)
        write_line(f, "**RAG+ vs RAG only**: Which mode scored higher overall, and on which queries was the difference largest?")
        write_line(f)
        write_line(f, "> *Your observation here*")
        write_line(f)
        write_line(f, "**RAG vs LLM only**: Did retrieval improve factual accuracy? Did it help for conceptual queries?")
        write_line(f)
        write_line(f, "> *Your observation here*")
        write_line(f)
        write_line(f, "**OpenAI vs Ollama**: Quality and speed comparison. What trade-offs did you observe?")
        write_line(f)
        write_line(f, "> *Your observation here*")
        write_line(f)
        write_line(f, "**Weaknesses identified**: Which query types or modes performed worst? What needs fixing before Phase 4?")
        write_line(f)
        write_line(f, "> *Your observation here*")
        write_line(f)


# ---------------------------------------------------------------------------
# File header
# ---------------------------------------------------------------------------

def write_file_header(provider: str) -> None:
    """Write the top-of-file header (only on first run / new file)."""
    if OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0:
        return  # Already has content — don't overwrite header

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        write_line(f, "# Phase 3 Comparative Test — Risk Explainer Agent")
        write_line(f)
        write_line(f, f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        write_line(f, f"**Project**: Maritime Fuel Risk Narrative System — MSc Dissertation, University of Greenwich")
        write_line(f, f"**Author**: Seymanur Ergezgin | Supervisor: Dr. Mike Sharp")
        write_line(f)
        write_line(f, "---")
        write_line(f)
        write_line(f, "## Test Configuration")
        write_line(f)
        write_line(f, "| Setting | Value |")
        write_line(f, "|---------|-------|")
        write_line(f, "| Queries tested | 8 (from the 25-query evaluation set) |")
        write_line(f, "| OpenAI modes | RAG+ (full system), RAG only, LLM only |")
        write_line(f, "| Ollama mode | RAG+ only (Q001, Q006, Q025) |")
        write_line(f, "| ChromaDB collection | risk_metrics (393 chunks) |")
        write_line(f, "| Embedding model | nomic-embed-text (Ollama, local) |")
        write_line(f, "| OpenAI LLM | gpt-4o-mini |")
        write_line(f, "| Ollama LLM | llama3.1:8b (CPU) |")
        write_line(f, "| Portfolio data | data/synthetic/risk_metrics.json (5 vessels, snapshot 2024-11-15) |")
        write_line(f)
        write_line(f, "## Scoring Rubric")
        write_line(f)
        write_line(f, "Each response is scored on 4 criteria, 0–3 each (max 12 per response):")
        write_line(f)
        write_line(f, "| Criterion | 0 | 1 | 2 | 3 |")
        write_line(f, "|-----------|---|---|---|---|")
        write_line(f, "| **Accuracy** | Wrong figures | Partially correct | Correct figures, vague | Exact figures + correct context |")
        write_line(f, "| **Structure** | No sections | Some sections | All 4 sections present | Sections correct + SUMMARY ≤50 words |")
        write_line(f, "| **Plain English** | Jargon / formula garbage | Mostly clear | Clear, no formulas | Clear + appropriate board tone |")
        write_line(f, "| **Completeness** | Misses expected elements | Gets ~50% | Gets ~75% | Covers all expected elements |")
        write_line(f)
        write_line(f, "## Query Set Overview")
        write_line(f)
        write_line(f, "| ID | Category | Difficulty | Query (shortened) |")
        write_line(f, "|----|----------|-----------|-------------------|")
        for q in TEST_QUERIES:
            short = q["query"][:60] + ("..." if len(q["query"]) > 60 else "")
            ollama_note = " *(Ollama included)*" if q["id"] in OLLAMA_QUERY_IDS else ""
            write_line(f, f"| {q['id']} | {q['category']} | {q['difficulty']} | {short}{ollama_note} |")
        write_line(f)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 3 comparative test: OpenAI vs Ollama, RAG+ vs RAG vs LLM-only"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "ollama", "all"],
        default="openai",
        help="Which provider(s) to test. 'all' runs OpenAI then Ollama. Default: openai",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*65}")
    print(f"  Phase 3 Comparative Test — Risk Explainer Agent")
    print(f"  Provider: {args.provider.upper()}")
    print(f"{'='*65}")

    write_file_header(args.provider)

    # Shared VectorStore (Ollama embeddings, reused across all tests)
    print("\n  Initialising VectorStore (loading Ollama embeddings)...", end=" ", flush=True)
    vs = VectorStore()
    print("done.")

    providers_run = []

    if args.provider in ("openai", "all"):
        run_openai_tests(vs)
        providers_run.append("openai")

    if args.provider in ("ollama", "all"):
        run_ollama_tests(vs)
        providers_run.append("ollama")

    write_scoring_summary(providers_run)

    print(f"\n  {'='*61}")
    print(f"  All tests complete.")
    print(f"  Results: {OUTPUT_FILE}")
    print(f"  {'='*61}\n")
    print(f"  Next steps:")
    print(f"  1. Open docs/test_results/phase3_comparative_test.md")
    print(f"  2. Read each response carefully")
    print(f"  3. Fill in the 'Manual scoring' tables (0-3 per criterion)")
    print(f"  4. Fill in the 'Key Findings' section at the bottom")
    print(f"  5. Discuss findings — then proceed to Phase 4\n")


if __name__ == "__main__":
    main()
