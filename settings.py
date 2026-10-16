# shared config + lazily-created clients
# clients are created on first use so that importing a module (e.g. in tests)
# doesn't require every API key to be set
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "codebase")

# "anthropic" (Claude) or "openai" (GPT-4o)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "claude-opus-5-5" if LLM_PROVIDER == "anthropic" else "gpt-4o",
)


@lru_cache
def get_openai():
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@lru_cache
def get_anthropic():
    import anthropic
    return anthropic.Anthropic()


@lru_cache
def get_qdrant():
    from qdrant_client import QdrantClient
    # QDRANT_URL lets you point at Qdrant Cloud / a Fly.io instance; defaults to local docker
    url = os.getenv("QDRANT_URL")
    if url:
        return QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"))
    return QdrantClient(host="localhost", port=6333)


@lru_cache
def get_github():
    from github import Github, Auth
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set")
    return Github(auth=Auth.Token(token))
