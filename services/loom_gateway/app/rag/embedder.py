import os
from typing import List
from openai import OpenAI
EMBED_MODEL = os.getenv("LOOM_EMBED_MODEL", "text-embedding-3-large")
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
def embed_chunks(chunks: List[str]) -> List[List[float]]:
    if not chunks:
        return []
    resp = _client.embeddings.create(model=EMBED_MODEL, input=chunks)
    return [d.embedding for d in resp.data]
def embed_query(query: str) -> List[float]:
    resp = _client.embeddings.create(model=EMBED_MODEL, input=[query])
    return resp.data[0].embedding
