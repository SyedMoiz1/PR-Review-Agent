# drives the Anthropic loop with a fake client: no network, no API key
import json
from types import SimpleNamespace as NS

from agent import loop

DIFF = [{"filename": "a.py", "line_number": 1, "content": "+x = eval(input())", "change_type": "added"}]
FINAL = json.dumps({"comments": [{"file_path": "a.py", "line_number": 1, "severity": "critical", "comment": "eval on user input"}]})


def tool_use(i):
    return NS(stop_reason="tool_use", content=[NS(type="tool_use", id=f"t{i}", name="retrieve_context", input={"query": f"q{i}"})])


class FakeMessages:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if kwargs["tool_choice"]["type"] == "none":
            return NS(stop_reason="end_turn", content=[NS(type="text", text=FINAL)])
        return self.responses.pop(0)


def run(monkeypatch, responses):
    fake = FakeMessages(responses)
    monkeypatch.setattr(loop, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(loop, "get_anthropic", lambda: NS(messages=fake))
    monkeypatch.setattr(loop, "retrieve_context", lambda q, collection_name: [
        {"function_name": "f", "file_path": "b.py", "start_line": 1, "end_line": 2, "source_text": "def f(): ...", "score": 0.9}])
    return loop.review_diff(DIFF), fake


def test_stops_retrieving_after_three_rounds(monkeypatch):
    result, fake = run(monkeypatch, [tool_use(i) for i in range(10)])
    assert result["rounds"] == 3
    assert result["queries"] == ["q0", "q1", "q2"]
    assert [c["tool_choice"]["type"] for c in fake.calls] == ["auto", "auto", "auto", "none"]
    # the last tool_result message carries the nudge to finish
    assert fake.calls[-1]["messages"][-1]["content"][-1] == {"type": "text", "text": loop.FINAL_NUDGE}
    assert result["comments"][0]["severity"] == "critical"
    assert result["contexts"] == ["# b.py:1-2\ndef f(): ..."]


def test_direct_answer_without_tools(monkeypatch):
    result, fake = run(monkeypatch, [NS(stop_reason="end_turn", content=[NS(type="text", text=FINAL)])])
    assert result["rounds"] == 0 and len(result["comments"]) == 1


def test_refusal_returns_no_comments(monkeypatch):
    result, _ = run(monkeypatch, [NS(stop_reason="refusal", content=[])])
    assert result["comments"] == []
