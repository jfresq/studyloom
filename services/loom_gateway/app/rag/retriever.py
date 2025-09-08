import os, time
from typing import List, Tuple
from .qdrant_client import ensure_collection, upsert_points, search
from .embedder import embed_chunks, embed_query, sha256
TOP_K = int(os.getenv("TOP_K", "6"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.0"))
def upsert_chunks(course_id: str, chunks: List[str]):
    vectors = embed_chunks(chunks)
    if not vectors:
        return 0, 0
    ensure_collection(course_id, vector_size=len(vectors[0]))
    payloads, ids = [], []
    base = int(time.time() * 1000)
    for idx, chunk in enumerate(chunks):
        payloads.append({"chunk_index": idx, "sha256": sha256(chunk), "course_id": course_id, "text": chunk})
        ids.append(base + idx)
    upsert_points(course_id, vectors, payloads, ids)
    return len(chunks), len(vectors)
def retrieve(course_id: str, query: str, top_k: int = TOP_K, min_score: float = MIN_SCORE) -> List[Tuple[str, float]]:
    qvec = embed_query(query)
    hits = search(course_id, qvec, top_k, min_score)
    return [((h.payload or {}).get("text", ""), h.score) for h in hits]
