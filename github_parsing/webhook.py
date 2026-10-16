# fastapi app + HMAC validation
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import hmac
import hashlib
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import settings  # noqa: F401  (loads .env)

app = FastAPI()
SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
REVIEW_ACTIONS = ["opened", "synchronize", "reopened"] #only want to trigger a review when: new pr opened, or new commits to existing pr


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive GitHub webhook, validate HMAC, extract PR metadata,
    dispatch to review pipeline as background task.
    """
    if not SECRET:
        return JSONResponse(status_code=500, content={"status": "GITHUB_WEBHOOK_SECRET is not configured"})

    raw_body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if signature_header == "":
        return JSONResponse(
            status_code=403,
            content={"status": "403 forbidden: No HMAC received"}
        )
    if not validate_signature(raw_body, SECRET, signature_header):
        return JSONResponse(
            status_code=403,
            content={"status": "403 forbidden: Invalid HMAC received"}
        )

    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return JSONResponse(status_code=200, content={"status": "pong"})
    if event != "pull_request":
        return JSONResponse(status_code=200, content={"status": "ignored"})

    payload = json.loads(raw_body)
    action = payload.get('action')
    if action not in REVIEW_ACTIONS:
        return JSONResponse(status_code=200, content={"status": "ignored"})

    repo_name = payload["repository"]["full_name"]
    pr_number = payload["number"]
    commit_sha = payload["pull_request"]["head"]["sha"]
    background_tasks.add_task(handle_pr_event, repo_name, pr_number, action, commit_sha)
    return JSONResponse(
        status_code=200,
        content={"status": "Valid HMAC received"}
    )


def validate_signature(raw_body: bytes, secret: str, signature_header: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def handle_pr_event(repo_name: str, pr_number: int, action: str, commit_sha: str):
    """
    Run the agent on the PR and post its comments as a single review.
    """
    # imported here so the server can start (and answer pings) before heavy deps load
    from agent.loop import run_review
    from github_parsing.commenter import post_review

    try:
        comments = run_review(repo_name, pr_number)
        if not comments:
            print(f"No comments to post on PR #{pr_number}")
            return
        post_review(repo_name, pr_number, commit_sha, comments)
        print(f"Posted {len(comments)} comments on PR #{pr_number}")
    except Exception as e:
        # background tasks swallow exceptions silently, so log them
        print(f"Review failed for {repo_name}#{pr_number}: {e!r}")
