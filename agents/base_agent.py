"""
Abstract base class for all agents in the maritime risk system.

All three agents (Risk Explainer, Hedge Advisor, Model Monitor) inherit
from BaseAgent, which defines the standard interface so the Phase 4
LangGraph orchestrator can route queries through a single consistent API.

Each concrete agent only needs to define three things:
  1. name (class attribute): human-readable label for logging/UI
  2. collection (class attribute): which ChromaDB collection it queries
  3. system_prompt (property): its persona and response format rules
  4. answer() (method): its custom logic for building the response

The base class handles logging and provides get_info() for the
orchestrator to inspect agent capabilities without calling them.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all specialist agents.

    How it works:
    1. On initialisation, the agent creates (or accepts) a RAGPipeline
       configured to query its specific ChromaDB collection.
    2. answer() is the only method the Phase 4 orchestrator calls.
       Each subclass implements its own logic: what context to inject,
       what prompt to build, what structure to return.
    3. system_prompt is exposed as a property so the orchestrator can
       inspect agent descriptions for routing and logging decisions.
    4. get_info() returns metadata without triggering any LLM calls —
       used by the orchestrator during initialisation.

    Args:
        pipeline: Pre-initialised RAGPipeline. If None, one is created
                  using the collection defined by the concrete subclass.
    """

    name: str = "BaseAgent"
    collection: str = "all"

    def __init__(self, pipeline: Optional[RAGPipeline] = None) -> None:
        self.pipeline = pipeline or RAGPipeline(collection=self.collection)
        logger.info("Agent '%s' initialised (collection: %s)", self.name, self.collection)

    @abstractmethod
    def answer(self, query: str) -> dict:
        """
        Answer a user query and return a structured result dict.

        Every agent returns a dict with at minimum these keys so the
        orchestrator and UI can handle all agents uniformly:
          - "answer" (str): The generated plain-English response
          - "sources" (list[dict]): Citation info for retrieved chunks
          - "agent" (str): This agent's name (for UI attribution)
          - "query" (str): The original user question (for logging)

        Args:
            query: The user's natural language question.

        Returns:
            Dict with answer, sources, agent name, and query.
            Subclasses may add additional keys (e.g., portfolio_snapshot).
        """
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """
        The agent's persona and instruction prompt.

        This is passed to the LLM as the system role message, defining
        the agent's tone, response format, and grounding constraints.
        Different agents have different audiences and formats.
        """
        pass

    def get_info(self) -> dict:
        """
        Return agent metadata without making any LLM calls.

        Used by the Phase 4 orchestrator during initialisation to
        understand each agent's capabilities and collection scope.
        """
        return {
            "name": self.name,
            "collection": self.collection,
            "system_prompt_preview": self.system_prompt[:120] + "...",
        }
