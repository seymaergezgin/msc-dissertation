"""
Unit tests for src/llm_provider.py.

Focused specifically on the AnthropicProvider fix from Phase 7: current-
generation Claude models (e.g. claude-sonnet-5) reject an explicit
`temperature` kwarg with a 400 error ("temperature is deprecated for this
model"). Found live when the cross-judge check first called this provider —
see PROJECT_DOC_v1.1.md Section 3.4. This test locks in the fix as a
regression guard; it does not call the real Anthropic API.
"""

from unittest.mock import MagicMock, patch

from src.llm_provider import AnthropicProvider


class TestAnthropicProviderExtractText:
    """
    Regression tests for the content-block normalisation fix: current-
    generation Claude models sometimes return response.content as a list
    of content blocks rather than a plain string, which crashed
    get_token_counts()'s `.split()` call with 'list' object has no
    attribute 'split'. Found live during the Phase 7 cross-judge check.
    """

    def test_plain_string_content_passed_through(self):
        assert AnthropicProvider._extract_text("Hello world") == "Hello world"

    def test_single_text_block_extracted(self):
        content = [{"type": "text", "text": "Hello world"}]
        assert AnthropicProvider._extract_text(content) == "Hello world"

    def test_multiple_text_blocks_concatenated(self):
        content = [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]
        assert AnthropicProvider._extract_text(content) == "Hello world"

    def test_non_text_blocks_ignored(self):
        content = [{"type": "thinking", "thinking": "internal reasoning"}, {"type": "text", "text": "Hello world"}]
        assert AnthropicProvider._extract_text(content) == "Hello world"

    def test_empty_list_returns_empty_string(self):
        assert AnthropicProvider._extract_text([]) == ""


class TestAnthropicProviderTemperature:

    def test_chat_anthropic_constructed_without_temperature_kwarg(self, monkeypatch):
        """
        ChatAnthropic must be constructed without a `temperature` argument —
        passing one causes a 400 Bad Request on current-generation models.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        config = {
            "provider": "anthropic", "model": "claude-sonnet-5", "temperature": 0.1,
            "cost_per_1k_input": 0.002, "cost_per_1k_output": 0.010,
        }
        provider = AnthropicProvider(config)

        with patch("langchain_anthropic.ChatAnthropic") as MockChatAnthropic:
            MockChatAnthropic.return_value = MagicMock()
            provider._get_langchain_llm()

        call_kwargs = MockChatAnthropic.call_args.kwargs
        assert "temperature" not in call_kwargs
        assert call_kwargs["model"] == "claude-sonnet-5"

    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = {
            "provider": "anthropic", "model": "claude-sonnet-5", "temperature": 0.1,
            "cost_per_1k_input": 0.002, "cost_per_1k_output": 0.010,
        }
        try:
            AnthropicProvider(config)
            assert False, "Expected EnvironmentError"
        except EnvironmentError:
            pass
