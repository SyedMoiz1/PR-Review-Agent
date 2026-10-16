from pathlib import Path

from ingestion.chunker import chunk_repository

CODEBASE = Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "codebase"


def test_chunks_use_repo_relative_paths_and_1_based_lines():
    chunks = chunk_repository(str(CODEBASE))
    get_conn = next(c for c in chunks if c["function_name"] == "get_connection")
    assert get_conn["file_path"] == "shopapp/db.py"
    source = (CODEBASE / "shopapp" / "db.py").read_text().splitlines()
    assert source[get_conn["start_line"] - 1].startswith("def get_connection")


def test_methods_inside_classes_are_chunked():
    names = {c["function_name"] for c in chunk_repository(str(CODEBASE))}
    assert {"AuthError", "require_auth", "order_total"} <= names
