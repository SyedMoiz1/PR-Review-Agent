import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from github_parsing import webhook

SECRET = "test-secret"


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webhook, "SECRET", SECRET)
    calls = []
    monkeypatch.setattr(webhook, "handle_pr_event", lambda *args: calls.append(args))
    c = TestClient(webhook.app)
    c.calls = calls
    return c


def pr_payload(action="opened"):
    return json.dumps({
        "action": action,
        "number": 7,
        "repository": {"full_name": "me/repo"},
        "pull_request": {"head": {"sha": "abc123"}},
    }).encode()


def post(client, body, event="pull_request", signature=None):
    return client.post("/webhook", content=body, headers={
        "X-Hub-Signature-256": signature if signature is not None else sign(body),
        "X-GitHub-Event": event,
        "Content-Type": "application/json",
    })


def test_valid_pr_event_dispatches_review(client):
    assert post(client, pr_payload()).status_code == 200
    assert client.calls == [("me/repo", 7, "opened", "abc123")]


def test_invalid_signature_rejected(client):
    assert post(client, pr_payload(), signature="sha256=deadbeef").status_code == 403
    assert client.calls == []


def test_missing_signature_rejected(client):
    assert post(client, pr_payload(), signature="").status_code == 403


def test_ignored_action_and_ping(client):
    assert post(client, pr_payload("closed")).json()["status"] == "ignored"
    assert post(client, b'{"zen": "hi"}', event="ping").json()["status"] == "pong"
    assert client.calls == []
