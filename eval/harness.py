# RAGAS eval pipeline
#
# Runs the review agent on every labelled PR fixture in eval/fixtures/prs, then scores it:
#   - RAGAS faithfulness      : are the comments' claims supported by the retrieved codebase context?
#   - RAGAS answer relevancy  : are the comments about the actual change?
#   - comment precision/recall: do the comments land on the ground-truth lines (same file, ±2 lines)?
# Each run is appended to eval/results/history.jsonl, which the Streamlit dashboard reads.
#
# usage: python -m eval.harness [--only 01-sql-injection,14-clean-change] [--skip-index] [--no-ragas]
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from github_parsing.diff_parser import parse_patch, format_diff
import settings

HERE = Path(__file__).parent
FIXTURES_DIR = HERE / "fixtures" / "prs"
CODEBASE_DIR = HERE / "fixtures" / "codebase"
HISTORY_FILE = HERE / "results" / "history.jsonl"
EVAL_COLLECTION = os.getenv("EVAL_COLLECTION", "eval_codebase")
LINE_TOLERANCE = 2

# RAGAS always sends temperature/top_p, which current Claude models reject, so the judge
# defaults to an OpenAI model (the OpenAI key is already required for embeddings)
JUDGE_MODEL = os.getenv("RAGAS_JUDGE_MODEL", "gpt-4o-mini")


def load_fixtures(only: list[str] | None = None) -> list[dict]:
    fixtures = [json.loads(p.read_text()) for p in sorted(FIXTURES_DIR.glob("*.json"))]
    if only:
        fixtures = [f for f in fixtures if f["id"] in only]
    return fixtures


def fixture_diff(fixture: dict) -> list[dict]:
    lines = []
    for file in fixture["files"]:
        lines.extend(parse_patch(file["filename"], file["patch"]))
    return lines


def match_comments(predicted: list[dict], expected: list[dict], tolerance: int = LINE_TOLERANCE) -> int:
    """Count true positives: each expected comment matches at most one predicted comment on the same file within ±tolerance lines."""
    used = set()
    true_positives = 0
    for exp in expected:
        for i, pred in enumerate(predicted):
            if i in used:
                continue
            if pred["file_path"] == exp["file_path"] and abs(pred["line_number"] - exp["line_number"]) <= tolerance:
                used.add(i)
                true_positives += 1
                break
    return true_positives


def safe_ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def comments_as_text(comments: list[dict]) -> str:
    return "\n".join(f"{c['file_path']}:{c['line_number']} [{c['severity']}] {c['comment']}" for c in comments)


class RagasScorer:
    def __init__(self):
        from ragas.embeddings import OpenAIEmbeddings
        from ragas.llms import llm_factory
        from ragas.metrics.collections import AnswerRelevancy, Faithfulness

        llm = llm_factory(JUDGE_MODEL, provider="openai", client=settings.get_openai())
        embeddings = OpenAIEmbeddings(client=settings.get_openai(), model=settings.EMBED_MODEL)
        self.faithfulness = Faithfulness(llm=llm)
        self.answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)

    def score(self, diff_text: str, comments: list[dict], contexts: list[str]) -> dict:
        scores = {"faithfulness": None, "answer_relevancy": None}
        if not comments:
            return scores  # nothing to judge (an empty review is scored by precision/recall instead)
        question = f"Review this pull request diff and point out problems:\n{diff_text}"
        answer = comments_as_text(comments)
        try:
            if contexts:  # faithfulness is undefined without retrieved context
                scores["faithfulness"] = float(self.faithfulness.score(
                    user_input=question, response=answer, retrieved_contexts=contexts).value)
            scores["answer_relevancy"] = float(self.answer_relevancy.score(
                user_input=question, response=answer).value)
        except Exception as e:
            print(f"  RAGAS scoring failed: {e!r}")
        return scores


def mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return None


def run_eval(only: list[str] | None = None, skip_index: bool = False, use_ragas: bool = True) -> dict:
    from agent.loop import review_diff
    from ingestion.embedder import ingest_repository

    fixtures = load_fixtures(only)
    if not fixtures:
        raise SystemExit("No fixtures matched.")

    if not skip_index:
        count = ingest_repository(str(CODEBASE_DIR), EVAL_COLLECTION)
        print(f"Indexed {count} chunks from the eval codebase into '{EVAL_COLLECTION}'")

    scorer = RagasScorer() if use_ragas else None
    results = []
    for fixture in fixtures:
        start = time.time()
        diff = fixture_diff(fixture)
        review = review_diff(diff, collection_name=EVAL_COLLECTION)
        predicted, expected = review["comments"], fixture["expected"]
        tp = match_comments(predicted, expected)

        row = {
            "id": fixture["id"],
            "title": fixture["title"],
            "n_expected": len(expected),
            "n_predicted": len(predicted),
            "true_positives": tp,
            "precision": safe_ratio(tp, len(predicted)),
            "recall": safe_ratio(tp, len(expected)),
            "rounds": review["rounds"],
            "queries": review["queries"],
            "comments": predicted,
            "seconds": round(time.time() - start, 1),
        }
        row.update(scorer.score(format_diff(diff), predicted, review["contexts"]) if scorer
                   else {"faithfulness": None, "answer_relevancy": None})
        results.append(row)
        print(f"{fixture['id']:<28} tp={tp}/{len(expected)} predicted={len(predicted)} "
              f"faith={fmt(row['faithfulness'])} relev={fmt(row['answer_relevancy'])} rounds={row['rounds']}")

    total_tp = sum(r["true_positives"] for r in results)
    total_pred = sum(r["n_predicted"] for r in results)
    total_exp = sum(r["n_expected"] for r in results)
    precision, recall = safe_ratio(total_tp, total_pred), safe_ratio(total_tp, total_exp)
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0

    run = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "judge_model": JUDGE_MODEL if use_ragas else None,
        "n_fixtures": len(results),
        "aggregate": {
            "faithfulness": mean([r["faithfulness"] for r in results]),
            "answer_relevancy": mean([r["answer_relevancy"] for r in results]),
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positives_on_clean": sum(r["n_predicted"] for r in results if r["n_expected"] == 0),
        },
        "fixtures": results,
    }
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(run) + "\n")
    return run


def fmt(value) -> str:
    return "  -  " if value is None else f"{value:.3f}"


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Run the PR review eval")
    arg_parser.add_argument("--only", help="comma-separated fixture ids")
    arg_parser.add_argument("--skip-index", action="store_true", help="reuse the existing eval collection")
    arg_parser.add_argument("--no-ragas", action="store_true", help="skip RAGAS (only precision/recall)")
    args = arg_parser.parse_args()

    run = run_eval(
        only=args.only.split(",") if args.only else None,
        skip_index=args.skip_index,
        use_ragas=not args.no_ragas,
    )
    print("\nAggregate:")
    for key, value in run["aggregate"].items():
        print(f"  {key:<26} {value if isinstance(value, int) else fmt(value)}")
    print(f"\nAppended run to {HISTORY_FILE}")
