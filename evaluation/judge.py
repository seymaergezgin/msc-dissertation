"""
LLM-as-judge scoring for Phase 6 evaluation.

Phase 3 established a 4-criterion rubric (Accuracy, Structure, Plain English,
Completeness — each 0-3, 12 max) but left every score blank in
docs/test_results/phase3_comparative_test.md for manual entry — no automated
scoring existed yet. This module automates that scoring using the same
rubric, calling an LLM (by default the same gpt-4o-mini used for generation)
to act as an impartial judge.

This does not replace manual/supervisor scoring — it runs alongside it. The
Phase 6 evaluation report includes both: the automated judge score for every
response, and a blank "supervisor override" column for a human to fill in,
exactly as Phase 3's report did for its manual-only column.

Usage:
    from src.llm_provider import get_llm_provider
    from evaluation.judge import judge_response

    llm = get_llm_provider("openai")
    result = judge_response(
        query="What is our current portfolio VaR at 95% confidence?",
        answer="**SUMMARY** Our VaR is $376,329 ...",
        expected_elements=["$376,329", "95%", "10-day", "5% chance"],
        llm=llm,
    )
    print(result["total"], "/12")
    print(result["justification"])
"""

import json
import logging
import re
from typing import Optional

from src.cost_tracker import CostTracker
from src.llm_provider import BaseLLMProvider

logger = logging.getLogger(__name__)


JUDGE_SYSTEM_PROMPT = """You are an impartial evaluator scoring an AI system's response to a maritime \
fuel risk question. You did not generate this response — you are reviewing it.

Score the response on exactly these 4 criteria, 0-3 each:

**Accuracy** (0-3): Are the specific figures (VaR, CVaR, hedge ratios, prices) correctly cited?
  0 = wrong figures, 1 = partially correct, 2 = correct but vague, 3 = exact figures + correct context

**Structure** (0-3): Does it follow a clear structured format (e.g. SUMMARY/EXPLANATION/IMPLICATIONS/CAVEATS)?
  0 = no sections, 1 = some sections, 2 = all sections present, 3 = sections correct + concise summary

**Plain English** (0-3): Would a non-technical business reader understand this without help?
  0 = jargon or formula garbage, 1 = mostly clear, 2 = clear no formulas, 3 = clear + appropriate board tone

**Completeness** (0-3): Does it cover the expected elements listed below?
  0 = misses expected elements, 1 = ~50% covered, 2 = ~75% covered, 3 = all expected elements covered

Respond with ONLY a JSON object in this exact shape, no other text:
{"accuracy": <0-3>, "structure": <0-3>, "plain_english": <0-3>, "completeness": <0-3>, "justification": "<one or two sentences>"}"""


def _build_judge_prompt(query: str, answer: str, expected_elements: list[str]) -> str:
    return f"""QUESTION ASKED:
{query}

EXPECTED ELEMENTS (the response should cover these):
{", ".join(expected_elements) if expected_elements else "(none specified)"}

RESPONSE TO SCORE:
{answer}

Score this response now, following the rubric exactly. Return only the JSON object."""


def _extract_json(text: str) -> dict:
    """
    Parse the judge's JSON response, tolerating markdown code fences.

    LLMs asked for "only JSON" sometimes still wrap it in ```json ... ```
    or add a stray sentence before/after — this strips fences and extracts
    the first {...} block rather than assuming the whole string is valid JSON.
    """
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1)
    else:
        brace_match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if brace_match:
            stripped = brace_match.group(0)
    return json.loads(stripped)


def judge_response(
    query: str,
    answer: str,
    expected_elements: list[str],
    llm: BaseLLMProvider,
    cost_tracker: Optional[CostTracker] = None,
    query_id: str = "",
) -> dict:
    """
    Score one agent response against the Phase 3/6 rubric using an LLM judge.

    Args:
        query: The original question that was asked.
        answer: The agent's full response text to be scored.
        expected_elements: The query's expected_elements list, used to score Completeness.
        llm: An initialised LLM provider (typically the same one used for generation).
        cost_tracker: Optional CostTracker to log this judging call's cost against
            the shared project budget. Created fresh if not provided.
        query_id: Optional query ID (e.g. "Q001") for the cost log's query_summary tag.

    Returns:
        Dict with keys "accuracy", "structure", "plain_english", "completeness"
        (each 0-3), "total" (0-12), and "justification" (str). If the judge's
        response fails to parse as valid JSON, returns a dict with the same
        keys set to None and an "error" key holding the parse failure message
        and raw response — this is a non-fatal degradation, not a crash,
        consistent with the rest of this project's error-handling approach.
    """
    tracker = cost_tracker or CostTracker()
    prompt = _build_judge_prompt(query, answer, expected_elements)

    raw_response = llm.invoke(prompt, system_prompt=JUDGE_SYSTEM_PROMPT)

    tokens = llm.get_token_counts(prompt, raw_response)
    try:
        tracker.log_usage(
            provider=llm.get_provider_name(),
            model=llm.model,
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            query_summary=f"[Judge] {query_id + ': ' if query_id else ''}{query[:60]}",
        )
    except Exception as cost_err:
        logger.warning("Judge cost tracking failed (non-fatal): %s", cost_err)

    try:
        scores = _extract_json(raw_response)
        result = {
            "accuracy": int(scores["accuracy"]),
            "structure": int(scores["structure"]),
            "plain_english": int(scores["plain_english"]),
            "completeness": int(scores["completeness"]),
            "justification": scores.get("justification", ""),
        }
        result["total"] = (
            result["accuracy"] + result["structure"] + result["plain_english"] + result["completeness"]
        )
        return result
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as parse_err:
        logger.warning("Judge response failed to parse (non-fatal): %s", parse_err)
        return {
            "accuracy": None,
            "structure": None,
            "plain_english": None,
            "completeness": None,
            "total": None,
            "justification": "",
            "error": f"{parse_err} | raw response: {raw_response[:300]}",
        }
