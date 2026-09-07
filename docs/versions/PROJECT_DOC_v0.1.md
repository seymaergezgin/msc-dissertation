# Project Documentation — Version 0.1
# AI-Based Narrative Risk Reporting for Maritime Fuel Management
# Last Updated: 2026-06-19
# Author: Seymanur Ergezgin | MSc Engineering Management, University of Greenwich
# Supervisor: Dr. Mike Sharp

---

## Changelog (v0.1 — Initial Release)

### Added
- Complete project folder structure (12 directories, 16 files)
- Git branching strategy: `master → dev → feature/phase1-setup`
- Python virtual environment: `env_dissertation` (Python 3.12)
- `requirements.txt` with pinned versions for reproducibility
- Abstract LLM provider interface with Ollama, OpenAI, and Anthropic implementations
- Cost tracker with CSV logging and budget alerting
- Configuration system using environment variables
- `.env.example` template (API keys never committed to git)
- `README.md` with quick-start instructions

---

## 1. Executive Summary

This project builds a Multi-Agent LLM system that translates quantitative maritime fuel
risk metrics into plain English narratives. The system is designed for maritime companies
whose risk managers produce numerical outputs (Value at Risk, hedge ratios, exposure figures)
that are difficult for non-technical decision-makers to interpret.

**Current status**: Phase 1 complete 

**Key achievements in v0.1**:
- Isolated, reproducible Python environment configured
- Provider-agnostic LLM interface built: switching between free (Ollama) and commercial
  (OpenAI, Anthropic) providers requires only one `.env` file change
- Budget protection in place before any API calls are made
- Full Git workflow operational with feature branches and version tagging

---

## 2. Problem Statement

### Why this project exists

Maritime fuel management companies generate complex quantitative risk reports daily:
Value at Risk figures, CVaR calculations, delta/gamma exposures, hedge effectiveness ratios.
These metrics are essential for risk management but create a communication gap between
risk analysts who produce them and senior managers or clients who need to act on them.

### What business problem it solves

This system acts as an intelligent interpreter: given a snapshot of risk metrics, it
generates a coherent natural language explanation tailored to the audience. A risk manager
can ask "What is our current fuel price exposure?" and receive a paragraph-length answer
in plain English, grounded in the actual metric data, with citations to the knowledge base.

### Who benefits

- **Maritime shipping companies**: Fleet operators with fuel price exposure
- **Bunker traders and brokers**: Need to explain hedging positions to clients
- **Risk managers**: Can produce stakeholder reports faster
- **Non-technical executives**: Can understand risk positions without reading spreadsheets
- **Researchers**: Demonstrates applicability of LLM systems to structured financial domains

---

## 3. Architecture Overview

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│                   (Streamlit — Phase 5)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ natural language query
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                                │
│              (LangGraph Supervisor — Phase 4)                  │
│   Routes query to the appropriate specialist agent             │
└──────────┬──────────────────┬───────────────────┬──────────────┘
           │                  │                   │
           ▼                  ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  RISK EXPLAINER  │ │  HEDGE ADVISOR   │ │  MODEL MONITOR   │
│     AGENT        │ │     AGENT        │ │     AGENT        │
│  (Phase 3)       │ │  (Phase 4)       │ │  (Phase 4)       │
│                  │ │                  │ │                  │
│  Answers: VaR,   │ │  Answers: hedge  │ │  Answers: model  │
│  CVaR, exposure  │ │  positions,      │ │  drift, accuracy │
│  questions       │ │  strategy        │ │  degradation     │
└────────┬─────────┘ └────────┬─────────┘ └──────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAG PIPELINE (Phase 2)                       │
│   1. Embed query → 2. Retrieve from ChromaDB → 3. Augment LLM   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
┌──────────────────┐               ┌──────────────────┐
│   VECTOR STORE   │               │   LLM PROVIDER   │
│   (ChromaDB)     │               │ Ollama / OpenAI  │
│                  │               │   / Anthropic    │
│  Maritime docs,  │               │                  │
│  risk metrics,   │               │  (Abstracted —   │
│  hedging guides  │               │   one .env line  │
│                  │               │   to switch)     │
└──────────────────┘               └──────────────────┘
```

### 3.2 Technology Stack

**Component:** Agent Framework
**Technology:** LangGraph
**Why This Choice:** Designed specifically for stateful multi-agent workflows; supervisor pattern is well-documented; active maintenance by LangChain team

**Component:** LLM (default)
**Technology:** Ollama / llama3.1:8b
**Why This Choice:** Free, runs locally, no API key, full privacy, reproducible

**Component:** LLM (evaluation)
**Technology:** OpenAI GPT-4o-mini
**Why This Choice:** High quality, very low cost (~$0.50 for full dissertation), widely cited in research

**Component:** Vector Database
**Technology:** ChromaDB
**Why This Choice:** Lightweight, runs embedded (no server needed), Python-native, well-supported in LangChain

**Component:** Embeddings (default)
**Technology:** nomic-embed-text via Ollama
**Why This Choice:** Free, local, 768-dimensional, good performance for English domain text

**Component:** UI
**Technology:** Streamlit
**Why This Choice:** Python-native, no JavaScript needed, rapid prototyping, renders markdown

**Component:** Language
**Technology:** Python 3.12
**Why This Choice:** Latest stable, required for type hint syntax used (`dict[str, Any]`), LangChain targets 3.10+

**Component:** Dependency management
**Technology:** pip + requirements.txt
**Why This Choice:** Simple, reproducible, no Conda required

**Component:** Version control
**Technology:** Git with feature branches
**Why This Choice:** Standard practice; branch-per-phase maps to dissertation methodology chapters


### 3.3 Design Decisions

#### Decision 1: Abstract LLM Provider Interface

**Decision**: Build a `BaseLLMProvider` abstract class that all LLM implementations inherit from.

**Context**: Need to support Ollama (free, local) for development and OpenAI/Anthropic
(paid, cloud) for high-quality evaluation outputs — without duplicating agent code.

**Options Considered**:
- Directly import `ChatOllama` wherever LLM is needed (simple, but locks provider into every file)
- LangChain's `BaseChatModel` (viable, but ties us to LangChain internals)
- Custom abstract class (chosen)

**Rationale**: A custom abstract class gives us full control, is easy to explain in the
dissertation methodology section, and makes provider switching a single `.env` variable change.

**Consequences**: Slightly more boilerplate upfront; saves significant refactoring effort
if we add a fourth provider later or if a package API changes.

---

#### Decision 2: Ollama as Default with Automatic Cloud Fallback

**Decision**: Default to Ollama; automatically fall back to OpenAI if Ollama is not running
and an OpenAI key is set.

**Context**: Student budget constraint — zero API cost during development and testing.

**Rationale**: Ollama is free and sufficient for testing system behaviour. Cloud APIs are
reserved for evaluation runs that will appear in the dissertation. Automatic fallback
prevents silent failures during development.

**Consequences**: System requires Ollama to be running locally (`ollama serve`). This is
a reasonable constraint for a development environment. Production deployment would always
specify a cloud provider explicitly.

---

#### Decision 3: ChromaDB with Local Persistence

**Decision**: Use ChromaDB in persistent mode, storing data in `data/embeddings/chroma_store/`.

**Context**: Need a vector database that is easy to set up, requires no separate server
process, and works offline for development.

**Options Considered**:
- Pinecone (cloud, requires account and billing)
- Weaviate (requires Docker)
- FAISS (in-memory only, no persistence without custom serialisation)
- ChromaDB (chosen)

**Rationale**: ChromaDB runs embedded in the Python process, persists to disk automatically,
and has first-class LangChain integration. The `data/embeddings/` directory is git-ignored
so the large binary index is not committed.

**Consequences**: ChromaDB 0.6.x has a different API from 0.4.x — the `requirements.txt`
is pinned to `0.6.3` to avoid breaking changes.

---

#### Decision 4: Pinned requirements.txt

**Decision**: Pin all dependencies to exact versions rather than using `>=` version ranges.

**Context**: Reproducibility is critical for a dissertation — anyone (supervisor, examiner,
future researcher) must be able to recreate the exact environment.

**Rationale**: LangChain in particular has breaking API changes between minor versions.
Pinning ensures the system behaves identically across all machines and at any future date.

**Consequences**: Manual effort to update versions if security patches are needed. Acceptable
trade-off for a research project with a defined end date.

---

## 4. Component Deep-Dive

### 4.1 Configuration System (`config/`)

#### Purpose
Centralises all runtime parameters so that no values are hardcoded in business logic.
The entire system's behaviour can be changed by editing a single `.env` file.

#### How It Works
1. `settings.py` loads `.env` using `python-dotenv` at import time.
2. All other modules import specific values from `settings.py`, `llm_config.py`, or
   `budget_config.py` — never directly from `os.getenv()`.
3. This single point of truth means adding a new setting never requires grep-and-replace
   across the codebase.

#### Code Structure
```
config/
├── __init__.py          — Package marker with documentation
├── settings.py          — Paths, logging, project name, ChromaDB location
├── llm_config.py        — Provider definitions, model names, cost rates
└── budget_config.py     — Monthly budget, alert threshold, CSV log location
```

#### Key Functions Explained

```python
# config/llm_config.py

def get_llm_config(provider: str | None = None) -> dict[str, Any]:
    """
    Returns configuration for the named provider (or the default from .env).

    How it works:
    1. If provider arg is None, reads LLM_PROVIDER from environment.
    2. Looks up that name in the LLM_PROVIDERS dictionary.
    3. Returns a copy of the dict with "provider" key added.

    Why designed this way:
    - Callers get a plain dict (no hidden state, easy to inspect/test).
    - The LLM_PROVIDERS dict is the single place to update costs or add models.
    """
```

#### Example Usage
```python
from config.llm_config import get_llm_config

config = get_llm_config()           # Uses .env default
print(config["model"])              # "llama3.1:8b" (if LLM_PROVIDER=ollama)

config_openai = get_llm_config("openai")
print(config_openai["cost_per_1k_input"])   # 0.00015
```

---

### 4.2 LLM Provider Interface (`src/llm_provider.py`)

#### Purpose
Provides a single import point for any part of the system that needs to call an LLM.
The agent code, RAG pipeline, and evaluation runner all call `get_llm_provider()` without
knowing (or caring) which underlying model is being used.

#### How It Works
1. `BaseLLMProvider` defines the interface: `invoke()` and `get_token_counts()`.
2. Three concrete classes implement it: `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`.
3. Each wraps the corresponding LangChain chat model (`ChatOllama`, `ChatOpenAI`, `ChatAnthropic`).
4. `get_llm_provider()` is the factory function — it reads the provider name, checks
   availability (for Ollama), and returns the appropriate instance.
5. Lazy initialisation: the LangChain model object is only created on the first `invoke()`
   call, not at import time — this speeds up startup and avoids errors if a provider's
   package is installed but not configured.

#### Code Structure
```
src/llm_provider.py
├── is_ollama_available()      — Pings localhost:11434 to check if Ollama is running
├── BaseLLMProvider (ABC)      — Abstract interface: invoke(), get_token_counts()
├── OllamaProvider             — Wraps ChatOllama; uses word-count token estimation
├── OpenAIProvider             — Wraps ChatOpenAI; uses tiktoken for accurate counts
├── AnthropicProvider          — Wraps ChatAnthropic; uses word-count estimation
└── get_llm_provider()         — Factory: reads .env, checks availability, returns instance
```

#### Key Functions Explained

```python
def get_llm_provider(provider: Optional[str] = None) -> BaseLLMProvider:
    """
    Returns a ready-to-use provider instance.

    How it works:
    1. Reads LLM_PROVIDER from .env if no override given.
    2. If Ollama requested but not running, and OpenAI key exists → falls back
       to OpenAI with a warning log message.
    3. If neither works → raises RuntimeError with instructions.
    4. Looks up the concrete class in _PROVIDER_MAP and instantiates it.

    Why designed this way:
    - Callers never import OllamaProvider directly — they always go through
      get_llm_provider(). This is the dependency inversion principle.
    - The fallback logic is centralised here, not scattered across agents.
    """
```

#### Example Usage
```python
from src.llm_provider import get_llm_provider

# Default usage — uses LLM_PROVIDER from .env
llm = get_llm_provider()
response = llm.invoke(
    prompt="What does a VaR of $2.3M at 95% confidence mean?",
    system_prompt="You are a maritime risk analyst. Explain in plain English."
)
print(response)

# Explicitly request a specific provider (e.g., for evaluation runs)
llm_openai = get_llm_provider("openai")
```

---

### 4.3 Cost Tracker (`src/cost_tracker.py`)

#### Purpose
Ensures the project stays within the £10/month budget. Logs every API call to a CSV
file so the dissertation can include a resource utilisation appendix. Ollama calls are
logged at $0.00 to capture token usage statistics even when no money is spent.

#### How It Works
1. On initialisation, reads the existing CSV log and restores the current month's
   cumulative spend (so the budget check is accurate if the program is restarted).
2. On each `log_usage()` call: calculates cost from per-token rates in `llm_config.py`,
   checks against the monthly budget, appends a row to the CSV, and logs a warning if
   spending crosses the 80% alert threshold.
3. `get_report()` returns a summary dict used by the Streamlit UI to show the cost panel.

#### Code Structure
```
src/cost_tracker.py
├── BudgetExceededError         — Custom exception raised when budget would be exceeded
└── CostTracker
    ├── __init__()              — Loads config, creates CSV if needed, restores spend
    ├── log_usage()             — Main method: calculate, check, write, alert
    ├── check_budget()          — Boolean check before expensive operations
    ├── get_report()            — Summary dict for UI display
    ├── reset_month()           — Reset counter at start of new billing month
    ├── _calculate_cost()       — Per-token cost arithmetic
    ├── _ensure_log_file()      — Creates CSV with headers if missing
    ├── _restore_from_log()     — Re-reads CSV to recover cumulative spend after restart
    ├── _write_row()            — Appends one row to CSV
    └── _check_alert_threshold() — Logs WARNING when 80% of budget is used
```

#### Example Usage
```python
from src.cost_tracker import CostTracker

tracker = CostTracker()  # Uses defaults from budget_config.py

# After an LLM call, log the usage
tracker.log_usage(
    provider="openai",
    model="gpt-4o-mini",
    input_tokens=156,
    output_tokens=312,
    query_summary="Explain fuel price VaR exposure",
)

# Check remaining budget
report = tracker.get_report()
print(f"Spent: ${report['current_spend_usd']:.4f} / ${report['monthly_budget_usd']}")
print(f"Remaining: ${report['remaining_budget_usd']:.4f}")
```

---

## 5. Data Architecture

### 5.1 Knowledge Base Structure (Phase 2 — to be populated)

```
data/documents/
├── risk_metrics/      # VaR methodology, CVaR, Greeks definitions
├── hedging/           # Hedging strategy documentation, instruments
└── maritime/          # Maritime-specific: MARPOL regulations, bunker price sources
```

Documents will be loaded in Phase 2. For Phase 1, these directories are empty placeholders.

### 5.2 Synthetic Data (Phase 2 — to be generated)

```
data/synthetic/
├── risk_metrics.json   # Simulated VaR/CVaR snapshots for multiple vessels
├── price_data.csv      # Simulated VLSFO/HSFO price time series
└── scenarios.json      # What-if scenarios (price shock, hedge unwind)
```

Synthetic data allows testing the full pipeline without requiring real company data,
which is confidential. The synthetic generator will be built in Phase 2.

### 5.3 Vector Store

ChromaDB will store document chunks in `data/embeddings/chroma_store/` (git-ignored).
Configuration:
- **Embedding model**: `nomic-embed-text` via Ollama (768 dimensions, free)
- **Chunk size**: 512 tokens with 50-token overlap (to be tuned in Phase 2)
- **Retrieval**: top-k=5 most relevant chunks per query

---

## 6. Agent System (Phase 3–4 — not yet implemented)

Three agents are planned. This section documents the design intent.

### 6.1 Orchestrator
- Built with LangGraph's supervisor pattern
- Routes queries based on keyword classification and semantic similarity
- Maintains conversation state across multi-turn interactions

### 6.2 Planned Agents

| Agent | Handles | RAG Source |
|-------|---------|------------|
| Risk Explainer | VaR, CVaR, exposure queries | risk_metrics/ documents + live synthetic data |
| Hedge Advisor | Hedging positions, strategy | hedging/ documents |
| Model Monitor | Drift detection, accuracy | model performance logs |

---

## 7. Prompt Engineering (Phase 3 — not yet implemented)

Prompt templates will follow these principles:
- **Role definition**: Each agent has a clear persona (e.g., "You are a senior maritime risk analyst")
- **Audience specification**: Prompts specify the target audience for the explanation
- **Format constraints**: Structured output with summary, detail, and caveats sections
- **Grounding instruction**: "Base your answer only on the provided context; do not speculate"

---

## 8. Evaluation Methodology (Phase 6 — not yet implemented)

Planned hybrid approach:
1. **BERTScore** — automated semantic similarity to reference answers (all 25-30 test queries)
2. **Manual rubric** — 4-criteria scoring by author on 20 sampled queries
3. **LLM-as-Judge** — GPT-4o-mini scoring the same 20 queries for cross-validation

Rubric criteria:
- **Accuracy** (0–5): Does the response correctly state the risk metric values?
- **Clarity** (0–5): Would a non-technical reader understand this?
- **Completeness** (0–5): Does it cover all expected elements?
- **Domain Relevance** (0–5): Is the language appropriate for maritime finance?

---

## 9. Challenges and Solutions

| Challenge | Impact | Solution | Lesson Learned |
|-----------|--------|----------|----------------|
| LangChain API changes between minor versions | Breaking code between sessions | Pinned all versions in `requirements.txt` | Always pin for research; use `>=` only in libraries |
| Ollama token counting not surfaced by LangChain | Inaccurate cost estimates for Ollama calls | Word-count heuristic (~1.3 tokens/word) | Document estimation approach in dissertation methodology |
| Existing `.gitignore` had heredoc artifacts (`EOF` in content) | Corrupted ignore rules | Rewrote file from scratch | Always verify generated config files before committing |

---

## 10. Academic Relevance

### 10.1 Research Questions Addressed

This version (v0.1) establishes the foundation. Research questions will be addressed in later phases:

- **RQ1**: Can LLM-based agents accurately explain maritime fuel risk metrics in natural language?
  — *Addressed in Phase 3 (Risk Agent) and Phase 6 (Evaluation)*
- **RQ2**: Does RAG-augmented generation produce more accurate explanations than base LLM?
  — *Addressed in Phase 2 (RAG) and Phase 6 (Evaluation with/without RAG comparison)*
- **RQ3**: Can multi-agent routing improve response relevance compared to a single agent?
  — *Addressed in Phase 4 (Multi-Agent) and Phase 6 (Evaluation)*

### 10.2 Literature Connections

**RAG and LLM systems**: This project implements the RAG paradigm described by Lewis et al. (2020),
combining parametric knowledge (LLM weights) with non-parametric retrieval (ChromaDB).

**Maritime risk**: The domain knowledge draws on maritime fuel risk management literature
including bunker price volatility, VLSFO/HSFO spread risk, and IMO regulatory compliance
(MARPOL Annex VI).

**Multi-agent LLMs**: The supervisor-worker architecture follows the pattern described in
LangGraph documentation and recent multi-agent LLM research (2023–2024).

### 10.3 Methodology Mapping

| Dissertation Section | Project Component | Status |
|----------------------|-------------------|--------|
| 3.1 Literature Review | Academic references in docs/ | Ongoing |
| 4.1 System Design | Architecture in this document | ✅ Complete |
| 4.2 Environment Setup | `config/`, `requirements.txt` | ✅ Complete |
| 4.3 RAG Implementation | `src/vector_store.py`, `src/rag_pipeline.py` | Phase 2 |
| 4.4 Agent Design | `agents/`, `prompts/` | Phase 3–4 |
| 4.5 Evaluation | `evaluation/` | Phase 6 |

---

## 11. Cost Analysis

### 11.1 API Costs Incurred (v0.1)

| Provider | Tokens Used | Cost USD |
|----------|-------------|----------|
| Ollama | 0 (setup only) | $0.00 |
| OpenAI | 0 (not yet used) | $0.00 |
| **Total** | **0** | **$0.00** |

No API calls made in Phase 1. All costs begin in Phase 3 when LLM inference starts.

### 11.2 Resource Usage

| Activity | Time Estimate |
|----------|---------------|
| Phase 1 implementation | ~3 hours |
| Environment setup (manual) | ~30 minutes |

---

## 12. Next Steps

### 12.1 Completed in This Version (v0.1)
- [x] Git repository with branching strategy
- [x] Virtual environment (`env_dissertation`, Python 3.12)
- [x] Full folder structure (12 directories)
- [x] `requirements.txt` with pinned dependencies
- [x] `.env.example` and `.gitignore`
- [x] `config/` package: settings, LLM config, budget config
- [x] `src/llm_provider.py`: abstract interface + 3 implementations
- [x] `src/cost_tracker.py`: CSV logging, budget alerts, spend restoration
- [x] `README.md` with quick-start guide

### 12.2 Planned for Next Version (v0.2 — Phase 2: RAG Foundation)
- [ ] `src/embeddings.py`: multi-provider embedding generation
- [ ] `src/vector_store.py`: ChromaDB setup and CRUD operations
- [ ] `src/document_loader.py`: load PDFs and Markdown into vector store
- [ ] `src/rag_pipeline.py`: retrieve + generate pipeline
- [ ] `data/synthetic/`: generate test risk data (VaR snapshots, prices, scenarios)
- [ ] Sample maritime domain documents in `data/documents/`
- [ ] Unit tests for vector store and RAG pipeline

### 12.3 Things You Need to Do Before Phase 2
- [ ] Copy `.env.example` to `.env` (no keys needed yet — Ollama default)
- [ ] Run `pip install -r requirements.txt` in `env_dissertation`
- [ ] Confirm Ollama is running: `ollama serve` in a separate terminal
- [ ] Confirm embedding model available: `ollama pull nomic-embed-text`
- [ ] Gather at least one maritime risk document for the knowledge base
  (even a Wikipedia article on VaR saved as `.txt` is enough to test)

### 12.4 Known Issues / Limitations
- `src/llm_provider.py` is written but not yet tested end-to-end (Phase 2 will add integration tests)
- ChromaDB 0.6.x API: `chromadb.Client()` is deprecated; use `chromadb.PersistentClient()` — already reflected in the planned Phase 2 implementation

---

## 13. Appendices

### Appendix A: Glossary

| Term | Definition |
|------|------------|
| VaR | Value at Risk — maximum expected loss at a given confidence level over a time horizon |
| CVaR | Conditional Value at Risk (Expected Shortfall) — average loss beyond the VaR threshold |
| RAG | Retrieval-Augmented Generation — LLM response augmented with retrieved context documents |
| ChromaDB | Open-source vector database for storing and querying document embeddings |
| LangGraph | Python library for building stateful multi-agent LLM workflows using directed graphs |
| Ollama | Tool for running open-source LLMs locally (no API key, no cost) |
| Embedding | Numerical vector representation of text, used for semantic similarity search |
| VLSFO | Very Low Sulphur Fuel Oil — maritime fuel compliant with IMO 2020 regulations |
| HSFO | High Sulphur Fuel Oil — cheaper but restricted to vessels with scrubbers |
| MARPOL | International Convention for the Prevention of Pollution from Ships |
| LLM | Large Language Model (e.g., GPT-4, Claude, Llama) |
| Bunker | Maritime term for ship fuel |

### Appendix B: File Reference

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `config/settings.py` | Paths and logging setup | `PROJECT_ROOT`, `DATA_DIR`, `LOG_LEVEL` |
| `config/llm_config.py` | Provider definitions | `LLM_PROVIDERS`, `get_llm_config()`, `get_embedding_config()` |
| `config/budget_config.py` | Budget parameters | `MONTHLY_BUDGET_USD`, `COST_LOG_FILE` |
| `src/llm_provider.py` | LLM abstraction | `BaseLLMProvider`, `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `get_llm_provider()` |
| `src/cost_tracker.py` | Budget tracking | `CostTracker`, `BudgetExceededError` |

### Appendix C: Configuration Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `ollama` | Active LLM provider |
| `OLLAMA_MODEL` | `llama3.1:8b` | Ollama model name |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `OPENAI_API_KEY` | (empty) | OpenAI authentication |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name |
| `ANTHROPIC_API_KEY` | (empty) | Anthropic authentication |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic model name |
| `EMBEDDING_PROVIDER` | `ollama` | Active embedding provider |
| `MONTHLY_BUDGET_USD` | `10.00` | Monthly API spend limit |
| `BUDGET_ALERT_THRESHOLD` | `0.80` | Alert at 80% budget usage |
| `LOG_LEVEL` | `INFO` | Python logging verbosity |
| `CHROMA_PERSIST_DIR` | `data/embeddings/chroma_store` | ChromaDB storage path |

### Appendix D: Useful Commands

```bash
# Activate virtual environment
source env_dissertation/bin/activate

# Install / update dependencies
pip install -r requirements.txt

# Start Ollama (required for default LLM provider)
ollama serve

# Pull required models (first time only)
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# Run tests
pytest tests/ -v

# Check Python version
python --version

# See git branch status
git branch -a
git log --oneline --graph

# Run Streamlit UI (Phase 5+)
streamlit run ui/app.py

# Check what's in the ChromaDB store (Phase 2+)
python -c "import chromadb; c = chromadb.PersistentClient('data/embeddings/chroma_store'); print(c.list_collections())"
```
