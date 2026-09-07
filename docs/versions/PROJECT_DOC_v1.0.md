# Project Documentation — Version 1.0 (Final, Consolidated)
# AI-Based Narrative Risk Reporting for Maritime Fuel Management
# Last Updated: 2026-07-16
# Author: Seymanur Ergezgin | MSc Engineering Management, University of Greenwich
# Supervisor: Dr. Mike Sharp

---

## How to Read This Document

This is the cumulative, dissertation-ready reference for the complete project — all 6 phases, consolidated. Per-phase detail, exact live-test transcripts, and the full reasoning behind superseded design iterations remain in `docs/versions/PROJECT_DOC_v0.1.md` through `v0.6.md`; this document synthesises them into one coherent account of what was built, why, and what it demonstrated. Section 3.3 numbers every design decision (1 through 19) in the order they were made, matching the numbering used in the per-phase documents, so a claim here can always be traced back to its original phase document for full context.

---

## 1. Executive Summary

This project is a multi-agent LLM system that translates quantitative maritime fuel risk metrics — Value at Risk (VaR), Conditional VaR (CVaR), hedge ratios, vessel-level exposure — into plain-English narratives for non-technical business stakeholders. It was built and evaluated across 6 phases, from project setup through a full evaluation with both automated and human-reviewable scoring.

**Final status: all 6 phases complete.**

**Headline results**:
- **RAG+ (this project's core architectural contribution) averages 11.6/12 on the evaluation rubric**, against 7.4/12 (RAG-only) and 8.6/12 (LLM-only) — validated across all three agent domains, not just one
- **92% routing accuracy** (23/25) for the multi-agent orchestrator, with both failure cases fully explained by a specific, documented limitation
- **A critical retrieval gap (Q017: maritime/regulatory questions retrieving from the wrong knowledge-base collection) was found in Phase 3 testing and directly fixed and verified in Phase 4** — a concrete before/after demonstration of why multi-agent routing matters
- **Total project cost: $0.0473** of the $10.00/month budget — three orders of magnitude under budget
- **57 → 134 unit tests** across the project's lifetime, all passing, all mocked (zero ongoing API cost for verification)

**Key architectural contribution**: "RAG+" — injecting live, structured portfolio data as a first context block *before* retrieved document chunks in the LLM prompt, so the model answers both "what is VaR?" (from documents) and "what is OUR VaR?" (from live data) in one response. This is documented and evidenced throughout as the single most important design decision in the system (Decision 9, Section 3.3).

---

## 2. Problem Statement

### Why this project exists
Maritime fuel management companies generate complex quantitative risk reports daily — VaR figures, CVaR calculations, hedge effectiveness ratios. These metrics are essential for risk management but create a communication gap between the risk analysts who produce them and the senior managers or clients who must act on them.

### What business problem it solves
The system acts as an intelligent interpreter: given a snapshot of risk metrics, it generates a coherent natural-language explanation tailored to its audience. A risk manager can ask "What is our current fuel price exposure?" and receive a paragraph-length answer in plain English, grounded in the actual metric data, with citations to the knowledge base.

### Who benefits
- **Maritime shipping companies** — fleet operators with fuel price exposure
- **Bunker traders and brokers** — need to explain hedging positions to clients
- **Risk managers** — can produce stakeholder reports faster
- **Non-technical executives** — can understand risk positions without reading spreadsheets
- **Researchers** — demonstrates applicability of LLM systems to structured financial domains

---

## 3. Architecture Overview

### 3.1 Final System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  STREAMLIT UI (Phase 5)                         │
│   Chat interface, routing transparency, budget display,          │
│   graceful error handling                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ natural language query
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              ORCHESTRATOR (Phase 4, refined v0.4.1/v0.6)         │
│   Keyword classifier — NOT a LangGraph StateGraph (Decision 12)  │
│   Strong/weak maritime keyword split (Decision 15)                │
│   Logs every interaction via log_interaction() (Decision 18)     │
└──────────┬──────────────────┬───────────────────┬──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
  │ RISK EXPLAINER │  │ HEDGE ADVISOR  │  │ MODEL MONITOR  │
  │  (Phase 3)     │  │  (Phase 4)     │  │  (Phase 4)     │
  │  risk_metrics  │  │  hedging       │  │  risk_metrics  │
  │  (or maritime, │  │  collection    │  │  collection    │
  │  via override) │  │                │  │                │
  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
          │                   │                    │
          ▼                   ▼                    ▼
  ┌───────────────────────────────────────────────────────┐
  │     RAG+ PIPELINE (Phase 2 + Phase 3)                  │
  │  [1] Live portfolio data (risk_metrics.json)           │
  │      injected as "Context 0", per-agent formatter      │
  │  [2] ChromaDB retrieval (top-5 relevant chunks)        │
  │  [3] LLM generation with agent-specific system prompt  │
  └───────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
  ┌──────────────────┐      ┌─────────────────────┐
  │   VECTOR STORE   │      │    LLM PROVIDER     │
  │   (ChromaDB)     │      │  OpenAI gpt-4o-mini │
  │  5,306 chunks    │      │  Ollama (offline)   │
  │  4 collections   │      │                     │
  └──────────────────┘      └─────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              PHASE 6 EVALUATION LAYER                            │
│   evaluation/run_evaluation.py — routing accuracy + ablation      │
│   evaluation/judge.py — LLM-as-judge rubric scoring                │
│   src/interaction_logger.py — durable Q&A record (all phases)     │
│   data/interaction_logs/interactions.jsonl                        │
│   docs/test_results/phase6_evaluation_report.md                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Technology Stack (Final)

| Component | Technology | Why This Choice |
|-----------|------------|-----------------|
| Orchestration | Plain Python keyword classifier | `langgraph` remained pinned but deliberately unused (Decision 12) — matched to the actual complexity of the routing problem, not the fanciest available tool |
| LLM (evaluation & production) | OpenAI gpt-4o-mini | High quality, very low cost (total project spend: $0.0473) |
| LLM (offline option) | Ollama llama3.1:8b | Free, local, no API key, full privacy, reproducible |
| Vector Database | ChromaDB | Lightweight, embedded, Python-native |
| Embeddings | nomic-embed-text via Ollama | Free, local, 768-dimensional |
| UI | Streamlit | Python-native, renders markdown, rapid to build |
| Testing | pytest, unittest.mock | 134 tests, all mocked — zero cost verification |
| Evaluation | Custom LLM-as-judge (`evaluation/judge.py`) | Automates the Phase 3 manual rubric while preserving a human-override column |
| Language | Python 3.12 | Latest stable at project start |
| Version control | Git, feature-branch-per-phase | Maps directly to dissertation methodology chapters |

### 3.3 Design Decisions — Complete Index

Every major decision made across all 6 phases, in order:

| # | Decision | Phase | Summary |
|---|---|---|---|
| 1-8 | Setup, RAG foundation decisions | 1-2 | Project structure, multi-provider LLM abstraction, ChromaDB collection design, chunking/quality filtering — see `PROJECT_DOC_v0.1.md`/`v0.2.md` |
| 9 | **RAG+ pattern** | 3 | Live portfolio data injected as "Context 0" before retrieved chunks — the project's core architectural contribution. See Section 4.1 below. |
| 10 | Agent-specific ChromaDB collections | 3 | Each agent queries its own named collection, not the merged "all" — precision over recall |
| 11 | Structured 4-section response format | 3 | SUMMARY/EXPLANATION/IMPLICATIONS/CAVEATS — enforced via system prompt, not code parsing |
| 12 | Keyword classifier, not LangGraph `StateGraph` | 4 | Matched tool complexity to problem complexity; explicit anti-overengineering choice |
| 13 | `collection_override` as a minimal extension | 4 | One optional parameter on `RiskExplainerAgent.answer()`, not a new agent or duplicated logic |
| 14 | Orchestrator history vs. persistent log | 4/6 | In-memory routing log (Phase 4) is deliberately separate from the durable interaction log (Phase 6, Decision 18) |
| 15 | Strong/weak maritime keyword split | 4 (self-review) | Fixed a real false-positive: "regulatory" alone could hijack correctly-routed queries |
| 16 | Chat history in `st.session_state`, not `Orchestrator.history` | 5 | UI display state kept separate from routing-audit state; anticipates multi-user deployment without a redesign |
| 17 | Escape dollar signs at render time | 5 | Fixed a Streamlit LaTeX-rendering bug at the UI boundary, not in agent code |
| 18 | Persistent interaction logger as a standalone module | 6 | Durable dissertation evidence, callable from anywhere a response is generated, not coupled only to the orchestrator |
| 19 | `expected_agent` reflects domain judgment, not router logic | 6 | Ground-truth labels independent of the system under test — makes routing accuracy a real measurement |

*(Full write-ups with context/rationale/consequences for each decision are in the corresponding phase document.)*

---

## 4. Component Deep-Dive

### 4.1 The RAG+ Pattern — The Project's Core Contribution

**What it is**: every agent's prompt to the LLM is structured as: `[live portfolio data] → [retrieved document chunks] → [user question]`, in that order. The live data appears first because LLMs read context top-to-bottom — putting the specific figure ("Portfolio VaR: $376,329") before the general textbook definition of VaR consistently produces answers that cite the actual figure rather than a generic explanation.

**Why it matters, with evidence**: the Phase 3 comparative test showed the difference starkly. Asked "What is our current portfolio VaR?":
- **RAG+** (portfolio data + documents + LLM): *"Our current portfolio VaR at 95% confidence over a 10-day period is $376,329."* — correct.
- **RAG only** (documents + LLM, no portfolio data): *"The current portfolio VaR ... is not provided in the context documents."* — honest, but useless to the user.
- **LLM only** (bare model): *"Our current portfolio Value at Risk ... is $2.5 million."* — confidently wrong by 6.6×, and invented a vessel ("MV Oceanic Star") that doesn't exist in the fleet.

Phase 6 confirmed this pattern generalises: across all three agents (not just Risk Explainer), RAG+ averaged 11.6/12 on the evaluation rubric vs. 7.4-8.6/12 for the two ablations (Section 8.2).

### 4.2 The Three Agents

| Agent | Audience | Collection | Response Format | Phase Introduced |
|---|---|---|---|---|
| Risk Explainer | Board / senior management | `risk_metrics` (or `maritime`, via override) | SUMMARY / EXPLANATION / BUSINESS IMPLICATIONS / CAVEATS | 3 |
| Hedge Advisor | Treasury / risk team | `hedging` | SUMMARY / ANALYSIS / RECOMMENDATION / MARKET CONTEXT | 4 |
| Model Monitor | Quant team / risk committee | `risk_metrics` | STATUS (GREEN/AMBER/RED) / FINDINGS / RECOMMENDATION / TECHNICAL NOTES | 4 |

All three share the same `BaseAgent` interface (Phase 3) and the same RAG+ pattern, each with a portfolio-context formatter that surfaces different fields from the same underlying `risk_metrics.json` snapshot — VaR/CVaR figures for Risk Explainer, hedge ratios and exposure for Hedge Advisor, model calibration parameters for Model Monitor.

### 4.3 The Orchestrator

A keyword classifier (Decision 12) scores each query against per-agent keyword tables, with one special case: maritime/regulatory keywords override the retrieval collection to `maritime` regardless of which agent answers (fixing the Phase 3 Q017 gap — Section 8.1 below). Ambiguous queries fall back to Risk Explainer with low confidence rather than failing. Every routing decision is returned to the caller with a human-readable reason and a confidence level, making the system's decisions inspectable — the UI (Phase 5) surfaces this directly to the user.

### 4.4 The Evaluation Layer

`evaluation/run_evaluation.py` runs the full 25-query set in two complementary ways: routing accuracy (all 25 queries via the real orchestrator) and a 3-way ablation (10 representative queries × RAG+/RAG-only/LLM-only). Every response is scored automatically by `evaluation/judge.py` (LLM-as-judge, against the same rubric Phase 3 defined manually) and persisted in full by `src/interaction_logger.py`.

---

## 5. Data Architecture

### 5.1 Knowledge Base (Final State)

| Collection | Chunks | Key Documents | Used By |
|-----------|--------|----------------|---------|
| `risk_metrics` | 393 | Deutsch VaR textbook, Value at Risk guides, Expected Shortfall guide | Risk Explainer, Model Monitor |
| `hedging` | 408 | Kavussanos 2022, Sun 2023, Bai 2022, Han 2021 (maritime hedging papers) | Hedge Advisor |
| `maritime` | 4,502 | Stopford Maritime Economics, IMO MEPC70/MEPC320-74 | Risk Explainer (via collection override) |
| `all` | 5,306 | Merged | Not queried directly by any agent |

### 5.2 Synthetic Portfolio Data

`data/synthetic/risk_metrics.json` — 5 vessels, snapshot date 2024-11-15. Portfolio VaR (95%, 10-day): $376,329. CVaR: $481,701. Average hedge ratio: 48%. Total annual fuel cost: $34,298,985. Methodology: Variance-Covariance (Delta-Normal), perfect positive correlation assumption, 2-year historical volatility window.

### 5.3 The Interaction Log (Phase 6)

`data/interaction_logs/interactions.jsonl` — one JSON object per real interaction: full query, full answer, agent, routing metadata, collection queried, sources, retrieval count, response time, provider, model, and cost. 55 entries as of this document. Deliberately committed to git (unlike cost logs), since it is curated dissertation evidence, not disposable operational bookkeeping (Section 5.1, `PROJECT_DOC_v0.6.md`).

---

## 6. Agent System

*(See Section 4.2/4.3 above for the consolidated view; full per-phase detail in the individual version documents.)*

---

## 7. Prompt Engineering

### 7.1 Design Philosophy
Three principles drove every prompt in this system: **audience specificity** (each agent's persona names its actual audience — "presenting to the board," "advising the treasury team"), **format enforcement** (mandatory section headers make responses systematically evaluable), and **source attribution** (agents are instructed to identify the source of any specific figure they cite).

### 7.2 The RAG+ Context Structure
```
CONTEXT DOCUMENTS:
[CURRENT PORTFOLIO DATA — snapshot date: 2024-11-15]
... live figures, formatted per-agent ...
---
[Context 1 — <source document>, page N]
... retrieved chunk ...
---
USER QUESTION:
<user's query>
```

### 7.3 The Judge Rubric
`evaluation/judge.py`'s `JUDGE_SYSTEM_PROMPT` uses the exact rubric wording Phase 3 defined manually (Accuracy/Structure/Plain English/Completeness, 0-3 each), so automated and any historical manual scores remain directly comparable.

---

## 8. Evaluation Methodology and Results

### 8.1 Routing Accuracy: 92% (23/25)

The two misroutes (Q009, Q023) were both methodology questions containing the word "VaR" (a Risk Explainer keyword) but no Model Monitor keyword ("model," "assumption," "correlation," etc.) — a specific, fully-explained limitation of pure keyword classification, not a random failure. Q024, phrased almost identically but containing "assumptions," routed correctly. Full detail in `PROJECT_DOC_v0.6.md` Section 8.1.

### 8.2 RAG+/RAG-only/LLM-only Ablation

| Mode | Avg Total (/12) | Avg Accuracy | Avg Structure | Avg Plain English | Avg Completeness |
|---|---|---|---|---|---|
| RAG+ | **11.6** | 2.9 | 2.9 | 2.9 | 2.9 |
| RAG only | 7.4 | 0.9 | 2.8 | 2.3 | 1.4 |
| LLM only | 8.6 | 1.4 | 3.0 | 2.4 | 1.8 |

Notable finding: LLM-only scores marginally *higher* than RAG-only on raw total and on Accuracy specifically, despite having zero grounding — because a fabricated but confident figure reads as more "accurate" to an LLM judge than an honest "the data isn't available," which RAG-only correctly produces. This is a documented, known category of LLM-as-judge limitation (Section 9), not a system defect, and is exactly why a human supervisor-override column remains part of the reporting format.

### 8.3 The Q017 Maritime Routing Fix — Before/After

| | Phase 3 (before) | Phase 4 (after) |
|---|---|---|
| Collection queried | `risk_metrics` | `maritime` |
| Sources retrieved | Value_at_risk.pdf, Value_at_risk_guide.pdf | imo_mepc70_fuel_oil_availability_assessment_2016.pdf |
| Result | Missing: scrubber, IMO 2020 | Answer explicitly discusses IMO sulphur regulation and scrubbers |

This is the clearest single piece of evidence in the project that multi-agent routing materially improves response relevance (RQ3) — same LLM, same RAG+ mechanism, materially better answer purely because retrieval was directed to the correct knowledge-base collection.

### 8.4 Evaluation Infrastructure Summary

- 25-query evaluation set (`prompts/risk_prompts.py`), each with `expected_elements`, `expected_agent`, `category`, `difficulty`
- Automated substring matching for `expected_elements` (same method since Phase 3)
- Automated routing-accuracy check against `expected_agent` (new in Phase 6)
- Automated LLM-as-judge rubric scoring (new in Phase 6)
- Manual supervisor-override columns preserved throughout, for human review
- Full durable log of every interaction (`data/interaction_logs/interactions.jsonl`)

---

## 9. Challenges and Solutions (Complete List)

| Challenge | Phase | Solution | Lesson Learned |
|-----------|-------|----------|----------------|
| LangChain 0.3.x → 1.x breaking change | 2 | Upgraded entire ecosystem, pinned requirements.txt | Pin the full ecosystem, not individual packages |
| Ollama crash on large PDFs | 2 | `EMBED_BATCH_SIZE=50` in vector_store.py | Local LLM servers have memory limits; always batch |
| CPU inference impractically slow (27 min/query) | 2-3 | Obtained OpenAI API key, switched to gpt-4o-mini | CPU inference with 8B models is impractical for iterative dev |
| Maritime-context questions retrieving from the wrong collection | 3→4 | Orchestrator routes maritime keywords to the `maritime` collection via `collection_override` | Collection-per-agent precision creates gaps at domain boundaries — a routing layer above the agents is where cross-domain cases get fixed |
| Temptation to build the orchestrator as a LangGraph `StateGraph` | 4 | Built a plain keyword classifier instead | A dependency being installed is not a reason to use its most complex API |
| The `"regulatory"` keyword was too generic, risked hijacking correct routings | 4 (self-review) | Split into strong/weak maritime keyword tiers | Re-examine even brief-supplied keyword lists once real queries are tried against them |
| `collection_override` shipped without a direct unit test | 4 (self-review) | Added tests verifying the exact collection queried | A live smoke test proves a feature works once; it doesn't replace a repeatable unit test |
| `streamlit run ui/app.py` crashed with `ModuleNotFoundError` for the student's exact command | 5 | Verification had used `python -m streamlit run`, which differs in sys.path handling from the plain console-script entry point; fixed by explicit sys.path insertion in `ui/app.py` | Verify with the *exact* command a user will actually type, not a convenient equivalent |
| Streamlit auto-renders `$...$` as LaTeX, mangling dollar figures | 5 | `_escape_markdown_dollars()` at the UI render boundary | A feature can pass all unit tests and still be visibly broken — look at the actual rendered output |
| Ablation responses generated correctly but weren't persisted to the interaction log | 6 | Added `log_interaction()` calls to all 3 ablation modes; refactored the report writer so a partial re-run doesn't erase already-reviewed results | A cross-cutting concern wired into only one call site will silently miss every other call site doing similar work |
| LLM-as-judge rewarded a confident fabrication over an honest refusal | 6 | Documented explicitly as a methodology limitation; kept the human supervisor-override column | An LLM judge without ground-truth access can conflate confidence with correctness — report it, don't silently patch it |

---

## 10. Academic Relevance

### 10.1 Research Questions — Final Answers

- **RQ1** (*Can LLM-based agents accurately explain maritime fuel risk metrics in natural language?*) — **Yes.** All three agents produce structured, figure-grounded, plain-English answers, evidenced across 25 queries with an average RAG+ score of 11.6/12.
- **RQ2** (*Does RAG-augmented generation produce more accurate explanations than a base LLM?*) — **Yes, decisively, and the RAG+ variant specifically.** RAG+ (11.6/12) substantially outperforms both RAG-only (7.4/12) and LLM-only (8.6/12) across all three agent domains.
- **RQ3** (*Can multi-agent routing improve response relevance compared to a single agent?*) — **Yes**, with two forms of evidence: a systematic 92% routing-accuracy measurement across 25 domain-realistic queries, and a direct before/after case study (Q017) showing the same LLM producing a materially better answer purely because the orchestrator redirected retrieval to the correct knowledge-base collection.

### 10.2 Literature Connections

**RAG+ / context-augmented RAG**: extends Lewis et al. (2020)'s RAG paradigm by combining static document retrieval with dynamic structured-data injection — relevant to enterprise AI literature's distinction between "knowledge retrieval" and "data retrieval."

**Multi-agent specialisation and routing**: the collection-per-agent design combined with the Q017 routing fix is a small-scale, concrete demonstration of a recurring theme in 2023-2024 multi-agent LLM literature — specialist agents outperform a single generalist, provided routing correctly identifies which specialist a query needs.

**LLM-as-judge limitations**: the RAG-only/LLM-only accuracy inversion (Section 8.2) is a project-specific instance of a documented weakness in automated LLM evaluation — judges without ground-truth access can reward confidence over honesty. This directly motivates the project's retained human-review mechanism (supervisor-override columns) rather than relying on automated scoring alone.

**Maritime domain grounding**: the risk figures explained throughout (VaR, CVaR, hedge ratios) mirror the metrics analysed mathematically in Kavussanos & Bai (2022) and Sun et al. (2023) — the system is designed to explain the same risk measures those papers formalise.

### 10.3 Complete Methodology Mapping

| Dissertation Section | Project Component | Status |
|----------------------|-------------------|--------|
| 3.1 Literature Review | Knowledge base documents (16 curated sources) | ✅ Complete |
| 4.1 System Design | Full architecture (Section 3 above) | ✅ Complete |
| 4.2 Environment Setup | config/, requirements.txt | ✅ Complete |
| 4.3 RAG Implementation | src/vector_store.py, src/rag_pipeline.py | ✅ Complete |
| 4.4 Agent Design | agents/, prompts/ | ✅ Complete |
| 4.5 Multi-Agent Orchestration | src/orchestrator.py | ✅ Complete |
| 4.6 User Interface | ui/app.py | ✅ Complete |
| 4.7 Evaluation Infrastructure | evaluation/, src/interaction_logger.py | ✅ Complete |
| 5.1 Routing Accuracy Results | docs/test_results/phase6_evaluation_report.md Part A | ✅ Complete |
| 5.2 RAG Ablation Results | docs/test_results/phase6_evaluation_report.md Part B | ✅ Complete |
| 5.3 Case Study: Maritime Routing Fix | Section 8.3 above | ✅ Complete |
| 5.4 Evaluation Methodology Limitations | Section 9 above | ✅ Complete |
| 6.1 Discussion / Future Work | Section 12 below | ✅ Complete |

---

## 11. Cost Analysis (Final)

| Phase | Description | Cost USD |
|-------|-------------|----------|
| 1-2 | Setup, RAG foundation (mostly Ollama, free) | ~$0.001 |
| 3 | Risk Explainer development + comparative test | ~$0.007 |
| 4-4.1 | Multi-agent orchestrator + self-review fixes | ~$0.002 |
| 5-5.1 | Streamlit UI + sys.path fix | ~$0.001 |
| 6 | Full evaluation (routing + ablation + judge, incl. backfill) | ~$0.036 |
| **Total** | | **$0.0473** |

**Budget utilisation: 0.47% of the $10.00/month allocation.** The project could be run in its entirety roughly 200 more times within a single month's budget.

---

## 12. Next Steps / Future Work

### 12.1 Completed (All 6 Phases)
- [x] Phase 1: Project setup, multi-provider LLM abstraction, cost tracking
- [x] Phase 2: RAG foundation, ChromaDB knowledge base, document loading
- [x] Phase 3: Risk Explainer Agent, RAG+ pattern established
- [x] Phase 4: Multi-agent orchestrator (Hedge Advisor, Model Monitor), maritime routing fix
- [x] Phase 5: Streamlit UI with routing transparency
- [x] Phase 6: Full evaluation (routing accuracy, ablation, LLM-as-judge, durable interaction log)

### 12.2 Identified But Deliberately Out of Scope
- **Semantic/embedding-based routing classifier**: the anticipated next step if keyword routing's ~92% accuracy proves insufficient for a production deployment (Decision 12, Decision 19)
- **Multi-user deployment**: the codebase was kept ready for this (Decisions 16, 18 deliberately separate per-session state from shared orchestrator state) but was never required for this single-user dissertation project
- **Persisted, context-carrying multi-turn conversation** (follow-up question resolution): explicitly out of scope per the Phase 4 brief's anti-overengineering guidance; the flat routing/interaction logs are the foundation this would build on if ever needed
- **Larger/broader evaluation set**: the 25-query set is skewed toward Risk Explainer topics because it was designed in Phase 3 before the other two agents existed — a larger, more balanced set would strengthen the RQ3 evidence further

### 12.3 Known Limitations (Consolidated)
1. Keyword routing misroutes methodology questions phrased around a Risk Explainer keyword without Model Monitor vocabulary (2/25 cases, fully explained)
2. LLM-as-judge can score confident fabrication over honest refusal (documented, mitigated by human-override columns)
3. `risk_metrics.json` is static synthetic data — a production system would connect to a live risk database
4. No authentication or multi-user session isolation in the Streamlit UI (not required for this single-user tool)

---

## 13. Appendices

### Appendix A: Complete Glossary

| Term | Definition |
|------|------------|
| VaR | Value at Risk — maximum expected loss at a given confidence level over a time horizon |
| CVaR | Conditional Value at Risk (Expected Shortfall) — average loss beyond the VaR threshold |
| RAG | Retrieval-Augmented Generation |
| **RAG+** | This project's core contribution — RAG extended with live structured data injection, placed before retrieved documents in the prompt |
| Orchestrator | The routing layer deciding which specialist agent answers a given query |
| Collection override | A per-call parameter redirecting an agent's retrieval to a different ChromaDB collection without changing its persona |
| Routing accuracy | The percentage of evaluation queries routed to their independently-labelled `expected_agent` |
| LLM-as-judge | Using an LLM to automatically score another LLM's output against a rubric |
| Interaction log | The persistent, complete record of every question/answer exchange (Phase 6) |
| VLSFO / HSFO | Very Low / High Sulphur Fuel Oil — IMO 2020 compliant / restricted-to-scrubber-equipped-vessels respectively |

### Appendix B: Complete File Reference

| Path | Purpose |
|------|---------|
| `config/` | Settings, LLM provider config, budget config |
| `src/embeddings.py`, `src/vector_store.py`, `src/document_loader.py` | RAG foundation (Phase 2) |
| `src/llm_provider.py` | Multi-provider LLM abstraction |
| `src/rag_pipeline.py` | Core RAG query/retrieval logic |
| `src/cost_tracker.py` | API cost accounting and budget alerts |
| `src/orchestrator.py` | Multi-agent routing (Phase 4, refined 4.1/6) |
| `src/interaction_logger.py` | Durable Q&A logging (Phase 6) |
| `agents/base_agent.py`, `agents/risk_explainer.py`, `agents/hedge_advisor.py`, `agents/model_monitor.py` | The three specialist agents |
| `prompts/system_prompts.py`, `prompts/risk_prompts.py` | Agent personas and the 25-query evaluation set |
| `ui/app.py` | Streamlit chat interface |
| `evaluation/judge.py`, `evaluation/run_evaluation.py` | Phase 6 evaluation infrastructure |
| `data/synthetic/risk_metrics.json` | Synthetic portfolio data |
| `data/interaction_logs/interactions.jsonl` | Durable interaction log |
| `docs/test_results/` | Phase 3 and Phase 6 evaluation reports |
| `docs/versions/` | This document and all per-phase documentation |
| `tests/` | 134 unit tests |

### Appendix C: Configuration Reference

| Variable | Value | Purpose |
|----------|-------|---------|
| `LLM_PROVIDER` | `openai` | Active LLM provider |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for generation and judging |
| `EMBEDDING_PROVIDER` | `ollama` | Local, free embeddings |
| `MONTHLY_BUDGET_USD` | `10.00` | Student budget cap |

### Appendix D: Useful Commands

```bash
# Run the full test suite (134 tests, zero cost)
env_dissertation/bin/python3 -m pytest tests/ -v

# Launch the UI
env_dissertation/bin/streamlit run ui/app.py

# Run the full Phase 6 evaluation (costs ~$0.06, estimate first)
env_dissertation/bin/python3 evaluation/run_evaluation.py --estimate-only
env_dissertation/bin/python3 evaluation/run_evaluation.py --part all

# Review all logged interactions
env_dissertation/bin/python3 -c "
from src.interaction_logger import read_interactions
for e in read_interactions():
    print(e['timestamp'], '|', e['agent'], '|', e['query'][:60])
"

# Check cumulative cost
python3 -c "
import csv
rows = list(csv.DictReader(open('data/cost_logs/api_costs.csv')))
print(f'Total spend: \${sum(float(r[\"cost_usd\"]) for r in rows):.4f}')
"
```

### Appendix E: Git History

```
Tags (in order): v0.1-setup, v0.2-rag, v0.3-agent, v0.4-multi, v0.4.1-multi,
                 v0.5-ui, v0.5.1-ui, v0.6-evaluation, v1.0
Branch workflow: feature/phaseN-* → dev → master (final release)
```
