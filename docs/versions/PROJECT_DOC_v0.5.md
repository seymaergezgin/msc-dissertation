# Project Documentation — Version 0.5
# AI-Based Narrative Risk Reporting for Maritime Fuel Management
# Last Updated: 2026-07-16
# Author: Seymanur Ergezgin | MSc Engineering Management, University of Greenwich
# Supervisor: Dr. Mike Sharp

---

## Changelog from v0.4.1 to v0.5

### Added
- `ui/app.py`: a Streamlit chat interface wrapping the Phase 4 `Orchestrator` — the first human-facing entry point in this project. Prior phases were exercised via test scripts or one-off terminal commands; Phase 5 is where a person can actually type a question and read an answer.
- `tests/test_ui.py`: 4 unit tests for `_escape_markdown_dollars()`, the one piece of `ui/app.py` that is pure logic and therefore practically unit-testable (Streamlit rendering itself is not — see Section 8.1).

### Fixed (found during Phase 5 manual browser testing, not present in any earlier phase)
- **Dollar-sign LaTeX rendering bug**: Streamlit's `st.markdown()` auto-detects `$...$` as inline LaTeX. Agent answers routinely contain two or more dollar figures in the same sentence (e.g. *"HSFO is priced at \$385.14/MT compared to VLSFO at \$470.73/MT"*) — the pair of dollar signs was silently parsed as a math expression, mangling the text in the browser (see Section 9 for the exact before/after). Fixed with `_escape_markdown_dollars()`, applied to every point agent-generated text is rendered.

### Test Suite
**99 tests passing** (95 from v0.4.1 + 4 new UI helper tests), all mocked/offline — zero additional API cost for the test suite itself.

---

## Changelog from v0.5 to v0.5.1 — User-Reported Startup Failure (2026-07-16)

Immediately after merging Phase 5, the student tried running the app themselves with the documented command (`streamlit run ui/app.py`) and hit an immediate crash:

```
File "ui/app.py", line 46, in <module>
    from src.cost_tracker import CostTracker
ModuleNotFoundError: No module named 'src'
```

### Root Cause
Manual verification during Phase 5 (Section 8.2) launched the app with `env_dissertation/bin/python3 -m streamlit run ui/app.py`. Python's `-m` flag adds the **current working directory** to `sys.path`, so `from src...`/`from config...` resolved correctly by accident. The `streamlit` console-script entry point that a user naturally runs (`streamlit run ui/app.py`, matching the `Usage` docstring and Appendix D's documented command) only adds the target script's own directory (`ui/`) to `sys.path` — not the project root — so the same imports fail under that invocation. The verification method didn't match the documented usage command, so this gap wasn't caught before merging.

### Fixed
`ui/app.py` now inserts the project root onto `sys.path` explicitly, at the top of the file, before any `src`/`config` imports:
```python
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
```
This makes the app correct regardless of invocation method. Re-verified with the **exact failing command** (`env_dissertation/bin/streamlit run ui/app.py`, not `-m`) in a real headless browser: loads cleanly, zero console errors, sidebar and chat input render as expected (screenshot on file).

### Lesson Learned
When manually verifying a CLI/entry-point-launched app, use the exact command documented for end users — not a convenient variant. `python -m streamlit run` and `streamlit run` are not equivalent with respect to `sys.path`, and that difference was invisible until a real user, on a real terminal, ran the real documented command.

**Test suite unaffected**: 99/99 still passing (pytest already has the project root on `sys.path` via its own rootdir discovery, so this bug was invisible to the test suite by construction — another reason the manual browser check mattered).

---

## 1. Executive Summary

This project builds a Multi-Agent LLM system that translates quantitative maritime fuel risk metrics into plain English narratives for business stakeholders. Phase 5 gives the Phase 4 orchestrator a usable interface: a chat-style Streamlit app where a person asks a question and sees the answer, which agent handled it and why, the source documents, and running spend against the budget.

**Current status**: Phase 5 complete — **83% of total project** (5 of 6 phases).

**Key achievements in v0.5**:
- A working chat UI exercising all three agents through the real orchestrator, verified in an actual headless browser (not just imported and unit-tested) — screenshots confirm the sidebar, routing-transparency panel, and source citations all render correctly
- **Routing transparency made visible to a human for the first time**: the "Routed to X (confidence: Y) — why?" panel is the UI-layer expression of the same routing evidence documented in PROJECT_DOC_v0.4.md — this is the first phase where a non-technical user, not just a test assertion, can see the Q017 maritime-routing fix working
- A real rendering bug (dollar-sign LaTeX mangling) was found and fixed during manual testing, not left for a supervisor demo to surface
- Graceful failure handling at the UI boundary, closing **Deferred item 2** from the Phase 4 self-review

**Live browser test result** (2026-07-16): submitted *"Why does MV Iron Maiden use HSFO instead of VLSFO?"* through the actual running app (not a script). The UI correctly displayed "Routed to Risk Explainer (confidence: high) — why?" with the reason text explicitly citing the maritime collection override, and "Sources (5)" listing IMO MEPC70/MEPC320-74 and Stopford documents — the same fix verified at the code level in Phase 4, now visible end-to-end through the interface a real user would use.

---

## 2. Problem Statement

*(Unchanged from v0.1 — see that document.)*

Maritime fuel companies generate complex quantitative risk reports (VaR, CVaR, hedge ratios) that create a communication gap between risk analysts and non-technical decision-makers. This system acts as an intelligent interpreter, producing plain-language explanations grounded in the actual metric data.

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE  ✅ (Phase 5)              │
│                       ui/app.py (Streamlit)                      │
│                                                                   │
│  st.cache_resource(Orchestrator)  ← built once per server process│
│  st.session_state.messages        ← per-browser-session chat log │
│  _escape_markdown_dollars()       ← renders agent text safely    │
│  try/except around answer()       ← graceful failure handling    │
└────────────────────────────┬────────────────────────────────────┘
                             │ natural language query
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR  ✅ (Phase 4)                    │
└──────────┬──────────────────┬───────────────────┬──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
  │ RISK EXPLAINER │  │ HEDGE ADVISOR  │  │ MODEL MONITOR  │
  │    AGENT  ✅   │  │    AGENT  ✅   │  │    AGENT  ✅   │
  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘
          │                   │                    │
          ▼                   ▼                    ▼
  ┌───────────────────────────────────────────────────────┐
  │     RAG+ PIPELINE (Phase 2 + Phase 3, reused as-is)   │
  └───────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
  ┌──────────────────┐      ┌─────────────────────┐
  │   VECTOR STORE   │      │    LLM PROVIDER     │
  │   (ChromaDB)     │      │  OpenAI gpt-4o-mini │
  └──────────────────┘      └─────────────────────┘
```

### 3.2 Technology Stack

*(Unchanged from v0.4 — see that document.)* `streamlit==1.43.2` (already pinned in `requirements.txt` since Phase 1) is used for the first time in Phase 5.

### 3.3 Design Decisions

#### Decision 16: Chat History Lives in `st.session_state`, Not `Orchestrator.history`

**Decision**: `ui/app.py` maintains its own `st.session_state.messages` list for display purposes. It does not read from or write to `Orchestrator.history` (the flat routing-decision log introduced in Phase 4, Decision 14).

**Context**: `Orchestrator.history` was designed as a routing-decision audit log (query, routed agent, confidence, timestamp) for dissertation evidence and debugging — not as a UI chat transcript. The UI needs full response content (answer text, sources) to redraw past messages on every Streamlit rerun, which is a different shape of data with a different purpose.

**Rationale**: keeping these separate means the UI's display state and the orchestrator's internal bookkeeping can evolve independently. It also sidesteps a real multi-user issue: `get_orchestrator()` is cached via `st.cache_resource`, meaning **one** `Orchestrator` instance (and its `self.history`) would be shared by every browser session hitting the same server process. `st.session_state`, by contrast, is inherently per-browser-session. This was flagged as a known consideration when Phase 5 was scoped (see the "extensibility" discussion preceding this phase) — for a local single-user dissertation demo it doesn't matter, but keeping chat state in session-scoped storage from the start means a future move to genuine multi-user deployment doesn't require restructuring where history lives, only where it's persisted.

**Consequences**: `Orchestrator.get_routing_history()` and the UI's chat log can disagree in a multi-session scenario (the orchestrator's log accumulates across all sessions; a given browser's chat only shows its own turns). This is correct behaviour for what each is for, not a bug.

---

#### Decision 17: Escape Dollar Signs at Render Time, Not at Generation Time

**Decision**: `_escape_markdown_dollars()` is applied in `ui/app.py` immediately before `st.markdown()`/`st.write()` calls. Agent code (`RiskExplainerAgent`, `HedgeAdvisorAgent`, `ModelMonitorAgent`, system prompts) was not changed to avoid producing `$` in its output.

**Context**: found during Phase 5 manual browser testing (Section 9) — Streamlit's automatic LaTeX detection mangled answers containing two dollar figures in one sentence.

**Rationale**: the dollar sign is completely correct and desired in the agent's output — these are dollar-denominated risk figures, and the system prompts explicitly instruct agents to cite specific figures. The bug is entirely a property of *how Streamlit renders* that correct text, not a property of the text itself. Fixing it at the display boundary (the UI layer) keeps agent code, system prompts, and the RAG+ pattern completely untouched, and it means the fix only needs to exist in one place regardless of how many future UI surfaces might display agent text.

**Consequences**: any *new* UI surface added later (e.g. a different page, a PDF export) that renders agent-generated text via Streamlit markdown must remember to apply the same escaping. This is a manageable, documented constraint rather than a structural risk, since `_escape_markdown_dollars()` is a small, reusable, tested function.

---

## 4. Component Deep-Dive

### 4.1 Streamlit UI (`ui/app.py`)

#### Purpose
The interactive entry point for a human user: type a question, see the answer, see which agent handled it and why, see the sources, see running spend.

#### How It Works (Step by Step)

```
User types: "Why does MV Iron Maiden use HSFO instead of VLSFO?"
   │
   ▼ Step 1: st.chat_input() captures the query
   │
   ▼ Step 2: get_orchestrator() returns the cached Orchestrator
   #          (built once per server process via st.cache_resource;
   #           first call is slow — loads 3x RAGPipeline/ChromaDB —
   #           subsequent calls are instant)
   │
   ▼ Step 3: orchestrator.answer(query), wrapped in try/except
   #          On success: result = {answer, sources, routed_to,
   #          routing_reason, confidence, ...}
   #          On failure: a clean st.error() message, no raw traceback
   │
   ▼ Step 4: render the result
   #          - st.markdown(_escape_markdown_dollars(result["answer"]))
   #          - st.expander("Routed to X (confidence: Y) — why?")
   #          - st.expander("Sources (N)") listing file + page
   │
   ▼ Step 5: append to st.session_state.messages for redisplay
   #          on the next Streamlit rerun
```

#### Code Structure
```
ui/app.py
├── _escape_markdown_dollars(text)  — escapes "$" before markdown rendering
├── get_orchestrator()              — @st.cache_resource, builds Orchestrator once
├── render_sidebar()                — budget metrics + agent roster
├── render_message(entry)           — redraws one past Q&A turn from session_state
└── main()                          — chat input, live query handling, error handling
```

#### Example Usage
```bash
streamlit run ui/app.py
# Opens http://localhost:8501 — type a question in the chat box.
```

---

## 5. Data Architecture

*(Unchanged from v0.4 — no new documents, no new synthetic data. Phase 5 is a UI layer over the existing agents/orchestrator.)*

---

## 6. Agent System

*(Unchanged from v0.4 — all three agents and the orchestrator's routing table are exercised through the UI exactly as documented in PROJECT_DOC_v0.4.md Section 6, now with a human-facing display of the routing decision.)*

---

## 7. Prompt Engineering

*(Unchanged from v0.3/v0.4 — the UI does not modify prompts. It does, however, make the effect of good system-prompt structure visible to a non-technical reader for the first time: the SUMMARY/EXPLANATION/BUSINESS IMPLICATIONS/CAVEATS headers render as Streamlit markdown headers directly in the chat bubble.)*

---

## 8. Evaluation Methodology

### 8.1 Why Streamlit Rendering Itself Isn't Unit-Tested

Streamlit apps are a script that re-runs against a live browser session; there is no practical way to assert "the sidebar shows three agent names" as a fast, mocked unit test the way `tests/test_orchestrator.py` asserts routing decisions. `tests/test_ui.py` therefore targets the one piece of `ui/app.py` that is pure logic — `_escape_markdown_dollars()` — with 4 tests. The actual rendering was verified manually (Section 8.2), which is the appropriate verification method for this kind of code, not a gap in rigor.

### 8.2 Manual Browser Verification (2026-07-16)

Since no project-specific "run the app" skill existed yet, and no headless-browser CLI (`chromium-cli`) was available, Playwright + a headless Chromium were installed **ephemerally into the project venv for this verification only** (not added to `requirements.txt`, and the `playwright` pip package was uninstalled again afterward — the downloaded browser binary remains cached outside the repo, in `~/Library/Caches/ms-playwright`, harmless and reusable if browser-driven testing is needed again).

Verification steps and results:

| Step | Result |
|---|---|
| Launch `streamlit run ui/app.py`, poll for server up | Server up immediately, no startup errors |
| Screenshot on first load (before orchestrator finishes building) | Sidebar showed budget correctly; "Agents" section empty while `st.cache_resource` was still loading — expected, not a bug |
| Screenshot after `st.cache_resource` finished | Sidebar fully populated: budget metric, progress bar, all 3 agents with their collections; chat input visible; **zero console errors** |
| Live query 1: "What is our current portfolio VaR at 95% confidence?" (cost: $0.000363) | Correct SUMMARY/EXPLANATION/BUSINESS IMPLICATIONS/CAVEATS answer; "Routed to Risk Explainer (confidence: high)" expander; "Sources (4)" expander — all rendered correctly |
| Live query 2: "Why does MV Iron Maiden use HSFO instead of VLSFO?" (cost: $0.000402) | Correctly routed to Risk Explainer with the maritime override; routing_reason text explicitly named the override; 5 sources listed, all from IMO MEPC70/MEPC320-74 and Stopford documents — **but revealed the dollar-sign rendering bug** in the answer text (see Section 9) |
| Fixed the bug, re-verified with a zero-cost standalone snippet (no orchestrator/LLM call — just the exact problem string through `_escape_markdown_dollars()`) | Confirmed: unescaped text rendered as a garbled KaTeX expression; escaped text rendered as correct plain text with both dollar figures intact |

**Total live API cost for Phase 5 verification: $0.000765** (2 queries), well under the pre-approved estimate.

### 8.3 Test Suite Summary

**99 tests passing**: 89 from the Phase 4 merge + 6 from the Phase 4 self-review (v0.4.1) + 4 new `tests/test_ui.py` tests, all mocked/offline.

---

## 9. Challenges and Solutions

*(v0.2–v0.4.1 entries carried forward — new entries below.)*

| Challenge | Impact | Solution | Lesson Learned |
|-----------|--------|----------|----------------|
| Streamlit's `st.markdown()` auto-renders `$...$` as inline LaTeX | Agent answers containing two dollar figures in one sentence (e.g. fuel prices, VaR + CVaR together) were silently mangled into a garbled math expression in the browser — invisible in any unit test, only visible by actually looking at the rendered page | Added `_escape_markdown_dollars()`, applied at every point agent text is rendered in the UI; verified with a before/after screenshot | A feature can pass 99 unit tests and still be visibly broken — for UI work, looking at the actual rendered output in a browser is not optional, it is the only way this class of bug is caught |
| No `chromium-cli` or other headless-browser tool available in this environment | Couldn't follow the project's `run` skill pattern directly | Installed Playwright + headless Chromium ephemerally into the venv for verification only, uninstalled the pip package afterward, never added to `requirements.txt` | A one-off verification tool doesn't need to become a tracked project dependency — install it, use it, remove it, and document what was actually verified |
| `st.cache_resource`-cached `Orchestrator` is shared across all browser sessions on one server process | `Orchestrator.history` would not be a reliable per-user chat log if this were ever a multi-user deployment | Kept chat display state in `st.session_state` (per-session) from the start, separate from `Orchestrator.history` (Decision 16) | Deciding *where state lives* is worth getting right the first time, even for a single-user tool — it's a cheap decision now and an expensive refactor later |
| Verification used `python -m streamlit run`, but the documented user command is plain `streamlit run` — the two differ in whether the project root lands on `sys.path`, so the app crashed with `ModuleNotFoundError: No module named 'src'` the first time the student ran it themselves | App was unusable for the actual end user despite 99/99 tests passing and a clean manual verification pass | Explicitly insert the project root onto `sys.path` at the top of `ui/app.py`, before any `src`/`config` imports; re-verified with the exact failing command in a real browser | Verify with the *exact* command a user will actually type, not a convenient equivalent — `-m module run` vs. the module's own console-script entry point are not the same with respect to import resolution, and pytest's own import machinery won't catch this class of bug either |

---

## 10. Academic Relevance

### 10.1 Research Questions Addressed

- **RQ3** ("can multi-agent routing improve response relevance?"): Phase 5 doesn't add new evidence, but it makes the existing Phase 4 evidence *legible to a human reader* for the first time — the "Routed to X (confidence: Y) — why?" panel is a direct UI expression of the routing decision, useful for a supervisor demo or a dissertation screenshot in a way a terminal log is not.

### 10.2 Literature Connections

**Explainability in agentic systems**: exposing `routing_reason` and `confidence` directly in the UI, rather than only logging them, reflects the broader "interpretable AI" principle that a system's automated decisions should be inspectable by the humans relying on them — directly relevant to a dissertation discussing narrative risk reporting for non-technical stakeholders, where trust in the system's reasoning matters as much as the answer's content.

### 10.3 Methodology Mapping

| Dissertation Section | Project Component | Status |
|----------------------|-------------------|--------|
| 4.7 UI | `ui/app.py` | ✅ Complete (v0.5) |
| 4.7.1 Routing Transparency in UI | `ui/app.py` (routing expander) | ✅ Complete (v0.5) |
| 5.1 Evaluation Results | `evaluation/` | Phase 6 |

---

## 11. Cost Analysis

### 11.1 API Costs to Date

| Phase | Provider | Queries | Est. Cost USD |
|-------|----------|---------|---------------|
| 1–4.1 (per v0.4.1) | Ollama / OpenAI | ~20 | ~$0.0093 |
| 5 (live browser verification) | OpenAI gpt-4o-mini | 2 | $0.000765 |
| **Total to date** | | **~22** | **~$0.0101** |

**Remaining budget**: $9.99 of $10.00 monthly limit.

**Projected remaining spend (Phase 6)**:
- Phase 6 evaluation (25 queries × 3 modes × ~1–2 runs): ~$0.05–0.08
- **Total project estimate remains under $0.20** — well within the $10.00 budget.

### 11.2 Resource Usage

| Activity | Time |
|----------|------|
| Phase 5 implementation (`ui/app.py` + tests) | ~1 session |
| Ephemeral Playwright/Chromium install (verification tooling, not a project dependency) | ~2 minutes, one-time |
| Manual browser verification (load, sidebar check, 2 live queries, bug repro, fix, re-verify) | ~10 minutes |
| Full test suite (99 tests) | 45.11s |

---

## 12. Next Steps

### 12.1 Completed in This Version (v0.5)
- [x] `ui/app.py`: Streamlit chat interface over the Phase 4 Orchestrator
- [x] Routing transparency displayed to the user (routed_to / routing_reason / confidence)
- [x] Source citation display
- [x] Cost tracker display (running spend vs. $10 budget)
- [x] Graceful error handling at the UI boundary (closes Phase 4 self-review Deferred item 2)
- [x] `tests/test_ui.py`: 4 new tests (99 total, all passing)
- [x] Manual browser verification with real screenshots (not just imported and smoke-tested)
- [x] Found and fixed a real rendering bug (dollar-sign LaTeX mangling) during that verification

### 12.2 Planned for Next Version (v0.6 — Phase 6: Evaluation)
- [ ] Score the 25-query set (`prompts/risk_prompts.py`) against the manual rubric + LLM-as-judge, per the Phase 3 evaluation methodology
- [ ] **Routing-labelled evaluation queries** (deferred from the Phase 4 self-review): add an `expected_agent` field so RQ3 has systematic quantitative evidence beyond the Q017 anecdote
- [ ] RAG+ vs. RAG vs. LLM-only comparative scoring (extending the Phase 3 comparative test to all three agents)
- [ ] Finalise the `main`/`master` branch question (Known Issue since v0.4) before the final release tag

### 12.3 Known Issues / Limitations

| Issue | Severity | Status |
|-------|----------|--------|
| `Orchestrator.history` is shared across browser sessions if the app is ever multi-user deployed | Low | Documented as Decision 16; chat display state already lives in `st.session_state`, so this only affects the routing-audit log, not the user-facing chat |
| No persisted chat history across app restarts | Low | Acceptable for a local single-user demo tool; `st.session_state` resets on server restart |
| No authentication on the Streamlit app | Low | Not needed for local single-user use; noted in the earlier extensibility discussion as an additive change if ever needed |
| No `main` branch exists in this repository (only `master`, untouched since initial setup) | Low | Still deferred to the final Phase 6 release-branch decision |
| No routing-labelled evaluation set for RQ3 | Medium | Planned for Phase 6 — see Section 12.2 |

---

## 13. Appendices

### Appendix A: Glossary

*(Extended from v0.4.1.)*

| Term | Definition |
|------|------------|
| `st.cache_resource` | Streamlit decorator that builds an object once per server process and reuses it across reruns/sessions — used here so the Orchestrator's ChromaDB/embedding connections aren't rebuilt on every query |
| `st.session_state` | Streamlit's per-browser-session storage, used here for the chat display log (distinct from `Orchestrator.history`, see Decision 16) |
| Routing transparency | Displaying `routed_to`/`routing_reason`/`confidence` directly to the user, rather than only logging them |

### Appendix B: File Reference

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `ui/app.py` | Streamlit chat interface | `main()`, `get_orchestrator()`, `render_sidebar()`, `render_message()`, `_escape_markdown_dollars()` |
| `tests/test_ui.py` | UI helper unit tests | 4 tests for `_escape_markdown_dollars()` |

*(All v0.2–v0.4.1 file references remain valid — see those documents.)*

### Appendix C: Configuration Reference

*(Unchanged from v0.4.1 — no `.env` changes in Phase 5.)*

### Appendix D: Useful Commands

```bash
# Run the UI
env_dissertation/bin/streamlit run ui/app.py
# Opens http://localhost:8501

# Run all unit tests (99 total, zero cost)
env_dissertation/bin/python3 -m pytest tests/ -v

# Check cost log
cat data/cost_logs/api_costs.csv
```
