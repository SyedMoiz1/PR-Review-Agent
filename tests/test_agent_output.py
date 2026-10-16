from agent.loop import parse_review
from github_parsing.commenter import to_github_comments


def test_parse_structured_output():
    text = '{"comments": [{"file_path": "a.py", "line_number": 3, "severity": "major", "comment": "bug"}]}'
    assert parse_review(text) == [{"file_path": "a.py", "line_number": 3, "severity": "major", "comment": "bug"}]


def test_parse_markdown_wrapped_legacy_shape():
    text = 'Here you go:\n```json\n[{"path": "a.py", "line": "4", "body": "x"}]\n```'
    assert parse_review(text) == [{"file_path": "a.py", "line_number": 4, "severity": "minor", "comment": "x"}]


def test_parse_garbage_returns_empty():
    assert parse_review("no json here") == []
    assert parse_review("") == []


def test_comments_outside_diff_are_dropped():
    review = [
        {"file_path": "a.py", "line_number": 3, "severity": "critical", "comment": "sql injection"},
        {"file_path": "a.py", "line_number": 99, "severity": "minor", "comment": "outside"},
    ]
    comments = to_github_comments(review, allowed={("a.py", 3)})
    assert comments == [{"path": "a.py", "line": 3, "body": "🔴 **Critical** sql injection", "side": "RIGHT"}]
