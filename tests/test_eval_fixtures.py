from eval.harness import load_fixtures, fixture_diff, match_comments


def test_fifteen_fixtures_with_valid_ground_truth():
    fixtures = load_fixtures()
    assert len(fixtures) == 15
    for fixture in fixtures:
        added = {(l["filename"], l["line_number"]) for l in fixture_diff(fixture) if l["change_type"] == "added"}
        for exp in fixture["expected"]:
            assert (exp["file_path"], exp["line_number"]) in added, fixture["id"]


def test_match_comments_tolerance_and_one_to_one():
    expected = [{"file_path": "a.py", "line_number": 10}]
    assert match_comments([{"file_path": "a.py", "line_number": 12}], expected) == 1
    assert match_comments([{"file_path": "a.py", "line_number": 13}], expected) == 0
    assert match_comments([{"file_path": "b.py", "line_number": 10}], expected) == 0
    two_preds = [{"file_path": "a.py", "line_number": 10}, {"file_path": "a.py", "line_number": 11}]
    assert match_comments(two_preds, expected) == 1
