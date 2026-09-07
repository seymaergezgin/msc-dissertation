"""
Unit tests for src/interaction_logger.py.

All tests write to a tmp_path log file, never the real project log at
data/interaction_logs/interactions.jsonl — no API calls, no dependency
on any other component.
"""

import json

from src.interaction_logger import log_interaction, read_interactions


class TestLogInteraction:

    def test_creates_log_file_and_directory_if_missing(self, tmp_path):
        log_file = tmp_path / "nested" / "interactions.jsonl"
        log_interaction(query="q", answer="a", agent="Risk Explainer", log_file=log_file)
        assert log_file.exists()

    def test_writes_one_json_line_per_call(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(query="q1", answer="a1", agent="Risk Explainer", log_file=log_file)
        log_interaction(query="q2", answer="a2", agent="Hedge Advisor", log_file=log_file)
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["query"] == "q1"
        assert json.loads(lines[1])["query"] == "q2"

    def test_entry_contains_all_core_fields(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(
            query="What is our VaR?",
            answer="Our VaR is $376,329.",
            agent="Risk Explainer",
            routed_to="Risk Explainer",
            routing_reason="Matched keyword(s) ['var']",
            confidence="high",
            collection="risk_metrics",
            sources=[{"file": "Value_at_risk.pdf", "page": 3}],
            retrieval_count=5,
            response_time_s=4.2,
            provider="openai",
            model="gpt-4o-mini",
            cost_usd=0.0004321,
            log_file=log_file,
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["query"] == "What is our VaR?"
        assert entry["answer"] == "Our VaR is $376,329."
        assert entry["agent"] == "Risk Explainer"
        assert entry["routed_to"] == "Risk Explainer"
        assert entry["confidence"] == "high"
        assert entry["collection"] == "risk_metrics"
        assert entry["sources"] == [{"file": "Value_at_risk.pdf", "page": 3}]
        assert entry["retrieval_count"] == 5
        assert entry["response_time_s"] == 4.2
        assert entry["provider"] == "openai"
        assert entry["model"] == "gpt-4o-mini"
        assert "timestamp" in entry

    def test_cost_is_rounded_to_six_decimal_places(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(query="q", answer="a", agent="Risk Explainer", cost_usd=0.00043212345, log_file=log_file)
        entry = json.loads(log_file.read_text().strip())
        assert entry["cost_usd"] == 0.000432

    def test_optional_fields_default_to_none_or_empty(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(query="q", answer="a", agent="Risk Explainer", log_file=log_file)
        entry = json.loads(log_file.read_text().strip())
        assert entry["routed_to"] is None
        assert entry["confidence"] is None
        assert entry["sources"] == []
        assert entry["cost_usd"] is None

    def test_eval_metadata_included_when_provided(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(
            query="q", answer="a", agent="Risk Explainer",
            eval_metadata={"query_id": "Q001", "category": "factual", "mode": "rag_plus"},
            log_file=log_file,
        )
        entry = json.loads(log_file.read_text().strip())
        assert entry["eval_metadata"]["query_id"] == "Q001"
        assert entry["eval_metadata"]["mode"] == "rag_plus"

    def test_eval_metadata_key_absent_when_not_provided(self, tmp_path):
        """Ordinary (non-evaluation) interactions shouldn't carry an empty eval_metadata key."""
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(query="q", answer="a", agent="Risk Explainer", log_file=log_file)
        entry = json.loads(log_file.read_text().strip())
        assert "eval_metadata" not in entry

    def test_logging_failure_is_non_fatal(self, tmp_path, monkeypatch):
        """A write failure must not raise — it should log a warning and return."""
        bad_path = tmp_path / "readonly_dir" / "interactions.jsonl"
        bad_path.parent.mkdir()
        bad_path.parent.chmod(0o400)  # read-only directory
        try:
            log_interaction(query="q", answer="a", agent="Risk Explainer", log_file=bad_path)
        finally:
            bad_path.parent.chmod(0o700)  # restore so tmp_path cleanup can delete it


class TestReadInteractions:

    def test_returns_empty_list_when_file_missing(self, tmp_path):
        assert read_interactions(log_file=tmp_path / "missing.jsonl") == []

    def test_reads_back_all_entries_in_order(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(query="q1", answer="a1", agent="Risk Explainer", log_file=log_file)
        log_interaction(query="q2", answer="a2", agent="Hedge Advisor", log_file=log_file)
        log_interaction(query="q3", answer="a3", agent="Model Monitor", log_file=log_file)

        entries = read_interactions(log_file=log_file)
        assert len(entries) == 3
        assert [e["query"] for e in entries] == ["q1", "q2", "q3"]
        assert [e["agent"] for e in entries] == ["Risk Explainer", "Hedge Advisor", "Model Monitor"]

    def test_skips_blank_lines(self, tmp_path):
        log_file = tmp_path / "interactions.jsonl"
        log_interaction(query="q1", answer="a1", agent="Risk Explainer", log_file=log_file)
        with open(log_file, "a") as f:
            f.write("\n\n")
        log_interaction(query="q2", answer="a2", agent="Risk Explainer", log_file=log_file)
        entries = read_interactions(log_file=log_file)
        assert len(entries) == 2
