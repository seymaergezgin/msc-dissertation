"""
Evaluation query set for the maritime risk narrative system.

These 38 queries form the canonical test set used in two ways:
  1. During development: iteratively test and improve the agents' responses
  2. In Phase 6/7 evaluation: score agent + routing performance against a rubric

Query categories:
  - factual:         Questions with specific numeric answers from the portfolio
  - conceptual:      Questions asking for a definition or explanation of a metric
  - comparative:     Questions comparing vessels or metrics
  - hedging:         Questions about hedge positions and strategy
  - maritime_context: Questions requiring regulatory / domain knowledge
  - actionable:      Questions asking for a recommendation
  - scenario:        What-if questions based on the stress-test scenarios
  - methodology:     Questions about how VaR is calculated
  - boundary:        (Phase 7) Deliberately mixes vocabulary from two agents,
                      to probe whether routing generalises beyond the two
                      known cases Decision 15 was built to fix

Difficulty levels:
  - easy:   Answer is a direct lookup from portfolio_summary
  - medium: Requires reasoning across multiple vessels or concepts
  - hard:   Requires combining portfolio data, domain knowledge, and judgment

Phase 6 addition — expected_agent:
  This set was written in Phase 3, before the Hedge Advisor and Model
  Monitor agents existed, so every query originally targeted the Risk
  Explainer by construction. Phase 6 adds an "expected_agent" field to
  each query so the Orchestrator's routing decisions can be scored
  against a real answer, not just re-derived from the router's own
  keyword logic (which would make "accuracy" tautological).

  expected_agent reflects domain judgment — which agent's expertise is
  the right one to answer this question well — independent of whether
  the current keyword classifier actually gets there. Two borderline
  cases worth flagging explicitly:
    - Q009 ("why do we use a 10-day time horizon") is a methodology-
      justification question -> expected_agent = model_monitor, even
      though its only strong keyword match is "var" (which would
      currently route it to risk_explainer). This is a genuine,
      intentional test of the router's limits, not an error.
    - Q010 ("what does 40.2% annualised volatility tell us about risk")
      is framed as a business-interpretation question, not a methodology
      question -> expected_agent = risk_explainer, despite touching the
      same volatility figure as Q009.

Phase 7 addition — Q026-Q038, rebalancing and boundary probes:
  An external dissertation review correctly identified that the original
  19/3/3 split (Risk Explainer / Hedge Advisor / Model Monitor) was too
  imbalanced to support a claim of validation "across all three agent
  domains" — n=3 per domain has enormous sampling uncertainty. Q026-Q035
  add 5 more Hedge Advisor and 5 more Model Monitor queries, bringing the
  split to 20/10/8 (Section 3.1, PROJECT_DOC_v1.1.md).

  Q036-Q037 are deliberate boundary probes: Q037 in particular mixes
  strong maritime keywords (HSFO, IMO 2020) with a fundamentally
  hedging-focused question, and is labelled expected_agent="hedge_advisor"
  — NOT because the current router is expected to get it right (Decision
  15's strong-maritime-keyword-always-wins rule will in fact route it to
  Risk Explainer with the maritime override), but because this is exactly
  the kind of undiscovered edge case worth surfacing honestly rather than
  hiding. A "failure" on Q037 is a finding, not a bug — see
  PROJECT_DOC_v1.1.md Section 3.2 for the discussion.

  Q038 is designed to demonstrate RAG+'s value more convincingly than the
  original Q001-style examples: it needs BOTH the live portfolio VaR
  figure AND retrieved industry-context documents to answer well, rather
  than one context source simply being present or absent (see
  PROJECT_DOC_v1.1.md Section 3.3 for why this distinction matters).
"""

from typing import Optional, TypedDict


class EvaluationQuery(TypedDict):
    id: str
    query: str
    category: str
    expected_elements: list[str]
    expected_agent: str
    difficulty: str


RISK_EVALUATION_QUERIES: list[EvaluationQuery] = [

    # ----------------------------------------------------------------
    # FACTUAL — direct lookups from the portfolio snapshot
    # ----------------------------------------------------------------
    {
        "id": "Q001",
        "query": "What is our current portfolio VaR at 95% confidence?",
        "category": "factual",
        "expected_elements": ["$376,329", "95%", "10-day", "5% chance"],
        "expected_agent": "risk_explainer",
        "difficulty": "easy",
    },
    {
        "id": "Q002",
        "query": "What is the CVaR (Expected Shortfall) for our total fleet?",
        "category": "factual",
        "expected_elements": ["$481,701", "95%", "worst 5%", "average loss"],
        "expected_agent": "risk_explainer",
        "difficulty": "easy",
    },
    {
        "id": "Q003",
        "query": "What is our current VLSFO price per metric ton?",
        "category": "factual",
        "expected_elements": ["$470.73", "VLSFO", "per metric ton"],
        "expected_agent": "risk_explainer",
        "difficulty": "easy",
    },
    {
        "id": "Q004",
        "query": "What is the total annual fuel cost for our fleet?",
        "category": "factual",
        "expected_elements": ["$34,298,985", "annual", "5 vessels"],
        "expected_agent": "risk_explainer",
        "difficulty": "easy",
    },
    {
        "id": "Q005",
        "query": "What is the VaR at 99% confidence for our portfolio?",
        "category": "factual",
        "expected_elements": ["$532,125", "99%", "10 trading days"],
        "expected_agent": "risk_explainer",
        "difficulty": "easy",
    },

    # ----------------------------------------------------------------
    # CONCEPTUAL — explain what a metric means
    # ----------------------------------------------------------------
    {
        "id": "Q006",
        "query": "Explain what Value at Risk means for a maritime shipping company in plain English.",
        "category": "conceptual",
        "expected_elements": ["maximum", "confidence level", "10-day", "5%"],
        "expected_agent": "risk_explainer",
        "difficulty": "medium",
    },
    {
        "id": "Q007",
        "query": "What is the difference between VaR and CVaR, and which one should management focus on?",
        "category": "conceptual",
        "expected_elements": ["VaR", "CVaR", "Expected Shortfall", "tail risk", "beyond the threshold"],
        "expected_agent": "risk_explainer",
        "difficulty": "medium",
    },
    {
        "id": "Q008",
        "query": "What does our daily fuel price volatility of 2.53% mean in practical business terms?",
        "category": "conceptual",
        "expected_elements": ["2.53%", "daily price change", "fuel cost impact", "uncertainty"],
        "expected_agent": "risk_explainer",
        "difficulty": "medium",
    },
    {
        "id": "Q009",
        "query": "Why do we use a 10-day time horizon for our VaR calculation?",
        "category": "conceptual",
        "expected_elements": ["time horizon", "liquidity", "rebalancing", "hedging"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },
    {
        "id": "Q010",
        "query": "What does an annualised volatility of 40.2% tell us about our fuel cost risk over the next year?",
        "category": "conceptual",
        "expected_elements": ["40.2%", "annual volatility", "annual fuel cost", "range of outcomes"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },

    # ----------------------------------------------------------------
    # COMPARATIVE — across vessels or metrics
    # ----------------------------------------------------------------
    {
        "id": "Q011",
        "query": "Which vessel in our fleet carries the highest fuel price risk and why?",
        "category": "comparative",
        "expected_elements": ["MV Iron Maiden", "VLCC", "largest fuel cost", "lowest hedge ratio"],
        "expected_agent": "risk_explainer",
        "difficulty": "medium",
    },
    {
        "id": "Q012",
        "query": "How does MV Atlantic Pioneer's risk profile compare to MV Nordic Star?",
        "category": "comparative",
        "expected_elements": ["Atlantic Pioneer", "Nordic Star", "VaR", "fuel consumption", "hedge ratio"],
        "expected_agent": "risk_explainer",
        "difficulty": "medium",
    },
    {
        "id": "Q013",
        "query": "What is the 95% VaR for MV Pacific Eagle, and how does it compare to the fleet average?",
        "category": "comparative",
        "expected_elements": ["$26,857", "Pacific Eagle", "Handymax", "fleet", "compare"],
        "expected_agent": "risk_explainer",
        "difficulty": "medium",
    },

    # ----------------------------------------------------------------
    # HEDGING — hedge ratio and exposure analysis
    # ----------------------------------------------------------------
    {
        "id": "Q014",
        "query": "What is our average hedge ratio across the fleet and what does it mean for our risk exposure?",
        "category": "hedging",
        "expected_elements": ["48%", "hedge ratio", "hedged", "unhedged", "exposure"],
        "expected_agent": "hedge_advisor",
        "difficulty": "easy",
    },
    {
        "id": "Q015",
        "query": "Which vessel is most vulnerable to fuel price increases due to its low hedge ratio?",
        "category": "hedging",
        "expected_elements": ["MV Iron Maiden", "30%", "VLCC", "unhedged exposure", "most vulnerable"],
        "expected_agent": "hedge_advisor",
        "difficulty": "medium",
    },
    {
        "id": "Q016",
        "query": "How much of our total fuel expenditure is currently unhedged across the fleet?",
        "category": "hedging",
        "expected_elements": ["unhedged", "dollar amount", "percentage", "fleet total"],
        "expected_agent": "hedge_advisor",
        "difficulty": "medium",
    },

    # ----------------------------------------------------------------
    # MARITIME CONTEXT — regulatory and domain knowledge required
    # ----------------------------------------------------------------
    {
        "id": "Q017",
        "query": "Why does MV Iron Maiden use HSFO instead of VLSFO, and what are the cost implications?",
        "category": "maritime_context",
        "expected_elements": ["HSFO", "scrubber", "VLSFO", "sulphur", "IMO 2020", "cost difference"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },
    {
        "id": "Q018",
        "query": "How does the IMO 2020 sulphur cap affect our fleet's fuel risk profile?",
        "category": "maritime_context",
        "expected_elements": ["IMO 2020", "sulphur", "VLSFO", "compliance", "spread risk"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },

    # ----------------------------------------------------------------
    # ACTIONABLE — management decision support
    # ----------------------------------------------------------------
    {
        "id": "Q019",
        "query": "Is our current VaR level acceptable, or should the risk committee be concerned?",
        "category": "actionable",
        "expected_elements": ["376,329", "percentage", "risk appetite", "hedge"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },
    {
        "id": "Q020",
        "query": "Given our current risk metrics, what actions should the risk committee consider at their next meeting?",
        "category": "actionable",
        "expected_elements": ["hedge ratio", "Iron Maiden", "recommendation", "concrete action"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },

    # ----------------------------------------------------------------
    # SCENARIO — stress-test what-if analysis
    # ----------------------------------------------------------------
    {
        "id": "Q021",
        "query": "If VLSFO prices increase by 30% due to a geopolitical shock, what would happen to our annual fuel costs?",
        "category": "scenario",
        "expected_elements": ["30%", "VLSFO", "increased cost", "calculation or estimate"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },
    {
        "id": "Q022",
        "query": "Describe our geopolitical oil price shock scenario and explain its potential financial impact on the fleet.",
        "category": "scenario",
        "expected_elements": ["Brent", "30%", "geopolitical", "probability", "fleet impact"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },

    # ----------------------------------------------------------------
    # METHODOLOGY — how VaR is calculated
    # ----------------------------------------------------------------
    {
        "id": "Q023",
        "query": "Explain the variance-covariance method we use to calculate VaR in simple terms that a non-technical manager could understand.",
        "category": "methodology",
        "expected_elements": ["variance-covariance", "normal distribution", "volatility", "simple explanation"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },
    {
        "id": "Q024",
        "query": "What assumptions does our VaR model make, and under what conditions might those assumptions break down?",
        "category": "methodology",
        "expected_elements": ["normal distribution", "correlation", "historical window", "tail risk", "limitations"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },

    # ----------------------------------------------------------------
    # SUMMARY — board-level presentation
    # ----------------------------------------------------------------
    {
        "id": "Q025",
        "query": "Provide a concise summary of our overall fuel risk position suitable for presenting to the board of directors.",
        "category": "summary",
        "expected_elements": ["portfolio VaR", "CVaR", "hedge ratio", "key vessel", "plain English", "recommendation"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },

    # ----------------------------------------------------------------
    # Phase 7 addition (Q026-Q038): rebalances the evaluation set toward
    # Hedge Advisor and Model Monitor, which had only 3 queries each in the
    # original Phase 3-era set — an external dissertation review correctly
    # flagged that "validated across all three agent domains" was not well
    # supported by n=3 per domain. Also adds boundary-probing queries (does
    # the strong/weak maritime keyword split, Decision 15, generalise to
    # cases beyond the two it was built to fix?) and one query designed to
    # show RAG+ combining both context sources, not just one masking the
    # other's absence (see PROJECT_DOC_v1.1.md Section 3.3 reframing).
    # ----------------------------------------------------------------

    # --- Hedge Advisor rebalancing ---
    {
        "id": "Q026",
        "query": "Which hedging instruments would you recommend to reduce our unhedged HSFO exposure on MV Iron Maiden?",
        "category": "hedging",
        "expected_elements": ["MV Iron Maiden", "HSFO", "hedging instrument", "unhedged exposure"],
        "expected_agent": "hedge_advisor",
        "difficulty": "hard",
    },
    {
        "id": "Q027",
        "query": "If we increased our average hedge ratio from 48% to 70%, how would that change our unhedged dollar exposure?",
        "category": "hedging",
        "expected_elements": ["48%", "70%", "unhedged", "dollar"],
        "expected_agent": "hedge_advisor",
        "difficulty": "medium",
    },
    {
        "id": "Q028",
        "query": "How does our current hedge ratio compare to what a fully hedged position would look like, and what's the cost trade-off?",
        "category": "hedging",
        "expected_elements": ["48%", "fully hedged", "100%", "cost", "trade-off"],
        "expected_agent": "hedge_advisor",
        "difficulty": "medium",
    },
    {
        "id": "Q029",
        "query": "If Brent crude rises 15% over the next quarter, how does that change our hedge effectiveness?",
        "category": "scenario",
        "expected_elements": ["15%", "Brent", "hedge effectiveness", "quarter"],
        "expected_agent": "hedge_advisor",
        "difficulty": "hard",
    },
    {
        "id": "Q030",
        "query": "What's driving the difference between our hedged and unhedged fuel cost exposure right now?",
        "category": "hedging",
        "expected_elements": ["hedged", "unhedged", "exposure", "48%"],
        "expected_agent": "hedge_advisor",
        "difficulty": "medium",
    },

    # --- Model Monitor rebalancing ---
    {
        "id": "Q031",
        "query": "Is our current model calibration within acceptable bounds, or are we due for recalibration?",
        "category": "methodology",
        "expected_elements": ["calibration", "recalibrat", "bounds", "assumption"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },
    {
        "id": "Q032",
        "query": "What would trigger a RED status in the model monitor, and are we close to any of those triggers?",
        "category": "methodology",
        "expected_elements": ["RED", "trigger", "status", "threshold"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },
    {
        "id": "Q033",
        "query": "Walk me through the correlation assumption in our VaR model and how sensitive the output is to it breaking down.",
        "category": "methodology",
        "expected_elements": ["correlation", "assumption", "sensitive", "perfect positive correlation"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },
    {
        "id": "Q034",
        "query": "How often should we recalibrate our VaR model's volatility inputs, and what would trigger an early recalibration?",
        "category": "methodology",
        "expected_elements": ["recalibrat", "volatility", "trigger", "historical window"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },
    {
        "id": "Q035",
        "query": "What historical window do we use for volatility estimation, and what are the risks of using a 2-year window versus a longer one?",
        "category": "methodology",
        "expected_elements": ["2-year", "historical window", "volatility", "risk"],
        "expected_agent": "model_monitor",
        "difficulty": "hard",
    },

    # --- Boundary-probing (routing robustness beyond the two known Decision 15 cases) ---
    {
        "id": "Q036",
        "query": "Our VaR is high on MV Iron Maiden — should hedging be increased to lower it?",
        "category": "boundary",
        "expected_elements": ["MV Iron Maiden", "hedge", "increase", "VaR"],
        "expected_agent": "hedge_advisor",
        "difficulty": "hard",
    },
    {
        "id": "Q037",
        "query": "What's the hedging cost implication of MV Iron Maiden's HSFO use under IMO 2020 rules?",
        "category": "boundary",
        "expected_elements": ["hedging cost", "HSFO", "IMO 2020", "MV Iron Maiden"],
        "expected_agent": "hedge_advisor",
        "difficulty": "hard",
    },

    # --- RAG+ combined-value demonstration (both context sources needed, not just one masking absence) ---
    {
        "id": "Q038",
        "query": "Is our current VaR high by industry standards, and what does that mean for our risk appetite?",
        "category": "conceptual",
        "expected_elements": ["$376,329", "industry", "risk appetite", "standard"],
        "expected_agent": "risk_explainer",
        "difficulty": "hard",
    },
]

# Quick-access by ID — useful in evaluation runner
QUERIES_BY_ID: dict[str, EvaluationQuery] = {
    q["id"]: q for q in RISK_EVALUATION_QUERIES
}

# Group by category — useful for targeted testing during development
QUERIES_BY_CATEGORY: dict[str, list[EvaluationQuery]] = {}
for _q in RISK_EVALUATION_QUERIES:
    QUERIES_BY_CATEGORY.setdefault(_q["category"], []).append(_q)

# Quick-access by difficulty
QUERIES_BY_DIFFICULTY: dict[str, list[EvaluationQuery]] = {}
for _q in RISK_EVALUATION_QUERIES:
    QUERIES_BY_DIFFICULTY.setdefault(_q["difficulty"], []).append(_q)

# Quick-access by expected agent — used by the Phase 6 routing-accuracy evaluation
QUERIES_BY_EXPECTED_AGENT: dict[str, list[EvaluationQuery]] = {}
for _q in RISK_EVALUATION_QUERIES:
    QUERIES_BY_EXPECTED_AGENT.setdefault(_q["expected_agent"], []).append(_q)
