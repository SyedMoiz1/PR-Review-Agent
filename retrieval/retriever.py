# query qdrant, return relevant chunks
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import COLLECTION_NAME, EMBED_MODEL, get_openai, get_qdrant


def retrieve_context(query: str, collection_name: str = COLLECTION_NAME, top_k: int = 5) -> list[dict]:
    """
    Embed query, search Qdrant, return top-k chunks with metadata and scores.
    Each result has:
    - function_name
    - file_path
    - start_line
    - end_line
    - source_text
    - score
    """
    search_result = get_qdrant().query_points(
        collection_name=collection_name,
        query=embed_query(query),
        with_payload=True,
        limit=top_k
    ).points

    result_list = []
    for point in search_result:
        result_list.append({
            'function_name': point.payload['function_name'],
            'file_path': point.payload['file_path'],
            'start_line': point.payload['start_line'],
            'end_line': point.payload['end_line'],
            'source_text': point.payload['source_text'],
            'score': point.score,
        })
    return result_list


def format_results(results: list[dict]) -> str:
    """Render retrieved chunks as readable text for the LLM (instead of a raw dict repr)."""
    if not results:
        return "No matching code found in the indexed codebase."
    return "\n\n".join(
        f"# {r['file_path']}:{r['start_line']}-{r['end_line']} ({r['function_name']}, score {r['score']:.3f})\n{r['source_text']}"
        for r in results
    )


def embed_query(query: str):
    response = get_openai().embeddings.create(
        model = EMBED_MODEL,
        input=query
    )
    return response.data[0].embedding


if __name__ == "__main__":
    results = retrieve_context("embed text chunks using openai")
    for r in results:
        print(f"{r['score']:.4f} | {r['function_name']} | {r['file_path']}")
