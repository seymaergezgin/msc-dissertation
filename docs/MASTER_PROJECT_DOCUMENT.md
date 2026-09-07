# Master Project Document
# AI-Based Narrative Risk Reporting System for Maritime Fuel Management
# MSc Engineering Management Dissertation — University of Greenwich
# Student: Seymanur Ergezgin | Supervisor: Dr. Mike Sharp
# Compiled: 2026-07-23 | Reflects state at git tag `v1.1`

---

# 0. How to Use This Document

This is the single, self-contained reference for the entire project. It is written so that four different readers can each get what they need from it without reading anything else first:

1. **Your supervisor**, who wants to understand what was built, why, and how well it works, without digging through seven phases of incremental documentation.
2. **You, writing the dissertation** — every section here maps to a chapter or sub-section you'll need to write, with the reasoning already worked out, not just the facts.
3. **You, preparing for your viva/presentation** — Section 18 is a rehearsed question-and-answer set built from the two independent critical reviews this project received, plus questions any competent examiner would ask.
4. **A completely unrelated new reader** — someone with no context at all should be able to read this top to bottom and understand what the system is, why every major decision was made, what it achieved, and what its honest limitations are.

**Suggested reading order**:
- First time, cover to cover: Sections 1 → 4 → 5 → 9 → 10 (this gives you the story, the architecture, the decisions, the results, and the honest self-assessment — the backbone of any dissertation chapter).
- Before your viva: Section 18, after re-reading Sections 9 and 10 so the numbers are fresh.
- While writing a specific chapter: use Section 15 (file map) and Section 19 (reading order by dissertation chapter) to jump straight to the relevant primary sources.

**This document does not replace the underlying evidence** — it synthesises and interprets it. Every claim here is traceable to a specific file: source code, a test file, a generated report, or a per-phase `PROJECT_DOC` document. Section 15 is the index. If you ever doubt a number in this document, the linked file is the ground truth, not this summary.

---

# 1. Executive Overview

## 1.1 The One-Paragraph Version

Maritime shipping companies manage fuel price risk using quantitative metrics — Value at Risk (VaR), Conditional VaR (CVaR), hedge ratios — that are essential for risk management but incomprehensible to most of the people who need to act on them: boards, treasury teams, non-technical executives. This project builds a multi-agent AI system that reads a company's live risk data and a curated library of domain knowledge, and answers natural-language questions about that risk position in plain English, correctly, with citations. It routes each question to one of three specialist AI agents (a general risk explainer, a hedging specialist, a model-health monitor), each of which combines the company's actual numbers with retrieved domain documents before generating an answer — a technique this project calls "RAG+". The system was built across 6 planned phases plus a 7th, self-initiated phase that rebalanced and statistically strengthened its own evaluation after independent critical review. Total cost to build, test, and evaluate: **$0.1362** (of a $10/month student budget). Final test suite: **156 automated tests**, all passing, all free to run.

## 1.2 Why This Matters (Business Context)

Maritime fuel management companies generate complex quantitative risk reports daily. A risk analyst produces a VaR figure; a board member needs to know "are we in trouble, and what should we do?" Translating between these two levels of understanding currently requires a human intermediary — a risk manager writing a narrative summary, which takes time and is inconsistent in quality. This project is a working prototype of automating that translation without sacrificing the grounding in actual data that makes such a summary trustworthy in the first place. See Section 2 for the fuller problem statement, and Section 10.3/18 for honest discussion of how far this prototype actually gets toward solving the real business problem versus how far the evidence currently proves it does.

## 1.3 Final Headline Results (as of v1.1, the current state)

| Metric | Result | Where the evidence lives |
|---|---|---|
| Routing accuracy (all 38 evaluation queries) | **32/38 = 84.2%** (95% Wilson CI: 69.6%–92.6%) | `docs/test_results/phase6_evaluation_report.md` Part A |
| Routing accuracy, Risk Explainer specifically | **20/20 = 100%** (CI: 83.9%–100%) | same |
| Routing accuracy, Hedge Advisor specifically | **7/10 = 70%** (CI: 39.7%–89.2%) | same |
| Routing accuracy, Model Monitor specifically | **5/8 = 62.5%** (CI: 30.6%–86.3%) | same |
| RAG+ vs RAG-only ablation (paired, n=15) | RAG+ 11.3/12 vs RAG-only 8.3/12, **Wilcoxon p=0.0022** (significant) | same, Part B + Ablation Significance Testing |
| RAG+ vs LLM-only ablation | RAG+ 11.3/12 vs LLM-only 9.3/12, **p=0.0164** (significant) | same |
| Cross-family LLM-judge bias check | gpt-4o-mini scores itself **+2.2/12 points** higher than Claude on average; only **33% exact agreement**; correlation **0.55** | same, Cross-Family Judge Check section |
| Total unit tests | **156**, all passing, all mocked (zero ongoing cost) | `tests/` directory |
| Total project spend | **$0.1362** of $10.00 monthly budget | `data/cost_logs/api_costs.csv` |
| Total durable interactions logged | **138** real question/answer exchanges | `data/interaction_logs/interactions.jsonl` |

**Read this table carefully before you present it**: the headline "84.2% routing accuracy" is deliberately reported with its confidence interval and its per-agent breakdown, not as a single clean number. This is not hedging for its own sake — it is the single most important methodological lesson of this whole project (Section 10.2, Section 18 Q1) and the thing that most distinguishes a merit-level evaluation from a distinction-level one.

## 1.4 The Single Most Important Technical Contribution

**"RAG+"**: injecting the company's live, structured portfolio data as a first block of context — *before* any retrieved documents — in every prompt sent to the LLM. Standard RAG (Retrieval-Augmented Generation) retrieves only static documents; it can explain what VaR *is* but cannot tell you what *your* VaR *is*, because that number isn't in any document, it's in a live database. RAG+ solves this by treating the live snapshot as its own context block, ordered first specifically because LLMs attend most reliably to the beginning of their context window (a finding independently supported by Liu et al.'s "Lost in the Middle" paper, arXiv:2307.03172 — see Section 11.2). This is documented, evidenced, and load-bearing throughout the whole project: Section 5 (Decision 9) has the full design rationale, and Section 9.3 has the live evidence that it works.

---

# 2. The Problem, in Full

## 2.1 The Business Problem

A maritime fuel risk team computes numbers like:
- **Portfolio VaR (95%, 10-day): $376,329** — "there is a 5% chance of losing more than this over any 10-day period"
- **Portfolio CVaR (95%, 10-day): $481,701** — "if we do exceed VaR, this is the average size of that loss"
- **Average hedge ratio: 48%** — "just under half of our exposure to fuel-price swings is protected"

These numbers are correct, standard, and useless on their own to a board member who does not work with risk metrics daily. Someone has to translate "VaR is $376,329" into "we could lose a third of a million dollars in a bad ten-day stretch, and given our hedge ratio, here's what we should consider doing about it." Today, a human analyst does this translation. It's slow, inconsistent between analysts, and doesn't scale if the board wants to ask a follow-up question at 9pm before a meeting.

## 2.2 Who Actually Benefits, and How

| Stakeholder | What they get | Evidence this project provides it |
|---|---|---|
| Risk managers | Faster first-draft narrative reports | `agents/risk_explainer.py`, live-tested in every phase |
| Treasury/hedging teams | Plain-English hedging position analysis | `agents/hedge_advisor.py`, Q014/Q026-30 evaluation results |
| Quant/model risk teams | Model health monitoring in accessible language | `agents/model_monitor.py`, Q023/Q031-35 evaluation results |
| Board members/executives | Understandable answers to direct questions, without needing an analyst present | The Streamlit UI (`ui/app.py`), and — pending — the Dr. Ireland practitioner validation session (Section 16) |
| Researchers/academia | A worked, evidenced example of "RAG+" (structured-data-augmented RAG) applied to a real financial-narrative domain | This document, `docs/versions/PROJECT_DOC_v1.1.md` |

## 2.3 Why This Is an Engineering Management Dissertation, Not a Pure Computer-Science One

This distinction matters and should be made explicitly in your dissertation (see Section 10.4 and Section 18 Q3 for exactly this point, which an external review flagged as under-addressed). The interesting Engineering Management questions aren't "can an LLM produce fluent text" (yes, trivially) — they are:
- **Cost-benefit**: is $0.0005 per query, ~4-8 seconds of latency, actually worth it against the status quo (a human analyst)? What's the real ROI story?
- **Governance and trust**: what safeguards are needed before a company would let an AI-generated number reach a board pack? (Section 10.3, Section 18 Q9)
- **Adoption barriers**: what would a real risk team need to see before trusting this? (This is exactly what the Dr. Ireland session, Section 16, is designed to surface.)
- **Process and methodology**: how do you build and validate a system like this responsibly, on a real budget, with real engineering discipline? (Section 13, and the entire Section 3 development narrative, is the answer — and it's one of this project's genuine strengths.)

---

# 3. The Complete Development Journey

This section tells the story in order — not just what was built, but what was learned at each step and why the next step happened because of it. This narrative *is* your methodology chapter's backbone; the reasoning here is what an examiner wants to see, not just a list of finished features.

## 3.1 Phase 1 — Project Setup (tag `v0.1-setup`)

Built the skeleton: configuration (`config/`), a pluggable multi-LLM-provider abstraction (`src/llm_provider.py` — Ollama/OpenAI/Anthropic, switchable via one `.env` variable with no code changes), and a cost tracker (`src/cost_tracker.py`) with a hard monthly budget ($10) and an 80% alert threshold. **Why this order first**: a dissertation project run on a student budget needs cost discipline built in from day one, not bolted on afterward — and it worked: total spend after 7 phases is still under $0.14.

## 3.2 Phase 2 — RAG Foundation (tag `v0.2-rag`)

Built the knowledge base: a ChromaDB vector store (`src/vector_store.py`) with four named collections (`risk_metrics`, `hedging`, `maritime`, `all`), a document loader (`src/document_loader.py`) that chunks PDFs and filters out corrupted text, and free local embeddings via Ollama's `nomic-embed-text`. **What was learned**: large PDFs (Stopford's 840-page maritime economics textbook) crashed Ollama's embedding endpoint when sent in one batch — fixed by batching at 50 chunks per request (`EMBED_BATCH_SIZE`). Mathematical textbook pages extracted as garbled Unicode noise — fixed with a non-ASCII-ratio quality filter. **Why this matters for the dissertation**: these are concrete, citable examples of engineering problems solved through iteration, not assumed away.

## 3.3 Phase 3 — The Risk Explainer Agent and the RAG+ Discovery (tag `v0.3-agent`)

Built the first working agent and, with it, the project's core intellectual contribution. **The reasoning that led to RAG+**: a plain RAG agent, asked "what is our VaR?", either says "I don't have that figure" (if only given documents) or invents a plausible-sounding number (if given nothing at all — Phase 3's comparative test literally caught the bare LLM inventing a **$2.5 million VaR figure, 6.6× the real $376,329, and a vessel name, "MV Oceanic Star," that does not exist in the fleet**). Neither is acceptable. The fix — RAG+ — injects the live portfolio snapshot as "Context 0," before any retrieved documents, so the model has the real figure available and doesn't need to guess. This is Decision 9 (Section 5), and the $2.5M hallucination is the single best "why does this matter" anecdote in the whole project — **use it in your viva** (Section 18 Q5).

Also built in Phase 3: the `BaseAgent` abstract interface (so any future agent plugs into the same system uniformly), the 4-section structured response format (SUMMARY/EXPLANATION/IMPLICATIONS/CAVEATS), and the original 25-query evaluation set.

## 3.4 Phase 4 — Multi-Agent Orchestrator, the Q017 Gap, and the First Self-Review (tags `v0.4-multi`, `v0.4.1-multi`)

Added two more specialist agents — Hedge Advisor and Model Monitor — and an orchestrator to route between all three. **The critical finding from Phase 3 testing that drove this phase's design**: asked "why does MV Iron Maiden use HSFO instead of VLSFO?", the Risk Explainer agent retrieved nothing useful, because "scrubber" and "IMO 2020" — the actual answer — live in the `maritime` ChromaDB collection, not `risk_metrics`, which is the only collection that one agent queried. **The fix**: the orchestrator detects maritime/regulatory keywords and overrides the retrieval collection to `maritime` for that one query, while keeping the same agent persona and portfolio-data injection (`collection_override` parameter, Decision 13). **This before/after is the project's single strongest piece of evidence for RQ3** (does multi-agent routing improve relevance) — same LLM, same RAG+ mechanism, materially better answer, purely because retrieval was redirected. **Use this in your viva** (Section 18 Q2).

The orchestrator itself was deliberately built as a plain keyword classifier, not a LangGraph `StateGraph`, even though `langgraph` was already a pinned dependency (Decision 12) — a genuine "match the tool to the problem" argument, not just laziness, and defensible as its own small methodological point (Section 18 Q4).

**The first self-review** (v0.4.1, done the same day, at the student's request, before moving to Phase 5): a fresh read of the just-merged code found that the `"regulatory"` keyword in the maritime-override list was dangerously generic — it could hijack a legitimate Model Monitor question ("what regulatory reporting standard should our model follow?") into the wrong collection purely because it contains the word "regulatory." Fixed by splitting maritime keywords into "strong" (always override — `hsfo`, `imo`, `scrubber`, etc.) and "weak" (`regulatory` — only overrides when nothing else matched). **Why this matters**: it is the first instance of a recurring, positive pattern in this project — catching real defects through deliberate, honest self-review rather than only through user-reported bugs.

## 3.5 Phase 5 — The Streamlit UI, and Two More Real Bugs Found by Actually Using It (tags `v0.5-ui`, `v0.5.1-ui`)

Built a chat interface over the orchestrator, with routing transparency (showing the user *which* agent answered and *why*) and a running budget display. **Two bugs found only by genuinely testing the running app, not just the code**:
1. Streamlit auto-renders `$...$` as LaTeX. An answer citing two dollar figures in one sentence ("$385.14/MT compared to $470.73/MT") was silently mangled into garbled math notation. Fixed with a `_escape_markdown_dollars()` helper. **This is a good example for your dissertation of why "the code passed all its tests" is not the same as "the feature works"** — this bug was invisible to any unit test and only found by looking at an actual rendered browser page.
2. The student ran `streamlit run ui/app.py` themselves (the plain, documented command) and hit `ModuleNotFoundError: No module named 'src'`. Root cause: development testing had used `python -m streamlit run`, and the `-m` flag adds the current directory to Python's import path — the plain `streamlit` command does not. Fixed by explicitly inserting the project root onto `sys.path` at the top of `ui/app.py`. **Lesson, stated generally**: verify with the exact command a real user will type, not a convenient equivalent.

## 3.6 Phase 6 — Full Evaluation Infrastructure (tag `v0.6-evaluation`)

Three new things, directly requested by the student ("I want the queries and answers logged... for supervisor review and dissertation"):
1. **`src/interaction_logger.py`** — a durable, append-only JSONL record of every real question and answer, with full routing metadata, sources, timing, and cost. Before this phase, only cost accounting existed (`api_costs.csv`), truncating every query to ~80 characters and never storing the answer at all.
2. **`evaluation/judge.py`** — an LLM-as-judge that automates the 4-criterion rubric (Accuracy/Structure/Plain English/Completeness) Phase 3 had left blank for manual scoring.
3. **`evaluation/run_evaluation.py`** — a full evaluation runner: Part A answers all 25 (at the time) queries through the real orchestrator to measure routing accuracy against an independently-assigned `expected_agent` label (Decision 19 — deliberately *not* derived from the router's own behaviour, or "accuracy" would be measuring nothing); Part B runs a representative subset through RAG+/RAG-only/LLM-only to extend Phase 3's ablation to all three agents.

**Results at this point**: 92% routing accuracy (23/25), RAG+ averaging 11.6/12 vs. 7.4 (RAG-only)/8.6 (LLM-only). **A mid-phase bug, caught and fixed the same day**: the ablation responses (Part B) were generated correctly but never logged to the durable interaction file — only the orchestrator-routed Part A calls were, because logging had only been wired into one call site. Fixed, and the already-generated (already-paid-for) responses were recovered via a cheap re-judging pass rather than regenerated from scratch.

## 3.7 Phase 7 — Responding to Two Independent Critical Reviews (tags `v1.1-evidence`, `v1.1`)

After v1.0 (all 6 planned phases "complete"), the student obtained **two independent critical reviews**: an internal code/architecture audit (this session, `docs/PROJECT_EVALUATION_AND_ROADMAP.md`) and an external, dissertation-focused review (`docs/Dissertation_Progress_Review.md.pdf`). Both converged on the same core finding: **the engineering was strong; the evaluation evidence backing the claims was thinner than it should be.** Specifically:
- The 25-query evaluation set was skewed 19/3/3 toward Risk Explainer — too few Hedge Advisor/Model Monitor data points to support "validated across all three agent domains."
- "92% routing accuracy" was reported with no confidence interval, at a sample size where that interval is genuinely wide.
- The RAG+ vs. RAG-only comparison was structurally somewhat unfair (only RAG+ ever receives the portfolio data at all) and needed a more precise framing.
- The LLM-as-judge (gpt-4o-mini) was scoring outputs from its own model family (also gpt-4o-mini) with no check for self-preference bias — a documented phenomenon in the literature.
- No independent domain-expert validation existed anywhere in the evidence base.

**What was built in response** (all now complete, see Section 9 for the full results):
1. **Rebalanced the evaluation set** from 19/3/3 to **20/10/8** (13 new queries, Q026-Q038), including two deliberate "boundary" queries designed to test whether the routing logic generalises beyond the two known failure cases, and one query (Q038) specifically designed to show RAG+ combining *both* context sources, not just one being present while the other is absent.
2. **Added real statistics** (`evaluation/statistics.py`): Wilson score confidence intervals for routing accuracy, and a Wilcoxon signed-rank significance test for the ablation comparison.
3. **Ran a cross-family judge check**: re-scored 15 ablation responses with Claude (a different model family from gpt-4o-mini) and found **real, measured evidence of same-family bias** — not just a theoretical risk, an actual result (Section 9.4).
4. **Prepared (but has not yet run) a practitioner validation session** with a genuine maritime-risk domain expert (`docs/DR_IRELAND_INTERVIEW_PROTOCOL.md`) — this remains the single highest-priority open item (Section 16).

**The bug-hunting saga that happened along the way, told honestly because it is itself good evidence of engineering rigor**: the cross-judge check failed **four times in a row**, each time for a different, genuine reason, because Anthropic's API had literally never been called in any of the six prior phases:
1. `.env` still had the `.env.example` placeholder API key.
2. `ANTHROPIC_MODEL` defaulted to a since-retired model ID (`claude-3-5-sonnet-20241022`, 404 Not Found) — updated to the current `claude-sonnet-5` after querying Anthropic's own models endpoint to confirm what was actually available.
3. Current-generation Claude models reject an explicit `temperature` parameter outright (400 Bad Request) — a real API evolution, not a misconfiguration.
4. `ChatAnthropic`'s response content sometimes comes back as a list of content blocks rather than a plain string, crashing a `.split()` call downstream — a genuine pre-existing bug in the code, simply never exercised before.

Each was diagnosed with a near-zero-cost test before spending more, fixed, and covered by a new regression test (`tests/test_llm_provider.py`, the first dedicated test coverage this file had ever had). A related, more structurally important bug was also found and fixed: `write_report()` was only called once, at the very end of the evaluation script, so when the cross-judge step first crashed, **166 real, already-computed API calls' worth of results were lost** because they were never saved. This is the same *category* of mistake as the Phase 6 logging gap — the lesson, now stated generally in project memory: any optional step added after a block of expensive work must not be allowed to prevent that work from being saved if it fails.

---

# 4. Final System Architecture

## 4.1 Layered Design

```
┌─────────────────────────────────────────────────────────────────┐
│                  STREAMLIT UI  (ui/app.py, Phase 5)              │
│   Chat interface · routing transparency · budget display         │
│   Graceful error handling · dollar-sign render fix                │
└────────────────────────────┬────────────────────────────────────┘
                             │ natural language query
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         ORCHESTRATOR  (src/orchestrator.py, Phase 4/4.1/6/7)     │
│  Keyword classifier — NOT a LangGraph StateGraph (Decision 12)   │
│  Strong/weak maritime keyword split (Decision 15)                 │
│  Priority-order tie-break: risk_explainer > hedge_advisor >       │
│    model_monitor  ← THE source of the uneven per-agent accuracy  │
│  Logs every interaction via log_interaction() (Decision 18)      │
└──────────┬──────────────────┬───────────────────┬──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
  │ RISK EXPLAINER │  │ HEDGE ADVISOR  │  │ MODEL MONITOR  │
  │  Phase 3       │  │  Phase 4       │  │  Phase 4       │
  │  risk_metrics  │  │  hedging       │  │  risk_metrics  │
  │  collection    │  │  collection    │  │  collection    │
  │  (or maritime  │  │                │  │                │
  │   via override)│  │                │  │                │
  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
          │                   │                    │
          ▼                   ▼                    ▼
  ┌───────────────────────────────────────────────────────┐
  │     RAG+ PIPELINE  (src/rag_pipeline.py, Phase 2/3)    │
  │  [1] Live portfolio data (risk_metrics.json)           │
  │      → injected as "Context 0", per-agent formatter    │
  │      → each agent's formatter surfaces DIFFERENT       │
  │        fields from the SAME underlying JSON            │
  │  [2] ChromaDB retrieval (top-5 relevant chunks)        │
  │  [3] LLM generation with agent-specific system prompt  │
  └───────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
  ┌──────────────────┐      ┌─────────────────────┐
  │   VECTOR STORE   │      │    LLM PROVIDER     │
  │   (ChromaDB)     │      │  OpenAI gpt-4o-mini  │
  │  5,306 chunks    │      │  (generation+judge)  │
  │  4 collections   │      │  Ollama (offline)    │
  │                  │      │  Anthropic (cross-   │
  │                  │      │  judge only, Ph.7)   │
  └──────────────────┘      └─────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│               EVALUATION LAYER  (Phase 6 + Phase 7)              │
│  evaluation/run_evaluation.py — routing accuracy + ablation       │
│  evaluation/judge.py — LLM-as-judge rubric scoring                │
│  evaluation/statistics.py — Wilson CI + Wilcoxon (Phase 7)        │
│  src/interaction_logger.py — durable Q&A record, ALL phases       │
│  data/interaction_logs/interactions.jsonl  (138 entries)          │
│  docs/test_results/phase6_evaluation_report.md  (full results)   │
└─────────────────────────────────────────────────────────────────┘
```

## 4.2 Why Each Layer Exists (the "so what" for each box)

- **UI**: the only layer a non-technical stakeholder ever touches. Its job is to make the orchestrator's decision *visible* (routing transparency) rather than hide it — a deliberate design choice connecting to the Engineering Management theme of trust and governance (Section 2.3).
- **Orchestrator**: the layer that turns three separate specialists into one coherent system. Its central limitation — a structural bias toward Risk Explainer on keyword ties — is now precisely measured (Section 9.2), not hidden, and is itself a legitimate, citable research finding about the limits of keyword-based routing.
- **The three agents**: each is a thin persona + audience-specific system prompt + RAG+ context-formatter layered over the *same* underlying pipeline. This is intentional: proving the RAG+ pattern generalises across audiences was more valuable than building three unrelated systems.
- **RAG+ pipeline**: the actual technical contribution. See Section 5, Decision 9, for the full reasoning, and Section 9.3 for the live evidence.
- **Vector store / LLM provider**: infrastructure, chosen for being free (Ollama embeddings), swappable (`LLM_PROVIDER` in `.env`), and reproducible.
- **Evaluation layer**: what makes every claim in this document checkable rather than asserted. This is the layer Phase 7 exists to strengthen.

## 4.3 Technology Stack and Why Each Choice Was Made

| Component | Technology | Why |
|---|---|---|
| Orchestration | Plain Python keyword classifier | Matched to the actual complexity of the routing problem — a `langgraph` `StateGraph` was available but deliberately not used (Decision 12) |
| LLM (generation + primary judge) | OpenAI gpt-4o-mini | Cheap ($0.15/$0.60 per 1M tokens), fast, good quality — the entire project cost $0.14 |
| LLM (cross-judge, Phase 7 only) | Anthropic Claude Sonnet 5 | A genuinely different model family, needed specifically to test for same-family judge bias (Section 9.4) |
| LLM (offline option) | Ollama `llama3.1:8b` | Free, local, no API key — but ~27 min/query on CPU, which is why OpenAI became the default for actual development and evaluation |
| Vector database | ChromaDB | Lightweight, embedded (no server to run), Python-native |
| Embeddings | `nomic-embed-text` via Ollama | Free, local, 768-dimensional, good enough for this domain |
| UI | Streamlit | Fast to build, renders markdown natively, no separate frontend needed |
| Testing | pytest + `unittest.mock` | 156 tests, all mocked — the entire test suite costs $0.00 to run, as many times as needed |
| Statistics (Phase 7) | `scipy` | Wilson score interval and Wilcoxon signed-rank test — standard, citable, not hand-rolled |

---

# 5. Core Design Decisions — Full Annotated Catalog

Every major decision made across all 7 phases, numbered in the order made. This is the single most useful table for viva prep and for writing a "Design and Implementation" chapter — each row is a decision, its reasoning, and (where relevant) what evidence later validated or complicated it.

| # | Decision | Phase | Reasoning | Later evidence |
|---|---|---|---|---|
| 1-8 | Project scaffolding, multi-provider LLM abstraction, ChromaDB collection-per-category design, chunking (800 chars/100 overlap) and non-ASCII quality filtering | 1-2 | Cost discipline and reproducibility from day one; collections kept separate so retrieval precision isn't diluted by irrelevant categories | Full detail in `docs/versions/PROJECT_DOC_v0.1.md`/`v0.2.md` |
| **9** | **RAG+ pattern**: live portfolio JSON injected as "Context 0," *before* retrieved chunks | 3 | Standard RAG can't answer "what is OUR VaR" — the figure isn't in any document. Ordering matters because LLMs attend best to context-start (Liu et al., "Lost in the Middle") | Phase 3: RAG+ correct ($376,329); LLM-only invented $2.5M and a fake vessel. Phase 6/7: RAG+ averages 11.3-11.6/12 vs 7.4-8.3 (RAG-only)/8.6-9.3 (LLM-only), Wilcoxon p<0.05 |
| 10 | Agent-specific ChromaDB collections, not the merged "all" | 3 | Precision over recall — a VaR question shouldn't retrieve hedging-optimisation chunks | Created the Q017 gap (Decision 13 fixes it) |
| 11 | Mandatory 4-section response format per agent | 3 | Makes responses systematically evaluable (Structure is a scored rubric criterion) and mirrors real risk-committee report structure | Structure scored 2.8-3.0/3 consistently across all evaluation runs |
| 12 | Keyword classifier, **not** LangGraph `StateGraph`, for the orchestrator | 4 | Match tool complexity to problem complexity; `langgraph` stayed pinned but unused | Structural bias found in Phase 7 (per-agent accuracy 100%/70%/62.5%) is a real limitation of this choice — the anticipated upgrade path (semantic classifier) is now justified by data, not speculation |
| 13 | `collection_override` — one optional parameter on `RiskExplainerAgent.answer()`, not a new agent | 4 | Fixes the Q017 maritime-routing gap without duplicating the RAG+ prompt-assembly logic in a 4th agent | Verified live: Q017 now retrieves from IMO/Stopford documents, not VaR textbooks |
| 14 | Orchestrator's in-memory routing history kept separate from the durable interaction log | 4/6 | Different purposes: quick in-memory audit trail vs. permanent dissertation evidence | The durable log (Decision 18) is what actually let Phase 7's cheap recovery (Section 3.7) work |
| 15 | Maritime keywords split into "strong" (always override) and "weak" (`regulatory`, conditional) | 4 self-review | The unconditional `"regulatory"` keyword could hijack a legitimate Model Monitor question | Confirmed working: no false-positive maritime overrides in Phase 6/7 evaluation runs |
| 16 | UI chat history in `st.session_state`, not `Orchestrator.history` | 5 | Keeps per-user display state separate from the orchestrator's own routing-audit state; anticipates multi-user deployment without a redesign | — |
| 17 | Escape `$` before rendering agent text in the UI | 5 | Streamlit auto-renders `$...$` as LaTeX, mangling dollar figures | Found by actually looking at the rendered browser page, not by a test |
| 18 | Persistent interaction logger as a standalone module, not orchestrator-only | 6 | Needs to be callable from anywhere a response is generated (e.g. the Phase 7 ablation runner, which bypasses the orchestrator entirely) | The gap in NOT calling it from the ablation runner (Phase 6) and the gap in NOT calling `write_report()` early enough (Phase 7) are both real lessons — see Section 3.6/3.7 |
| 19 | `expected_agent` ground-truth labels assigned by domain judgment, **not** derived from the router's own output | 6 | Bootstrapping labels from the system under test would make "accuracy" 100% by construction and prove nothing | Deliberately mislabelled 2 (later 6) cases to disagree with predictable router behaviour — all of them were in fact misrouted exactly as predicted, confirming the labels were doing real diagnostic work |
| **20** *(new, Phase 7)* | Rebalance the evaluation set to 20/10/8 rather than leave 19/3/3 | 7 | n=3 per domain cannot support a claim of "validated across all three domains" | Immediately changed the headline finding: exposed a real 100%/70%/62.5% split that the smaller sample could not detect |
| **21** *(new, Phase 7)* | Report Wilson score CIs, not bare percentages | 7 | The normal approximation misbehaves at these sample sizes and near-boundary proportions | `tests/test_statistics.py` cross-checks the implementation against a hand-computed reference value |
| **22** *(new, Phase 7)* | Cross-family judge check using Claude, not a second OpenAI model | 7 | A same-*family* check requires a genuinely different provider, not just a different model from the same vendor | Found real bias: -2.2 point mean difference, 33% exact agreement |
| **23** *(new, Phase 7)* | `write_report()` called immediately after Part A/B, not only at script end | 7 self-review | A later optional step's failure must not be able to erase already-computed, already-paid-for results | Directly caused by, and fixes, the 166-call loss described in Section 3.7 |

---

# 6. The Knowledge Base and Synthetic Data

## 6.1 ChromaDB Collections

| Collection | Chunks | Key documents | Queried by |
|---|---|---|---|
| `risk_metrics` | 393 | Deutsch VaR textbook, Value at Risk guides, Expected Shortfall guide | Risk Explainer, Model Monitor |
| `hedging` | 408 | Kavussanos 2022, Sun 2023, Bai 2022, Han 2021 (maritime hedging papers) | Hedge Advisor |
| `maritime` | 4,502 | Stopford *Maritime Economics*, IMO MEPC70/MEPC320-74 | Risk Explainer, via `collection_override` |
| `all` | 5,306 | Everything merged | Not queried directly by any agent (kept for completeness/future use) |

## 6.2 The Synthetic Portfolio (`data/synthetic/risk_metrics.json`)

A fixed snapshot, dated 2024-11-15, for **5 vessels**. This is the "live data" that RAG+ injects. Key figures, worth memorising for your viva since they appear in almost every worked example throughout this document and the evaluation report:

- **Portfolio VaR (95%, 10-day): $376,329** | **CVaR (95%, 10-day): $481,701**
- **Average hedge ratio: 48%** | **Total annual fuel cost: $34,298,985**
- **Methodology**: Variance-Covariance (Delta-Normal), perfect positive correlation assumption (a conservative upper bound), 2-year historical volatility window
- **MV Iron Maiden** (VLCC tanker, HSFO fuel, only 30% hedged) carries the highest single-vessel VaR ($177,482) and is the vessel used in almost every maritime-context and hedging-boundary evaluation query (Q017, Q026, Q036, Q037)

**Honest limitation, stated plainly**: this is synthetic, static data. It was a deliberate simplification appropriate for a dissertation (Section 12.2), not an oversight — but it does mean every result in this document is a demonstration of the *mechanism* working, not proof that the exact numbers (84.2% accuracy, 11.3/12 mean score) would hold against a real company's messier, changing data.

---

# 7. The Three Agents, in Detail

| | **Risk Explainer** | **Hedge Advisor** | **Model Monitor** |
|---|---|---|---|
| Audience | Board / senior management | Treasury / risk team | Quant team / risk committee |
| ChromaDB collection | `risk_metrics` (or `maritime` via override) | `hedging` | `risk_metrics` |
| Response format | SUMMARY / EXPLANATION / BUSINESS IMPLICATIONS / CAVEATS | SUMMARY / ANALYSIS / RECOMMENDATION / MARKET CONTEXT | STATUS (GREEN/AMBER/RED) / FINDINGS / RECOMMENDATION / TECHNICAL NOTES |
| What its RAG+ formatter surfaces from `risk_metrics.json` | Fuel prices, portfolio VaR/CVaR, per-vessel breakdown | Hedge ratios, hedged/unhedged dollar exposure | Methodology parameters, correlation/volatility assumptions |
| Phase introduced | 3 | 4 | 4 |
| Final measured routing accuracy | **100%** (20/20) | **70%** (7/10) | **62.5%** (5/8) |
| Source file | `agents/risk_explainer.py` | `agents/hedge_advisor.py` | `agents/model_monitor.py` |

All three inherit from `agents/base_agent.py`'s `BaseAgent` abstract class, which is what lets the orchestrator route to any of them through one uniform `.answer()` interface without knowing their internals — a clean example of programming to an interface, worth naming explicitly in an implementation chapter.

---

# 8. The Orchestrator and Routing Logic, in Detail

## 8.1 How Routing Actually Works

`src/orchestrator.py`'s `route()` method, in order:
1. Check for **strong** maritime keywords (`imo`, `hsfo`, `vlsfo`, `scrubber`, `sulphur`, `stopford`) — if found, **always** route to Risk Explainer with the `maritime` collection override, regardless of anything else that matched.
2. Check for the **weak** maritime keyword (`regulatory`) — only override if nothing else matched at all.
3. Otherwise, score the query against each agent's keyword list and pick the highest-scoring agent.
4. **Ties are broken by `PRIORITY_ORDER = ["risk_explainer", "hedge_advisor", "model_monitor"]`** — this single line is the root cause of the uneven per-agent accuracy (Section 9.2). Every one of the 6 misroutes in the final evaluation run went *to* Risk Explainer.
5. If nothing matched at all, default to Risk Explainer with confidence `"low"`.

## 8.2 Why This Matters More Than It Looks

This is a genuinely good viva topic (Section 18 Q6) because it's a *precise, mechanistic* explanation for an empirical result, not a vague "the model sometimes gets confused." You can trace a misrouted query (e.g. Q009: *"why do we use a 10-day time horizon for our VaR calculation?"*) exactly: it contains "var" (a Risk Explainer keyword) and no Model Monitor keyword at all, so it loses the tie-break by construction, every time, deterministically. This is falsifiable and was, in fact, predicted and deliberately tested for (Decision 19, the boundary queries Q036/Q037) before the live run confirmed it.

## 8.3 The Explicit Argument: Why a Diagnosed Failure Is Stronger Evidence Than a Flattering Aggregate

**Make this argument explicitly in your dissertation rather than leaving an examiner to construct it themselves** — a second independent review specifically flagged this as worth stating outright, not just implying across several sections. The honest headline is "70% and 62.5% routing accuracy for two of three agents" — on its face, that sounds like a weaker result than a single clean 92%. It is not, and here is the precise reason why: **a routing failure with a known, single-line-of-code, structural cause is more valuable evidence for RQ3 than a mysteriously-perfect aggregate would have been.** A flattering 92% with no per-agent breakdown tells you multi-agent routing "worked" but gives you no way to predict when it will fail next, or how to fix it. The diagnosed failure — every misroute traceable to `PRIORITY_ORDER` breaking ties toward Risk Explainer, confirmed by two deliberately-adversarial boundary queries that misrouted exactly as predicted before the live run — tells you *exactly* where the cross-agent boundary breaks down and *why*, which is precisely the kind of transferable, mechanistic knowledge a dissertation is supposed to produce. Anyone building a similar multi-agent system now has a specific, actionable finding ("keyword-tie-break routing will systematically favour whichever agent sits first in your priority list") rather than a single unexplained percentage. **If an examiner asks "if two of your agents only route correctly 62-70% of the time, is multi-agent routing actually validated here?" — this is the answer**: yes, in the sense that matters for a research contribution — the mechanism is validated and its failure boundary is precisely characterised, which is a stronger and more useful result than an aggregate number that happened to look better.

---

# 9. Evaluation Methodology and Results — Complete and Honest

## 9.1 The Evaluation Query Set

`prompts/risk_prompts.py` — **38 queries**, each with `id`, `query`, `category`, `expected_elements` (substrings a correct answer should contain), `expected_agent` (independently-assigned ground truth, Decision 19), and `difficulty`. Final distribution: **risk_explainer 20, hedge_advisor 10, model_monitor 8**.

## 9.2 Routing Accuracy Results

**Overall: 32/38 = 84.2%, 95% Wilson CI: 69.6%–92.6%.**

| Agent | Correct/Total | Point estimate | 95% Wilson CI |
|---|---|---|---|
| Risk Explainer | 20/20 | 100% | 83.9%–100% |
| Hedge Advisor | 7/10 | 70.0% | 39.7%–89.2% |
| Model Monitor | 5/8 | 62.5% | 30.6%–86.3% |

**All 6 misroutes** (Q009, Q023, Q026, Q035, Q036, Q037) went *to* Risk Explainer, and every single one was an intended Hedge Advisor or Model Monitor query — a perfectly consistent pattern, fully explained by `PRIORITY_ORDER` (Section 8.1). **How to present this honestly**: don't say "the system is 84% accurate." Say: *"the router is essentially perfectly reliable for Risk Explainer, and has a specific, structural, well-understood bias against the other two agents when their questions share vocabulary with Risk Explainer's — a limitation of keyword-based classification that a semantic router would be expected to fix, and which this evaluation was specifically designed to surface, not hide."*

## 9.3 RAG+ Ablation Results

Representative subset, 15 queries (9 Risk Explainer, 3 Hedge Advisor, 3 Model Monitor), each run through 3 modes:

| Mode | Mean score (/12) | vs. RAG+ (Wilcoxon) |
|---|---|---|
| **RAG+** (full agent) | **11.3** | — |
| RAG-only (retrieval, no live data) | 8.3 | p=0.0022 (significant) |
| LLM-only (no context at all) | 9.3 | p=0.0164 (significant) |
| *(RAG-only vs. LLM-only, for completeness)* | — | p=0.0301 (significant) |

**The counter-intuitive finding, and why it strengthens rather than weakens the RAG+ story**: LLM-only scores *higher* than RAG-only. This is not RAG-only failing to reason — it's RAG-only correctly, honestly saying "the context documents don't contain this figure" (which a judge scores low on Accuracy because it doesn't answer the question), versus LLM-only confidently fabricating a plausible number (which a judge, with no ground truth to check against, can score higher purely for sounding confident). **The precise, defensible claim** (see Section 5 Decision 9's "Later evidence" column, and Section 18 Q7): generic document retrieval cannot answer questions that need live structured data — this project's contribution is architecting exactly where that live data enters the prompt, not "RAG beats no-RAG" in some generic sense.

**Is the significance driven by a handful of outliers, or is it a consistent pattern?** (A second, independent review — Section 10.5 — specifically flagged this as worth checking before relying on the Wilcoxon result, and it's a fair, cheap check to do.) Directly inspecting all 15 paired differences: **RAG+ scores higher than RAG-only on 12 of 15 queries** (mean difference +3.0 points), and **higher than LLM-only on 10 of 15** (mean difference +2.0 points). This is a broad, consistent directional pattern, not two or three extreme differences carrying the whole result. There is exactly **one query that goes the other way in both comparisons — Q023** ("explain the variance-covariance method... in simple terms"), where RAG+ actually scored *lower* (8/12) than both RAG-only (9/12) and LLM-only (11/12). This is itself explicable, not just noise: Q023 is a pure methodology-explanation question that doesn't need portfolio grounding at all, so injecting it may have added length or a slight framing distraction rather than helping — consistent with this project's broader finding that RAG+'s advantage is concentrated in questions that need the *company's own figures*, not general conceptual explanations. **State this explicitly if asked** (Section 18 Q7 has been extended with this point) — it turns "is your test appropriate at n=15?" from a potential weakness into a demonstration that you checked.

## 9.4 The Cross-Family Judge Check — a Genuinely Important Result

15 ablation RAG+ responses were independently re-scored by Claude Sonnet 5 (a different model family from the gpt-4o-mini primary judge and the gpt-4o-mini that generated the responses).

- **Mean signed difference (Claude − gpt-4o-mini): −2.20 points** (out of 12) — gpt-4o-mini scores itself higher on 12 of 15 comparisons
- **Exact agreement: 5/15 (33%)**
- **Correlation between the two judges' totals: 0.55** (moderate, not strong)

**Why this is a strength, not a weakness, of the dissertation, if framed correctly**: this is not a documented risk cited from the literature and left unaddressed — it is a *measured result from this project's own data*, obtained specifically because the risk was taken seriously (Section 18 Q1, Q8). It directly justifies keeping the manual/practitioner-review mechanism (Section 16) as more than a formality: the automated judge alone is now *demonstrated*, not just assumed, to be an imperfect proxy for answer quality.

## 9.5 The Interaction Log as a Complete Evidence Trail

`data/interaction_logs/interactions.jsonl` — **138 real interactions**, every one with the full query, full answer, routing decision, sources, timing, and cost. This is the raw material behind every summary table in this document, behind `docs/DR_IRELAND_INTERVIEW_PROTOCOL.md`'s curated samples, and behind `docs/test_results/phase6_evaluation_report.md`. If an examiner asks to see a specific example, this file has it, verbatim, with a timestamp.

---

# 10. Critical Self-Assessment — Strengths and Weaknesses, Stated Honestly

*(This section deliberately synthesises `docs/PROJECT_EVALUATION_AND_ROADMAP.md` and `docs/Dissertation_Progress_Review.md.pdf` — read both in full for more detail than fits here.)*

## 10.1 Genuine Strengths

1. **The RAG+ contribution is real, evidenced, and generalises** across all three agents (Section 9.3), not asserted once and left untested.
2. **The engineering discipline is unusually strong for an MSc project**: 156 mocked tests costing $0.00 to run, a 23-decision annotated log with rationale (Section 5), cost tracking down to the cent, and — critically — **a demonstrated habit of catching and honestly documenting its own mistakes** (Sections 3.4, 3.6, 3.7) rather than presenting a polished-after-the-fact narrative. Examiners are trained to reward this; it is evidence of real process, not retrofitted confidence.
3. **The Q017 before/after (Section 3.4) is a clean, falsifiable, single-variable demonstration** of RQ3 — rare to have such a crisp piece of evidence in a system this complex.
4. **The statistical rigor added in Phase 7 is a genuine methodological upgrade**, not cosmetic: it changed the actual headline finding (Section 9.2) rather than just adding decoration to an unchanged conclusion.

## 10.2 Genuine Weaknesses — What Would Cap This at Merit, Not Distinction, If Left Unaddressed

1. **No independent domain-expert validation yet.** Every result in Section 9 is automated/technical. This is the single most heavily-weighted gap for an *Engineering Management* degree specifically — see Section 16.
2. **Literature anchoring for "RAG+" is not yet fully secured.** Candidate citations exist (Section 11.2) but have not been read in depth and confirmed by the student — see Section 17 action items.
3. **All evaluation queries were written by the same person who built the system.** Decision 19 mitigates this (labels are independent of router logic), but a single author's domain judgment is still one perspective — the practitioner session (Section 16) is the planned, and necessary, further mitigation.
4. **Small sample sizes remain small even after rebalancing.** n=8 for Model Monitor's routing accuracy, n=15 for the ablation. The Wilson CIs and Wilcoxon tests (Section 9) report this honestly rather than hide it, but "honestly reported" is not the same as "resolved" — an examiner may still ask for more data, and the honest answer is that more would help, budget permits it easily, and it wasn't done only for time reasons.
5. **Synthetic, static data only** (Section 6.2) — a stated, deliberate scope boundary, but real.
6. **The managerial/cost-benefit/adoption-risk discussion is thinner than the technical evaluation.** Section 2.3 states what's needed; it has not yet been written into dissertation prose.

## 10.3 The Honest Answer to "Does This Actually Solve the Business Problem?"

Not yet fully proven — and you should say so plainly if asked (Section 18 Q3). What is proven: the system produces figure-grounded, correctly-structured, plain-English answers to realistic questions, faster and cheaper than a human analyst, and it fails in specific, explained, non-catastrophic ways (a misrouted query still typically gets a substantively correct answer from the "wrong" persona — see the Q023/Q026 examples in `docs/DR_IRELAND_INTERVIEW_PROTOCOL.md`). What is *not* yet proven: that a real risk professional would trust it enough to send its output to a board unedited. That is exactly what the Dr. Ireland session is designed to test.

## 10.4 On the Engineering-Management Framing Specifically

The external review weighted this heavily, and it deserves a direct answer in your dissertation, not just in this document: **the technical work here is a means, not the end.** The actual Engineering Management questions — is this cheaper than the status quo, what governance would a real deployment need, what would block adoption, who are the stakeholders and what does each actually need — are answerable using material already gathered in this project (the four agent personas *are* a stakeholder analysis; the $0.0005/query cost *is* half of a cost-benefit argument; the same-family judge bias finding *is* a governance/trust argument) but have not yet been written up as such. This is prose work, not further code — see Section 17.

## 10.5 A Second Independent Review, After Phase 7 — and What It Confirmed

After Phase 7's work was documented (`PROJECT_DOC_v1.1.md`), a **second round** of external review was obtained specifically to check whether the Phase 7 response to the first review actually held up (`docs/Dissertation_Progress_Review_v2.md.pdf`). This is worth knowing about and citing in your methodology chapter as evidence of an iterative, independently-checked review process — it is unusual, and a positive, for a student to seek a second round of critique rather than stop after addressing the first. Its verdict, stated directly: **"strong build, strong argument, with one real evidentiary gap remaining (practitioner validation) and a couple of framing refinements that are writing tasks, not research tasks"** — and, on the technical substance specifically, **"very plausibly distinction-range work"** conditional on the practitioner session being conducted and written up honestly.

Three things from this second review are worth internalising directly:

1. **It independently re-derived the routing numbers from the raw `interactions.jsonl` file itself**, not just trusted the summary in `PROJECT_DOC_v1.1.md` — and got exactly 32/38, with the same 100%/70%/62.5% per-agent split and the same six misroutes, all landing on Risk Explainer. This is a genuine, independent confirmation that the evaluation report's numbers are real and reproducible from the raw data, not an artifact of how they were summarised.
2. **It independently verified all four candidate literature citations** against live sources (Section 11.2) — confirming they are real, correctly-attributed papers, not hallucinated.
3. **It raised one genuinely new, cheap, valuable check**: whether the Wilcoxon significance (Section 9.3) was being driven by a handful of extreme outlier queries rather than a broad, consistent pattern. This was checked directly (Section 9.3) and found to be a consistent pattern (12/15 and 10/15 queries respectively favour RAG+), not an outlier artifact — closing that specific concern with evidence rather than argument.

**One framing note for when this material moves from project documentation into the dissertation text itself**: the honest, blow-by-blow bug-hunting narrative in Section 3.7 (four Anthropic-provider bugs found in a row) is exactly the right way to document engineering work *as it happens*, and should stay that way in `PROJECT_DOC_v1.1.md`. But in the dissertation proper, frame this material as **verification/testing methodology** — evidence that integrations were rigorously tested before being trusted, which is a strength — rather than as a "things kept going wrong" narrative, which could read as noise to an examiner unfamiliar with the day-to-day process. Same underlying facts, different frame, for a different audience. This distinction — process documentation versus dissertation prose — is worth remembering for every phase's material, not just this one.

---

# 11. Academic Positioning

## 11.1 Research Questions — Precisely Stated Answers

- **RQ1** (*Can LLM agents accurately explain maritime fuel risk metrics in natural language?*) — Yes, with a stated caveat: "accurately" is currently measured by an automated judge itself shown to have measurable bias (Section 9.4), pending independent practitioner corroboration (Section 16).
- **RQ2** (*Does RAG-augmented generation produce more accurate explanations than a base LLM?*) — Yes, decisively for RAG+ specifically (Section 9.3), and the RAG-only/LLM-only comparison reveals *why*: live structured data, correctly placed in the prompt, not retrieval in general, is what closes the accuracy gap on data-specific questions.
- **RQ3** (*Can multi-agent routing improve response relevance vs. a single agent?*) — Partially yes, precisely bounded: routing is reliable for Risk Explainer (100%, tight-ish CI) and measurably weaker for the other two agents (70%, 62.5%, wide CIs), with the weakness traced to a specific, named, structural cause (Section 8.1) rather than left as unexplained noise. The Q017 case study (Section 3.4) is the strongest single piece of RQ3 evidence in the project.

## 11.2 Literature — Located and Independently Verified as Real; Reading Them Properly Is Still Your Job

**Status upgrade**: these were originally located via web search and reviewed only at the abstract/summary level. A second, independent review (Section 10.5) then separately checked all four against live sources and confirmed **all four are real, correctly-attributed papers** — not hallucinated or misattributed. This matters more than it sounds: fabricated or misattributed citations are exactly the kind of error that can turn a strong dissertation into a viva disaster, so having this independently confirmed is a genuine, checked foundation. **What is still your job, and is not yet done**: reading them properly and pulling the specific claims you actually cite, rather than citing from the abstract alone.

- **Liu et al., "Lost in the Middle: How Language Models Use Long Contexts,"** arXiv:2307.03172, *TACL* 12:157-173 (2024). Supports Decision 9's ordering rationale directly: LLMs attend best to context-start/end, which is why portfolio data is placed first.
- **"A Survey on Retrieval And Structuring Augmented Generation"** (the "RAS" survey), arXiv:2509.10697, KDD'25 — the closest existing academic umbrella term for what this project calls "RAG+."
- **"Retrieval-Augmented Generation: A Comprehensive Survey of Architectures, Enhancements, and Robustness Frontiers,"** arXiv:2506.00054 (2025) — general RAG grounding.
- **"Self-Preference Bias in LLM-as-a-Judge,"** arXiv:2410.21819 (2024), and **"Great Models Think Alike and this Undermines AI Oversight,"** arXiv:2502.04313 (2025) — directly relevant to Section 9.4's finding.
- **Lewis et al. (2020)** — the foundational RAG paper this project extends.

**What is actually novel, once anchored against this literature** (say this precisely, not as an overclaim): not the general idea of combining structured and unstructured context (that's established, and now has a named survey — the RAS paper — covering it), but the specific ordering choice (validated against the "Lost in the Middle" attention-position finding) and the per-agent formatter design that lets three different personas each surface a different projection of one underlying JSON snapshot.

---

# 12. Threats to Validity (Formal)

## 12.1 Internal Validity
Are the routing-accuracy figures measuring routing quality, or partly measuring how the evaluation set was constructed by the system's own builder? Mitigated by Decision 19 (independent labelling) and the deliberately-adversarial boundary queries, but not eliminated — a single author's judgment is still one perspective. The Dr. Ireland session (Section 16) is the further mitigation.

## 12.2 External Validity
All results come from one static synthetic portfolio, one LLM family for generation, one domain. The precise numbers (84.2%, 11.3/12) should not be claimed to generalise; the architectural findings (RAG+'s ordering matters; keyword routing has a specific tie-break bias) plausibly do, and that is the level at which RQ1-RQ3 should be argued.

## 12.3 Construct Validity
Does the LLM-judge rubric score actually measure "answer quality" a real professional would care about? Section 9.4 demonstrates this is a real concern, not hypothetical — a different judge, scoring identical text, disagrees 67% of the time by a meaningful margin. This is precisely why the practitioner session matters more than any further automated metric would.

---

# 13. Cost, Testing, and Engineering Discipline — Summary

| Metric | Value |
|---|---|
| Total project spend, all 7 phases | **$0.1362** of $10.00/month budget (1.36%) |
| Total unit tests | **156**, all mocked, $0.00 to run |
| Total real interactions logged | **138** |
| Git tags (chronological) | v0.1-setup → v0.2-rag → v0.3-agent → v0.4-multi → v0.4.1-multi → v0.5-ui → v0.5.1-ui → v0.6-evaluation → v1.0 → v1.1-evidence → **v1.1** (current) |
| Branching model | `feature/phaseN-*` → `dev` → `master`, tagged at every merge |

**Why this belongs in a dissertation methodology chapter**: it is direct, checkable evidence of disciplined, budget-conscious, test-driven engineering practice — not just a claim about process, but an artifact trail (git log, cost CSV, test suite) that proves it.

---

# 14. Glossary (for a Reader New to This Project)

| Term | Definition |
|---|---|
| **VaR** | Value at Risk — the maximum expected loss at a given confidence level over a time horizon (e.g. "$376,329 at 95% confidence over 10 days") |
| **CVaR** | Conditional VaR / Expected Shortfall — the *average* loss in the worst-case scenarios beyond the VaR threshold |
| **Hedge ratio** | The percentage of fuel-price exposure covered by a financial hedging instrument |
| **RAG** | Retrieval-Augmented Generation — an LLM's response augmented with retrieved document context |
| **RAG+** | *This project's term*: RAG extended with live structured data injected as a first context block, ahead of retrieved documents |
| **Orchestrator** | The routing layer that decides which of the three specialist agents answers a given query |
| **`collection_override`** | A parameter letting the orchestrator redirect an agent's document retrieval to a different ChromaDB collection without changing its persona |
| **`expected_agent`** | An independently-assigned ground-truth label (which agent *should* answer a query) used to measure routing accuracy |
| **Wilson score interval** | A confidence interval for a proportion (like accuracy) that stays well-behaved at small sample sizes, unlike the simpler normal approximation |
| **Wilcoxon signed-rank test** | A non-parametric statistical test for paired data, used here because judge scores are bounded/ordinal and the samples are small |
| **LLM-as-judge** | Using an LLM to automatically score another LLM's output against a rubric |
| **Same-family judge bias** | An LLM judge's tendency to score its own model family's outputs more favourably, independent of actual quality |
| **HSFO / VLSFO** | High / Very Low Sulphur Fuel Oil — HSFO is cheaper but requires scrubbers to meet IMO 2020 sulphur regulations; VLSFO is compliant without one |

---

# 15. Complete File and Repository Map

## 15.1 Core System
| Path | What it is |
|---|---|
| `config/settings.py`, `llm_config.py`, `budget_config.py` | All runtime configuration |
| `src/embeddings.py`, `vector_store.py`, `document_loader.py` | RAG foundation (Phase 2) |
| `src/llm_provider.py` | Multi-provider LLM abstraction (Phase 1, extended Phase 7) |
| `src/rag_pipeline.py` | Core retrieve→prompt→generate logic |
| `src/cost_tracker.py` | API cost accounting, budget alerts |
| `src/orchestrator.py` | Multi-agent routing (Phase 4, refined 4.1/6/7) |
| `src/interaction_logger.py` | Durable Q&A log (Phase 6) |
| `agents/base_agent.py`, `risk_explainer.py`, `hedge_advisor.py`, `model_monitor.py` | The three specialist agents + shared interface |
| `prompts/system_prompts.py`, `risk_prompts.py` | Agent personas; the 38-query evaluation set |
| `ui/app.py` | Streamlit chat interface (Phase 5) |
| `evaluation/judge.py`, `run_evaluation.py`, `statistics.py` | Evaluation infrastructure (Phase 6-7) |

## 15.2 Evidence and Results
| Path | What it is |
|---|---|
| `data/synthetic/risk_metrics.json` | The synthetic portfolio (Section 6.2) |
| `data/interaction_logs/interactions.jsonl` | Every real Q&A, ever (138 entries) |
| `data/cost_logs/api_costs.csv` | Every API call's cost, ever |
| `docs/test_results/phase3_comparative_test.md` | The original RAG+ vs RAG vs LLM-only comparison (Phase 3), including the $2.5M hallucination |
| `docs/test_results/phase6_evaluation_report.md` | **The primary evidence file** — full Part A/B results, statistics, cross-judge section |
| `docs/DR_IRELAND_INTERVIEW_PROTOCOL.md` | Practitioner validation session protocol + 9 curated real samples |

## 15.3 Documentation (Read in This Order for Full History)
| Path | Covers |
|---|---|
| `docs/versions/PROJECT_DOC_v0.1.md` → `v0.6.md` | Phase-by-phase detail, in order |
| `docs/versions/PROJECT_DOC_v1.0.md` | Cumulative synthesis after all 6 planned phases |
| `docs/versions/PROJECT_DOC_v1.1.md` | Phase 7 in full: the rebalance, the statistics, the bug saga, the validity discussion |
| `docs/PROJECT_EVALUATION_AND_ROADMAP.md` | The internal code/architecture audit that helped motivate Phase 7 |
| `docs/Dissertation_Progress_Review.md.pdf` | Round 1 external review — motivated Phase 7 |
| `docs/Dissertation_Progress_Review_v2.md.pdf` | Round 2 external review — independently verified the Phase 7 fixes and citations, raised the Wilcoxon outlier check (Section 9.3) |
| **This document (`docs/MASTER_PROJECT_DOCUMENT.md`)** | The single synthesis of everything above — start here |

## 15.4 Tests (156 total)
`tests/test_agents.py`, `test_orchestrator.py`, `test_rag.py`, `test_vector_store.py`, `test_ui.py`, `test_interaction_logger.py`, `test_judge.py`, `test_statistics.py`, `test_llm_provider.py` — every one mocked, zero API cost, runnable anytime with `pytest tests/ -v`.

---

# 16. What You Still Need to Do — Action Items Before Submission

Ranked by priority, per the second independent review's updated ordering (Section 10.5) — nothing left on this list is a technical/research task; it is entirely writing and one conversation:

1. **Conduct the Dr. Ireland practitioner validation session. Nothing else on this list matters as much — book it.** Protocol and 9 curated samples are fully prepared in `docs/DR_IRELAND_INTERVIEW_PROTOCOL.md`. This is the single evidence source in the entire project that measures the actual thing the Problem Statement (Section 2) claims to solve, rather than a proxy for it (Section 10.3/12.3 make this argument — take your own advice on it).
2. **Write up the session honestly, including any criticism or disagreement he raises.** If he disagrees with an automated judge score, or flags something the evaluation missed, that disagreement is itself valuable dissertation evidence — the argument in Section 12.3 only works if this is a genuine independent check, not a rubber stamp.
3. **Draft the managerial/adoption/cost-benefit section (Section 2.3, 10.4) using the session's answers to the trust-calibration and adoption-barrier questions as primary material** — the protocol's open questions (Section 3 of the interview protocol) were specifically designed to generate exactly this raw material.
4. **Actually read the four cited papers properly** (Section 11.2) — they are confirmed real and well-matched, but pull the specific claims you cite from the papers themselves, not from an abstract summary.
5. **Add the explicit "diagnosed structural failure vs. flattering aggregate" paragraph to your RQ3 discussion** — the argument is already fully written out in Section 8.3 above; this is a matter of transferring it into your dissertation text, not developing new reasoning.
6. Optional, already partly done as insurance: the Wilcoxon outlier/consistency check (Section 9.3) — already performed and documented; if you want to strengthen it further, a larger ablation sample would tighten the picture, and the budget easily supports it (total spend so far: $0.14 of $10).

---

# 17. Distinction-Level Readiness Checklist

Per the second independent review's verdict (Section 10.5): **"strong build, strong argument, with one real evidentiary gap remaining and a couple of framing refinements that are writing tasks, not research tasks... very plausibly distinction-range work"** conditional on the items below.

| Item | Status | Where |
|---|---|---|
| A genuine, evidenced technical contribution (RAG+) | ✅ Done | Section 5 Decision 9, Section 9.3 |
| Multi-agent system with a clean, falsifiable before/after demonstration (Q017) | ✅ Done | Section 3.4 |
| Rigorous, disciplined engineering process (tests, cost tracking, decision log) | ✅ Done | Section 13 |
| Statistical honesty (confidence intervals, significance testing) | ✅ Done, and independently re-derived from raw data by a second reviewer | Section 9.2, 9.3, 10.5 |
| Checking your own evaluation methodology for bias (same-family judge check) | ✅ Done | Section 9.4 |
| Checking significance tests aren't driven by outliers | ✅ Done | Section 9.3 |
| Formal validity/limitations discussion (not just a bullet list) | ✅ Done | Section 12 |
| Literature citations located AND independently verified as real | ✅ Located and verified; reading them properly is the remaining step | Section 11.2 |
| Explicit "diagnosed failure > flattering aggregate" argument for RQ3 | ✅ Written (Section 8.3) — needs transferring into dissertation prose | Section 8.3, Section 16 item 5 |
| Independent, practitioner (non-technical) validation | ⏳ **The single remaining gap — your action** | Section 16 item 1-2 |
| Managerial/Engineering-Management framing written into prose | ⏳ **Pending — your action** | Section 16 item 3 |
| Comfortable, fluent answers to the hardest anticipated questions | ⏳ **Practice with Section 18** | Section 18 |

Everything marked ✅ is real, evidenced — much of it now independently double-checked by a second reviewer — and yours to present confidently. Everything marked ⏳ is achievable in the remaining time, squarely in your control, and per the second review's own assessment is "almost entirely about whether the last 10% gets done with the same rigor as everything else, not about the technical foundation, which is solid."

---

# 18. Viva / Presentation Preparation — Anticipated Questions and Model Answers

*Read Section 9 and Section 10 again immediately before your viva so these numbers are fresh. Practise saying these answers out loud, not just reading them.*

### Q1. "You claim validation across all three agents — walk me through the sample size for each."

**Model answer**: "The evaluation set has 20 Risk Explainer, 10 Hedge Advisor, and 8 Model Monitor queries — rebalanced in a later phase specifically because the original 19/3/3 split couldn't support that claim. With the rebalanced set, routing accuracy is 100% for Risk Explainer with a tight confidence interval, but 70% and 62.5% for the other two, with wide 95% Wilson intervals — roughly 40-89% and 31-86% respectively. I report the interval alongside the point estimate specifically because at this sample size the point estimate alone would overstate how precisely I actually know these figures. What the data supports confidently is that the router has a specific, structural bias — it defaults to Risk Explainer on keyword ties — not that any of the three per-agent numbers is precisely known."

### Q2. "How do you know your judge isn't just easier on outputs from its own model family?"

**Model answer**: "I checked directly rather than assuming. I re-scored 15 of the ablation responses with Claude — a different model family from the gpt-4o-mini used both to generate the responses and as the primary judge — and found a mean difference of -2.2 points out of 12, with only 33% exact agreement between the two judges. So yes, there is measurable same-family bias in my primary judge, and I report it rather than hide it. That's precisely why I don't treat the automated judge score as ground truth — it's one signal, and the planned practitioner validation session is the independent check that would actually establish whether either judge's scores track what a real risk professional considers a good answer."

### Q3. "This is an Engineering Management dissertation — where's the evidence this actually solves the business problem, beyond an automated rubric?"

**Model answer, if the Ireland session has NOT yet happened**: "Honestly — not yet fully proven, and I want to be direct about that rather than overclaim. What I have is strong technical evidence: the system produces figure-grounded, correctly-structured answers faster and cheaper than a human analyst, and its failure modes are specific and explainable rather than random. What I don't yet have is independent practitioner validation. I've prepared a structured session with [a genuine domain expert] specifically to close that gap — a 1-to-5 'would I send this as-is' scale across a representative, honestly-selected set of outputs, including ones the system got wrong. [If it has happened by your viva, replace this with the actual scores and quotes.]"

### Q4. "Why not use LangGraph, since you had it as a dependency from the start?"

**Model answer**: "Because the actual routing problem — pick one of three agents based on query content, occasionally override a retrieval collection — doesn't need graph-based state management to solve. Building that abstraction before evaluation had shown keyword routing was insufficient would have been solving a problem I didn't have yet. And the data now backs that call up two ways: keyword routing works close to perfectly for the majority-class agent, and its failure mode — a specific tie-break rule — is fully explained and predictable, which is exactly the kind of finding you'd want before deciding a more complex classifier is actually necessary."

### Q5. "What is 'RAG+' exactly, and how is it different from standard RAG?"

**Model answer**: "Standard RAG retrieves static documents and answers from those alone — it can tell you what VaR *is*, but not what *our* VaR *is*, because that figure lives in a database, not a document. RAG+ injects the company's live portfolio snapshot as a first block of context, *before* the retrieved documents, in every prompt. The ordering is deliberate, not cosmetic — language models attend most reliably to the start of their context window, a finding independently supported in the 'Lost in the Middle' literature. The clearest evidence it matters: without it, the bare LLM once invented a $2.5 million VaR figure — 6.6 times the real $376,329 — and a vessel that doesn't exist in the fleet. With it, the same model correctly cites $376,329 every time."

### Q6. "Why does routing accuracy differ so much between your three agents — 100% versus 70% versus 62.5%?"

**Model answer**: "It's a single, traceable design choice: when the keyword classifier scores a tie between two agents, it breaks the tie in a fixed priority order that favours Risk Explainer. Almost every misrouted query in the evaluation set contains a Risk Explainer keyword — usually 'VaR' — but no Hedge Advisor or Model Monitor keyword, so it loses that tie by construction, deterministically, every time. I actually predicted this and tested for it deliberately — two of the evaluation queries were written specifically to probe this boundary before the live run, and both misrouted exactly as expected."

### Q7. "Doesn't your RAG+ vs. RAG-only comparison unfairly favour RAG+, since only RAG+ gets the portfolio data at all?"

**Model answer**: "That's a fair challenge, and I reframed the finding specifically because of it. The precise claim isn't 'RAG+ beats RAG' in some generic sense — it's that generic document retrieval structurally cannot answer questions requiring live structured data, and this project's contribution is the architecture that decides where that data enters the prompt. The evidence that makes this more than a semantic reframing: RAG-only actually scores *lower* than a bare LLM with no context at all, because RAG-only honestly says 'the documents don't contain this figure' — which a judge scores as low accuracy — while the bare LLM confidently fabricates a number, which reads as higher accuracy to a judge with no ground truth to check against. That's a real, if slightly uncomfortable, finding about what these automated judges can and can't detect, not an artifact of an unfair comparison."

### Q7b. "With only 15 paired queries, is your Wilcoxon test even appropriate — couldn't a couple of extreme queries be driving the whole 'significant' result?"

**Model answer**: "I checked that directly rather than just trusting the p-value. Looking at all 15 individual paired differences: RAG+ scores higher than RAG-only on 12 of the 15 queries, and higher than LLM-only on 10 of the 15 — that's a broad, consistent pattern, not two or three extreme outliers carrying the result. There's exactly one query, out of fifteen, where RAG+ actually scores lower in both comparisons — a pure methodology-explanation question that doesn't need the company's live figures at all, which is itself a sensible, explicable exception rather than noise. I still describe the overall finding as suggestive rather than confirmatory given the sample size, but it's not fragile — the direction holds for the large majority of individual queries, not just on average."

### Q8. "Your total project spend is $0.14 — is that realistic, or is this too cheap to mean anything?"

**Model answer**: "The generation cost genuinely is that cheap — gpt-4o-mini costs about $0.0005 per query, and I've logged 608 real API calls across the whole project's lifetime and stayed under $0.14. That's a real, if favourable, part of the cost-benefit argument: even fully loading in evaluation and iteration cost, this is orders of magnitude cheaper than the analyst time it would offset. What it doesn't tell you is the cost of the surrounding infrastructure a real deployment would need — governance, human sign-off processes, monitoring — which is exactly the kind of Engineering Management question the adoption-barriers discussion in my dissertation addresses, separate from the pure API cost."

### Q9. "What happens if the system gives a real risk committee a wrong number?"

**Model answer**: "That's the most serious open risk, and I don't think it's fully solved by the current system — I think it's mitigated by RAG+ grounding (which measurably reduces fabrication) but not eliminated, and any real deployment would need a human-in-the-loop sign-off step before a generated figure reaches a board pack, which the durable interaction log I built would support as an audit trail but doesn't itself enforce. This connects directly to the same-family judge bias finding: if even an automated judge can be fooled by a confident wrong answer, a time-pressured human reader could be too, which is exactly why I don't treat this system as ready to remove the human from the loop."

### Q10. "What's the single biggest weakness of this project, in your own words?"

**Model answer**: "That every piece of evidence backing my results is currently technical or automated — routing accuracy, ablation scores, even the same-family bias check. None of it yet comes from an actual risk professional looking at real outputs and saying whether they'd trust them. I've built the protocol to close that gap and I know it's the highest-priority thing left to do, precisely because this is an Engineering Management degree where 'does it work for the business' matters as much as 'does it work technically.'"

### Q11. "Tell me about a mistake you made during this project and how you handled it."

**Model answer**: "Several, and I documented all of them rather than clean them up after the fact. The clearest example: late in the project, I was checking whether my automated LLM judge was biased toward its own model family, so I ran a comparison against a different provider. That comparison failed four separate times in a row, each for a different real reason — an unset API key, a retired model ID, a deprecated API parameter, and a genuine parsing bug in code that had simply never been exercised before. Each time I diagnosed it with the cheapest possible test before spending more, fixed the actual cause, and added a regression test. One of the failures also exposed a more serious problem: my evaluation script only saved its results at the very end, so when it crashed partway through, I lost a batch of already-computed results that had cost real money to generate. I fixed that structurally — results are now saved incrementally — and recovered the lost data by re-scoring the already-generated answers rather than paying to regenerate them. I think this kind of honest, traceable mistake-and-fix history is actually a strength of the project, not something to hide."

### Q11b. "Why did you get a second round of external review after already responding to the first one?"

**Model answer**: "Because responding to feedback once and assuming it's now fixed is exactly the kind of thing an examiner should be sceptical of — claims of 'I addressed this' are cheap unless someone independently checks them. So I asked for a second review specifically to verify the Phase 7 fixes actually held up, not just to hear that they looked good on paper. It independently re-derived my routing-accuracy numbers directly from the raw interaction log rather than trusting my summary, and got the identical result — 32 of 38, with the same per-agent breakdown and the same six misroutes. It also independently checked my four literature citations against live sources and confirmed they're real and correctly attributed. That combination — my own honest self-critique, plus an outsider's numbers matching when they pulled on the data themselves — is the kind of double-checked evidence trail I wanted before standing behind these results in a viva."

### Q12. "How would this scale — more agents, a bigger knowledge base, more users?"

**Model answer**: "A few specific, known limits: the keyword router's structural bias would likely get worse, not better, with more agents sharing vocabulary, which is exactly why a semantic/embedding-based router is the documented next step. The vector store's document-deduplication check currently loads every existing document ID into memory on each write, which is fine at 5,300 chunks but would need revisiting an order of magnitude higher. And the current architecture is single-user by design — the UI's session state and the orchestrator's routing history are already kept separately specifically to make a future multi-user version a contained change rather than a redesign, but that work hasn't been done yet."

---

# 19. Suggested Reading Order by Dissertation Chapter

| Your dissertation chapter | Read this project material first |
|---|---|
| Introduction / Problem Statement | Section 1, Section 2 |
| Literature Review | Section 11.2 (then go read the actual papers) |
| Methodology | Section 3 (the whole journey), Section 5 (decisions), Section 13 (discipline) |
| System Design / Architecture | Section 4, Section 7, Section 8 |
| Implementation | Section 5's decision table, linked source files in Section 15 |
| Evaluation | Section 9 in full, then `docs/test_results/phase6_evaluation_report.md` for every underlying number |
| Discussion / Limitations | Section 10, Section 12 |
| Conclusion / Future Work | Section 16, Section 10.2, `docs/PROJECT_EVALUATION_AND_ROADMAP.md` Section 6 (long-term roadmap) |
| Viva prep | Section 18, the week before |

---

*This document reflects the project state at git tag `v1.1`. If further work happens (the Ireland session, more evaluation queries, citation verification), come back and ask for this document to be refreshed — a summary that isn't kept in sync with the underlying evidence becomes actively misleading, not just outdated.*
