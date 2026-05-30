# post inline comments via pygithub


from dotenv import load_dotenv
import os
from github import Github, Auth

load_dotenv()
token = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPO")

g = Github(auth=Auth.Token(token))

def post_review(repo_name: str, pr_number: int, commit_sha: str, comments_to_post: list[dict]) -> None:
    """
    Post a batch of inline review comments to a GitHub PR.
    Each comment dict should have:
    - path: str
    - line: int
    - body: str
    - side: str
    """
    repo = g.get_repo(repo_name)
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


