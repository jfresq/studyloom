import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLL_PREFIX = os.getenv("QDRANT_COLLECTION_PREFIX", "course_")
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
def collection_name(course_id: str) -> str:
    return f"{COLL_PREFIX}{course_id}"
def ensure_collection(course_id: str, vector_size: int):
    coll = collection_name(course_id)
    existing = [c.name for c in client.get_collections().collections]
    if coll not in existing:
        client.create_collection(collection_name=coll, vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE))
def upsert_points(course_id: str, vectors, payloads, ids):
    coll = collection_name(course_id)
    client.upsert(collection_name=coll, points=[PointStruct(id=i, vector=v, payload=p) for i, (v, p) in enumerate(zip(vectors, payloads))])
def search(course_id: str, query_vector, top_k: int, min_score: float, must_payload=None):
    coll = collection_name(course_id)
    flt = None
    if must_payload:
        flt = Filter(must=[FieldCondition(key=k, match=MatchValue(value=v)) for k, v in must_payload.items()])
    try:
        return client.search(collection_name=coll, query_vector=query_vector, limit=top_k, score_threshold=min_score, query_filter=flt)
    except Exception:
        return []
