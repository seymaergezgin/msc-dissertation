# Project Documentation — Version 0.4
# AI-Based Narrative Risk Reporting for Maritime Fuel Management
# Last Updated: 2026-07-16
# Author: Seymanur Ergezgin | MSc Engineering Management, University of Greenwich
# Supervisor: Dr. Mike Sharp

---

## Changelog from v0.3 to v0.4

### Added
- `agents/hedge_advisor.py`: `HedgeAdvisorAgent` — RAG+ pattern over the `hedging` ChromaDB collection, using `HEDGE_ADVISOR_SYSTEM_PROMPT`. Portfolio context emphasises hedge ratios and hedged/unhedged dollar exposure per vessel.
- `agents/model_monitor.py`: `ModelMonitorAgent` — RAG+ pattern over the `risk_metrics` ChromaDB collection, using `MODEL_MONITOR_SYSTEM_PROMPT`. Portfolio context emphasises the VaR methodology/calibration block (method, confidence levels, time horizon, volatility basis, correlation assumption) rather than the resulting VaR/CVaR dollar figures.
- `src/orchestrator.py`: `Orchestrator` — keyword-based query router across all three agents, with a dedicated maritime-context case that overrides the retrieval collection, an ambiguous-query fallback, and a flat routing-history log.
- `tests/test_orchestrator.py`: 32 mocked unit tests covering routing for every keyword category, the maritime override, tie-break priority resolution, ambiguous fallback, response structure, and routing history.
- `data/terminal_logs/terminal_test_outputs`: archived Ollama connection-error logs from Phase 2/3 document-loader debugging (housekeeping, unrelated to Phase 4 code).

### Changed
- `agents/risk_explainer.py`: `answer()` gained an optional `collection_override: Optional[str] = None` parameter. When set, retrieval uses that ChromaDB collection instead of `self.collection` ("risk_metrics"), while the Risk Explainer persona and portfolio-data injection are unchanged. This is the mechanism the orchestrator uses to route maritime-context questions to the `maritime` collection without duplicating the RAG+ prompt-assembly logic elsewhere.

### Fixed
- **The Phase 3 Q017 gap** (Section 11, Finding 3 of the Phase 4 brief): questions like "Why does MV Iron Maiden use HSFO instead of VLSFO?" previously retrieved only from `risk_metrics` (VaR textbooks), which contain no IMO/scrubber/sulphur content, so the agent's answer omitted the actual regulatory reasoning. The orchestrator now detects maritime/regulatory keywords (IMO, sulphur, scrubber, HSFO, VLSFO, regulatory, Stopford) and routes to `RiskExplainerAgent` with `collection_override="maritime"`. Verified in the Phase 4 live test (Section 8.3 below): retrieval now pulls from `imo_mepc70_fuel_oil_availability_assessment_2016.pdf` and the answer explicitly discusses IMO sulphur regulation and scrubbers — neither appeared in the Phase 3 test.

### Knowledge Base State After Phase 4
No changes to the ChromaDB collections in Phase 4 — same 4 collections as v0.3 (`risk_metrics`: 393, `hedging`: 408, `maritime`: 4,502, `all`: 5,306 chunks). Phase 4 is a routing-layer addition, not a knowledge-base change.

---

## Changelog from v0.4 to v0.4.1 — Self-Review Findings and Refinements (2026-07-16)

Immediately after merging Phase 4, a self-review pass (requested by the student, performed before starting Phase 5) surfaced two concrete issues and two items worth deferring rather than fixing now. This section documents that review as dissertation evidence of iterative quality control, not as a sign Phase 4 was rushed — both issues were found by re-reading the merged code with fresh eyes, not by any test or user-reported bug.

### Fixed

**Finding 1 — Untested `collection_override` behaviour.** The Phase 4 merge added `collection_override` to `RiskExplainerAgent.answer()`, but no test in `tests/test_agents.py` exercised it directly — the only evidence it worked was the one-off live smoke test (Section 8.2), which is not repeatable or part of CI. Added two tests: `test_collection_override_changes_retrieval_collection` and `test_no_override_uses_agents_default_collection`, both verifying `pipeline.vs.query()` receives the expected `collection=` argument via `call_args.kwargs`.

**Finding 2 — The `"regulatory"` maritime keyword was too generic.** `MARITIME_KEYWORDS` (as originally implemented) included `"regulatory"` as an unconditional trigger for the maritime collection override, per the Phase 4 brief's own routing table. Because the maritime check ran before any other category, a query like *"What regulatory reporting standard should our risk model follow?"* — clearly a Model Monitor question — would have been hijacked into the `maritime` collection purely because it contains the word "regulatory". Fixed by splitting the keyword list into `MARITIME_STRONG_KEYWORDS` (imo, imo 2020, sulphur, sulfur, scrubber, hsfo, vlsfo, stopford — all maritime-specific, safe to always override on) and `MARITIME_WEAK_KEYWORDS` (regulatory — only overrides when no other category also matched a keyword). See Decision 15 below for the full rationale, and Section 8.5 for the specific test cases that prove the fix.

### Reviewed and Deliberately Deferred (not fixed now — documented for Phase 6 / the final release)

**Deferred item 1 — No routing-labelled evaluation set.** RQ3 ("can multi-agent routing improve response relevance?") is currently supported by one worked example (the Q017 before/after in Section 8.3), not a systematic measurement. Closing this properly means adding an `expected_agent` field to a routing-focused query set — a Phase 6 evaluation-design task, not a Phase 4/5 code change. Recorded here so it is planned for, not forgotten. See Section 12.2.

**Deferred item 2 — No graceful failure handling at the point a human will use the system live.** Phase 5 is the first phase where a person interacts with the system directly rather than via a test script or a one-off terminal command. Right now, an OpenAI rate-limit, a dropped Ollama connection, or any other transient failure would surface as a raw unhandled exception. The fix belongs in the Phase 5 UI layer (wrap `orchestrator.answer()` in a try/except and show a clean message) rather than in agent/orchestrator internals, so it is scoped into the Phase 5 plan (Section 12.2) instead of being retrofitted here.

**Not an issue, confirmed by re-check**: the monthly budget alert/threshold logic (`BudgetExceededError`, `BUDGET_ALERT_THRESHOLD` in `config/budget_config.py`, wired into `CostTracker.log_usage()`) was suspected as a possible gap during the review but was confirmed already implemented since Phase 1 — no action needed.

### Test Suite After Refinement
**95 tests passing** (89 after the original Phase 4 merge + 2 new `collection_override` tests + 4 new "regulatory" weak-keyword regression tests), all mocked — zero additional API cost for this refinement.

---

## 1. Executive Summary

This project builds a Multi-Agent LLM system that translates quantitative maritime fuel risk metrics into plain English narratives for business stakeholders. Phase 4 completes the three-agent system designed since Phase 1 and adds the orchestrator that routes queries between them.

**Current status**: Phase 4 complete — **67% of total project** (4 of 6 phases).

**Key achievements in v0.4**:
- Two new specialist agents (`HedgeAdvisorAgent`, `ModelMonitorAgent`) built on the same validated RAG+ pattern as the Risk Explainer, each with its own audience, system prompt, and collection
- A working orchestrator that routes queries to the correct specialist using keyword classification, with **95/95 unit tests passing** (57 existing + 32 from the initial Phase 4 merge + 6 from the post-merge self-review, all mocked)
- The single most important gap identified in Phase 3 testing — maritime/regulatory questions retrieving from the wrong collection — is now fixed and **verified working in a live test**
- A minimal, well-justified extension to `RiskExplainerAgent` (`collection_override`) that lets the orchestrator reuse existing agent logic instead of duplicating it
- A self-review pass immediately after merging caught and fixed a real routing edge case (the generic `"regulatory"` keyword could hijack a correctly-routed Model Monitor or Hedge Advisor query) and closed a test-coverage gap in the `collection_override` mechanism — see the v0.4.1 changelog above

**Key live test result** (2026-07-16):

> Query: *"Why does MV Iron Maiden use HSFO instead of VLSFO, and what are the cost implications?"* — the exact query that failed in the Phase 3 comparative test (Q017).
>
> **Before (Phase 3, RAG+ mode, `risk_metrics` collection)**: retrieved from `Value_at_risk.pdf`/`Value_at_risk_guide.pdf`. Missing elements: *scrubber*, *IMO 2020*.
>
> **After (Phase 4, orchestrator routes to `maritime` collection)**: retrieved from `imo_mepc70_fuel_oil_availability_assessment_2016.pdf` (5 chunks). Answer explicitly states: *"HSFO has a higher sulphur content, which may lead to regulatory challenges, especially with the International Maritime Organization's (IMO) regulations on sulphur emissions"* and recommends *"exploring options for scrubbers."*
>
> Response time: **3.76 seconds** | Cost: **$0.000466**

---

## 2. Problem Statement

*(Unchanged from v0.1 — see that document.)*

Maritime fuel companies generate complex quantitative risk reports (VaR, CVaR, hedge ratios) that create a communication gap between risk analysts and non-technical decision-makers. This system acts as an intelligent interpreter, producing plain-language explanations grounded in the actual metric data.

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│                   (Streamlit — Phase 5)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ natural language query
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR  ✅ (Phase 4)                    │
│   1. Keyword-match query against 3 routing tables + maritime     │
│      override case                                                │
│   2. Dispatch to the winning agent (with collection_override      │
│      when the maritime case matched)                              │
│   3. Merge routed_to / routing_reason / confidence into the       │
│      agent's response dict                                        │
│   4. Append to flat routing-history log                           │
└──────────┬──────────────────┬───────────────────┬──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
  │ RISK EXPLAINER │  │ HEDGE ADVISOR  │  │ MODEL MONITOR  │
  │    AGENT  ✅   │  │    AGENT  ✅   │  │    AGENT  ✅   │
  │  (Phase 3)     │  │  (Phase 4)     │  │  (Phase 4)     │
  │  risk_metrics  │  │  hedging       │  │  risk_metrics  │
  │  (or maritime  │  │  collection    │  │  collection    │
  │  when routed)  │  │                │  │                │
  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
          │                   │                    │
          ▼                   ▼                    ▼
  ┌───────────────────────────────────────────────────────┐
  │     RAG+ PIPELINE (Phase 2 + Phase 3, reused as-is)   │
  │                                                       │
  │  [1] Live Portfolio Data (risk_metrics.json)          │
  │      ↓  injected as "Context 0" (per-agent formatter) │
  │  [2] ChromaDB retrieval (top-5 relevant chunks)       │
  │      ↓  appended after portfolio data                 │
  │  [3] LLM generation with agent system prompt          │
  └───────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
  ┌──────────────────┐      ┌─────────────────────┐
  │   VECTOR STORE   │      │    LLM PROVIDER     │
  │   (ChromaDB)     │      │  OpenAI gpt-4o-mini │
  │  5,306 chunks    │      │  (dev + evaluation) │
  │  4 collections   │      │  Ollama (offline)   │
  └──────────────────┘      └─────────────────────┘
```

### 3.2 Technology Stack

*(Unchanged from v0.2/v0.3 — see those documents for rationale.)* `langgraph==1.2.6` remains pinned in `requirements.txt` but is **not used as a StateGraph** in this version — see Decision 12 below.

| Component | Technology | Version |
|-----------|------------|---------|
| Agent Framework | Plain Python classifier (LangGraph pinned, unused this phase) | langgraph 1.2.6 |
| LLM | OpenAI gpt-4o-mini / Ollama llama3.1:8b | Latest |
| Vector Database | ChromaDB | 0.6.3 |
| Embeddings | nomic-embed-text via Ollama | Latest |
| Agent base class | Custom Python ABC | — |
| UI | Streamlit (Phase 5) | 1.43.2 |

### 3.3 Design Decisions

#### Decision 12: Keyword Classifier Instead of a LangGraph StateGraph

**Decision**: The Phase 4 orchestrator (`src/orchestrator.py`) is a plain Python class that scores query keywords against per-agent keyword lists. It does not use LangGraph's `StateGraph` / node-and-edge graph API, even though `langgraph` has been a pinned dependency since Phase 1.

**Context**: The original project brief (`CLAUDE_CODE_PROMPT.md`) and the Phase 4 prompt both label the orchestrator a "LangGraph Supervisor." The Phase 4 brief simultaneously warns, in its explicit "what not to do" list: *"Do NOT make the orchestrator too complex on first pass — a simple keyword classifier + semantic fallback is better than an over-engineered state machine that doesn't work."*

**Problem**: A `StateGraph` is designed for workflows with multiple steps, conditional branches, and persisted state across turns. Phase 4's actual routing problem — pick 1 of 3 agents based on query content, occasionally override a collection — does not need graph machinery to solve.

**Rationale**: Building the graph abstraction now, before evaluation (Phase 6) has shown whether keyword routing is even insufficient, would be solving a problem that may not exist. The `Orchestrator` class exposes the same conceptual shape a graph node would (`route()` decides, `answer()` executes) so migrating to a real `StateGraph` later — if evaluation shows keyword routing misclassifies too often — is a contained change, not a rewrite.

**Consequences**: If Phase 6 evaluation reveals systematic misrouting (e.g., queries that mix vocabulary from two agents in ways keyword-counting can't resolve), a semantic/embedding-based classifier — or LangGraph proper — is the documented next step, not a design admission of failure.

---

#### Decision 13: `collection_override` as a Minimal Extension, Not a New Abstraction

**Decision**: `RiskExplainerAgent.answer()` gained one optional parameter, `collection_override: Optional[str] = None`, rather than introducing a separate "MaritimeRiskExplainer" agent or duplicating the RAG+ prompt-assembly logic inside the orchestrator.

**Context**: The Phase 3 Q017 finding showed that maritime-regulatory questions need the `maritime` collection, but the *persona and portfolio injection* that make Risk Explainer answers useful (board-level tone, live VaR/CVaR figures, 4-section format) are still exactly right for those questions — only the *retrieval source* is wrong.

**Options considered**:
1. A fourth agent, e.g. `MaritimeContextAgent` — rejected: would duplicate `RiskExplainerAgent` almost entirely for a difference of one line (which collection to query).
2. Reimplement RAG+ prompt assembly inside `src/orchestrator.py` for this one case — rejected: duplicates `_format_portfolio_as_context()` and the RAG+ ordering logic that Decision 9 (v0.3) established as a core methodology contribution; a bug fix there would need to be applied in two places.
3. One optional parameter on `answer()` that swaps only the retrieval collection — **chosen**.

**Rationale**: This keeps the RAG+ pattern's implementation in exactly one place while giving the orchestrator the hook it needs. It required amending `agents/risk_explainer.py` despite Section 18 of the Phase 4 brief generally protecting Phase 3 files from change — but that section explicitly permits extension "if Phase 4 genuinely requires it," and this is that case.

**Consequences**: `HedgeAdvisorAgent` and `ModelMonitorAgent` do not have an equivalent override parameter yet, because no Phase 4 routing case currently needs to redirect their retrieval. If a future phase needs, say, the Hedge Advisor to answer from the `maritime` collection too, the same pattern should be applied there rather than inventing a different mechanism.

---

#### Decision 14: Routing History as a Flat Log, Not Multi-Turn Memory

**Decision**: `Orchestrator.answer()` appends `{query, routed_to, confidence, timestamp}` to `self.history` after every call. There is no mechanism for a later query to reference an earlier one (no pronoun resolution, no carried-over context).

**Context**: Section 10 of the Phase 4 brief lists "manages conversation state for multi-turn queries" as an orchestrator responsibility, while Section 18 explicitly warns against adding features beyond what Phase 4 requires and against over-engineering the orchestrator.

**Rationale**: A flat routing-history log satisfies the practical need this phase actually has — a queryable record of what was asked, which agent handled it, and how confident the routing was, useful both for debugging and as dissertation evidence of routing behaviour. True multi-turn context-carrying (e.g., "what about the second one?" referring back to a previous vessel comparison) is a materially larger feature with its own design questions (how much history to carry, how to detect referential language) that were not required by any Phase 4 checklist item or test.

**Consequences**: If a later phase (UI, or evaluation) surfaces a real need for follow-up-question handling, this log is the natural place to build from — but it does not yet support it.

---

#### Decision 15: Splitting Maritime Keywords into "Strong" and "Weak" Signals

**Decision**: `MARITIME_KEYWORDS` was split into `MARITIME_STRONG_KEYWORDS` (imo, imo 2020, sulphur, sulfur, scrubber, hsfo, vlsfo, stopford) and `MARITIME_WEAK_KEYWORDS` (regulatory). A strong keyword always triggers the maritime collection override, regardless of what else matched. A weak keyword only triggers it when no other category (Risk Explainer, Hedge Advisor, Model Monitor) also matched something.

**Context**: found during a self-review immediately after the Phase 4 merge (see the v0.4.1 changelog above), not during original implementation or testing. The original routing table (Section 10 of the Phase 4 brief) listed "regulatory" alongside genuinely maritime-specific terms like "IMO" and "scrubber" — reasonable at the table-design stage, but every other word in that list is maritime-specific, while "regulatory" is a word that legitimately belongs in Model Monitor questions too (e.g. "regulatory reporting for our VaR model").

**Problem**: because the maritime check runs before category scoring (by design — Decision in Section 3.3 above explains why maritime must take priority), an unconditional "regulatory" trigger would silently override a correct Model Monitor or Hedge Advisor routing decision any time that one word appeared, with no way for the rest of the query to override it back.

**Rationale**: the fix keeps the maritime-priority design intact for the cases that actually need it (unambiguous maritime vocabulary) while removing the one keyword broad enough to cause false positives. "Regulatory" is not discarded — it still triggers the maritime override when it is the *only* signal present, which is the case the brief's routing table was actually trying to capture (a query with no other domain vocabulary, just asking about "regulatory" matters, is very likely maritime/IMO-related in this system's context).

**Consequences**: this is a deliberately narrow, low-risk fix — it changes behaviour only for the specific case of "regulatory" co-occurring with another category's keywords, which is exactly the scenario that was wrong before. All existing Phase 4 tests continued to pass unchanged; new regression tests (`TestRegulatoryWeakKeywordRouting` in `tests/test_orchestrator.py`) were added specifically to prove the fix and guard against reintroducing the issue.

---

## 4. Component Deep-Dive

### 4.1 Hedge Advisor Agent (`agents/hedge_advisor.py`)

#### Purpose
Answers questions from the treasury/risk team about the fleet's hedging position: whether the current hedge ratio is adequate, how much dollar exposure is unhedged, and what hedging instruments or strategy changes might be warranted.

#### How It Works
Structurally identical to `RiskExplainerAgent` (same five-step `answer()` flow: retrieve → inject portfolio context → build prompt → call LLM → log cost), but:
- Queries the `hedging` ChromaDB collection (Kavussanos, Sun, Bai, Han maritime hedging papers) instead of `risk_metrics`
- `_format_portfolio_as_context()` reads the **same** `risk_metrics.json` file as the other two agents, but surfaces different fields: `hedge_ratio_pct`, `hedged_exposure_usd`, `unhedged_exposure_usd` per vessel, plus fleet-wide totals computed by summing across vessels
- Uses `HEDGE_ADVISOR_SYSTEM_PROMPT` (SUMMARY / ANALYSIS / RECOMMENDATION / MARKET CONTEXT format)

#### Code Structure
```
agents/hedge_advisor.py
├── RISK_METRICS_PATH              — path to data/synthetic/risk_metrics.json
└── HedgeAdvisorAgent(BaseAgent)
    ├── name = "Hedge Advisor"
    ├── collection = "hedging"
    ├── __init__()                       — loads snapshot, calls super().__init__()
    ├── answer()                         — retrieve + inject + generate + log
    ├── system_prompt                    — returns HEDGE_ADVISOR_SYSTEM_PROMPT
    ├── _load_risk_snapshot()            — reads risk_metrics.json
    ├── _format_portfolio_as_context()   — hedging-focused context block
    └── _get_snapshot_summary()          — hedging-focused summary dict
```

#### Example Usage
```python
from agents.hedge_advisor import HedgeAdvisorAgent

agent = HedgeAdvisorAgent()
result = agent.answer("Is our current hedge ratio of 48% sufficient?")

print(result["answer"])                                        # Structured plain-English response
print(result["portfolio_snapshot"]["total_unhedged_exposure_usd"])  # 20,664,753
```

**Live test result** (2026-07-16): asked *"Is our current hedge ratio of 48% sufficient given our unhedged exposure?"* — response correctly computed total unhedged exposure as $20,664,753 (~60% of $34,298,985 total fuel cost) and recommended a target hedge ratio of ~70%, citing Kavussanos et al. (2022) for IMO 2020 regulatory context. Response time: 4.20s. Cost: $0.000403.

---

### 4.2 Model Monitor Agent (`agents/model_monitor.py`)

#### Purpose
Reviews the health of the VaR *model itself* — not the portfolio's risk level — for the quant team and risk committee. Answers questions about whether calibration assumptions (correlation, volatility window) still hold and when recalibration is warranted.

#### How It Works
Same five-step flow as the other two agents, but:
- Queries `risk_metrics` (same collection as Risk Explainer — both reason about VaR methodology, for different audiences)
- `_format_portfolio_as_context()` surfaces the `methodology` block (`var_method`, `confidence_levels`, `time_horizon`, `volatility_basis`, `correlation_assumption`) plus per-vessel observed daily/annualised volatility — the calibration inputs a model reviewer checks for drift — rather than the resulting VaR/CVaR dollar figures
- Uses `MODEL_MONITOR_SYSTEM_PROMPT` (STATUS traffic-light / FINDINGS / RECOMMENDATION / TECHNICAL NOTES format)

#### Code Structure
```
agents/model_monitor.py
├── RISK_METRICS_PATH              — path to data/synthetic/risk_metrics.json
└── ModelMonitorAgent(BaseAgent)
    ├── name = "Model Monitor"
    ├── collection = "risk_metrics"
    ├── __init__()                       — loads snapshot, calls super().__init__()
    ├── answer()                         — retrieve + inject + generate + log
    ├── system_prompt                    — returns MODEL_MONITOR_SYSTEM_PROMPT
    ├── _load_risk_snapshot()            — reads risk_metrics.json
    ├── _format_portfolio_as_context()   — methodology-focused context block
    └── _get_snapshot_summary()          — methodology-focused summary dict
```

#### Example Usage
```python
from agents.model_monitor import ModelMonitorAgent

agent = ModelMonitorAgent()
result = agent.answer("Are our correlation assumptions still valid?")

print(result["answer"])                                    # STATUS: AMBER/GREEN/RED + findings
print(result["portfolio_snapshot"]["correlation_assumption"])  # "Perfect positive correlation..."
```

**Live test result** (2026-07-16): asked *"Are our VaR model correlation assumptions still valid, or is recalibration needed?"* — returned **STATUS: AMBER**, flagged the perfect-positive-correlation assumption as a potential underestimate of risk given observed 40.2% annualised volatility, and recommended considering a GARCH model plus regular backtesting. Response time: 3.41s. Cost: $0.000308.

---

### 4.3 Orchestrator (`src/orchestrator.py`)

#### Purpose
The single entry point for a query: decides which of the three agents should answer it, invokes that agent (with a collection override when needed), and returns the agent's response annotated with routing metadata.

#### How It Works (Step by Step)

```
User: "Why does MV Iron Maiden use HSFO instead of VLSFO?"
   │
   ▼ Step 1: route() — lower-case the query, check keyword sets
   MARITIME_KEYWORDS match: ['hsfo', 'vlsfo']   ← checked FIRST, takes priority
   → agent_key = "risk_explainer", collection_override = "maritime"
   │
   ▼ Step 2: answer() — dispatch to the winning agent
   RiskExplainerAgent.answer(query, collection_override="maritime")
   # Same persona/portfolio injection as usual, but retrieves from
   # the "maritime" ChromaDB collection instead of "risk_metrics"
   │
   ▼ Step 3: merge routing metadata into the agent's response dict
   result["routed_to"] = "Risk Explainer"
   result["routing_reason"] = "Matched maritime/regulatory keyword(s)
                                ['hsfo', 'vlsfo'] — routed to Risk Explainer
                                with the 'maritime' collection override..."
   result["confidence"] = "high"
   │
   ▼ Step 4: append to routing history log
   self.history.append({query, routed_to, confidence, timestamp})
   │
   ▼ return result
```

#### Routing Logic Detail

`route()` evaluates categories in this order:

1. **Maritime check first** — `MARITIME_KEYWORDS = ["imo", "imo 2020", "sulphur", "sulfur", "scrubber", "hsfo", "vlsfo", "regulatory", "stopford"]`. If any match, the query is routed to Risk Explainer with `collection_override="maritime"` regardless of what else matches. This is checked before the other three categories because it changes *how* the winning agent is invoked, not just *which* agent wins, and because Section 11 of the Phase 4 brief calls it "the single most important gap."
2. **Category keyword scoring** — if no maritime keywords matched, `route()` counts keyword hits for `risk_explainer`, `hedge_advisor`, and `model_monitor` against their respective lists (see Section 6.5 below for the full table) and picks the category with the most hits.
3. **Tie-break** — if two categories tie on hit count, the winner is whichever appears first in `PRIORITY_ORDER = ["risk_explainer", "hedge_advisor", "model_monitor"]` (mirroring the top-to-bottom order of the routing table in the Phase 4 brief), and confidence drops from `"high"` to `"medium"`.
4. **Ambiguous fallback** — if no category matched at all, default to Risk Explainer with `confidence="low"`.

#### Code Structure
```
src/orchestrator.py
└── Orchestrator
    ├── RISK_EXPLAINER_KEYWORDS / HEDGE_ADVISOR_KEYWORDS /
    │   MODEL_MONITOR_KEYWORDS / MARITIME_KEYWORDS   — class-level keyword tables
    ├── PRIORITY_ORDER                                — tie-break order
    ├── __init__(agents)          — builds/accepts the 3 agents, empty history list
    ├── route(query)               — decides agent_key, collection_override, reason, confidence
    ├── answer(query)              — routes, dispatches, merges metadata, logs history
    ├── get_agent_info()           — metadata for all 3 agents, no LLM calls
    ├── get_routing_history()      — returns the flat routing log
    ├── _match_keywords()          — substring-match helper
    └── _agent_label()             — agent name lookup for routing_reason messages
```

#### Example Usage
```python
from src.orchestrator import Orchestrator

orchestrator = Orchestrator()

result = orchestrator.answer("Why does MV Iron Maiden use HSFO instead of VLSFO?")
print(result["routed_to"])       # "Risk Explainer"
print(result["routing_reason"])  # explains the maritime override
print(result["confidence"])      # "high"
print(result["answer"])          # plain-English response, now grounded in IMO/scrubber content

print(orchestrator.get_routing_history())  # flat log of all queries answered so far
```

---

## 5. Data Architecture

*(Unchanged from v0.2/v0.3 — knowledge base and synthetic data documented there.)* Phase 4 introduces no new documents and no new synthetic data files — all three agents read the same `data/synthetic/risk_metrics.json` snapshot, each surfacing a different subset of its fields.

### 5.1 Knowledge Base State (Unchanged from v0.3)

| Category | Files | Chunks | Status |
|----------|-------|--------|--------|
| risk_metrics | 4 | 393 | ✅ Used by Risk Explainer + Model Monitor |
| hedging | 4 | 408 | ✅ Used by Hedge Advisor |
| maritime | 8 | 4,502 | ✅ Used by Risk Explainer when maritime-routed |
| all (merged) | 16 | 5,306 | Not queried by any Phase 3/4 agent directly |

---

## 6. Agent System

### 6.1 Orchestrator (✅ Implemented — Phase 4)

| Attribute | Value |
|-----------|-------|
| Routing method | Keyword classifier (deliberately not a LangGraph StateGraph — see Decision 12) |
| Categories | Risk Explainer, Hedge Advisor, Model Monitor, + maritime collection-override case |
| Fallback | Ambiguous queries → Risk Explainer, confidence "low" |
| State | Flat routing-history log (query, routed agent, confidence, timestamp) — not multi-turn context (see Decision 14) |

### 6.2 Risk Explainer Agent (✅ Implemented — Phase 3, extended Phase 4)

| Attribute | Value |
|-----------|-------|
| Role | Answers questions about VaR, CVaR, portfolio exposure, fuel price risk |
| ChromaDB collection | `risk_metrics` (or `maritime`, via `collection_override`) |
| Live data source | `data/synthetic/risk_metrics.json` |
| System prompt persona | Senior maritime fuel risk analyst (board presentations) |
| Response format | SUMMARY / EXPLANATION / BUSINESS IMPLICATIONS / CAVEATS |

### 6.3 Hedge Advisor Agent (✅ Implemented — Phase 4)

| Attribute | Value |
|-----------|-------|
| Role | Hedging positions, strategy, instrument selection |
| ChromaDB collection | `hedging` |
| System prompt persona | Maritime fuel hedging specialist (treasury team) |
| Response format | SUMMARY / ANALYSIS / RECOMMENDATION / MARKET CONTEXT |

### 6.4 Model Monitor Agent (✅ Implemented — Phase 4)

| Attribute | Value |
|-----------|-------|
| Role | Model drift detection, recalibration recommendations |
| ChromaDB collection | `risk_metrics` |
| System prompt persona | Quantitative risk model validation specialist |
| Response format | STATUS (GREEN/AMBER/RED) / FINDINGS / RECOMMENDATION / TECHNICAL NOTES |

### 6.5 Routing Table (Complete)

| Keywords (substring match, case-insensitive) | Routed Agent | Collection |
|---|---|---|
| var, cvar, value at risk, exposure, volatility, methodology | Risk Explainer | risk_metrics |
| hedge, hedging, hedge ratio, futures, swap, unhedged | Hedge Advisor | hedging |
| model, drift, recalibrate, recalibration, assumption, correlation, historical window | Model Monitor | risk_metrics |
| imo, imo 2020, sulphur, sulfur, scrubber, hsfo, vlsfo, regulatory, stopford | Risk Explainer | **maritime** (override) |
| *(no keyword matched)* | Risk Explainer (fallback) | risk_metrics |

---

## 7. Prompt Engineering

### 7.1 Prompt Design Philosophy

*(Unchanged from v0.3 — audience specificity, format enforcement, source attribution. See that document Section 7.1 for the full rationale.)*

### 7.2 HEDGE_ADVISOR_SYSTEM_PROMPT and MODEL_MONITOR_SYSTEM_PROMPT — How They Work

Both prompts were written in Phase 3 (`prompts/system_prompts.py`) but exercised for the first time in Phase 4:

**HEDGE_ADVISOR_SYSTEM_PROMPT**: Persona is "maritime fuel hedging specialist advising the treasury and risk management team." The key instruction — *"distinguish clearly between hedged and unhedged exposure in dollar terms"* — is what produced the $13,634,232 hedged / $20,664,753 unhedged breakdown in the live test, rather than a vaguer "roughly half is hedged" answer.

**MODEL_MONITOR_SYSTEM_PROMPT**: Persona is "quantitative risk model validation specialist." The instruction to output a GREEN/AMBER/RED status line first is what produced the traffic-light `**STATUS**: AMBER` opening in the live test — a format specifically useful for a risk-committee audience that needs to triage model health at a glance before reading technical detail.

### 7.3 Context Block Structure — Per-Agent Variation

All three agents use the same RAG+ prompt skeleton (`CONTEXT DOCUMENTS: [portfolio block] --- [retrieved chunks] --- USER QUESTION`), but each agent's portfolio block surfaces different fields from the same `risk_metrics.json`:

| Agent | Portfolio block emphasises |
|---|---|
| Risk Explainer | Fuel prices, portfolio VaR/CVaR (95%/99%), average hedge ratio, per-vessel VaR/CVaR |
| Hedge Advisor | Average hedge ratio, total hedged/unhedged exposure (fleet + per-vessel) |
| Model Monitor | VaR method name, confidence levels, time horizon, volatility basis, correlation assumption, per-vessel observed volatility |

This is the same "portfolio data before retrieved documents" ordering established in v0.3 Decision 9 — unchanged in Phase 4, just re-purposed per agent.

---

## 8. Evaluation Methodology

### 8.1 Unit Testing (Phase 4)

`tests/test_orchestrator.py` — 32 mocked tests (exceeding the ~20 target in the Phase 4 brief; all still scoped to the required routing/fallback/structure checks, not speculative additions):

| Test class | Count | Verifies |
|---|---|---|
| `TestOrchestratorSetup` | 4 | Agent injection, default construction, empty history, `get_agent_info()` |
| `TestRiskExplainerRouting` | 4 | VaR/CVaR/exposure keywords route correctly, confidence is high |
| `TestHedgeAdvisorRouting` | 3 | hedge/unhedged/futures keywords route correctly |
| `TestModelMonitorRouting` | 3 | drift/recalibrate/correlation keywords route correctly |
| `TestMaritimeContextRouting` | 6 | HSFO/IMO/scrubber trigger the maritime override; override kwarg is (or isn't) passed correctly |
| `TestFallbackRouting` | 3 | Ambiguous queries fall back to Risk Explainer, confidence low |
| `TestOrchestratorAnswer` | 5 | Response dict structure, `routed_to`, `confidence` validity |
| `TestRoutingHistory` | 3 | History accumulates correctly across calls |
| `TestTieBreakRouting` | 1 | Overlapping keywords resolve via `PRIORITY_ORDER` |
| `TestRegulatoryWeakKeywordRouting` *(added in the v0.4.1 self-review)* | 3 | "regulatory" alone still routes to maritime; "regulatory" does NOT override a clear Model Monitor or Hedge Advisor match |

Plus, in `tests/test_agents.py` (added in the v0.4.1 self-review): `test_collection_override_changes_retrieval_collection` and `test_no_override_uses_agents_default_collection`, directly verifying the `collection_override` mechanism against a real (mocked-pipeline) `RiskExplainerAgent`, not just against a mocked orchestrator.

**Total test suite**: **95 passing** (57 from Phase 3 + 32 from the initial Phase 4 merge + 6 from the post-merge self-review), 100% mocked — zero API cost.

### 8.5 Regression Cases: The "Regulatory" Keyword Fix

These are the specific queries used to prove Finding 2 (Section "Changelog from v0.4 to v0.4.1") is fixed, kept here as a permanent record of the exact before/after behaviour:

| Query | Before the fix | After the fix |
|---|---|---|
| "What are the regulatory requirements for our fleet?" (no competing category) | Routes to maritime | Still routes to maritime (confidence "medium" — correct, no regression) |
| "What regulatory reporting standard should our risk model follow?" | Would have routed to maritime (wrong) | Routes to Model Monitor (correct) |
| "Are there regulatory constraints on the futures we use to hedge?" | Would have routed to maritime (wrong) | Routes to Hedge Advisor (correct) |
| "Should we hedge our HSFO exposure given IMO rules?" (strong keyword present) | Routes to maritime | Still routes to maritime (strong keywords always win — correct, no regression) |

### 8.2 Live Orchestrator Test (2026-07-16)

Five representative queries were run through the real `Orchestrator` (OpenAI gpt-4o-mini, Ollama embeddings) to verify routing works end-to-end, not just against mocks:

| Query | Routed to | Confidence | Cost |
|---|---|---|---|
| "What is our current portfolio VaR at 95% confidence?" | Risk Explainer | high | $0.000377 |
| "Is our current hedge ratio of 48% sufficient given our unhedged exposure?" | Hedge Advisor | high | $0.000403 |
| "Are our VaR model correlation assumptions still valid, or is recalibration needed?" | Model Monitor | high | $0.000308 |
| "Why does MV Iron Maiden use HSFO instead of VLSFO...?" (Q017) | Risk Explainer + maritime override | high | $0.000466 |
| "Tell me something about our fleet." (ambiguous) | Risk Explainer | **low** | $0.000357 |

**Total live test cost: $0.0019** (5 calls, well under the $0.05 Phase 4 live-testing budget in the brief).

### 8.3 The Q017 Fix, Before/After

This is the clearest evidence Phase 4 solved the problem it set out to solve:

| | Phase 3 (Section 11, Finding 3) | Phase 4 (this test) |
|---|---|---|
| Collection queried | `risk_metrics` | `maritime` |
| Sources retrieved | `Value_at_risk.pdf`, `Value_at_risk_guide.pdf` | `imo_mepc70_fuel_oil_availability_assessment_2016.pdf` (5 chunks) |
| Expected elements found | 3/5 (missing: scrubber, IMO 2020) | Answer explicitly names "International Maritime Organization's (IMO) regulations on sulphur emissions" and recommends "exploring options for scrubbers" |

### 8.4 Full Evaluation (Phase 6 — not yet run)

The 25-query set in `prompts/risk_prompts.py` does not yet include orchestrator-specific routing queries. Per the Phase 4 brief, adding those is explicitly scoped to Phase 6, not Phase 4.

---

## 9. Challenges and Solutions

*(v0.2/v0.3 entries carried forward — new entries below.)*

| Challenge | Impact | Solution | Lesson Learned |
|-----------|--------|----------|----------------|
| Maritime-context questions routing to the wrong collection (Phase 3 Q017) | Agent answers omitted IMO/scrubber reasoning entirely | Orchestrator detects maritime keywords first, overrides `RiskExplainerAgent`'s retrieval collection to `maritime` | Collection-per-agent routing (v0.3 Decision 10) solves precision within a domain but creates gaps at domain boundaries — a routing layer above the agents is where cross-domain cases get fixed, not inside a single agent |
| Risk of duplicating RAG+ prompt logic for the maritime special case | Two implementations of the same context-assembly logic to keep in sync | Added one optional `collection_override` parameter to `RiskExplainerAgent.answer()` instead of a new agent or orchestrator-side reimplementation | A single well-placed parameter can resolve a routing requirement more cleanly than a new abstraction — reach for the smallest change that satisfies the actual need |
| Overlapping keywords across routing categories (e.g. "exposure" matches Risk Explainer, "unhedged" matches Hedge Advisor, in the same query) | A naive first-match classifier could route inconsistently | Implemented full keyword-count scoring across all categories with an explicit, documented tie-break priority order | Even a "simple" keyword classifier needs a deterministic tie-break rule once real queries are tried — don't assume keyword sets are mutually exclusive |
| Temptation to build the orchestrator as a LangGraph `StateGraph` because the dependency was already pinned and the tech-stack table already listed it | Risk of overengineering the first pass, per the Phase 4 brief's explicit warning | Built a plain keyword-classifier class instead; documented the LangGraph deferral as Decision 12 | Having a dependency installed is not a reason to use its most complex API — match the tool to the problem's actual complexity |
| The generic `"regulatory"` keyword, copied directly from the brief's own routing table, could hijack a correctly-routed Model Monitor or Hedge Advisor question | A query like "what regulatory reporting standard should our risk model follow?" would have been wrongly routed to the maritime collection | Split maritime keywords into strong (always override) and weak (`"regulatory"` — only overrides when no other category matched); see Decision 15 | Even a keyword list taken directly from a design brief should be re-examined for words that are too generic once real queries are tried against it — don't assume a source document's routing table is final |
| `collection_override` (a Phase 4 extension to a Phase 3 file) went live-tested but not unit-tested | A regression in this one-line behaviour could pass the full test suite undetected | Added two direct tests in `tests/test_agents.py` verifying the exact `collection=` argument passed to retrieval | A live smoke test proves a feature works once; it does not replace a repeatable unit test — any new parameter on an existing method needs its own test, even a small one |

---

## 10. Academic Relevance

### 10.1 Research Questions Addressed

- **RQ1**: Can LLM-based agents accurately explain maritime fuel risk metrics in natural language?
  — *Reconfirmed in Phase 4: all three agents produce structured, figure-grounded answers (see Section 8.2 live test table).*

- **RQ2**: Does RAG-augmented generation produce more accurate explanations than base LLM?
  — *Unchanged from Phase 3 — full comparative scoring remains a Phase 6 activity.*

- **RQ3**: Can multi-agent routing improve response relevance compared to a single agent?
  — *Phase 4 directly answers this. The Q017 before/after (Section 8.3) is direct evidence: the same underlying LLM and RAG+ mechanism produced a materially better answer purely because the orchestrator routed retrieval to the correct collection. This is the strongest empirical result Phase 4 has to offer the dissertation.*

### 10.2 Literature Connections

**Multi-agent routing and specialisation**: The collection-per-agent design (v0.3 Decision 10) combined with Phase 4's cross-domain routing fix mirrors a recurring theme in the 2023–2024 multi-agent LLM literature: specialist agents outperform a single generalist agent on domain-specific tasks, provided a routing mechanism correctly identifies which specialist a given query needs. The Q017 case is a concrete, small-scale demonstration of exactly this trade-off and its resolution.

**Simplicity as a design principle**: The explicit choice to defer LangGraph's `StateGraph` (Decision 12) reflects the "start with the simplest thing that could work" principle common in agentic-systems engineering practice — relevant to the dissertation's methodology chapter discussion of engineering decisions made under a defined scope and budget.

### 10.3 Methodology Mapping

| Dissertation Section | Project Component | Status |
|----------------------|-------------------|--------|
| 4.4 Agent Design | agents/, prompts/ | ✅ Complete (v0.3) |
| 4.6 Multi-Agent Orchestration | src/orchestrator.py | ✅ Complete (v0.4) |
| 4.6.1 Hedge Advisor Agent | agents/hedge_advisor.py | ✅ Complete (v0.4) |
| 4.6.2 Model Monitor Agent | agents/model_monitor.py | ✅ Complete (v0.4) |
| 4.6.3 Cross-Domain Routing | src/orchestrator.py (maritime override) | ✅ Complete (v0.4) |
| 4.7 UI | ui/app.py | Phase 5 |
| 5.1 Evaluation Results | evaluation/ | Phase 6 |

---

## 11. Cost Analysis

### 11.1 API Costs to Date

| Phase | Provider | Queries | Est. Cost USD |
|-------|----------|---------|---------------|
| 1–3 (per v0.3) | Ollama / OpenAI | ~15 | ~$0.0074 |
| 4 (live orchestrator test) | OpenAI gpt-4o-mini | 5 | $0.0019 |
| **Total to date** | | **~20** | **~$0.0093** |

**Remaining budget**: $9.99 of $10.00 monthly limit.

**Projected remaining spend (Phases 5–6)**:
- Phase 5 UI manual testing (estimated 20–30 queries): ~$0.015
- Phase 6 evaluation (25 queries × 3 modes × ~1–2 runs): ~$0.05–0.08
- **Total project estimate remains under $0.20** — well within the $10.00 budget.

### 11.2 Resource Usage

| Activity | Time |
|----------|------|
| Phase 4 implementation (2 agents + orchestrator + 32 tests) | ~1 session |
| Full test suite (89 tests) | 39.99s |
| Live orchestrator test (5 queries) | ~26s total (avg 4.3s/query) |

---

## 12. Next Steps

### 12.1 Completed in This Version (v0.4)
- [x] `agents/hedge_advisor.py`: Hedge Advisor Agent
- [x] `agents/model_monitor.py`: Model Monitor Agent
- [x] `agents/risk_explainer.py`: `collection_override` extension
- [x] `src/orchestrator.py`: keyword-based router with maritime override, fallback, and routing history
- [x] `tests/test_orchestrator.py`: 32 new mocked tests (89 total, all passing)
- [x] Live orchestrator test: all 3 agents exercised, maritime gap fix verified, ambiguous fallback verified
- [x] Phase 3 Q017 gap confirmed fixed with a direct before/after comparison
- [x] **Post-merge self-review (v0.4.1)**: closed the `collection_override` test-coverage gap (2 new tests) and fixed the `"regulatory"` keyword over-triggering false positive (strong/weak maritime split + 3 regression tests); 95/95 tests passing

### 12.2 Planned for Next Version (v0.5 — Phase 5: Streamlit UI)
- [ ] `ui/app.py`: Streamlit interface for submitting queries and displaying agent responses
- [ ] Query input with routing transparency (show `routed_to` / `routing_reason` / `confidence` to the user)
- [ ] Source citation display
- [ ] Cost tracker display (running spend vs. $10 budget)
- [ ] **Graceful error handling at the UI boundary** (deferred from the v0.4.1 self-review, Deferred item 2): wrap `orchestrator.answer()` calls in a try/except so an OpenAI rate-limit or a dropped Ollama connection shows the user a clean message instead of a raw traceback

### 12.2.1 Planned for Phase 6 (Evaluation)
- [ ] **Routing-labelled evaluation queries** (deferred from the v0.4.1 self-review, Deferred item 1): add an `expected_agent` field to a routing-focused query set so RQ3 ("multi-agent routing improves response relevance") has systematic quantitative evidence, not only the single Q017 before/after comparison in Section 8.3

### 12.3 Before Starting Phase 5

1. **Consider whether `HedgeAdvisorAgent`/`ModelMonitorAgent` need their own `collection_override`** if Phase 5/6 testing surfaces a cross-domain question that should route to them with a non-default collection (none currently does — the routing table only has one such case, and it targets Risk Explainer).
2. **Re-run `git log --oneline -10` and `git branch`** to confirm you're on `dev` with the `v0.4-multi` tag applied before branching for Phase 5.
3. **Check git log** to confirm the merge and tag landed correctly:
   ```bash
   git log --oneline --decorate -5
   git tag
   ```

### 12.4 Known Issues / Limitations

*Two issues previously tracked here — the untested `collection_override` behaviour and the over-broad `"regulatory"` keyword — were fixed in the v0.4.1 self-review (see the changelog at the top of this document) and are no longer open.*

| Issue | Severity | Status |
|-------|----------|--------|
| Keyword routing can still be fooled by queries that use vocabulary from an unintended category in ways the strong/weak split doesn't cover (e.g., a hedging question that happens to contain "model") | Medium | Documented tie-break behaviour handles the general case deterministically; the "regulatory" case specifically was fixed in v0.4.1; full robustness testing remains a Phase 6 evaluation activity |
| No `collection_override` mechanism for Hedge Advisor or Model Monitor | Low | Not currently needed — only one routing table entry (maritime) requires an override, and it targets Risk Explainer |
| Orchestrator routing history is in-memory only, not persisted | Low | Acceptable for this phase; a UI (Phase 5) may want to persist or display it |
| No `main` branch exists in this repository (only `master`, untouched since initial setup) | Low | Does not block Phase 4/5 (branch → dev → tag workflow only needs `dev`); flagged for the final evaluation phase when all work merges to a release branch |
| No routing-labelled evaluation set for RQ3 (deferred item 1, v0.4.1 self-review) | Medium | Planned for Phase 6 — see Section 12.2.1 |
| No graceful failure handling for live LLM/embedding errors (deferred item 2, v0.4.1 self-review) | Medium | Planned for Phase 5 UI layer — see Section 12.2 |

---

## 13. Appendices

### Appendix A: Glossary

*(Extended from v0.3.)*

| Term | Definition |
|------|------------|
| Orchestrator | The Phase 4 routing layer that decides which specialist agent answers a given query |
| Collection override | A per-call parameter that redirects an agent's ChromaDB retrieval to a different collection than its default, without changing its persona or portfolio injection |
| Routing confidence | "high" (unambiguous keyword match), "medium" (tie broken by priority order), or "low" (no keyword matched — ambiguous fallback) |
| Routing history | The orchestrator's flat, in-memory log of past queries, the agent each was routed to, and the confidence of that decision |
| GARCH model | Generalized Autoregressive Conditional Heteroskedasticity — a volatility model referenced by the Model Monitor Agent's live test response as an alternative to the constant-correlation assumption |

*(All v0.2/v0.3 glossary entries remain valid — see those documents.)*

### Appendix B: File Reference

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `agents/hedge_advisor.py` | Hedge Advisor Agent | `HedgeAdvisorAgent`, `_format_portfolio_as_context()` |
| `agents/model_monitor.py` | Model Monitor Agent | `ModelMonitorAgent`, `_format_portfolio_as_context()` |
| `agents/risk_explainer.py` | Risk Explainer Agent (extended) | `RiskExplainerAgent.answer(query, collection_override=None)` |
| `src/orchestrator.py` | Multi-agent query router | `Orchestrator`, `route()`, `answer()`, `get_routing_history()`, `MARITIME_STRONG_KEYWORDS`/`MARITIME_WEAK_KEYWORDS` (v0.4.1) |
| `tests/test_orchestrator.py` | Orchestrator unit tests | 36 tests (32 original + 4 from v0.4.1) — mocked agents, no API/Ollama calls |
| `tests/test_agents.py` | Risk Explainer unit tests | 37 tests (35 from Phase 3 + 2 `collection_override` tests from v0.4.1) — mocked, no API calls |

*(All v0.2/v0.3 file references remain valid — see those documents.)*

### Appendix C: Configuration Reference

*(Unchanged from v0.3 — no `.env` changes in Phase 4.)*

### Appendix D: Useful Commands

```bash
# Run the full orchestrator live (costs ~$0.0004 per query)
env_dissertation/bin/python3 -c "
from src.orchestrator import Orchestrator
orch = Orchestrator()
result = orch.answer('Why does MV Iron Maiden use HSFO instead of VLSFO?')
print(result['routed_to'], '|', result['confidence'])
print(result['answer'])
"

# Run all unit tests (89 total, zero cost)
env_dissertation/bin/python3 -m pytest tests/ -v

# Check routing history after a session of queries
env_dissertation/bin/python3 -c "
from src.orchestrator import Orchestrator
orch = Orchestrator()
orch.answer('What is our VaR?')
orch.answer('Is our hedge ratio sufficient?')
print(orch.get_routing_history())
"

# Check cost log
cat data/cost_logs/api_costs.csv
```
