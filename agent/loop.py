# agentic tool loop
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import re
from github_parsing.diff_parser import get_pr_diff, format_diff, commentable_lines
from github_parsing.commenter import to_github_comments
from retrieval.retriever import retrieve_context, format_results
from agent.prompt import SYSTEM_PROMPT
from settings import COLLECTION_NAME, LLM_MODEL, LLM_PROVIDER, get_anthropic, get_openai

MAX_ROUNDS = 3
MAX_TOKENS = 16000
SEVERITIES = ["critical", "major", "minor", "nit"]
FINAL_NUDGE = "Retrieval limit reached. Give your final review now without further tool calls."

TOOL_DESCRIPTION = "Retrieves relevant code chunks from the codebase vector database based on a natural language query. Use this when you need to find how something is implemented before writing a review comment."
TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language description of the code context you need"
        }
    },
    "required": ["query"],
    "additionalProperties": False,
}

# structured output: the final answer is constrained to this schema
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "line_number": {"type": "integer"},
                    "severity": {"type": "string", "enum": SEVERITIES},
                    "comment": {"type": "string"},
                },
                "required": ["file_path", "line_number", "severity", "comment"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["comments"],
    "additionalProperties": False,
}

anthropic_tools = [{
    "name": "retrieve_context",
    "description": TOOL_DESCRIPTION,
    "input_schema": TOOL_PARAMETERS,
    "strict": True,
}]

openai_tools = [{
    "type": "function",
    "function": {
        "name": "retrieve_context",
        "description": TOOL_DESCRIPTION,
        "parameters": TOOL_PARAMETERS,
        "strict": True,
    },
}]


def display_messages(messages):
    RESET  = "\033[0m"
    PURPLE = "\033[95m"
    AMBER  = "\033[93m"
    TEAL   = "\033[96m"
    BLUE   = "\033[94m"
    GRAY   = "\033[90m"
    BOLD   = "\033[1m"

    print("\n" + "─" * 60)
    print(f"{BOLD}  conversation flow{RESET}")
    print("─" * 60 + "\n")

    for msg in messages:
        role    = msg["role"]
        content = msg["content"]

        if role == "user" and isinstance(content, str):
            print(f"{PURPLE}{BOLD}[user]{RESET}")
            print(f"  {content[:500]}\n")

        elif role == "assistant":
            for block in content:
                if block.type == "text":
                    print(f"{GRAY}{BOLD}[claude · text]{RESET}")
                    print(f"  {block.text}\n")
                elif block.type == "tool_use":
                    print(f"{AMBER}{BOLD}[tool_use · {block.name}]{RESET}")
                    print(f"  query : {block.input.get('query')}")
                    print(f"  id    : {block.id}\n")

        elif role == "user" and isinstance(content, list):
            for item in content:
                if item["type"] == "tool_result":
                    print(f"{TEAL}{BOLD}[tool_result]{RESET}")
                    print(f"  {item['content'][:500]}")
                    print(f"  {GRAY}tool_use_id: {item['tool_use_id']}{RESET}\n")

    print(f"{BLUE}{BOLD}[end_turn · final answer]{RESET}")
    print("─" * 60 + "\n")


def extract_json(text: str):
    """Fallback parser: pull the first JSON object/array out of the text, handling markdown wrapping."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # try whichever of {...} / [...] starts first, so a list of objects isn't mistaken for one object
    matches = [m for m in (re.search(r'\{.*\}', text, re.DOTALL), re.search(r'\[.*\]', text, re.DOTALL)) if m]
    for match in sorted(matches, key=lambda m: m.start()):
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
    return None


def parse_review(text: str) -> list[dict]:
    """Turn the model's final text into a clean list of {file_path, line_number, severity, comment}."""
    data = extract_json(text or "")
    if isinstance(data, dict):
        data = data.get("comments", [])
    if not isinstance(data, list):
        return []

    comments = []
    for item in data:
        if not isinstance(item, dict):
            continue
        # accept the older {path, line, body} shape too
        path = item.get("file_path") or item.get("path")
        line = item.get("line_number", item.get("line"))
        body = item.get("comment") or item.get("body")
        try:
            line = int(line)
        except (TypeError, ValueError):
            continue
        if not path or not body:
            continue
        severity = item.get("severity") if item.get("severity") in SEVERITIES else "minor"
        comments.append({"file_path": path, "line_number": line, "severity": severity, "comment": body})
    return comments


class Retriever:
    """Wraps retrieve_context so the loop can record every query + chunk (used by the eval)."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.queries: list[str] = []
        self.contexts: list[str] = []

    def __call__(self, query: str) -> str:
        self.queries.append(query)
        try:
            results = retrieve_context(query, collection_name=self.collection_name)
        except Exception as e:
            return f"retrieve_context failed: {e}"
        for r in results:
            chunk = f"# {r['file_path']}:{r['start_line']}-{r['end_line']}\n{r['source_text']}"
            if chunk not in self.contexts:
                self.contexts.append(chunk)
        return format_results(results)


def _run_anthropic(diff_text: str, retrieve: Retriever, max_rounds: int, verbose: bool) -> tuple[str, int]:
    client = get_anthropic()
    messages = [{
        "role": "user",
        "content": f"Please review this pull request:\n\n{diff_text}"
    }]
    rounds = 0

    while True:
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=anthropic_tools,
            # once the retrieval budget is spent, keep the tool defined but don't allow calls
            tool_choice={"type": "auto"} if rounds < max_rounds else {"type": "none"},
            output_config={"format": {"type": "json_schema", "schema": REVIEW_SCHEMA}},
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            rounds += 1
            tool_result = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_result.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": retrieve(block.input.get("query", "")),
                    })
            if rounds >= max_rounds:
                tool_result.append({"type": "text", "text": FINAL_NUDGE})
            messages.append({"role": "user", "content": tool_result})
            continue

        if response.stop_reason not in ("end_turn", "stop_sequence"):
            # refusal / max_tokens: there's no usable review in this response
            print(f"Review stopped early: stop_reason={response.stop_reason}")
            if verbose:
                display_messages(messages)
            return "", rounds

        if verbose:
            display_messages(messages)
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, rounds


def _run_openai(diff_text: str, retrieve: Retriever, max_rounds: int, verbose: bool) -> tuple[str, int]:
    client = get_openai()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Please review this pull request:\n\n{diff_text}"},
    ]
    rounds = 0

    while True:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto" if rounds < max_rounds else "none",
            response_format={"type": "json_schema", "json_schema": {"name": "review", "schema": REVIEW_SCHEMA, "strict": True}},
        )
        message = response.choices[0].message

        if message.tool_calls and rounds < max_rounds:
            rounds += 1
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                try:
                    query = json.loads(call.function.arguments).get("query", "")
                except json.JSONDecodeError:
                    query = ""
                if verbose:
                    print(f"[tool_use · retrieve_context] {query}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": retrieve(query)})
            if rounds >= max_rounds:
                messages.append({"role": "user", "content": FINAL_NUDGE})
            continue

        return message.content or "", rounds


def review_diff(diff_lines: list[dict], collection_name: str = COLLECTION_NAME,
                max_rounds: int = MAX_ROUNDS, verbose: bool = False) -> dict:
    """
    Run the agentic loop on an already-parsed diff.
    Returns {comments, queries, contexts, rounds} — the eval harness uses everything,
    the webhook only needs comments.
    """
    retrieve = Retriever(collection_name)
    diff_text = format_diff(diff_lines)
    if LLM_PROVIDER == "openai":
        text, rounds = _run_openai(diff_text, retrieve, max_rounds, verbose)
    else:
        text, rounds = _run_anthropic(diff_text, retrieve, max_rounds, verbose)

    return {
        "comments": parse_review(text),
        "queries": retrieve.queries,
        "contexts": retrieve.contexts,
        "rounds": rounds,
    }


def run_review(repo_name: str, pr_number: int, verbose: bool = False) -> list[dict]:
    """
    Run the full PR review pipeline:
    - Parse diff
    - Run agentic loop with retrieve_context tool
    - Return list of comment dicts ready for post_review
    """
    diffs = get_pr_diff(repo_name, pr_number)
    if not diffs:
        return []
    result = review_diff(diffs, verbose=verbose)
    return to_github_comments(result["comments"], commentable_lines(diffs))


if __name__ == "__main__":
    import argparse
    arg_parser = argparse.ArgumentParser(description="Run the review agent on a PR (prints, does not post)")
    arg_parser.add_argument("repo", help="owner/name")
    arg_parser.add_argument("pr", type=int)
    args = arg_parser.parse_args()

    for comment in run_review(args.repo, args.pr, verbose=True):
        print(f"{comment['path']}:{comment['line']}  {comment['body']}\n")
