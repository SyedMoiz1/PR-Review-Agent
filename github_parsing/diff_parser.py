# parse raw diff into structured hunks

from dotenv import load_dotenv
import os
from github import Github, Auth
import re

load_dotenv()
token = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPO")
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

# # Comments
# for comment in pr.get_review_comments():
#     comment.body
#     comment.path     # file the comment is on


g = Github(auth=Auth.Token(token))


def get_pr_diff(repo_name: str, pr_number: int) -> list[dict]:
    """
    Get all changed lines across all files in a PR.
    Returns a flat list of changed line dicts.
    Each item should have:
    - filename: str
    - line_number: int
    - content: str
    - change_type: str  (added, removed, context)
    """
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    print(pr.head.sha)
    print(repo_name)
    changed_lines = []
    for file in pr.get_files():
        if not file.patch:
            continue
        for line in file.patch.splitlines():
            if line.startswith("@@"):
                match = re.search(r'\+(\d+)', line)
                current_line = int(match.group(1))
                continue
            if line.startswith("\\"):
                continue
            changes = {}
            changes['filename'] = file.filename
            changes['content'] = line
            if line.startswith(" "):
                changes['line_number'] = current_line
                changes['change_type'] = "context"
                current_line +=1
            elif line.startswith("-"):
                changes['line_number'] = None
                changes['change_type'] = "removed"
            elif line.startswith("+"):
                changes['line_number'] = current_line
                changes['change_type'] = "added"
                current_line +=1
            
            changed_lines.append(changes)
    return changed_lines


if __name__ == "__main__":
    diff = get_pr_diff(REPO_NAME, 1)
    for line in diff:
       print(f"[{line['change_type']}] {line['filename']} | line {line['line_number']} | {line['content']}")