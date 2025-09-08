# Technical Overview (Studyloom)

**Core idea / flow**

1. **Upload** course files (PDF first): syllabus, readings, assignments, etc. (Eventually LMS integration)
    
2. **Parse → Markdown/Text → Chunk → Embed → Upsert to Vector DB (Qdrant).**
    
3. **Chat:** OpenWebUI points to Loom’s OpenAI-compatible endpoint; Loom retrieves top-k chunks + guardrails → calls an LLM → streams answer back.
    

**APIs (OpenAI-compatible surface)**

- `POST /v1/ingest` (multipart): `course_id`, `file=*.pdf` → parses, chunks, embeds, stores in Qdrant + Postgres.
    
- `POST /v1/chat/completions` (JSON): same schema as OpenAI; add `{"loom":{"course_id":"CS101"}}` or include `[course:CS101]` in the user message.
    

**Runtime components**

- **Loom Gateway (FastAPI):** RAG orchestrator + OpenAI proxy.
    
- **Qdrant:** vector DB per course (collection per `course_id`).
    
- **Postgres:** metadata (courses, documents, chunks, guardrails).
    
- **Caddy:** reverse proxy exposing `/v1/*` for clients.
    
- **OpenWebUI:** front end the user chats in; points to Loom instead of OpenAI.
    

**Data model (minimal)**

- `courses(id, name, guardrails)`
    
- `documents(id, course_id, filename, sha256, bytes)`
    
- `chunks(id, document_id, course_id, chunk_index, sha256, text)`
    

**Retrieval**

- Embeddings: `text-embedding-3-large` (configurable).
    
- Search: cosine similarity in Qdrant, `top_k` tunable (default 6).
    
- Context block (with scores) + syllabus-derived **guardrails** prepended to system prompt.
    

**Dev & deploy**

- **Monorepo**: `studyloom/services/{loom_gateway,caddy,(frontend_wizard),(ingest_worker)}`
    
- **Docker Compose** for local; volumes persist Qdrant/Postgres/data.
    
- Point OpenWebUI Custom Model → `http://host:8080/v1` (API key can be placeholder; Loom uses server-side key).
    
- Secrets via `.env` (commit `.env.example`, never `.env`).
    

**Scale & costs (ballpark)**

- Typical course: **150–600 chunks** → a few MB of vectors.
    
- **1,000 bots ≈ ~10 GB** of vectors → storage is cheap; **token usage is the cost driver**.
    
- Embed once (cache by SHA256); pay per chat.
    

**Security/guardrails**

- System prompt auto-built from syllabus (academic honesty, policies).
    
- Refuse to produce graded work verbatim; encourage citations/learning.
    

**Roadmap**

- Re-ranker, PII scan, eval harness, multi-tenant isolation, async ingest worker, MinIO/S3 for raw files, metrics (hit rate/latency), quotas/rate-limits, frontend onboarding wizard + dashboard.
    

**Why this design works**

- Keeps OpenWebUI UX intact while giving you full control over retrieval, guardrails, and indexing—no hacks inside OpenWebUI, just an API swap.