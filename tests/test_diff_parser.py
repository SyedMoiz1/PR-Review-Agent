from github_parsing.diff_parser import parse_patch, commentable_lines, format_diff

PATCH = """@@ -1,3 +1,4 @@
 import os
-import sys
+import json
+import re
 
@@ -10,2 +11,3 @@ def main():
     run()
+    cleanup()
\\ No newline at end of file"""


def test_line_numbers_follow_new_file():
    lines = parse_patch("app.py", PATCH)
    added = [(l["line_number"], l["content"]) for l in lines if l["change_type"] == "added"]
    assert added == [(2, "+import json"), (3, "+import re"), (12, "+    cleanup()")]


def test_removed_lines_have_no_line_number():
    removed = [l for l in parse_patch("app.py", PATCH) if l["change_type"] == "removed"]
    assert len(removed) == 1 and removed[0]["line_number"] is None


def test_no_newline_marker_is_skipped():
    assert not any(l["content"].startswith("\\") for l in parse_patch("app.py", PATCH))


def test_commentable_lines_and_format():
    lines = parse_patch("app.py", PATCH)
    assert ("app.py", 12) in commentable_lines(lines)
    assert "[removed] app.py:- | -import sys" in format_diff(lines)
