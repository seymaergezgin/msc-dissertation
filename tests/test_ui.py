"""
Unit tests for pure helper logic in ui/app.py.

Streamlit's rendering itself isn't practically unit-testable (it's a
script re-run against a live browser session), so these tests target
the one piece of ui/app.py that is pure logic: the markdown-dollar-sign
escaping helper. See ui/app.py's module docstring for why it exists —
found via manual browser testing during Phase 5, where an agent answer
containing two dollar figures in one sentence was silently mangled by
Streamlit's automatic LaTeX rendering.
"""

from ui.app import _escape_markdown_dollars


class TestEscapeMarkdownDollars:

    def test_single_dollar_figure_is_escaped(self):
        assert _escape_markdown_dollars("VaR is $376,329.") == "VaR is \\$376,329."

    def test_two_dollar_figures_in_one_sentence_are_both_escaped(self):
        """
        This is the exact case that triggered Streamlit's LaTeX auto-render:
        two dollar amounts in the same paragraph get treated as a math
        expression's opening/closing delimiters.
        """
        text = "HSFO is priced at $385.14/MT compared to VLSFO at $470.73/MT."
        result = _escape_markdown_dollars(text)
        assert result == "HSFO is priced at \\$385.14/MT compared to VLSFO at \\$470.73/MT."
        assert "$" not in result.replace("\\$", "")

    def test_text_without_dollar_signs_is_unchanged(self):
        text = "Our average hedge ratio across the fleet is 48 percent."
        assert _escape_markdown_dollars(text) == text

    def test_does_not_affect_other_markdown_formatting(self):
        text = "**SUMMARY**\nOur VaR is $376,329."
        result = _escape_markdown_dollars(text)
        assert result.startswith("**SUMMARY**")
