# agentic tool loop
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from github_parsing.diff_parser import get_pr_diff
from retrieval.retriever import retrieve_context
import anthropic
from dotenv import load_dotenv
from prompt import SYSTEM_PROMPT
import json
import re

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-6"

tools = [{
    "name": "retrieve_context",
    "description": "Retrieves relevant code chunks from the codebase vector database based on a natural language query. Use this when you need to find how something is implemented before writing a review comment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of the code context you need"
            }
        },
        "required": ["query"]
    }
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
            print(f"  {content}\n")

        elif role == "assistant":
            for block in content:
                if block.type == "text":
                    print(f"{GRAY}{BOLD}[claude · text]{RESET}")
                    print(f"  {block.text}\n")
                elif block.type == "tool_use":
                    print(f"{AMBER}{BOLD}[tool_use · {block.name}]{RESET}")
                    print(f"  query : {block.input['query']}")
                    print(f"  id    : {block.id}\n")

        elif role == "user" and isinstance(content, list):
            for item in content:
                if item["type"] == "tool_result":
                    print(f"{TEAL}{BOLD}[tool_result]{RESET}")
                    print(f"  {item['content']}")
                    print(f"  {GRAY}tool_use_id: {item['tool_use_id']}{RESET}\n")

    print(f"{BLUE}{BOLD}[end_turn · final answer]{RESET}")
    print("─" * 60 + "\n")

def extract_json(text: str) -> list[dict]:
    """Extract JSON array from Claude's response, handling markdown wrapping."""
    text = text.strip()
    
    # try to find a JSON array anywhere in the text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return []
    
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

def run_review(repo_name: str, pr_number: int, commit_sha: str) -> list[dict]:
    """
    Run the full PR review pipeline:
    - Parse diff
    - Run agentic Claude loop with retrieve_context tool
    - Return list of comment dicts ready for post_review
    """
    diffs = get_pr_diff(repo_name, pr_number)
    
    diff_text = "\n".join([
    f"[{line['change_type']}] {line['filename']}:{line['line_number']} | {line['content']}"
    for line in diffs
    ])

    messages = [{
        "role": "user",
        "content": f"Please review this pull request:\n\n{diff_text}"
    }]

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages
    )

    max_rounds = 3
    rounds = 0
    print("starting loop\n")


    while response:
        if response.stop_reason == "tool_use" and rounds < max_rounds:
            rounds +=1
            tool_result = []
            for block in response.content:
                if block.type == "tool_use":
                    results = retrieve_context(block.input["query"])
                    tool_result.append({
                        "type":"tool_result",
                        "tool_use_id":block.id,
                        "content": str(results)
                    })
            messages.append({"role":"assistant", "content":response.content})
            messages.append({"role": "user", "content": tool_result})
            response = client.messages.create(
                model=MODEL,
                max_tokens = 1000,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages
            )
        elif response.stop_reason == "end_turn":
            messages.append({"role":"assistant", "content": response.content})
            for block in response.content:
                if block.type == "text":
                    comments = extract_json(block.text)
            #display_messages(messages)
            for comment in comments: 
                print(F"{comment} + \n")
            return comments
    return []
    

if __name__ == "__main__":

    run_review("SyedMoiz1/test-repo", 1, "bd7f7556f6800363c2399f7313b360e5a2e11b9f")

