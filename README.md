# PR Review Agent

An AI-powered GitHub PR review agent that posts inline, codebase-grounded review comments, indistinguishable from a human reviewer.

**Stack:** Python · FastAPI · PyGithub · tree-sitter · OpenAI (`text-embedding-3-small`) · Qdrant · LangChain · RAGAS · Streamlit · Fly.io

---

## Overview

Most LLM code review tools operate on the diff alone. This agent retrieves semantically relevant context from the full codebase before generating comments — so it can flag inconsistencies with existing patterns, not just surface-level issues in the changed lines.

Eval harness ships with 15 labelled PR fixtures and RAGAS scores tracked on every run.

---

## Architecture

```
GitHub Webhook (PR opened/updated)
        │
        ▼
FastAPI server — HMAC-SHA256 validation
        │
        ▼
Diff Parser — structured hunks (file, line range, content)
        │
        ├──► Embedder ──► Qdrant (ANN lookup)
        │                      │
        │              retrieve_context()
        │                      │
        ▼                      ▼
   LangChain Tool Loop (Claude / GPT-4o, swappable)
        │   ↑___________________│
        │   up to 3 retrieval rounds
        │
        ▼
Structured output (file, line, severity, comment)
        │
        ▼
PyGithub — inline PR review comments
```

**Codebase indexing** runs at setup time. tree-sitter parses source files into function- and class-level chunks; each chunk is embedded and upserted into a local Qdrant instance (Docker).

---

## How It Works

**1. Ingestion**

tree-sitter parses the codebase at the AST level, chunking by function and class boundaries rather than fixed line windows. This preserves semantic units, which materially improves retrieval precision — a 50-line function lands in one chunk, not split across two arbitrary windows.

**2. Retrieval**

At review time, each changed hunk from the diff is embedded and queried against Qdrant via approximate nearest-neighbor search. The most semantically relevant existing code is surfaced as context for the agent.

**3. Agentic Loop**

The LLM runs inside a LangChain tool loop with a single tool: `retrieve_context(query)`. The model decides autonomously when it needs more context, issues its own retrieval queries, and iterates — up to a hard cap of 3 rounds — before producing its final review. The 3-round cap keeps API cost~s bounded while covering the vast majority of real review scenarios.

This self-directed retrieval is the architectural choice that separates this from a naive RAG pipeline. The agent can ask "how does this codebase handle auth elsewhere?" before commenting on an auth change, rather than receiving a fixed context window and generating from it.

**4. Output**

The agent returns structured output: `{ file_path, line_number, severity, comment }`. Each comment is posted as a GitHub pull request review comment — inline on the specific line, via PyGithub.

---

## Eval

Quality is measured, not asserted.

- **15 labelled PR fixtures** with human-written ground-truth reviews
- **RAGAS** scores each run on:
  - *Faithfulness* — no hallucinated claims about the codebase
  - *Answer relevance* — comments are specific to the actual change
- Harness runs on every code change; scores are tracked over time in the Streamlit dashboard

---

## Setup

**Prerequisites:** Docker, Python 3.11+, a GitHub App or webhook secret, OpenAI API key, Anthropic API key (if using Claude).

```bash
# 1. Start Qdrant
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env .env.local
# fill in GITHUB_WEBHOOK_SECRET, GITHUB_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY

# 4. Index the codebase
python -m ingestion.embedder --repo /path/to/target/repo

# 5. Start the webhook server
uvicorn github.webhook:app --reload

# 6. Start the dashboard (optional)
streamlit run dashboard/app.py
```

Expose the webhook endpoint via ngrok or deploy to Fly.io. Point your GitHub webhook to `/webhook` with `application/json` content type.
