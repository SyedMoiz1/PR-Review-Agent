# PR Review Agent

An AI-powered GitHub PR review agent that posts inline, codebase-grounded review comments — indistinguishable from a human reviewer.

**Stack:** Python · FastAPI · PyGithub · tree-sitter · OpenAI (`text-embedding-3-small`) · Qdrant · Anthropic / OpenAI tool use · RAGAS · Streamlit · Fly.io

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
   Tool-use Loop (Claude / GPT-4o, swappable)
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

At review time, the agent's retrieval queries are embedded with the same model and run against Qdrant via approximate nearest-neighbor search. The most semantically relevant existing code (with file path and line range) is surfaced as context for the agent.

**3. Agentic Loop**

The LLM runs inside a tool-use loop with a single tool: `retrieve_context(query)`. The model decides autonomously when it needs more context, issues its own retrieval queries, and iterates — up to a hard cap of 3 rounds — before producing its final review. The 3-round cap keeps API costs bounded while covering the vast majority of real review scenarios.

This self-directed retrieval is the architectural choice that separates this from a naive RAG pipeline. The agent can ask "how does this codebase handle auth elsewhere?" before commenting on an auth change, rather than receiving a fixed context window and generating from it.

**4. Output**

The agent returns structured output: `{ file_path, line_number, severity, comment }`, constrained by a JSON schema (`output_config.format` on Claude, `response_format` on GPT-4o). Comments that point outside the diff are dropped, since GitHub rejects a whole review if one comment is off-diff. The rest are posted as a single GitHub pull request review — inline on the specific lines, via PyGithub.

The provider is picked with `LLM_PROVIDER=anthropic` (default, `claude-opus-5-5`) or `LLM_PROVIDER=openai` (`gpt-4o`); override the model with `LLM_MODEL`.

---

## Eval

Quality is measured, not asserted.

- **15 labelled PR fixtures** (`eval/fixtures/prs/`) with ground-truth review comments, written against a small sample service (`eval/fixtures/codebase/shopapp`). Each PR breaks one of that codebase's conventions: SQL injection instead of parameterized `fetch_all`, `==` instead of `hmac.compare_digest`, float money instead of `to_money`, a missing `@require_admin`, an N+1 query instead of `items_for_orders`, and so on. One fixture is a clean change, so any comment on it counts as a false positive.
- **RAGAS** scores each run on:
  - *Faithfulness* — no hallucinated claims about the codebase (comments vs. retrieved chunks)
  - *Answer relevance* — comments are specific to the actual change
- **Comment precision / recall / F1**: a comment counts as a hit when it lands on the labelled file within ±2 lines.
- Every run is appended to `eval/results/history.jsonl` and charted over time in the Streamlit dashboard. `.github/workflows/eval.yml` runs the harness when agent, retrieval or ingestion code changes on `main` (it needs `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` repo secrets).

```bash
python -m eval.harness                       # index the sample codebase, run all 15 fixtures, score
python -m eval.harness --only 01-sql-injection,14-clean-change --skip-index
python -m eval.harness --no-ragas            # precision/recall only (no judge LLM calls)
```

To add a fixture, add an entry to `PRS` in `eval/fixtures/build_fixtures.py` and run `python -m eval.fixtures.build_fixtures`. Patches and ground-truth line numbers are generated from the "after" file content, so they're always consistent. The RAGAS judge defaults to `gpt-4o-mini` (`RAGAS_JUDGE_MODEL`), because RAGAS always sends `temperature`/`top_p`, and current Claude models reject those parameters.

---

## Setup

**Prerequisites:** Docker, Python 3.11+, a GitHub App or webhook secret, OpenAI API key, Anthropic API key (if using Claude).

```bash
# 1. Start Qdrant
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# fill in GITHUB_WEBHOOK_SECRET, GITHUB_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY

# 4. Index the codebase (re-run after large changes; it rebuilds the collection)
python -m ingestion.embedder --repo /path/to/target/repo

# 5. Start the webhook server
uvicorn github_parsing.webhook:app --reload

# 6. Start the dashboard (optional)
streamlit run dashboard/app.py
```

Expose the webhook endpoint via ngrok or deploy to Fly.io. Point your GitHub webhook to `/webhook` with `application/json` content type, and subscribe it to **Pull request** events. The token in `GITHUB_TOKEN` needs read/write access to pull requests.

To try the agent on an existing PR without posting anything:

```bash
python -m agent.loop owner/repo 42
```

## Deploy to Fly.io

```bash
fly launch --no-deploy        # creates the app; keep the included fly.toml
fly secrets set GITHUB_WEBHOOK_SECRET=... GITHUB_TOKEN=... OPENAI_API_KEY=... ANTHROPIC_API_KEY=... \
  QDRANT_URL=https://your-qdrant-host QDRANT_API_KEY=...
fly deploy
```

The webhook server reads `QDRANT_URL`/`QDRANT_API_KEY` to reach a hosted Qdrant (e.g. Qdrant Cloud). Index the target repo against that same instance by setting those variables locally before running step 4. `/health` is used as the Fly health check.

## Tests

```bash
pytest -q
```

The unit tests run offline: diff parsing, HMAC validation and event filtering, chunking, structured-output parsing, the 3-round retrieval cap (driven by a fake client), and fixture integrity. CI runs them on every push via `.github/workflows/tests.yml`.

## Project layout

```
settings.py              shared config + lazily-created OpenAI / Anthropic / Qdrant / GitHub clients
ingestion/chunker.py     tree-sitter → function/class chunks (repo-relative paths, 1-based lines)
ingestion/embedder.py    embed chunks, rebuild the Qdrant collection   (python -m ingestion.embedder --repo …)
retrieval/retriever.py   retrieve_context(query) → top-k chunks
agent/loop.py            tool-use loop (Claude or GPT-4o), 3-round cap, structured output
agent/prompt.py          system prompt
github_parsing/          webhook server, diff parser, review poster
eval/                    fixtures, harness, results history
dashboard/app.py         Streamlit eval dashboard
```
