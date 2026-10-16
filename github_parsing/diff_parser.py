# parse raw diff into structured hunks

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import get_github

REPO_NAME = os.getenv("GITHUB_REPO")
HUNK_HEADER = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')

# # Common PR fields
# pr.title
# pr.body
# pr.state          # "open" or "closed"
# pr.user.login     # author
# pr.base.ref       # target branch (e.g. "main")
# pr.head.ref       # source branch
# pr.merged
# pr.mergeable

# # Files changed
# for file in pr.get_files():
#     file.filename
#     file.patch       # the diff
#     file.additions
#     file.deletions
#     file.status      # "added", "modified", "removed"


def parse_patch(filename: str, patch: str) -> list[dict]:
    """
    Parse a single file's unified diff patch into changed line dicts.
    Each item has:
    - filename: str
    - line_number: int | None  (line in the new file; None for removed lines)
    - content: str
    - change_type: str  (added, removed, context)
    """
    changed_lines = []
    current_line = None
    for line in patch.splitlines():
        if line.startswith("@@"): #used to indicate starting line number
            match = HUNK_HEADER.match(line)
            current_line = int(match.group(1)) if match else None
            continue
        if line.startswith("\\") or current_line is None: # "\ No newline at end of file"
            continue
        changes = {'filename': filename, 'content': line}
        if line.startswith("-"):
            changes['line_number'] = None #removed lines are indicated using no line number
            changes['change_type'] = "removed"
        elif line.startswith("+"):
            changes['line_number'] = current_line
            changes['change_type'] = "added"
            current_line += 1
        else:
            changes['line_number'] = current_line
            changes['change_type'] = "context"
            current_line += 1
        changed_lines.append(changes)
    return changed_lines


def get_pr_diff(repo_name: str, pr_number: int) -> list[dict]:
    """
    Get all changed lines across all files in a PR.
    Returns a flat list of changed line dicts (see parse_patch).
    """
    pr = get_github().get_repo(repo_name).get_pull(pr_number)
    changed_lines = []
    for file in pr.get_files():
        if not file.patch: # binary files / very large diffs have no patch
            continue
        changed_lines.extend(parse_patch(file.filename, file.patch))
    return changed_lines


def format_diff(diff_lines: list[dict]) -> str:
    """Render parsed diff lines into the text format the agent reads."""
    return "\n".join(
        f"[{line['change_type']}] {line['filename']}:{line['line_number'] if line['line_number'] is not None else '-'} | {line['content']}"
        for line in diff_lines
    )


def commentable_lines(diff_lines: list[dict]) -> set[tuple[str, int]]:
    """(path, line) pairs GitHub accepts for a RIGHT-side review comment."""
    return {
        (line['filename'], line['line_number'])
        for line in diff_lines
        if line['line_number'] is not None
    }


if __name__ == "__main__":
    diff = get_pr_diff(REPO_NAME, 1)
    for line in diff:
       print(f"[{line['change_type']}] {line['filename']} | line {line['line_number']} | {line['content']}")
