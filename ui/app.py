"""
Streamlit UI for the maritime fuel risk narrative system.

The first human-facing entry point in this project — Phases 1-4 were all
exercised via test scripts or a terminal one-liner. This app wraps the
Phase 4 Orchestrator in a chat-style interface so a non-technical
stakeholder can ask a question and see:
  - the plain-English answer
  - which specialist agent answered it, why, and how confident the
    routing decision was (routing transparency, per PROJECT_DOC_v0.4.md
    Section 12.2)
  - the source documents the answer was grounded in
  - running API spend against the $10/month student budget

Design notes:
  - The Orchestrator is built once via st.cache_resource, not on every
    rerun — building it loads ChromaDB collections and embeddings for
    all three agents, which is too slow to repeat per interaction.
  - Conversation history lives in st.session_state, not in
    Orchestrator.history. This keeps the UI's per-user chat log separate
    from the orchestrator's own routing-decision log (see
    PROJECT_DOC_v0.4.md Decision 14) and avoids coupling the UI's display
    state to the orchestrator's internal bookkeeping.
  - Every call to orchestrator.answer() is wrapped in a try/except.
    This closes Deferred item 2 from the Phase 4 self-review
    (PROJECT_DOC_v0.4.md changelog v0.4->v0.4.1): a transient OpenAI
    rate-limit or a dropped Ollama connection now shows a clean message
    instead of a raw Streamlit traceback.
  - Agent-generated text is escaped before st.markdown()/st.write() via
    _escape_markdown_dollars(). Streamlit renders "$...$" as inline LaTeX,
    and agent answers routinely contain two dollar figures in one
    sentence (e.g. "$385.14/MT compared to VLSFO at $470.73/MT") — found
    during Phase 5 manual browser testing, where it silently mangled the
    text into a garbled KaTeX expression. Escaping "$" to a backslash-escaped
    dollar sign is the standard fix; it does not affect **bold**/other
    markdown formatting.

Usage:
    streamlit run ui/app.py
"""

import logging
import sys
from pathlib import Path

# Make the project root importable regardless of how Streamlit was invoked.
# `streamlit run ui/app.py` (the console-script entry point) only adds this
# script's own directory (ui/) to sys.path, not the project root, so
# `from src...`/`from config...` fail with ModuleNotFoundError. Running via
# `python -m streamlit run ui/app.py` masks this, because `-m` adds the
# current working directory to sys.path instead — that difference is exactly
# what caused this to work in testing but fail for a plain `streamlit run`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from src.cost_tracker import CostTracker
from src.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Maritime Fuel Risk Narrative Assistant",
    page_icon="🚢",
    layout="wide",
)


def _escape_markdown_dollars(text: str) -> str:
    """
    Escape literal '$' so Streamlit's markdown renderer doesn't mistake a
    dollar figure for a LaTeX math delimiter.

    Streamlit auto-detects "$...$" as inline LaTeX. Agent answers frequently
    contain two or more dollar amounts in the same paragraph (VaR, CVaR, fuel
    prices), which get silently parsed as a math expression instead of
    displayed as plain text. This is agent-generated content, not markup we
    wrote, so escaping before display is the correct fix rather than asking
    agents to avoid "$" in their responses.
    """
    return text.replace("$", "\\$")


@st.cache_resource(show_spinner="Loading agents and knowledge base...")
def get_orchestrator() -> Orchestrator:
    """
    Build the Orchestrator once per server process.

    Cached with st.cache_resource so the three agents' RAGPipelines
    (and the ChromaDB/embedding connections they hold) are created once,
    not on every user interaction or Streamlit rerun.
    """
    logger.info("Building Orchestrator for Streamlit session")
    return Orchestrator()


def render_sidebar() -> None:
    """
    Render the budget tracker and agent roster in the sidebar.

    Reads a fresh CostTracker report on every rerun (cheap: it only
    reads the CSV log) so the spend figure reflects the very latest
    query, including ones answered earlier in this same session.
    """
    st.sidebar.header("Budget")
    report = CostTracker().get_report()
    st.sidebar.metric(
        "Spend this month",
        f"${report['current_spend_usd']:.4f}",
        help=f"Monthly budget: ${report['monthly_budget_usd']:.2f}",
    )
    st.sidebar.progress(min(report["budget_used_pct"] / 100, 1.0))
    st.sidebar.caption(
        f"{report['budget_used_pct']}% used · "
        f"${report['remaining_budget_usd']:.4f} remaining · "
        f"{report['call_count']} calls logged"
    )

    st.sidebar.header("Agents")
    for info in get_orchestrator().get_agent_info():
        st.sidebar.caption(f"**{info['name']}** — collection: `{info['collection']}`")


def render_message(entry: dict) -> None:
    """Render one past Q&A exchange as a user bubble + assistant bubble."""
    with st.chat_message("user"):
        st.markdown(entry["query"])

    with st.chat_message("assistant"):
        if entry.get("error"):
            st.error(entry["error"])
            return

        st.markdown(_escape_markdown_dollars(entry["answer"]))

        with st.expander(
            f"Routed to **{entry['routed_to']}** "
            f"(confidence: {entry['confidence']}) — why?"
        ):
            st.write(_escape_markdown_dollars(entry["routing_reason"]))

        sources = entry.get("sources") or []
        if sources:
            with st.expander(f"Sources ({len(sources)})"):
                for src in sources:
                    page_str = f", p.{src['page']}" if src.get("page") != "" else ""
                    st.markdown(f"- **{src['file']}**{page_str}")


def main() -> None:
    st.title("🚢 Maritime Fuel Risk Narrative Assistant")
    st.caption(
        "Ask a question about the fleet's fuel price risk, hedging position, "
        "or VaR model health. Answers are grounded in live portfolio data and "
        "the project's document knowledge base — not the model's general knowledge."
    )

    render_sidebar()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for entry in st.session_state.messages:
        render_message(entry)

    query = st.chat_input("e.g. What is our current portfolio VaR at 95% confidence?")
    if not query:
        return

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Routing query and generating response..."):
            try:
                result = get_orchestrator().answer(query)
            except Exception as exc:
                logger.error("Orchestrator failed to answer query: %s", exc, exc_info=True)
                error_message = (
                    "Something went wrong generating a response "
                    "(the LLM provider or embedding service may be unavailable). "
                    "Please try again in a moment."
                )
                st.error(error_message)
                st.session_state.messages.append({"query": query, "error": error_message})
                return

        st.markdown(_escape_markdown_dollars(result["answer"]))

        with st.expander(
            f"Routed to **{result['routed_to']}** "
            f"(confidence: {result['confidence']}) — why?"
        ):
            st.write(_escape_markdown_dollars(result["routing_reason"]))

        sources = result.get("sources") or []
        if sources:
            with st.expander(f"Sources ({len(sources)})"):
                for src in sources:
                    page_str = f", p.{src['page']}" if src.get("page") != "" else ""
                    st.markdown(f"- **{src['file']}**{page_str}")

    st.session_state.messages.append({
        "query": query,
        "answer": result["answer"],
        "routed_to": result["routed_to"],
        "routing_reason": result["routing_reason"],
        "confidence": result["confidence"],
        "sources": sources,
    })


if __name__ == "__main__":
    main()
