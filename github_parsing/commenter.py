# post inline comments via pygithub

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import get_github

REPO_NAME = os.getenv("GITHUB_REPO")
SEVERITY_LABEL = {
    "critical": "🔴 **Critical**",
    "major": "🟠 **Major**",
    "minor": "🟡 **Minor**",
    "nit": "⚪ **Nit**",
}


def to_github_comments(review: list[dict], allowed: set[tuple[str, int]] | None = None) -> list[dict]:
    """
    Convert agent output ({file_path, line_number, severity, comment}) into
    PyGithub review comments ({path, line, body, side}).
    If `allowed` is given, drop comments on lines that aren't part of the diff —
    GitHub rejects the *entire* review if a single comment points outside it.
    """
    comments = []
    for item in review:
        path, line = item.get("file_path"), item.get("line_number")
        if not path or not isinstance(line, int) or not item.get("comment"):
            continue
        if allowed is not None and (path, line) not in allowed:
            print(f"Skipping comment outside diff: {path}:{line}")
            continue
        label = SEVERITY_LABEL.get(item.get("severity", ""), "")
        body = f"{label} {item['comment']}".strip()
        comments.append({"path": path, "line": line, "body": body, "side": "RIGHT"})
    return comments


def post_review(repo_name: str, pr_number: int, commit_sha: str, comments_to_post: list[dict]) -> None:
    """
    Post a batch of inline review comments to a GitHub PR.
    Each comment dict should have:
    - path: str
    - line: int
    - body: str
    - side: str
    """
    repo = get_github().get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    pr.create_review(
        commit = repo.get_commit(commit_sha),
        body="Automated review by PR Review Agent",
        event="COMMENT",
        comments = comments_to_post
    )


if __name__ == "__main__":
    comments = [
        {
            "path": "README.md",
            "line": 3,
            "body": "This looks risky",
            "side": "RIGHT"
        }
    ]
    post_review(REPO_NAME, 7, '0c189cc9feea36c34a58e62fe074320b4604c19c', comments)
