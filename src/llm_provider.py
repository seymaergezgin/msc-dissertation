"""
Abstract LLM provider interface and concrete implementations.

Architecture decision: all three providers (Ollama, OpenAI, Anthropic) share
the same BaseLLMProvider interface. Switching providers requires only changing
LLM_PROVIDER in .env — no code changes anywhere else in the system.

Usage:
    from src.llm_provider import get_llm_provider

    llm = get_llm_provider()          # Uses LLM_PROVIDER from .env
    response = llm.invoke("What is VaR?")

    llm_openai = get_llm_provider("openai")   # Override for specific call
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import requests

from config.llm_config import get_llm_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

def is_ollama_available(base_url: str = "http://localhost:11434") -> bool:
    """
    Check whether the local Ollama server is reachable.

    Returns True only if the /api/tags endpoint responds with HTTP 200.
    Used to decide whether to fall back to a cloud provider.
    """
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class BaseLLMProvider(ABC):
    """
    Common interface that all LLM providers must implement.

    Every concrete provider must implement `invoke` and `get_provider_name`.
    The `invoke` method returns a plain string so the rest of the system
    does not need to know which provider is active.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.provider_name = config["provider"]
        self.model = config["model"]
        self.temperature = config.get("temperature", 0.1)

    @abstractmethod
    def invoke(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Send a prompt to the LLM and return the text response.

        Args:
            prompt: The user message / query.
            system_prompt: Optional system-level instruction for the LLM.

        Returns:
            The model's text response as a plain string.
        """

    @abstractmethod
    def get_token_counts(self, prompt: str, response: str) -> dict[str, int]:
        """
        Estimate or retrieve token counts for a prompt/response pair.

        Args:
            prompt: The input text.
            response: The model's output text.

        Returns:
            Dict with keys "input_tokens" and "output_tokens".
        """

    def get_provider_name(self) -> str:
        """Return the provider identifier string."""
        return self.provider_name


# ---------------------------------------------------------------------------
# Ollama implementation (free, local)
# ---------------------------------------------------------------------------

class OllamaProvider(BaseLLMProvider):
    """
    Ollama local LLM provider.

    Communicates with a locally running Ollama server via its REST API.
    Free to use — no API key needed. Requires `ollama serve` to be running.

    How it works:
    1. Sends a POST request to /api/chat with the model name and messages.
    2. Parses the JSON response to extract the assistant's message content.
    3. Returns the content as a plain string.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self._langchain_llm: Any = None

    def _get_langchain_llm(self) -> Any:
        """Lazily initialise the LangChain Ollama wrapper (avoids import cost at startup)."""
        if self._langchain_llm is None:
            from langchain_ollama import ChatOllama
            self._langchain_llm = ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
            )
        return self._langchain_llm

    def invoke(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Ollama via LangChain's ChatOllama wrapper."""
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        llm = self._get_langchain_llm()
        start = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - start

        logger.info(
            "Ollama (%s) responded in %.2fs", self.model, elapsed
        )
        return response.content

    def get_token_counts(self, prompt: str, response: str) -> dict[str, int]:
        """
        Estimate token counts using a simple word-based heuristic.

        Ollama's REST API returns token counts in the response metadata, but
        the LangChain wrapper does not always surface them. Using ~1.3 tokens
        per word as a conservative estimate that works for English text.
        """
        input_tokens = int(len(prompt.split()) * 1.3)
        output_tokens = int(len(response.split()) * 1.3)
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------

class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI GPT provider.

    Uses langchain-openai under the hood. Requires OPENAI_API_KEY in .env.
    Default model: gpt-4o-mini (good quality, very low cost ~$0.50 for
    a full dissertation's worth of testing).

    How it works:
    1. Initialises a ChatOpenAI instance with the configured model.
    2. Sends messages and returns the text content of the response.
    3. Uses tiktoken for accurate token counting (OpenAI's tokeniser).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not found in environment. "
                "Set it in your .env file or switch to LLM_PROVIDER=ollama."
            )
        self._langchain_llm: Any = None

    def _get_langchain_llm(self) -> Any:
        if self._langchain_llm is None:
            from langchain_openai import ChatOpenAI
            self._langchain_llm = ChatOpenAI(
                model=self.model,
                temperature=self.temperature,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
            )
        return self._langchain_llm

    def invoke(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call OpenAI via LangChain's ChatOpenAI wrapper."""
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        llm = self._get_langchain_llm()
        start = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - start

        logger.info("OpenAI (%s) responded in %.2fs", self.model, elapsed)
        return response.content

    def get_token_counts(self, prompt: str, response: str) -> dict[str, int]:
        """Use tiktoken for accurate OpenAI token counting."""
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(self.model)
            input_tokens = len(enc.encode(prompt))
            output_tokens = len(enc.encode(response))
        except Exception:
            # Fall back to word-based estimate if tiktoken fails
            input_tokens = int(len(prompt.split()) * 1.3)
            output_tokens = int(len(response.split()) * 1.3)
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}


# ---------------------------------------------------------------------------
# Anthropic implementation
# ---------------------------------------------------------------------------

class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude provider.

    Uses langchain-anthropic. Requires ANTHROPIC_API_KEY in .env.
    Default model: claude-3-5-sonnet-20241022.

    How it works:
    1. Initialises a ChatAnthropic instance with the configured model.
    2. Sends messages and returns the text content.
    3. Estimates tokens via word count (Anthropic's tokeniser is similar to OpenAI's).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not found in environment. "
                "Set it in .env or switch to LLM_PROVIDER=ollama."
            )
        self._langchain_llm: Any = None

    def _get_langchain_llm(self) -> Any:
        if self._langchain_llm is None:
            from langchain_anthropic import ChatAnthropic
            # Current-generation Claude models (e.g. claude-sonnet-5, the
            # default as of Phase 7) reject an explicit `temperature` kwarg
            # outright (400: "temperature is deprecated for this model") —
            # found the hard way when the cross-judge check first hit this
            # provider. Anthropic's older model lines accepted it, but since
            # ANTHROPIC_MODEL now defaults to the current model, temperature
            # is omitted here rather than passed conditionally per model.
            self._langchain_llm = ChatAnthropic(
                model=self.model,
                anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            )
        return self._langchain_llm

    def invoke(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Anthropic via LangChain's ChatAnthropic wrapper."""
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        llm = self._get_langchain_llm()
        start = time.time()
        response = llm.invoke(messages)
        elapsed = time.time() - start

        logger.info("Anthropic (%s) responded in %.2fs", self.model, elapsed)
        return self._extract_text(response.content)

    @staticmethod
    def _extract_text(content: Any) -> str:
        """
        Normalise ChatAnthropic's response content to a plain string.

        Current-generation Claude models (e.g. claude-sonnet-5) sometimes
        return `response.content` as a list of content blocks (each a dict
        with a "type" and, for text blocks, a "text" key) rather than a
        plain string — found the hard way when the cross-judge check's
        `.split()` call on the response crashed with "'list' object has no
        attribute 'split'". Older Claude models returned a plain string
        directly, which is why this wasn't caught before Phase 7 (Anthropic
        was never actually called in earlier phases).
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return str(content)

    def get_token_counts(self, prompt: str, response: str) -> dict[str, int]:
        """Estimate token counts using word-based heuristic."""
        input_tokens = int(len(prompt.split()) * 1.3)
        output_tokens = int(len(response.split()) * 1.3)
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}


# ---------------------------------------------------------------------------
# Factory function — the one import the rest of the system uses
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def get_llm_provider(provider: Optional[str] = None) -> BaseLLMProvider:
    """
    Factory function: return a ready-to-use LLM provider instance.

    Switching logic:
    1. If `provider` is given, use that.
    2. Otherwise read LLM_PROVIDER from .env.
    3. If the requested provider is Ollama but Ollama is not running,
       fall back to OpenAI (if key is set) with a warning.
    4. Raise RuntimeError if no provider is available.

    Args:
        provider: Optional override. One of "ollama", "openai", "anthropic".

    Returns:
        An initialised BaseLLMProvider instance.

    Raises:
        RuntimeError: If no LLM provider is reachable.
    """
    from config.llm_config import DEFAULT_LLM_PROVIDER, get_llm_config

    name = provider or DEFAULT_LLM_PROVIDER

    # Automatic Ollama → OpenAI fallback
    if name == "ollama" and not is_ollama_available():
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            logger.warning(
                "Ollama not reachable at localhost:11434. "
                "Falling back to OpenAI (gpt-4o-mini). "
                "Run 'ollama serve' to use the free local model."
            )
            name = "openai"
        else:
            raise RuntimeError(
                "Ollama is not running and no OPENAI_API_KEY is set. "
                "Start Ollama with 'ollama serve', or add an API key to .env."
            )

    if name not in _PROVIDER_MAP:
        raise ValueError(
            f"Unknown provider '{name}'. Choose from: {list(_PROVIDER_MAP.keys())}"
        )

    config = get_llm_config(name)
    logger.info("Using LLM provider: %s (model: %s)", name, config["model"])
    return _PROVIDER_MAP[name](config)
