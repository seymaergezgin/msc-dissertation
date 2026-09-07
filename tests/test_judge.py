"""
Unit tests for evaluation/judge.py (LLM-as-judge scoring).

All tests use a mocked LLM provider — no real API calls. Tests verify:
  - Well-formed JSON responses are parsed correctly
  - JSON wrapped in markdown code fences is still parsed correctly
  - Malformed judge responses degrade gracefully (non-fatal, "error" key set)
  - The cost tracker is invoked for every judge call
  - The judge prompt includes the query, answer, and expected elements
"""

from unittest.mock import MagicMock

from evaluation.judge import _extract_json, judge_response


def _make_mock_llm(response_text: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value = response_text
    llm.get_token_counts.return_value = {"input_tokens": 300, "output_tokens": 80}
    llm.get_provider_name.return_value = "openai"
    llm.model = "gpt-4o-mini"
    return llm


class TestExtractJson:

    def test_parses_plain_json(self):
        text = '{"accuracy": 3, "structure": 2, "plain_english": 3, "completeness": 2, "justification": "Good."}'
        result = _extract_json(text)
        assert result["accuracy"] == 3

    def test_parses_json_wrapped_in_markdown_fence(self):
        text = '```json\n{"accuracy": 1, "structure": 2, "plain_english": 3, "completeness": 0, "justification": "Weak."}\n```'
        result = _extract_json(text)
        assert result["accuracy"] == 1
        assert result["completeness"] == 0

    def test_parses_json_with_surrounding_prose(self):
        text = 'Here is my evaluation:\n{"accuracy": 2, "structure": 2, "plain_english": 2, "completeness": 2, "justification": "OK."}\nHope that helps!'
        result = _extract_json(text)
        assert result["structure"] == 2


class TestJudgeResponse:

    def test_well_formed_response_is_scored_correctly(self):
        llm = _make_mock_llm(
            '{"accuracy": 3, "structure": 3, "plain_english": 2, "completeness": 3, "justification": "Cites exact figures."}'
        )
        result = judge_response(
            query="What is our VaR?",
            answer="Our VaR is $376,329.",
            expected_elements=["$376,329", "95%"],
            llm=llm,
        )
        assert result["accuracy"] == 3
        assert result["structure"] == 3
        assert result["plain_english"] == 2
        assert result["completeness"] == 3
        assert result["total"] == 11
        assert result["justification"] == "Cites exact figures."

    def test_total_is_sum_of_four_criteria(self):
        llm = _make_mock_llm(
            '{"accuracy": 1, "structure": 1, "plain_english": 1, "completeness": 1, "justification": "Partial."}'
        )
        result = judge_response(query="q", answer="a", expected_elements=[], llm=llm)
        assert result["total"] == 4

    def test_malformed_json_degrades_gracefully(self):
        """A judge response that isn't valid JSON must not raise — it returns None scores + an error key."""
        llm = _make_mock_llm("I refuse to answer in JSON format, sorry!")
        result = judge_response(query="q", answer="a", expected_elements=[], llm=llm)
        assert result["accuracy"] is None
        assert result["total"] is None
        assert "error" in result

    def test_missing_rubric_key_degrades_gracefully(self):
        """A JSON response missing a required key must not raise."""
        llm = _make_mock_llm('{"accuracy": 3, "structure": 2}')  # missing plain_english, completeness
        result = judge_response(query="q", answer="a", expected_elements=[], llm=llm)
        assert result["accuracy"] is None
        assert "error" in result

    def test_cost_tracker_is_called_once(self):
        llm = _make_mock_llm(
            '{"accuracy": 2, "structure": 2, "plain_english": 2, "completeness": 2, "justification": "Fine."}'
        )
        tracker = MagicMock()
        judge_response(query="q", answer="a", expected_elements=[], llm=llm, cost_tracker=tracker)
        tracker.log_usage.assert_called_once()

    def test_cost_tracker_query_summary_tagged_with_judge(self):
        llm = _make_mock_llm(
            '{"accuracy": 2, "structure": 2, "plain_english": 2, "completeness": 2, "justification": "Fine."}'
        )
        tracker = MagicMock()
        judge_response(query="What is our VaR?", answer="a", expected_elements=[], llm=llm, cost_tracker=tracker, query_id="Q001")
        call_kwargs = tracker.log_usage.call_args.kwargs
        assert "[Judge]" in call_kwargs["query_summary"]
        assert "Q001" in call_kwargs["query_summary"]

    def test_judge_prompt_includes_query_answer_and_expected_elements(self):
        llm = _make_mock_llm(
            '{"accuracy": 2, "structure": 2, "plain_english": 2, "completeness": 2, "justification": "Fine."}'
        )
        judge_response(
            query="What is our CVaR?",
            answer="Our CVaR is $481,701.",
            expected_elements=["$481,701", "95%"],
            llm=llm,
        )
        prompt_sent = llm.invoke.call_args[0][0]
        assert "What is our CVaR?" in prompt_sent
        assert "Our CVaR is $481,701." in prompt_sent
        assert "$481,701" in prompt_sent

    def test_judge_uses_rubric_system_prompt(self):
        llm = _make_mock_llm(
            '{"accuracy": 2, "structure": 2, "plain_english": 2, "completeness": 2, "justification": "Fine."}'
        )
        judge_response(query="q", answer="a", expected_elements=[], llm=llm)
        call_kwargs = llm.invoke.call_args
        system_prompt_used = call_kwargs[1].get("system_prompt") or call_kwargs[0][1]
        assert "Accuracy" in system_prompt_used
        assert "Structure" in system_prompt_used
        assert "Plain English" in system_prompt_used
        assert "Completeness" in system_prompt_used
