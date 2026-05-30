# fastapi app + HMAC validation
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import hmac
import hashlib
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive GitHub webhook, validate HMAC, extract PR metadata,
    dispatch to review pipeline as background task.
    """
    raw_body = await request.body()
    payload = json.loads(raw_body)
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if signature_header == "":
        return JSONResponse(
            status_code=403,
            content={"status": "403 forbidden: No HMAC received"}
        )
    else:
        if validate_signature(raw_body, SECRET, signature_header):
            action = payload['action']
            repo_name = payload["repository"]["full_name"]
            pr_number = payload["number"]
            commit_sha = payload["pull_request"]["head"]["sha"]

            if action not in ["opened", "synchronize"]: #only want to trigger a review when: new pr opened, or new commits to existing pr
                return JSONResponse(status_code=200, content={"status": "ignored"})
            
            background_tasks.add_task(handle_pr_event, repo_name, pr_number, action, commit_sha)
            return JSONResponse(
                status_code=200,
                content={"status": "Valid HMAC received"}
            )
        else:
            return JSONResponse(
                status_code=403,
                content={"status": "403 forbidden: Invalid HMAC received"}
            )

def validate_signature(raw_body: bytes, secret: str, signature_header: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)



def handle_pr_event(repo_name: str, pr_number: int, action: str, commit_sha: str):
    """
    Placeholder for now — will call the agent loop in Week 2.
    Just print the PR metadata for now.
    """
    print(f"Repo Name: {repo_name}")
    print(f"PR Number: {pr_number}")
    print(f"Action Type: {action}")
    print(f"Commit SHA: {commit_sha}")
