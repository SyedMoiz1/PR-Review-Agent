# embedding generation and qdrant upsert
import os
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from chunker import chunk_repository
from dotenv import load_dotenv
import uuid

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
qdrant_client = QdrantClient(host="localhost", port=6333)

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "codebase")

# Batch your embedding calls, don't loop and call the API once per chunk
# Each Qdrant point needs a UUID, a vector, and a payload with all chunk metadata

def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Takes a list of chunks, embeds source_text for each,
    adds 'vector' key to each chunk and returns them.
    """
    batch_size = 512
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i: i+batch_size]
        response = client.embeddings.create(
            model = "text-embedding-3-small",
            input=[chunk['source_text'] for chunk in batch]
        )
        for j, chunk in enumerate(batch):
            chunk['vector'] = response.data[j].embedding
    return chunks    


def check_create_collection(collection_name, Qdrantclient):
    for collection in Qdrantclient.get_collections().collections:
        if collection.name == collection_name:
            return
    Qdrantclient.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
def upsert_chunks(chunks: list[dict], collection_name: str) -> None:
    """
    Takes embedded chunks and upserts them into Qdrant.
    Creates the collection if it doesn't exist.
    """
    check_create_collection(collection_name, qdrant_client)
    points = [
        PointStruct(
            id=uuid.uuid4(),
            vector=chunk['vector'],
            payload={k: v for k, v in chunk.items() if k != 'vector'}
        )
        for chunk in chunks
    ]
    qdrant_client.upsert(
        collection_name = collection_name,
        points=points
    )

def ingest_repository(repo_path: str, collection_name: str = COLLECTION_NAME) -> None:
    """
    Full pipeline: chunk repo → embed → upsert into Qdrant.
    """

    chunks = embed_chunks(chunk_repository(repo_path))
    upsert_chunks(chunks, COLLECTION_NAME)

if __name__ == "__main__":
    ingest_repository("./", COLLECTION_NAME)
    print("Ingestion complete.")