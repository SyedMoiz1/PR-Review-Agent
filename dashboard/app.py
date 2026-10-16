# streamlit dashboard
#
# usage: streamlit run dashboard/app.py
import json
from pathlib import Path

import pandas as pd
import streamlit as st

HISTORY_FILE = Path(__file__).resolve().parent.parent / "eval" / "results" / "history.jsonl"
METRICS = ["faithfulness", "answer_relevancy", "precision", "recall", "f1"]


def load_runs() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    runs = []
    for line in HISTORY_FILE.read_text().splitlines():
        if line.strip():
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return runs


def pct(value) -> str:
    return "—" if value is None else f"{value:.2f}"


st.set_page_config(page_title="PR Review Agent · Eval", layout="wide")
st.title("PR Review Agent — eval dashboard")

runs = load_runs()
if not runs:
    st.info("No eval runs yet. Run `python -m eval.harness` to create one.")
    st.stop()

# ── latest run headline ────────────────────────────────────────────────
latest = runs[-1]
previous = runs[-2] if len(runs) > 1 else None
st.caption(
    f"Latest run {latest['timestamp']} · commit {latest.get('git_sha') or '—'} · "
    f"model {latest.get('model')} · judge {latest.get('judge_model') or 'none'} · {latest['n_fixtures']} fixtures"
)
cols = st.columns(len(METRICS) + 1)
for col, metric in zip(cols, METRICS):
    value = latest["aggregate"].get(metric)
    delta = None
    if previous and value is not None and previous["aggregate"].get(metric) is not None:
        delta = f"{value - previous['aggregate'][metric]:+.2f}"
    col.metric(metric.replace("_", " ").title(), pct(value), delta)
cols[-1].metric("False positives (clean PRs)", latest["aggregate"].get("false_positives_on_clean", 0))

# ── scores over time ───────────────────────────────────────────────────
st.subheader("Scores over time")
history = pd.DataFrame([
    {"run": f"{r['timestamp'][:16]} {r.get('git_sha') or ''}".strip(), **{m: r["aggregate"].get(m) for m in METRICS}}
    for r in runs
]).set_index("run")
st.line_chart(history)

# ── per-fixture drill-down ─────────────────────────────────────────────
st.subheader("Per-fixture results")
run_labels = [f"{r['timestamp']} · {r.get('git_sha') or '—'} · {r.get('model')}" for r in runs]
selected = runs[st.selectbox("Run", range(len(runs)), index=len(runs) - 1, format_func=lambda i: run_labels[i])]

table = pd.DataFrame([
    {
        "fixture": f["id"],
        "expected": f["n_expected"],
        "predicted": f["n_predicted"],
        "true positives": f["true_positives"],
        "precision": f["precision"],
        "recall": f["recall"],
        "faithfulness": f["faithfulness"],
        "answer relevancy": f["answer_relevancy"],
        "retrieval rounds": f["rounds"],
        "seconds": f["seconds"],
    }
    for f in selected["fixtures"]
])
st.dataframe(table, width="stretch", hide_index=True)

fixture_id = st.selectbox("Inspect fixture", [f["id"] for f in selected["fixtures"]])
fixture = next(f for f in selected["fixtures"] if f["id"] == fixture_id)
left, right = st.columns(2)
with left:
    st.markdown("**Agent comments**")
    if not fixture["comments"]:
        st.write("_No comments._")
    for c in fixture["comments"]:
        st.markdown(f"- `{c['file_path']}:{c['line_number']}` **{c['severity']}** — {c['comment']}")
with right:
    st.markdown("**Retrieval queries**")
    if not fixture["queries"]:
        st.write("_No retrieval._")
    for q in fixture["queries"]:
        st.markdown(f"- {q}")
