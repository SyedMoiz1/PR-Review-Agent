# embedding generation and qdrant upsert
#
# usage: python -m ingestion.embedder --repo /path/to/target/repo [--collection codebase]
import argparse
import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qdrant_client.models import Distance, VectorParams, PointStruct
from ingestion.chunker import chunk_repository
from settings import COLLECTION_NAME, EMBED_DIM, EMBED_MODEL, get_openai, get_qdrant

# Batch your embedding calls, don't loop and call the API once per chunk
# Each Qdrant point needs a UUID, a vector, and a payload with all chunk metadata
BATCH_SIZE = 128
MAX_EMBED_CHARS = 24_000  # text-embedding-3-small caps inputs at 8191 tokens


def embedding_text(chunk: dict) -> str:
    # prefixing the path + name helps queries like "how is auth handled" find the right file
    return f"{chunk['file_path']} :: {chunk['function_name']}\n{chunk['source_text']}"[:MAX_EMBED_CHARS]


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Takes a list of chunks, embeds source_text for each,
    adds 'vector' key to each chunk and returns them.
    """
    client = get_openai()
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i: i+BATCH_SIZE]
        response = client.embeddings.create(
            model = EMBED_MODEL,
            input=[embedding_text(chunk) for chunk in batch]
        )
        for j, chunk in enumerate(batch):
            chunk['vector'] = response.data[j].embedding
    return chunks


def reset_collection(collection_name: str) -> None:
    """Drop + recreate so stale chunks from deleted/renamed code don't linger."""
    qdrant = get_qdrant()
    if qdrant.collection_exists(collection_name):
        qdrant.delete_collection(collection_name)
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )


def chunk_id(chunk: dict) -> str:
    # deterministic ids: re-upserting the same chunk overwrites instead of duplicating
    key = f"{chunk['file_path']}:{chunk['start_line']}:{chunk['function_name']}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def upsert_chunks(chunks: list[dict], collection_name: str) -> None:
    """
    Takes embedded chunks and upserts them into Qdrant.
    """
    points = [
        PointStruct(
            id=chunk_id(chunk),
            vector=chunk['vector'],
            payload={k: v for k, v in chunk.items() if k != 'vector'}
        )
        for chunk in chunks
    ]
    for i in range(0, len(points), BATCH_SIZE):
        get_qdrant().upsert(collection_name=collection_name, points=points[i:i+BATCH_SIZE])


def ingest_repository(repo_path: str, collection_name: str = COLLECTION_NAME) -> int:
    """
    Full pipeline: chunk repo → embed → upsert into Qdrant. Returns the chunk count.
    """
    chunks = chunk_repository(repo_path)
    if not chunks:
        print(f"No Python chunks found under {repo_path}")
        return 0
    chunks = embed_chunks(chunks)
    reset_collection(collection_name)
    upsert_chunks(chunks, collection_name)
    return len(chunks)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Index a repository into Qdrant")
    arg_parser.add_argument("--repo", default="./", help="path to the repository to index")
    arg_parser.add_argument("--collection", default=COLLECTION_NAME, help="Qdrant collection name")
    args = arg_parser.parse_args()

    count = ingest_repository(args.repo, args.collection)
    print(f"Ingestion complete: {count} chunks into '{args.collection}'.")
