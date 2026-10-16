import tree_sitter_python as tspython
from tree_sitter import Language, Parser
from pathlib import Path

# tree-sitter logic for parsing and chunking source code
PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

# directories that never contain code worth indexing
SKIP_DIRS = {"venv", ".venv", "env", ".git", "node_modules", "__pycache__", "site-packages", "build", "dist"}

def chunk_file(filepath: str, repo_root: str | None = None) -> list[dict]:
    """
    Parse a Python file and return a list of chunks.
    Each chunk is a dict with:
    - function_name: str
    - file_path: str  (relative to repo_root when given, so it matches PR diff paths)
    - start_line: int (1-based, like GitHub)
    - end_line: int
    - source_text: str
    - node_type: str  (function_definition or class_definition)
    """
    try:
        chunks = []
        display_path = Path(filepath).relative_to(repo_root).as_posix() if repo_root else str(filepath)
        cursor = parse_file(filepath).walk()
        parse_tree(cursor.node, display_path, chunks) #cursor.node is used to access the root node in the tree

        return chunks
    except Exception as e:
        print(f"Warning: could not parse {filepath}: {e}")
        return []

def chunk_repository(repo_path: str) -> list[dict]:
    """
    Walk an entire repo and chunk all Python files.
    """
    root = Path(repo_path).resolve()
    chunks = []
    for file in sorted(root.rglob("*.py")):
        if file.is_file() and not SKIP_DIRS.intersection(file.relative_to(root).parts):
            chunks.extend(chunk_file(file, root))
    return chunks

def parse_file(filepath: str):
    """
    This function is used to return the tree
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source_code = f.read()
    source_bytes = bytes(source_code, "utf-8")
    tree = parser.parse(source_bytes)
    return tree

def parse_tree(node, filepath, chunks) -> list[dict]:
    if node.type == "function_definition" or node.type == "class_definition":
        chunk = {
            'function_name': None,
            'file_path': str(filepath),
            'start_line': int(node.start_point[0]) + 1, # tree-sitter rows are 0-based
            'end_line': int(node.end_point[0]) + 1,
            'source_text': node.text.decode('utf-8'),
            'node_type': str(node.type)
        }
        for child in node.children:
            if child.type == 'identifier':
                chunk['function_name'] = child.text.decode('utf-8')
        if node.type == 'class_definition':
            for child in node.children:
                parse_tree(child, filepath, chunks)
        chunks.append(chunk)
    else:
        for child in node.children:
            parse_tree(child, filepath, chunks)


if __name__ == "__main__":

    chunks = chunk_repository("./")

    for chunk in chunks:
        print(f"[{chunk['node_type']}] {chunk['function_name']}")
        print(f"  file      : {chunk['file_path']}")
        print(f"  lines     : {chunk['start_line']} - {chunk['end_line']}")
        print(f"  source    :")
        for line in chunk['source_text'].splitlines():
            print(f"    {line}")
        print()
