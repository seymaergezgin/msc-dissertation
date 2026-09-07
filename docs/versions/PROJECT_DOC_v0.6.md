# Project Documentation — Version 0.6
# AI-Based Narrative Risk Reporting for Maritime Fuel Management
# Last Updated: 2026-07-16
# Author: Seymanur Ergezgin | MSc Engineering Management, University of Greenwich
# Supervisor: Dr. Mike Sharp

---

## Changelog from v0.5.1 to v0.6

### Added
- `src/interaction_logger.py`: `log_interaction()` / `read_interactions()` — persists every question/answer exchange (full query, full answer, routing decision, sources, timing, provider/model, per-call cost) to `data/interaction_logs/interactions.jsonl`. Requested by the student explicitly: *"I want the queries and answers to be logged so that we could use those to evaluate, show to the supervisor and use it in my dissertation process."* Before this, only `cost_tracker.py` persisted anything about live queries, and only cost accounting with the query truncated to ~80 characters — there was no durable record of what was actually asked and answered.
- `evaluation/judge.py`: LLM-as-judge scoring against the exact 4-criterion rubric Phase 3 established (Accuracy/Structure/Plain English/Completeness, 0-3 each). Automates what Phase 3's comparative test left blank for manual entry.
- `evaluation/run_evaluation.py`: the Phase 6 evaluation runner — Part A (routing accuracy across all 25 queries via the real `Orchestrator`) and Part B (RAG+/RAG-only/LLM-only ablation extended to all three agent domains).
- `docs/test_results/phase6_evaluation_report.md`: the full evaluation report — see Section 8 below for headline results.
- `expected_agent` field added to all 25 queries in `prompts/risk_prompts.py` — closes **Deferred item 1** from the Phase 4 self-review (v0.4.1 changelog): RQ3 ("does multi-agent routing improve response relevance?") previously had only one worked example (Q017) as evidence; it now has a systematic, 25-query accuracy measurement.
- 35 new tests: `tests/test_interaction_logger.py` (11), `tests/test_judge.py` (11), 9 new tests in `tests/test_orchestrator.py` (interaction logging), 4 new tests in `tests/test_agents.py` (`expected_agent`).

### Changed
- `src/orchestrator.py`: `Orchestrator.answer()` now logs every interaction via `log_interaction()`, computes the per-call cost as the delta in the agent's own `CostTracker.current_spend` (agents don't return their call's cost directly), and gained an optional `eval_metadata` parameter so the evaluation runner can tag logged interactions with `query_id`/`category`/`difficulty`/`expected_agent`/`mode`.

### Fixed (found mid-run, during this phase)
- **Ablation responses weren't being logged.** The first live evaluation run wired `log_interaction()` into `Orchestrator.answer()` (Part A) but not into the ablation runner's direct agent/pipeline calls (Part B) — so only 25 of the expected 55 generation responses landed in `interactions.jsonl`, even though all 55 were correctly generated and appear in the markdown report. Fixed by adding `log_interaction()` calls to all three ablation modes, then re-running Part B only (preserving the already-reviewed Part A results, which required refactoring `write_report()` into independent `write_part_a()`/`write_part_b()`/`write_key_findings()` functions so a partial re-run doesn't overwrite the whole file). Verified: `interactions.jsonl` now has all 55 entries (25 `orchestrator` + 10 `rag_plus` + 10 `rag_only` + 10 `llm_only`).

### Test Suite
**134 tests passing**, all mocked/offline — zero additional API cost for the test suite itself.

---

## 1. Executive Summary

This project builds a Multi-Agent LLM system that translates quantitative maritime fuel risk metrics into plain English narratives for business stakeholders. Phase 6 is the evaluation phase: it measures how well the system actually performs, using both automated and (optionally) human judgment, and produces the durable evidence record the dissertation and supervisor review need.

**Current status**: Phase 6 complete — **100% of the originally planned 6 phases**.

**Key achievements in v0.6**:
- **Routing accuracy: 23/25 (92%)** — the first systematic measurement of RQ3, not a single anecdote
- **RAG+ dramatically outperforms both ablation baselines** across all three agent domains: average judge score 11.6/12 (RAG+) vs. 7.4/12 (RAG-only) vs. 8.6/12 (LLM-only) — confirming the Phase 3 finding still holds now that Hedge Advisor and Model Monitor exist too
- A genuinely interesting nuance surfaced by the automated judge: **LLM-only sometimes scores higher than RAG-only** on the Accuracy criterion (1.4/3 vs. 0.9/3) — because a confidently fabricated figure can read as more "accurate" to an LLM judge than an honest "the context doesn't contain this data," which RAG-only correctly produces when portfolio data is absent. This is a real, documented limitation of automated judging, not a system defect — see Section 9.
- A complete, durable interaction log (`data/interaction_logs/interactions.jsonl`, 55 entries) now exists for the first time in this project, ready for supervisor review and dissertation evidence
- A real logging gap was found and fixed mid-evaluation (see changelog above) — another example of the self-review discipline established in Phase 4

---

## 2. Problem Statement

*(Unchanged from v0.1 — see that document.)*

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE (Phase 5)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (Phase 4)                        │
│   answer() now also calls log_interaction() ✅ (Phase 6)         │
└──────────┬──────────────────┬───────────────────┬──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
  │ RISK EXPLAINER │  │ HEDGE ADVISOR  │  │ MODEL MONITOR  │
  └────────────────┘  └────────────────┘  └────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              PHASE 6 EVALUATION LAYER (new)                      │
│                                                                   │
│  evaluation/run_evaluation.py                                    │
│    Part A: 25 queries → Orchestrator → routing accuracy check    │
│    Part B: 10 queries × 3 modes → RAG+/RAG/LLM-only ablation     │
│                    │                                              │
│                    ▼                                              │
│  evaluation/judge.py — LLM-as-judge scores every response         │
│  against the Phase 3 rubric (Accuracy/Structure/Plain Eng/Compl.) │
│                    │                                              │
│                    ▼                                              │
│  src/interaction_logger.py — persists every response to           │
│  data/interaction_logs/interactions.jsonl                         │
│                    │                                              │
│                    ▼                                              │
│  docs/test_results/phase6_evaluation_report.md — combined report  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Technology Stack

*(Unchanged from v0.5.1 — no new dependencies in Phase 6.)*

### 3.3 Design Decisions

#### Decision 18: `Orchestrator.history` vs. the Persistent Interaction Log

**Decision**: `src/interaction_logger.py` is a standalone module (not part of `Orchestrator`), called from `Orchestrator.answer()` but also directly callable by anything that generates a response outside the orchestrator (e.g. the Phase 6 ablation runner, which calls agents and pipelines directly).

**Context**: Phase 4 already gave `Orchestrator` an in-memory `self.history` list for routing-decision evidence (Decision 14, v0.4). Phase 6 needed something materially different: a *durable*, *complete* record of full questions and answers — not just routing metadata — usable after the process exits, for supervisor review and dissertation evidence.

**Rationale**: conflating these two would have been a mistake. `self.history` is intentionally minimal (query, routed agent, confidence, timestamp) and in-memory, by design (Decision 14 explicitly rejected building it into a heavier structure). The interaction log needs to be the opposite: complete, persistent, and usable by code that never touches the orchestrator at all (the ablation runner). Keeping them as two separate mechanisms — one lightweight and orchestrator-scoped, one comprehensive and standalone — let each stay simple for its own purpose.

**Consequences**: any code path that generates a real response (not a mock/test) is responsible for calling `log_interaction()` itself if it bypasses the orchestrator — this was exactly the source of the mid-run bug documented in this version's changelog. The lesson generalises: a cross-cutting concern (logging) attached to only one call site (the orchestrator) will silently miss any other call site that does similar work.

---

#### Decision 19: `expected_agent` Reflects Domain Judgment, Not the Router's Own Logic

**Decision**: each query's `expected_agent` field in `prompts/risk_prompts.py` was assigned by asking "which agent's expertise should answer this well?", independent of what the current keyword classifier would actually produce.

**Context**: it would have been trivial (and useless) to set `expected_agent` by just running each query through `Orchestrator.route()` once and copying its answer — that would make "routing accuracy" 100% by construction, measuring nothing.

**Rationale**: the entire point of adding this field was to get real evidence about the router's limitations, including cases where it might be wrong. Two queries (Q009, Q023) were deliberately labelled `model_monitor` despite containing no Model Monitor keywords — and both were indeed misrouted to Risk Explainer, which is exactly the kind of finding this exercise needed to surface. See Section 8.1 for the result and Section 9 for the explanation.

**Consequences**: the 92% routing accuracy figure is a genuine measurement of the keyword classifier's real-world behaviour on domain-realistic questions, not a tautology. It also gives a concrete, evidence-based starting point for the semantic-classifier upgrade path Decision 12 (v0.4) already anticipated as a possible future step.

---

## 4. Component Deep-Dive

### 4.1 Interaction Logger (`src/interaction_logger.py`)

#### Purpose
Give the project a durable, structured record of every question asked and answer given — the raw evidence for dissertation writing and supervisor review that no prior phase persisted.

#### How It Works
`log_interaction()` appends one JSON object per line (JSONL) to `data/interaction_logs/interactions.jsonl`: timestamp, full query, full answer, agent name, routing metadata (when routed), collection queried, sources, retrieval count, response time, provider, model, and cost. It is deliberately non-fatal — a disk or serialisation failure logs a WARNING and returns, it never breaks a live query, matching this project's established error-handling convention (Section 12 of the original brief: "non-fatal failures should log a WARNING and continue").

#### Code Structure
```
src/interaction_logger.py
├── INTERACTION_LOG_FILE      — data/interaction_logs/interactions.jsonl
├── log_interaction(...)      — append one interaction (non-fatal on failure)
└── read_interactions(...)    — read all logged interactions back as list[dict]
```

#### Example Usage
```python
from src.interaction_logger import read_interactions

entries = read_interactions()
print(len(entries), "interactions logged")
for e in entries[-5:]:
    print(e["timestamp"], "|", e["agent"], "|", e["query"][:60])
```

---

### 4.2 LLM-as-Judge (`evaluation/judge.py`)

#### Purpose
Automate the rubric scoring Phase 3 left blank for manual entry, using the same 4 criteria (Accuracy, Structure, Plain English, Completeness), so every response gets a first-pass score immediately, with a supervisor override column left for human disagreement.

#### How It Works
`judge_response()` sends the query, the expected elements, and the response text to an LLM (by default the same `gpt-4o-mini` used for generation) with a system prompt that defines the rubric precisely and demands a strict JSON reply. `_extract_json()` tolerates markdown code fences and stray prose around the JSON, since LLMs asked for "only JSON" don't always comply perfectly. A malformed judge response degrades to a dict of `None` scores plus an `"error"` key — non-fatal, consistent with the rest of the codebase.

#### Code Structure
```
evaluation/judge.py
├── JUDGE_SYSTEM_PROMPT       — the 4-criterion rubric, verbatim from Phase 3
├── _build_judge_prompt()     — assembles query + expected elements + answer
├── _extract_json()           — tolerant JSON parsing (fences, stray prose)
└── judge_response()           — calls the LLM, logs cost, returns scores or an error dict
```

---

### 4.3 Evaluation Runner (`evaluation/run_evaluation.py`)

#### Purpose
The Phase 6 deliverable: run the full 25-query set through the real system in two complementary ways and produce one combined report.

#### How It Works
**Part A** answers all 25 queries via the real `Orchestrator`, tagging each with `eval_metadata` (query ID, category, difficulty, expected agent), and compares the actual `routed_to` against `expected_agent`. **Part B** runs a representative 10-query subset (the original Phase 3 set of 8, plus one Hedge Advisor and one Model Monitor query) through three modes — RAG+ (the full agent), RAG-only (retrieval without portfolio injection), and LLM-only (bare model) — using each query's correct agent class, system prompt, and ChromaDB collection (including the `maritime` override for maritime-context queries). Every response in both parts is checked against `expected_elements`, scored by `judge_response()`, and persisted via `log_interaction()`.

#### Code Structure
```
evaluation/run_evaluation.py
├── ABLATION_QUERY_IDS         — the 10-query representative subset
├── AGENT_CLASSES               — maps expected_agent -> (class, system prompt, default collection)
├── check_expected()             — same substring-match method as Phase 3
├── estimate_cost()              — printed before any live run, per this project's cost-approval convention
├── run_routing_accuracy()       — Part A
├── run_ablation()               — Part B
├── write_header() / write_part_a() / write_part_b() / write_key_findings()
│                                 — independent report sections (refactored mid-phase — see changelog)
└── write_report()               — full report from scratch (used by --part all)
```

#### Example Usage
```bash
# Cost estimate only, no API calls
env_dissertation/bin/python3 evaluation/run_evaluation.py --estimate-only

# Full run (both parts)
env_dissertation/bin/python3 evaluation/run_evaluation.py --part all
```

---

## 5. Data Architecture

### 5.1 New Data Artifact: `data/interaction_logs/interactions.jsonl`

Unlike `data/cost_logs/` and `data/embeddings/` (both git-ignored — see `.gitignore`), **`data/interaction_logs/` is deliberately NOT git-ignored**. This is a conscious departure from the established convention: cost logs and embeddings are operational/regenerable bookkeeping, while the interaction log is curated evidence of system behaviour that the student explicitly wants preserved for supervisor review and dissertation writing. If this decision should be reversed (kept local-only instead), it is a one-line `.gitignore` addition — flagged here so it's an explicit, revisitable choice, not a silent default.

*(Knowledge base and synthetic data otherwise unchanged from v0.2/v0.3 — no new documents or portfolio data in Phase 6.)*

---

## 6. Agent System

*(Unchanged from v0.4.1/v0.5.1 — Phase 6 evaluates the existing three agents and orchestrator, it does not modify them beyond the `eval_metadata` passthrough in `Orchestrator.answer()`.)*

---

## 7. Prompt Engineering

### 7.1 The Judge System Prompt

`JUDGE_SYSTEM_PROMPT` (in `evaluation/judge.py`) is deliberately built from the *exact same rubric wording* Phase 3's comparative test used, rather than a freshly written scoring prompt. This matters for consistency: any score comparison between Phase 3's (unfilled, manual) rubric and Phase 6's (automated) scores is a fair comparison, not an apples-to-oranges one, because the criteria definitions are identical.

---

## 8. Evaluation Methodology

### 8.1 Part A — Routing Accuracy Results

**23/25 (92%) routing accuracy.**

| Query | Expected | Actual | Correct? | Why |
|---|---|---|---|---|
| Q009 | model_monitor | Risk Explainer | ❌ | *"Why do we use a 10-day time horizon for our VaR calculation?"* — a methodology-justification question, but its only strong keyword match is "var" (Risk Explainer), with none of Model Monitor's keywords ("model", "drift", "recalibrate", "assumption", "correlation", "historical window") present |
| Q023 | model_monitor | Risk Explainer | ❌ | *"Explain the variance-covariance method..."* — same pattern: matches "var" only, no Model Monitor keyword present |
| Q024 | model_monitor | Model Monitor | ✅ | *"What assumptions does our VaR model make..."* — contains "assumption" (Model Monitor keyword) alongside "var", so Model Monitor wins on keyword count |

All 23 correct routings included both easy factual lookups and hard maritime-context/scenario/actionable queries — the maritime override (Section 6.5, PROJECT_DOC_v0.4.md) worked correctly for both Q017 and Q018 in this run.

**This is the systematic RQ3 evidence the Phase 4 self-review flagged as missing** (Deferred item 1, v0.4.1 changelog) — not just the single Q017 anecdote, but a measured 92% accuracy with the two failure cases fully explained by the keyword classifier's actual limitation (methodology questions phrased around "VaR" without any Model Monitor vocabulary).

### 8.2 Part B — Ablation Results (RAG+ vs. RAG-only vs. LLM-only)

Average judge score across the 10-query representative subset, all three agent domains:

| Mode | Avg Total (/12) | Avg Accuracy | Avg Structure | Avg Plain English | Avg Completeness |
|---|---|---|---|---|---|
| RAG+ | **11.6** | 2.9 | 2.9 | 2.9 | 2.9 |
| RAG only | 7.4 | 0.9 | 2.8 | 2.3 | 1.4 |
| LLM only | 8.6 | 1.4 | 3.0 | 2.4 | 1.8 |

**RAG+ is unambiguously best** — near-perfect across every criterion, confirming the Phase 3 finding holds across all three agent domains (Risk Explainer, Hedge Advisor, Model Monitor), not just the one agent Phase 3 tested.

**The RAG-only vs. LLM-only comparison is the interesting nuance**: LLM-only scores *higher* on Accuracy (1.4 vs. 0.9) despite having zero grounding. This is explained by what each mode actually produces when it lacks the portfolio figure: RAG-only correctly says *"the context documents do not provide this figure"* (honest, but scored low on Accuracy since it doesn't answer the question); LLM-only fabricates a plausible-sounding number confidently (dishonest, but reads as more "accurate" to a judge that doesn't have ground truth to check against). This is a known category of LLM-as-judge weakness — see Section 9.

### 8.3 The Value of the Supervisor-Override Column

Both `docs/test_results/phase6_evaluation_report.md` and Phase 3's report include a blank column for a human to record disagreement with the automated score. Section 8.2's RAG-only/LLM-only finding is a direct, concrete demonstration of why this column exists: the automated judge's Accuracy score for LLM-only responses should probably be *lower* than RAG-only's, not higher, once a human notices the LLM-only answers are confidently fabricated — but the judge, working only from the text in front of it, cannot always detect this without independent access to the true figures.

---

## 9. Challenges and Solutions

*(v0.2–v0.5.1 entries carried forward — new entries below.)*

| Challenge | Impact | Solution | Lesson Learned |
|-----------|--------|----------|----------------|
| Ablation responses generated correctly but weren't logged (Part B never called `log_interaction()`) | `interactions.jsonl` was missing 30 of 55 expected entries after the first live run | Added logging to all 3 ablation modes; refactored `write_report()` into independent part-writers so Part B could be safely re-run without erasing the already-reviewed Part A results | A cross-cutting concern wired into only one call site (the orchestrator) will silently miss every other call site doing similar work — verify the log is complete, don't just verify the feature that writes to it compiles |
| LLM-as-judge can score a confident fabrication higher than an honest "I don't know" | Automated Accuracy scores for LLM-only (1.4) exceeded RAG-only (0.9) despite LLM-only having zero grounding | Documented explicitly (Section 8.2) rather than treated as a bug; kept the supervisor-override column so a human can correct it | An LLM judge without access to ground truth will sometimes reward confidence over honesty — this is a known category of LLM-as-judge weakness, not something to silently patch over; report it as a limitation |
| `expected_agent` could have been set to whatever the router already outputs, making "accuracy" meaningless | Risk of a self-validating metric that looks good but proves nothing | Assigned `expected_agent` by domain judgment first (Decision 19), deliberately creating two cases (Q009, Q023) where the label disagrees with current router behaviour | A ground-truth label written by copying the system under test's own output cannot measure that system — the label must come from an independent source of truth |

---

## 10. Academic Relevance

### 10.1 Research Questions Addressed

- **RQ1**: *(Unchanged — addressed since Phase 3.)*
- **RQ2**: *(RAG vs. non-RAG.)* Phase 6 provides the fullest evidence yet: RAG+ averages 11.6/12 vs. 7.4-8.6/12 for the ablations, across all three agent domains, not just one.
- **RQ3**: *(Multi-agent routing.)* Now has systematic evidence: 92% routing accuracy across 25 domain-realistic queries, with both failure cases fully explained by a specific, documented limitation of keyword-based classification (methodology questions phrased around a Risk Explainer keyword without any Model Monitor vocabulary).

### 10.2 Literature Connections

**LLM-as-judge limitations**: the RAG-only/LLM-only accuracy inversion (Section 8.2) is a concrete, project-specific instance of a documented weakness in LLM-as-judge methodologies discussed in the broader evaluation literature — judges without ground-truth access can conflate confidence with correctness. This is directly citable in a methodology chapter discussing why this project retained a human supervisor-override mechanism rather than relying on automated judging alone.

**Routing accuracy as a measurable system property**: treating `expected_agent` as an independent ground-truth label (Decision 19) rather than deriving it from the router itself reflects standard practice in classifier evaluation (a held-out, independently-labelled test set) — relevant methodology-chapter grounding for the RQ3 evidence.

### 10.3 Methodology Mapping

| Dissertation Section | Project Component | Status |
|----------------------|-------------------|--------|
| 4.8 Evaluation Infrastructure | evaluation/, src/interaction_logger.py | ✅ Complete (v0.6) |
| 5.1 Routing Accuracy Results | docs/test_results/phase6_evaluation_report.md Part A | ✅ Complete (v0.6) |
| 5.2 RAG Ablation Results | docs/test_results/phase6_evaluation_report.md Part B | ✅ Complete (v0.6) |
| 5.3 Evaluation Methodology Limitations | Section 9 of this document | ✅ Complete (v0.6) |

---

## 11. Cost Analysis

### 11.1 API Costs to Date

| Phase | Queries | Est. Cost USD |
|-------|---------|---------------|
| 1–5.1 (per v0.5.1) | ~22 | ~$0.0112 |
| 6 (initial evaluation run) | 110 | $0.0240 |
| 6 (Part B backfill after logging-gap fix) | 60 | $0.0121 |
| **Total to date** | **~192** | **$0.0473** |

**Remaining budget**: $9.95 of $10.00 monthly limit. Total project spend across all 6 phases is well under half a percent of the allocated budget.

### 11.2 Resource Usage

| Activity | Time |
|----------|------|
| Phase 6 implementation (logger, judge, runner, 35 new tests) | ~1 session |
| Full test suite (134 tests) | ~40s |
| Live evaluation run (Part A + Part B, 110 calls) | ~8 minutes |
| Part B backfill (60 calls) | ~4 minutes |

---

## 12. Next Steps

### 12.1 Completed in This Version (v0.6)
- [x] `src/interaction_logger.py`: persistent Q&A logging
- [x] `expected_agent` field added to all 25 evaluation queries
- [x] `evaluation/judge.py`: LLM-as-judge scoring
- [x] `evaluation/run_evaluation.py`: full routing-accuracy + ablation evaluation runner
- [x] Live evaluation run: 92% routing accuracy, RAG+ validated across all 3 agent domains
- [x] Logging gap found and fixed mid-phase; interaction log now complete (55/55 entries)
- [x] `docs/test_results/phase6_evaluation_report.md`: full combined report

### 12.2 Remaining Before Final Release
- [ ] `docs/versions/PROJECT_DOC_v1.0.md`: cumulative, dissertation-ready consolidated documentation
- [ ] Merge `feature/phase6-evaluation` → `dev`
- [ ] Merge `dev` → `master` (the agreed final-release branch — see Section 12.3)
- [ ] Tag `v1.0`

### 12.3 Known Issues / Limitations

| Issue | Severity | Status |
|-------|----------|--------|
| LLM-as-judge can score a confident fabrication higher than an honest refusal (Section 8.2/9) | Medium | Documented as a methodology limitation; supervisor-override column exists precisely for this |
| Keyword routing still misroutes methodology questions phrased around a Risk Explainer keyword without Model Monitor vocabulary (Q009, Q023) | Medium | Documented with root cause (Section 8.1); a semantic classifier remains the anticipated next step if this proves costly in practice (Decision 12, v0.4) |
| `CostTracker.current_spend`/`cumulative_cost_usd` can read as inconsistent across multiple short-lived tracker instances in the same process (each restores from the CSV once at construction, doesn't see other instances' later writes) | Low | Discovered during Phase 6 cost verification; does not affect budget safety (true total spend, summed directly from the CSV, was verified correct) or any per-call cost figure; not fixed as it's a pre-existing property of `CostTracker`'s one-instance-per-pipeline design, not a Phase 6 regression |
| `data/interaction_logs/` is committed to git, unlike `data/cost_logs/` | Low | Deliberate decision (Section 5.1) — flagged as reversible if the student prefers it local-only |

---

## 13. Appendices

### Appendix A: Glossary

*(Extended from v0.5.1.)*

| Term | Definition |
|------|------------|
| Interaction log | The persistent JSONL record (`data/interaction_logs/interactions.jsonl`) of every question, answer, and its full metadata — the durable evidence record this phase introduced |
| LLM-as-judge | Using an LLM to automatically score another LLM's output against a rubric, in place of (or alongside) manual human scoring |
| Routing accuracy | The percentage of evaluation queries the orchestrator routed to their `expected_agent` |
| `expected_agent` | A ground-truth label (domain judgment, not derived from the router) marking which agent should correctly answer a given evaluation query |
| Ablation | Systematically removing a component (portfolio injection, then retrieval entirely) to measure its individual contribution to response quality |

### Appendix B: File Reference

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `src/interaction_logger.py` | Persistent Q&A logging | `log_interaction()`, `read_interactions()` |
| `evaluation/judge.py` | LLM-as-judge scoring | `judge_response()`, `JUDGE_SYSTEM_PROMPT` |
| `evaluation/run_evaluation.py` | Phase 6 evaluation runner | `run_routing_accuracy()`, `run_ablation()`, `write_report()` |
| `docs/test_results/phase6_evaluation_report.md` | Full evaluation results | — |
| `data/interaction_logs/interactions.jsonl` | Durable Q&A record | — |

*(All v0.2–v0.5.1 file references remain valid — see those documents.)*

### Appendix C: Configuration Reference

*(Unchanged from v0.5.1 — no `.env` changes in Phase 6.)*

### Appendix D: Useful Commands

```bash
# Cost estimate only, zero API calls
env_dissertation/bin/python3 evaluation/run_evaluation.py --estimate-only

# Full evaluation run (both parts) — costs real money, confirm the estimate first
env_dissertation/bin/python3 evaluation/run_evaluation.py --part all

# Read back all logged interactions
env_dissertation/bin/python3 -c "
from src.interaction_logger import read_interactions
for e in read_interactions():
    print(e['timestamp'], '|', e['agent'], '|', e['query'][:60])
"

# Run all unit tests (134 total, zero cost)
env_dissertation/bin/python3 -m pytest tests/ -v
```
