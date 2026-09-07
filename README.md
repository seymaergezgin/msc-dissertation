# AI-Based Narrative Risk Reporting System for Maritime Fuel Management

**MSc Engineering Management Dissertation**
University of Greenwich | Supervisor: Dr. Mike Sharp

---

## What This Project Does

This system converts quantitative maritime fuel risk metrics (VaR, CVaR, Greeks, hedge ratios)
into plain English narratives that non-technical stakeholders can understand. It uses a
Multi-Agent LLM architecture with Retrieval-Augmented Generation (RAG) so responses are
grounded in domain knowledge rather than hallucinated.

```
User Query
    │
    ▼
┌─────────────────────────────┐
│  Orchestrator (LangGraph)   │  ← Decides which agent handles the query
└──────────┬──────────────────┘
           │
    ┌──────┼──────┐
    ▼      ▼      ▼
 Risk   Hedge  Model
 Agent  Agent  Monitor
 (RAG)  (RAG)
```

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Runtime |
| Ollama | Latest | Free local LLM (no API key needed) |
| Git | Any | Version control |

### 1. Clone and navigate

```bash
git clone https://github.com/seymaergezgin/msc-dissertation.git
cd thesis-risk-narrative
```

### 2. Activate the virtual environment

```bash
# The virtual environment is named env_dissertation
source env_dissertation/bin/activate   # Mac / Linux
# env_dissertation\Scripts\activate    # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum, confirm LLM_PROVIDER=ollama
```

### 5. Start Ollama (required for default setup)

```bash
ollama serve          # Start the server (keep this terminal open)
ollama pull llama3.1:8b        # First-time only
ollama pull nomic-embed-text   # First-time only
```

### 6. Run the application (Phase 5+)

```bash
streamlit run ui/app.py
```

---

## Project Structure

```
thesis-risk-narrative/
├── config/          # Settings, LLM provider config, budget limits
├── src/             # Core: RAG pipeline, LLM provider, cost tracker, orchestrator
├── agents/          # Three specialist agents + base class
├── prompts/         # Prompt templates for each agent
├── evaluation/      # Test queries, metrics, evaluation runner
├── ui/              # Streamlit web interface
├── tests/           # pytest test suite
├── data/            # Documents, synthetic data, ChromaDB store, cost logs
├── docs/versions/   # Living documentation updated at each phase
└── notebooks/       # Jupyter exploration notebooks
```

## Switching LLM Providers

Change one line in `.env`:

```bash
LLM_PROVIDER=ollama      # Free, local — default
LLM_PROVIDER=openai      # Requires OPENAI_API_KEY
LLM_PROVIDER=anthropic   # Requires ANTHROPIC_API_KEY
```

No code changes needed.

## Development Phases

| Phase | Branch | Status | Tag |
|-------|--------|--------|-----|
| 1 — Setup & Config | `feature/phase1-setup` | Complete | `v0.1-setup` |
| 2 — RAG Foundation | `feature/phase2-rag` | Pending | `v0.2-rag` |
| 3 — Risk Agent | `feature/phase3-risk-agent` | Pending | `v0.3-agent` |
| 4 — Multi-Agent | `feature/phase4-multi-agent` | Pending | `v0.4-multi` |
| 5 — UI | `feature/phase5-ui` | Pending | `v0.5-ui` |
| 6 — Evaluation | `feature/phase6-evaluation` | Pending | `v1.0` |

## Cost Tracking

All API calls are logged to `data/cost_logs/api_costs.csv`.
Default monthly budget: **$10.00** (configurable via `MONTHLY_BUDGET_USD` in `.env`).
Ollama calls cost $0.00 and are still logged for token count statistics.

## Running Tests

```bash
pytest tests/ -v
```

## Documentation

Detailed documentation for each phase is in [docs/versions/](docs/versions/).
Start with [PROJECT_DOC_v0.1.md](docs/versions/PROJECT_DOC_v0.1.md).

---

*Built for academic research. 100% independent from any company codebase.*
