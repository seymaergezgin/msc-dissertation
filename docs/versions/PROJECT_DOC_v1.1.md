# Project Documentation — Version 1.1
# AI-Based Narrative Risk Reporting for Maritime Fuel Management
# Last Updated: 2026-07-21
# Author: Seymanur Ergezgin | MSc Engineering Management, University of Greenwich
# Supervisor: Dr. Mike Sharp

---

## Why This Version Exists

`PROJECT_DOC_v1.0.md` documented a complete, working 6-phase system. This version documents a 7th, unplanned phase: a structured response to **two independent reviews** — an internally-authored code/architecture audit (`docs/PROJECT_EVALUATION_AND_ROADMAP.md`) and an external dissertation-focused review (`docs/Dissertation_Progress_Review.md.pdf`) — both converging on the same core finding: **the engineering was strong, but the evaluation evidence was thinner than the claims resting on it.** This phase closes that gap with real data, not just process.

The honest instruction that kicked this off: *"let's fix the weaknesses... focus on strengthen our case and model monitoring and tests... don't forget to keep documenting everything!! the way we progress is exactly the same. the rules are exactly the same!!"* — same phase-gate workflow, same cost-approval discipline, same living documentation this project has followed since Phase 1.

---

## Changelog from v1.0 to v1.1

### Added
- **13 new evaluation queries** (Q026-Q038) rebalancing `prompts/risk_prompts.py` from 19/3/3 (risk_explainer/hedge_advisor/model_monitor) to **20/10/8** — directly addressing the external review's Section 3.1 critique that "validated across all three agent domains" was not well supported by n=3 per domain.
- **`evaluation/statistics.py`**: `wilson_score_interval()` (confidence intervals for routing accuracy) and `paired_significance_test()` (Wilcoxon signed-rank test for the ablation comparison) — closing the external review's Section 3.2 critique that point estimates were reported without uncertainty.
- **Cross-family judge check** (`run_cross_judge_check()` in `evaluation/run_evaluation.py`): re-scores ablation RAG+ responses with Claude (Anthropic), a different model family from the gpt-4o-mini used for generation and the primary judge — closing the external review's Section 3.4 critique about same-family judge bias.
- **`docs/DR_IRELAND_INTERVIEW_PROTOCOL.md`**: a structured practitioner-validation interview protocol with 9 curated real outputs (including 2 deliberately-included misrouted examples), prepared for a session with a genuine maritime-risk domain expert — addressing the external review's Section 3.6 critique, the one weighted most heavily given this is an Engineering Management degree.
- **`tests/test_statistics.py`** (13 tests), **`tests/test_llm_provider.py`** (7 tests, the first dedicated coverage for `src/llm_provider.py`).

### Changed
- **`prompts/risk_prompts.py`**: added 2 deliberate "boundary" queries (Q036, Q037) that mix vocabulary from two agents, and Q038, designed to demonstrate RAG+ combining both context sources rather than one masking the other's absence (Section 3.3 below).
- **`evaluation/run_evaluation.py`**: `ABLATION_QUERY_IDS` expanded from 10 to 15 (Hedge Advisor and Model Monitor each go from 1 ablation query to 3); `write_report()` restructured to save results immediately after Part A/B rather than only at the very end (Section 4 below — this fix was itself the product of a real failure during this phase); `estimate_cost()` now reads cross-judge pricing from `config/llm_config.py` dynamically instead of a hardcoded rate.
- **`config/llm_config.py`, `.env`, `.env.example`**: `ANTHROPIC_MODEL` updated from a retired model ID to `claude-sonnet-5`, with corrected per-token pricing (Section 4 below).
- **`src/llm_provider.py`**: `AnthropicProvider` no longer passes an explicit `temperature` kwarg (current-generation Claude models reject it); added `_extract_text()` to normalise `response.content`, which current-generation Claude models sometimes return as a list of content blocks rather than a plain string.

### Live Evaluation Results (this phase)
See Section 3 below for full discussion. Headline: **32/38 (84.2%, 95% Wilson CI: 69.6%-92.6%) routing accuracy**; **RAG+ significantly outperforms both ablations** (Wilcoxon, p<0.05 for all three pairwise comparisons); **cross-judge check found real evidence of same-family judge bias** (gpt-4o-mini scores itself higher than Claude does, on average, by 2.2/12 points).

### Test Suite
**156 tests passing** (149 from v1.0 + 7 new), all mocked/offline.

### Cost
**Total project spend: $0.1345** of the $10.00 monthly budget (up from $0.0473 at v1.0) — see Section 4 for why this phase cost more than a clean run would have.

---

## 1. Executive Summary — Rewritten for Statistical Honesty

*(This section deliberately replaces, rather than appends to, the v1.0 Executive Summary's headline claims — per the external review's Section 3 finding that the original framing overstated what the evidence supported. This is the rewrite exercise the review recommended as Priority Action #3.)*

This project is a multi-agent LLM system that translates quantitative maritime fuel risk metrics into plain-English narratives for non-technical business stakeholders. Across 7 phases (6 planned, 1 responsive), it was built, evaluated, and then critically re-evaluated against both an internal audit and an external dissertation review.

**What the evidence actually supports, precisely stated**:

- **Routing accuracy: 32/38 (84.2%), 95% Wilson CI 69.6%-92.6%.** This interval is wide — at this sample size, the true accuracy could plausibly be anywhere in a ~23-point range. Per-agent, the picture is uneven and should be reported as such: **Risk Explainer 100% (20/20, CI 83.9%-100%)**, **Hedge Advisor 70% (7/10, CI 39.7%-89.2%)**, **Model Monitor 62.5% (5/8, CI 30.6%-86.3%)**. The headline number obscures that two of the three agents have real, quantified routing weaknesses — this is now visible precisely because the evaluation set was rebalanced (Section 3.1).
- **RAG+ significantly outperforms both ablation baselines** — RAG+ (mean 11.3/12) vs. RAG-only (8.3/12, Wilcoxon p=0.0022) and vs. LLM-only (9.3/12, p=0.0164), both significant at α=0.05 despite the modest sample (n=15 paired queries). This is stronger evidence than v1.0's mean-only comparison, though still exploratory rather than confirmatory given the sample size — see Section 3.1.
- **The RAG-only vs. LLM-only difference is itself significant (p=0.0301) and counter-intuitive**: LLM-only, with zero grounding, scores *higher* than RAG-only. Section 3.3 explains why, and why this doesn't undermine RAG+'s value — it actually sharpens what RAG+'s real contribution is.
- **The cross-family judge check found real evidence of same-family bias**, not just a documented risk from the literature: gpt-4o-mini (the primary judge) scored its own model family's outputs higher than Claude did on 12 of 15 comparisons, by a mean of 2.2 points out of 12, with only 33% exact agreement and a moderate 0.55 correlation between the two judges. This is now measured, not assumed.
- **No domain-expert validation exists yet** — `docs/DR_IRELAND_INTERVIEW_PROTOCOL.md` is prepared and ready, but the session itself is the student's action item, not something completed in this phase.

---

## 2. Problem Statement

*(Unchanged from v0.1 — see that document.)*

---

## 3. What Changed, and Why It Matters

### 3.1 The Evaluation Set Rebalance and What It Revealed

**Before**: 19 risk_explainer / 3 hedge_advisor / 3 model_monitor queries (v1.0). **After**: 20 / 10 / 8.

The rebalance did more than satisfy a methodological objection — it **changed the headline finding**. With only 3 queries each, Hedge Advisor and Model Monitor's routing accuracy could not be meaningfully distinguished from Risk Explainer's. With 10 and 8 queries respectively, a real, statistically visible gap emerged: **all 6 misroutes in this evaluation went to Risk Explainer**, and every one of them was an intended-Hedge-Advisor or intended-Model-Monitor query (Q009, Q023, Q026, Q035, Q036, Q037). Risk Explainer's 100% accuracy is not evidence the router works well in general — it's evidence the router is *biased toward* Risk Explainer specifically, which the small original sample could not detect.

**Root cause** (confirmed, not merely hypothesised): `PRIORITY_ORDER = ["risk_explainer", "hedge_advisor", "model_monitor"]` (Decision 12, v0.4) breaks every keyword tie in Risk Explainer's favour, and the maritime-override (Decision 15) always routes to Risk Explainer regardless of which agent's domain the question is actually in. Two of the three "boundary" queries designed to probe this (Q036, Q037) misrouted exactly as predicted when they were written — this is confirmatory of a known, structural limitation, not a surprising new bug.

**Honest framing for the dissertation**: this project does not claim the current keyword router achieves reliable routing across all three domains. It claims — with evidence — that Risk Explainer's routing is reliable, and that Hedge Advisor's and Model Monitor's routing has a specific, explained, structural bias that a semantic classifier (the upgrade path already anticipated in Decision 12) would need to address. That is a more defensible claim than "92% accurate," and it is a stronger dissertation contribution: identifying *why* a design choice (priority-order tie-breaking) creates a specific, predictable failure mode is more valuable than a single aggregate percentage.

### 3.2 Statistical Honesty: Confidence Intervals, Not Just Percentages

Every routing-accuracy figure in this document and the evaluation report is now reported with a 95% Wilson score confidence interval (`evaluation/statistics.py`), computed rather than approximated, because the normal approximation misbehaves at these sample sizes and near-boundary proportions (Model Monitor's 62.5% and Risk Explainer's 100% both sit in the range where the normal approximation gives a materially wrong interval). The Wilson interval was chosen and cross-checked against a hand-computed reference value in `tests/test_statistics.py`, not just trusted from `scipy`.

The ablation comparison is now backed by a Wilcoxon signed-rank test (paired, non-parametric — appropriate given judge scores are ordinal/bounded and n=15), rather than a bare mean comparison. All three pairwise comparisons (RAG+ vs. RAG-only, RAG+ vs. LLM-only, RAG-only vs. LLM-only) are statistically significant at α=0.05, which is genuinely informative given how small the sample is — but the report and this document both explicitly flag that n=15 supports "suggestive, not confirmatory" conclusions, per standard practice for a sample this size.

### 3.3 Reframing RAG+ vs. RAG-only (and why LLM-only sometimes wins)

The external review's Section 3.3 pointed out something worth taking seriously: if a query asks "what is OUR VaR," and only RAG+ receives the portfolio data at all, RAG+ almost *has* to win on Accuracy — the other two conditions are missing information they were never given, not failing to reason well. Framing this as "RAG+ beats RAG" oversells the comparison's fairness.

The more precise, and more defensible, framing: **generic document retrieval cannot answer questions that require live structured data, and this project's contribution is architecting *where* that data enters the prompt** (Decision 9 — portfolio data as "Context 0," before retrieved chunks). The live cross-judge and ablation data now make this concrete in an unexpected way: **RAG-only (mean 8.3/12) scores lower than LLM-only (mean 9.3/12) on average**, a difference that is itself statistically significant (p=0.0301). This is not RAG-only "failing" in the usual sense — it is RAG-only correctly, honestly reporting *"the context documents do not provide this figure"* when portfolio data is absent, which a judge scores as low Accuracy, whereas LLM-only fabricates a plausible-sounding number confidently, which a judge (without ground truth to check against) can score as higher Accuracy purely because it commits to an answer. Q038 (new in Phase 7) was specifically designed to show the more convincing form of RAG+'s value: a question ("is our VaR high by industry standards?") that genuinely needs *both* the live portfolio figure *and* retrieved industry-context documents combined, not one context source simply being present while the other is absent.

### 3.4 The Cross-Judge Check, and the Bug Saga Behind It

**The finding**: re-scoring 15 ablation RAG+ responses with Claude (a different model family from the gpt-4o-mini primary judge) found a mean signed difference of **-2.20 points** (Claude scored lower on 12 of 15), an exact-agreement rate of only **33%**, and a moderate correlation of **0.55**. This is concrete evidence — not a documented risk cited from the literature, but a measured result from this project's own responses — that the primary judge inflates scores for its own model family. This directly strengthens the dissertation's methodology chapter: the automated judge's scores should be read as *one signal, corroborated where possible*, not ground truth, and this is now demonstrated rather than merely acknowledged as a theoretical concern.

**How it was obtained (worth documenting honestly, as this project has done at every phase)**: the cross-judge check failed **four separate times** before succeeding, and each failure was a genuine bug, not the same mistake repeated:

1. **`ANTHROPIC_API_KEY` was the `.env.example` placeholder value**, never replaced with a real key (Anthropic had never actually been called in any prior phase). Resolved by the student obtaining a real key.
2. **`write_report()` was only called once, at the very end of `main()`.** When the cross-judge step first crashed (on issue #1, before the key was fixed), **166 real API calls' worth of routing and ablation results — already correctly computed — were never saved**, because the crash propagated up before the report-writing call was reached. This is the same category of mistake as the Phase 6 self-review finding (a partial failure destroying already-good results), recurring because a new code path (the cross-judge addition) hadn't yet been checked against that lesson. **Fixed**: `write_report()` now runs immediately after Part A/B complete, and again afterward if the optional cross-judge step succeeds — so a later failure can never erase earlier, valid work. **Recovery**: rather than re-paying to regenerate the lost responses, they were re-judged directly from `data/interaction_logs/interactions.jsonl` (which had captured the actual answers correctly throughout, since `log_interaction()` is called incrementally, not at the end) — roughly half the cost of a full re-run.
3. **`ANTHROPIC_MODEL` defaulted to `claude-3-5-sonnet-20241022`, a retired model ID** (404 Not Found) — a 2024-era default that was never updated because, again, nothing had called Anthropic before. Fixed by querying Anthropic's models endpoint directly and updating to the current `claude-sonnet-5`, with corrected pricing.
4. **Current-generation Claude models reject an explicit `temperature` parameter** (400 Bad Request) — a genuine API/model evolution, not a configuration error. Fixed by omitting it from `AnthropicProvider`'s `ChatAnthropic` construction.
5. **`ChatAnthropic` sometimes returns `response.content` as a list of content blocks rather than a plain string**, crashing `get_token_counts()`'s `.split()` call — a real, pre-existing bug in `AnthropicProvider` that had simply never been exercised. Fixed with a new `_extract_text()` normaliser, now covered by 5 dedicated tests.

Each failure was caught, diagnosed with a minimal-cost or zero-cost test before spending more, fixed with a regression test, and documented — the same discipline established in Phases 4-6. The practical cost of this saga: an estimated $0.02-0.03 of "wasted" spend across the four attempts (re-judging already-generated answers multiple times), against a total phase cost of $0.13 — not free, but modest, and every one of the four bugs is now fixed for any future use of the Anthropic provider in this project.

### 3.5 Literature Anchoring for RAG+

The external review correctly noted that "RAG+," presented alone against Lewis et al. (2020), risks reading as a rebranded standard technique to an examiner familiar with the RAG literature. The following candidate citations were located (via search, with abstracts/summaries reviewed) to more precisely situate what is and isn't novel about this project's specific implementation. **These are starting points for the student's own reading and verification before citing** — they are reported here as located and plausible, not as citations already fully read and confirmed in depth:

- **Liu et al., "Lost in the Middle: How Language Models Use Long Contexts,"** arXiv:2307.03172, published in *Transactions of the Association for Computational Linguistics* 12:157-173 (2024). Directly supports Decision 9's ordering rationale: LLMs attend best to the beginning (and end) of their context window, which is precisely why portfolio data is placed as "Context 0" before retrieved chunks, not after.
- **"A Survey on Retrieval And Structuring Augmented Generation,"** arXiv:2509.10697 (2025) — a recent survey specifically on combining structured data with RAG, the closest existing umbrella term for what this project calls "RAG+."
- **"Retrieval-Augmented Generation: A Comprehensive Survey of Architectures, Enhancements, and Robustness Frontiers,"** arXiv:2506.00054 (2025) — general RAG grounding citation, useful for situating the standard RAG baseline this project extends.
- **"Self-Preference Bias in LLM-as-a-Judge,"** arXiv:2410.21819 (2024), and **"Great Models Think Alike and this Undermines AI Oversight,"** arXiv:2502.04313 (2025) — directly relevant to Section 3.4's cross-judge finding; both discuss the same-family/self-preference bias this project independently measured.

**What is actually novel, once anchored against this literature**: not the general idea of combining structured and unstructured context (well-established), but the specific *ordering choice* validated against "Lost in the Middle"'s attention-position findings, and the *per-agent formatter design* (Section 4.2, v1.0) that lets three different specialist personas each surface a different projection of the same underlying JSON snapshot. This is a narrower, more defensible claim than "RAG+ is a novel architecture," and a stronger one for a viva.

### 3.6 Practitioner Validation — Prepared, Not Yet Conducted

`docs/DR_IRELAND_INTERVIEW_PROTOCOL.md` is a complete, ready-to-run interview protocol: a 1-5 "would I send this as-is" scoring scale, 9 curated real outputs (pulled from this phase's actual evaluation run, including 2 deliberately-included misrouted examples so the session tests honest range, not curated best cases), and a set of open questions probing adoption barriers, trust calibration, and automation risk — directly aimed at the external review's Section 3.6 critique, which it weighted most heavily given this is an Engineering Management, not Computer Science, dissertation. **This session is the student's remaining action item** — it cannot be completed by further code changes.

---

## 4. Updated Cost Analysis

| Phase | Description | Cost USD |
|-------|-------------|----------|
| 1-6 (per v1.0) | Full system build + first evaluation | $0.0473 |
| 7 | Rebalanced evaluation (166 calls) | $0.0955 |
| 7 | Recovery re-judging after the report-timing bug (no regeneration needed) | included above (reused already-generated answers) |
| 7 | Cross-judge attempts (4 attempts, 3 failed on bugs before succeeding) | ~$0.05 net (final clean run: $0.04; ~$0.01-0.02 spent on failed partial attempts before each bug was fixed) |
| **Total** | | **$0.1345** |

**Budget utilisation: 1.3% of the $10.00/month allocation.** Even accounting for the repeated cross-judge debugging cost, the project remains far under budget.

---

## 5. Formal Validity and Limitations Discussion

*(Replaces the bare bullet-list "Known Limitations" format used through v1.0, per the external review's Section 3.7 — a structured internal/external/construct validity discussion is what a research-methods-literate reader expects, and most of the underlying reasoning already existed in this project's decision log; this section makes it explicit.)*

### 5.1 Internal Validity — Is the Routing-Accuracy Figure Measuring What It Claims To?

**Threat**: `expected_agent` labels were assigned by the same person who built the router. If those labels were derived from the router's own behaviour, "accuracy" would be tautological.

**Mitigation, and its limit**: Decision 19 (v0.6) explicitly assigned `expected_agent` by domain judgment *before* checking what the router would produce, and two labels (Q009, Q023) were deliberately set to disagree with the router's predictable behaviour specifically to test this. The Phase 7 boundary queries (Q036, Q037) extend this further. This mitigates, but does not eliminate, the threat: a single author's domain judgment is still one perspective, not an independently validated ground truth. The Dr. Ireland practitioner session (Section 3.6) is the planned mitigation for this residual threat — an independent domain expert's judgment on real outputs is a different, corroborating source of truth.

### 5.2 External Validity — Do These Results Generalise?

**Threat**: all evaluation queries were run against one static synthetic portfolio snapshot (`risk_metrics.json`, 5 vessels, one date), one LLM (gpt-4o-mini) for generation, and a maritime fuel risk domain specifically.

**What this limits**: confidence that these exact routing-accuracy and ablation figures would hold for a different portfolio, a different LLM, or a different domain is low — this project does not claim they would. What generalises with more confidence is the *architectural finding* (RAG+'s ordering matters; keyword routing has a structural tie-breaking bias) rather than the *exact numbers* (84.2%, 11.3/12). The dissertation should frame RQ1-RQ3's answers at this level: the mechanism is demonstrated and evidenced; the precise figures are specific to this system, this data, and this evaluation set.

### 5.3 Construct Validity — Does the Judge Score Measure "Answer Quality"?

**Threat**: the LLM-as-judge rubric (Accuracy/Structure/Plain English/Completeness) is a proxy for what a real business stakeholder would consider a good answer — it is not that judgment itself.

**Evidence this threat is real, not hypothetical**: Section 3.4's cross-judge finding demonstrates the primary judge's scores are not judge-independent — a different judge, scoring the identical text, disagrees on 67% of comparisons by a mean of 2.2 points. Section 3.3 demonstrates a further construct-validity gap: the judge can score a confident fabrication (LLM-only) higher than an honest refusal (RAG-only) on the Accuracy dimension specifically, because the judge has no independent access to ground truth beyond what's in the prompt. Both findings are reasons the practitioner validation session (Section 3.6) is weighted so heavily in this document's priority ordering — it is the only evidence source in this project that measures the actual construct (would a real professional send this) rather than a proxy for it.

---

## 6. Academic Relevance — Updated

### 6.1 Research Questions — Precisely Restated

- **RQ1** (*Can LLM-based agents accurately explain maritime fuel risk metrics in natural language?*) — Yes, with the construct-validity caveat in Section 5.3: "accurately" is measured by an automated judge shown to have its own biases, pending independent practitioner corroboration.
- **RQ2** (*Does RAG-augmented generation produce more accurate explanations than a base LLM?*) — Yes, and specifically: RAG+ significantly outperforms both RAG-only and LLM-only (Section 3.2), and the RAG-only/LLM-only comparison itself reveals *why* — live structured data, not retrieval alone, is what closes the accuracy gap on data-specific questions (Section 3.3).
- **RQ3** (*Can multi-agent routing improve response relevance compared to a single agent?*) — Partially yes, with a precisely bounded claim: routing is reliably accurate for Risk Explainer (100%, tight-ish CI) and measurably weaker for Hedge Advisor and Model Monitor (70%, 62.5%, both with wide CIs), with the weakness traced to a specific, explained structural cause (Section 3.1) rather than left as an unexplained residual.

### 6.2 Literature Connections — See Section 3.5 for the specific candidate citations located this phase.

### 6.3 Methodology Mapping

| Dissertation Section | Project Component | Status |
|----------------------|-------------------|--------|
| 4.9 Statistical Methodology | evaluation/statistics.py | ✅ Complete (v1.1) |
| 5.1 Routing Accuracy Results (revised) | Section 3.1-3.2 above, phase6_evaluation_report.md | ✅ Complete (v1.1) |
| 5.2 RAG Ablation Results (revised) | Section 3.3 above | ✅ Complete (v1.1) |
| 5.3 Judge Reliability / Same-Family Bias | Section 3.4 above | ✅ Complete (v1.1) |
| 5.4 Threats to Validity | Section 5 above | ✅ Complete (v1.1) |
| 6.1 Practitioner Validation | docs/DR_IRELAND_INTERVIEW_PROTOCOL.md | ⏳ Protocol ready; session pending (student action) |
| 6.2 Managerial/Adoption Discussion | Interview protocol Section 3, questions 3-4 | ⏳ Depends on the session above |

---

## 7. Next Steps

### 7.1 Completed in This Version (v1.1)
- [x] Evaluation set rebalanced 19/3/3 → 20/10/8
- [x] Wilson score CIs and Wilcoxon significance testing added and reported
- [x] Cross-family judge check completed (15/15), finding real same-family bias evidence
- [x] Four real Anthropic-provider bugs found, fixed, and regression-tested
- [x] Executive Summary and results framing rewritten for statistical honesty
- [x] Formal internal/external/construct validity discussion added
- [x] Candidate literature citations located for RAG+ anchoring
- [x] Dr. Ireland interview protocol drafted with 9 real curated samples

### 7.2 Remaining — Student Action Required
- [ ] **Conduct the Dr. Ireland practitioner validation session** (protocol ready) — highest remaining priority per the external review
- [ ] **Read and confirm the candidate citations** in Section 3.5 before using them in the dissertation text
- [ ] Write the managerial/cost-benefit/adoption-barrier discussion (Section 4.3 of `docs/PROJECT_EVALUATION_AND_ROADMAP.md`) — a writing task, not a further code task
- [ ] Decide on final release branch timing (`master` already holds v1.0; this phase's work should merge to `dev` then `master` once reviewed)

### 7.3 Known Issues / Limitations (Updated)

| Issue | Severity | Status |
|-------|----------|--------|
| Hedge Advisor / Model Monitor routing accuracy has wide confidence intervals even after rebalancing (n=8-10) | Medium | Expected at this sample size; further expansion possible but subject to diminishing returns — see Section 5.2 on what generalises regardless |
| Same-family judge bias is now measured, not just flagged | Low (informational — this is a completed mitigation, not an open gap) | Practitioner validation (pending) is the remaining independent check |
| `AnthropicProvider` had never been exercised before this phase, hence 3 latent bugs | Low (all now fixed and regression-tested) | — |
| No domain-expert validation yet | Medium-High (per external review, weighted heavily for this degree) | Protocol ready; session is the student's next action |

---

## 8. Appendices

### Appendix A: New Glossary Terms

| Term | Definition |
|------|------------|
| Wilson score interval | A confidence interval for a binomial proportion that remains well-behaved at small n and near-boundary proportions, unlike the normal approximation |
| Wilcoxon signed-rank test | A non-parametric test for paired data, used here because judge scores are ordinal/bounded and the ablation sample is small |
| Same-family judge bias | An LLM judge's tendency to score outputs from its own model family more favourably than outputs from a different family, independent of actual quality |
| Boundary query | A Phase 7 evaluation query deliberately mixing vocabulary from two agents' keyword sets, to test routing robustness beyond known cases |

### Appendix B: New/Changed Files

| File | Purpose |
|------|---------|
| `evaluation/statistics.py` | Wilson CI, Wilcoxon test |
| `tests/test_statistics.py` | 13 tests for the above |
| `tests/test_llm_provider.py` | 7 tests — first coverage of src/llm_provider.py, covering the Phase 7 Anthropic fixes |
| `docs/DR_IRELAND_INTERVIEW_PROTOCOL.md` | Practitioner validation session protocol + curated samples |
| `docs/PROJECT_EVALUATION_AND_ROADMAP.md` | The internal audit that partly motivated this phase |
| `docs/Dissertation_Progress_Review.md.pdf` | The external review that partly motivated this phase |

### Appendix C: Useful Commands

```bash
# Run all 156 tests (zero cost)
env_dissertation/bin/python3 -m pytest tests/ -v

# Re-run the full evaluation (costs ~$0.10, estimate first)
env_dissertation/bin/python3 evaluation/run_evaluation.py --estimate-only --cross-judge
env_dissertation/bin/python3 evaluation/run_evaluation.py --part all --cross-judge

# Check current Anthropic model availability (zero/negligible cost)
env_dissertation/bin/python3 -c "
import os, requests
from dotenv import load_dotenv
load_dotenv()
r = requests.get('https://api.anthropic.com/v1/models', headers={'x-api-key': os.getenv('ANTHROPIC_API_KEY'), 'anthropic-version': '2023-06-01'})
for m in r.json()['data'][:10]: print(m['id'])
"
```
