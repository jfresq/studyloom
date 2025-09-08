import os, io, time, hashlib, re
from typing import Optional, Tuple, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Header
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import psycopg
from openai import OpenAI

from .models.openai_types import ChatRequest, ChatResponse, Choice, ChoiceMessage
from .rag.chunker import chunk_text
from .rag.retriever import upsert_chunks, retrieve
from .rag.embedder import sha256

# ---------- Config & clients ----------
app = FastAPI(title="Loom Gateway", version="0.3.0")

DATA_DIR = os.getenv("DATA_DIR", "/data")
RAW_DIR = os.getenv("RAW_DIR", "/data/raw")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OAI = OpenAI(api_key=OPENAI_API_KEY)

DB_DSN = (
    f"host={os.getenv('POSTGRES_HOST')} "
    f"port={os.getenv('POSTGRES_PORT')} "
    f"dbname={os.getenv('POSTGRES_DB')} "
    f"user={os.getenv('POSTGRES_USER')} "
    f"password={os.getenv('POSTGRES_PASSWORD')}"
)

def db():
    return psycopg.connect(DB_DSN, autocommit=True)

# ---------- Helpers ----------
def ensure_dirs(course_id: str) -> str:
    path = os.path.join(RAW_DIR, course_id)
    os.makedirs(path, exist_ok=True)
    return path

def pdf_to_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n\n".join(pages)

def _default_model() -> str:
    # base upstream model (OpenAI-compatible)
    return os.getenv("LOOM_CHAT_MODEL", "gpt-4o-mini")

def _model_prefix() -> str:
    # prefix for "virtual" course models (e.g., "loom:CS101")
    return os.getenv("LOOM_MODEL_PREFIX", "loom")

def _list_courses() -> List[Tuple[str, str]]:
    """
    Returns list of (course_id, display_name). Populated by /v1/ingest.
    """
    rows: List[Tuple[str, str]] = []
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, COALESCE(name, id) FROM courses ORDER BY id;")
            rows = cur.fetchall() or []
    return rows

def _parse_model(req_model: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Accept:
      - 'gpt-4o-mini'                  -> upstream = gpt-4o-mini, no forced course
      - 'gpt-4o-mini@TCMT631_Fall25'   -> upstream = gpt-4o-mini, course = TCMT631_Fall25
      - 'loom:TCMT631_Fall25'          -> upstream = default,     course = TCMT631_Fall25
    """
    upstream = _default_model()
    course_id = None
    if not req_model:
        return upstream, course_id

    if "@" in req_model:
        left, right = req_model.split("@", 1)
        upstream = left or upstream
        course_id = right or None
        return upstream, course_id

    pref = _model_prefix() + ":"
    if req_model.startswith(pref):
        course_id = req_model[len(pref):] or None
        return upstream, course_id

    # treat as an upstream base model id
    upstream = req_model
    return upstream, course_id

# ---------- Endpoints ----------
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/v1/models")
def list_models():
    """
    Advertise a base model + per-course "virtual models" so courses
    show up in OpenWebUI's model picker.
    """
    base = _default_model()
    data = [{"id": base, "object": "model", "owned_by": "loom"}]
    pref = _model_prefix()
    for cid, name in _list_courses():
        # Two naming styles; use either in the UI:
        #  - <base>@<course_id>
        #  - <prefix>:<course_id>
        data.append({
            "id": f"{base}@{cid}",
            "object": "model",
            "owned_by": "loom",
            "metadata": {"course_id": cid, "name": name}
        })
        data.append({
            "id": f"{pref}:{cid}",
            "object": "model",
            "owned_by": "loom",
            "metadata": {"course_id": cid, "name": name}
        })
    return {"object": "list", "data": data}

@app.post("/v1/ingest")
async def ingest(course_id: str = Form(...), file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF supported in MVP.")

    file_bytes = await file.read()
    ensure_dirs(course_id)
    raw_path = os.path.join(RAW_DIR, course_id, file.filename)
    with open(raw_path, "wb") as f:
        f.write(file_bytes)

    try:
        text = pdf_to_text(file_bytes)
    except PdfReadError as e:
        raise HTTPException(status_code=400, detail=f"PDF parse error: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found. (Is this a scanned PDF? Try OCR.)")

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Upsert metadata
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO courses (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;",
                (course_id, course_id),
            )
            cur.execute(
                "INSERT INTO documents (id, course_id, filename, sha256, bytes) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
                (file_hash, course_id, file.filename, file_hash, len(file_bytes)),
            )

    # Chunk + embed + upsert to vector DB
    chunks = chunk_text(
        text,
        chunk_size=int(os.getenv("CHUNK_SIZE_CHARS", "1500")),
        overlap=int(os.getenv("CHUNK_OVERLAP_CHARS", "200")),
    )
    upserted, _ = upsert_chunks(course_id, chunks)

    # Persist chunks in Postgres
    with db() as conn:
        with conn.cursor() as cur:
            for idx, chunk in enumerate(chunks):
                cid = sha256(f"{file_hash}:{idx}")
                cur.execute(
                    "INSERT INTO chunks (id, document_id, course_id, chunk_index, sha256, text) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;",
                    (cid, file_hash, course_id, idx, sha256(chunk), chunk),
                )

    return {
        "course_id": course_id,
        "filename": file.filename,
        "bytes": len(file_bytes),
        "chunks": len(chunks),
        "qdrant_upserts": upserted,
    }

def _build_system_prompt(guardrails: str) -> str:
    return (
        "You are Studyloom's course-specific Tutor Bot.\n"
        "Follow academic honesty; do not write graded work verbatim. "
        "Cite which doc/chunk you used if asked.\n"
        "If the answer is not in the provided context, say you don't know and ask for more details.\n"
        f"{guardrails}\n"
    )

async def _chat_core(req: ChatRequest, forced_course_id: Optional[str] = None) -> JSONResponse:
    # Resolve upstream model and course
    upstream_model, model_course = _parse_model(getattr(req, "model", None))

    # Input priority: forced (query/path/header) > model-encoded > body.loom > [course:ID]
    resolved_course = forced_course_id or model_course
    if not resolved_course and req.loom and isinstance(req.loom, dict):
        resolved_course = req.loom.get("course_id")

    if not resolved_course:
        for m in reversed(req.messages):
            if m.role == "user":
                m_ = re.search(r"\[course:([^\]]+)\]", m.content)
                if m_:
                    resolved_course = m_.group(1)
                    break

    if not resolved_course:
        raise HTTPException(
            status_code=400,
            detail="Missing course_id (pick a course model, use ?course_id=, X-Loom-Course header, "
                   "req.loom.course_id, or include [course:ID] in your message)."
        )

    # Last user message as the query
    last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
    if not last_user:
        raise HTTPException(status_code=400, detail="No user message provided.")
    query = last_user.content

    # Pull course guardrails
    guardrails = ""
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT guardrails FROM courses WHERE id=%s;", (resolved_course,))
            row = cur.fetchone()
            if row and row[0]:
                guardrails = row[0]

    # Retrieve context
    contexts = retrieve(resolved_course, query)
    context_block = "\n\n".join([f"[score={score:.3f}]\n{txt}" for txt, score in contexts])

    # Build messages
    oai_messages = [{"role": "system", "content": _build_system_prompt(guardrails)}]
    if context_block.strip():
        oai_messages.append({"role": "system", "content": "Context:\n" + context_block})
    for m in req.messages:
        oai_messages.append({"role": m.role, "content": m.content})

    # Call upstream LLM
    resp = OAI.chat.completions.create(
        model=upstream_model,
        messages=oai_messages,
        temperature=req.temperature or 0.2,
        max_tokens=req.max_tokens or 512,
        # NOTE: MVP returns non-streaming responses
    )
    choice = resp.choices[0].message

    out = ChatResponse(
        id=f"chatcmpl-{int(time.time())}",
        created=int(time.time()),
        model=upstream_model,
        choices=[
            Choice(
                index=0,
                message=ChoiceMessage(role=choice.role, content=choice.content),
                finish_reason="stop",
            )
        ],
    )
    return JSONResponse(content=out.model_dump())

@app.post("/v1/chat/completions")
async def chat(
    req: ChatRequest,
    course_id: Optional[str] = Query(default=None),
    x_loom_course: Optional[str] = Header(default=None),
):
    # Prefer explicit query/header if provided
    forced = course_id or x_loom_course
    return await _chat_core(req, forced_course_id=forced)

@app.post("/v1/{course_id}/chat/completions")
async def chat_course(course_id: str, req: ChatRequest):
    # Convenience path that binds a course via URL
    return await _chat_core(req, forced_course_id=course_id)
