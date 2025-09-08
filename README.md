# Studyloom — Loom (RAG Engine)

Course-scoped tutor bots built from your actual class materials. OpenAI-compatible API.

## TL;DR
- **Ingest PDFs** (syllabus, readings, assignments) → **chunk → embed → Qdrant** (+ Postgres metadata).
- **Chat** via `/v1/chat/completions` with grounding + guardrails.
- Each course appears as its **own model** in OpenWebUI (e.g., `gpt-4o-mini@TCMT631_Fall25`).

---

## Quickstart

~~~
cp .env.example .env        # set OPENAI_API_KEY, etc.
docker compose up -d --build
~~~

Health:
~~~
curl -s http://localhost:8080/healthz           # ok (via Caddy)
curl -s http://localhost:6333/ | jq .version    # Qdrant
~~~

### Ingest a PDF (MVP = PDFs only)
~~~
BASE=http://localhost:8080/v1
curl -s -F course_id=TCMT631_Fall25 \
     -F 'file=@/path/to/syllabus.pdf;type=application/pdf' \
     $BASE/ingest | jq
~~~

> If you see “No extractable text”, the PDF is probably a scan. OCR it first:
> `docker run --rm -v "$PWD:/d" -w /d jbarlow83/ocrmypdf in.pdf out_OCR.pdf`

### OpenWebUI → connect to Loom
- Run OpenWebUI in Docker.
- Put it on the **same network** as Studyloom or use `host.docker.internal`.
- **Best URL** inside OpenWebUI connection:  
  `http://loom-gateway:8000/v1`  (service-to-service)

Refresh models — you should see:
- `gpt-4o-mini` (base)
- `gpt-4o-mini@TCMT631_Fall25`
- `loom:TCMT631_Fall25`

Pick a course model (e.g., `gpt-4o-mini@TCMT631_Fall25`) and chat.

> **Non-streaming:** Loom returns non-streaming JSON. Disable streaming in OpenWebUI (Interface settings) or add a tiny pre-processor that sets `"stream": false`.

---

## APIs (OpenAI-compatible)

### `POST /v1/ingest`  *(multipart)*
- **Form fields:** `course_id`, `file=*.pdf`
- Saves raw PDF, extracts text, chunks, embeds, upserts to Qdrant, writes metadata to Postgres.

### `POST /v1/chat/completions`  *(JSON)*
- Same schema as OpenAI; Loom adds RAG.
- **How Loom picks the course** (priority):
  1. **Model id**: `gpt-4o-mini@<course>` or `loom:<course>`
  2. `?course_id=<course>` (query)
  3. `X-Loom-Course: <course>` (header)
  4. `{"loom":{"course_id":"<course>"}}` (body)
  5. `[course:<course>]` tag in the latest user message

### `GET /v1/models`
Returns the base model and **virtual models per course** so OpenWebUI can list them.

### `GET /healthz`
Simple health check.

---

## Runtime Components

- **Loom Gateway (FastAPI)** — retrieval + prompting + OpenAI proxy.
- **Qdrant** — vector DB (collection per `course_id`).
- **Postgres** — `courses`, `documents`, `chunks`.
- **Caddy** — reverse proxy (maps `/v1/*` → gateway).

---

## Data Model (minimal)

- `courses(id, name, guardrails)`
- `documents(id, course_id, filename, sha256, bytes, created_at)`
- `chunks(id, document_id, course_id, chunk_index, sha256, text, created_at)`

---

## Retrieval

- **Embeddings:** `text-embedding-3-large` (configurable via `.env`).
- **Search:** cosine similarity in Qdrant (`TOP_K` default 6).
- Context (with scores) + **guardrails** are prepended to the system prompt.

---

## Configuration

Key `.env` vars:
~~~
LOOM_CHAT_MODEL=gpt-4o-mini
LOOM_EMBED_MODEL=text-embedding-3-large
QDRANT_HOST=qdrant
POSTGRES_HOST=postgres
TOP_K=6
CHUNK_SIZE_CHARS=1500
CHUNK_OVERLAP_CHARS=200
~~~

Optional:
~~~
LOOM_MODEL_PREFIX=loom   # for model ids like loom:<course>
~~~

---

## Troubleshooting

- **OpenWebUI “Network Problem”**
  - Usually a **400 Missing course_id**. Fix by selecting a **course model** (e.g., `gpt-4o-mini@TCMT631_Fall25`) or append `?course_id=...` to the connection URL.
  - Ensure Loom URL is `http://loom-gateway:8000/v1` from inside the OpenWebUI container (same docker network).

- **Qdrant unhealthy**
  - Remove the healthcheck in `docker-compose.yml` and use `condition: service_started`.

- **PDF parse error / empty text**
  - OCR the PDF and re-ingest.

---

## Roadmap
Re-ranker, OCR pipeline, async ingest worker, S3/MinIO raw store, metrics (hit rate/latency), RBAC hardening, LMS integrations, eval harness, quotas/rate limits, multi-tenant isolation, onboarding wizard + dashboard.

---

## Why this design
OpenWebUI UX stays intact while Loom controls retrieval, guardrails, and indexing. Per-course “models” give a clean mental model **and** plug into OpenWebUI’s model-level RBAC.
