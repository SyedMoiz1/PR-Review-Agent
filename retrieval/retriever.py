# query qdrant, return relevant chunks

# ex. query to find a stored vector most similar to query vector: 
# ```python
# search_result = client.query_points(
#     collection_name="test_collection",
#     query=[0.2, 0.1, 0.9, 0.7],
#     with_payload=False,
#     limit=3
# ).points

# print(search_result)
import os
from openai import OpenAI
from qdrant_client import QdrantClient
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
qdrant_client = QdrantClient(host="localhost", port=6333)

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "codebase")

def retrieve_context(query: str, collection_name: str = COLLECTION_NAME, top_k: int = 5) -> list[dict]:
    """
    Embed query, search Qdrant, return top-k chunks with metadata and scores.
    Each result should have:
    - function_name
    - file_path
    - start_line
    - end_line
    - source_text
    - score
    """
    embedded_query = embed_query(query)

    search_result = qdrant_client.query_points(
        collection_name=collection_name,
        query=embedded_query,
        with_payload=True,
        limit=top_k
    ).points

    result_list = []
    for point in search_result:
        point_dict = {}
        point_dict['function_name'] = point.payload['function_name']
        point_dict['file_path'] = point.payload['file_path']
        point_dict['start_line'] = point.payload['start_line']
        point_dict['end_line'] = point.payload['end_line']
        point_dict['source_text'] = point.payload['source_text']
        point_dict['score'] = point.score
        result_list.append(point_dict)

    return result_list


def embed_query(query: str):
    response = client.embeddings.create(
        model = "text-embedding-3-small",
        input=query
    )
    return response.data[0].embedding


if __name__ == "__main__":
    results = retrieve_context("embed text chunks using openai")
    for r in results:
        print(f"{r['score']:.4f} | {r['function_name']} | {r['file_path']}")