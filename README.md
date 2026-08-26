# Logos

A backend for turning YouTube sermons into a searchable, personal knowledge base: submit a sermon URL, get back a structured summary, key teachings, themes, and Bible references; then search across everything you've listened to in natural language, or ask a question and get an answer grounded in your own library, with sources cited.

Built as a from-scratch redesign of an earlier single-tenant pipeline, this version is multi-tenant, asynchronous, and built around a persistent, searchable library rather than a one-shot notification.

## Architecture

```mermaid
flowchart TB
    Client([Client])

    subgraph API["API process (FastAPI)"]
        Router["Routers<br/>auth · sermons · notes · search · ask"]
        Services["Services<br/>business rules, no SQL or HTTP"]
        Repos["Repositories<br/>persistence access"]
    end

    subgraph Async["Async ingestion"]
        Queue[("Redis<br/>broker")]
        Worker["Celery worker<br/>process_sermon"]
    end

    subgraph Data["Data"]
        PG[("PostgreSQL<br/>+ pgvector")]
    end

    subgraph External["External services"]
        YT["YouTube<br/>transcript"]
        LLM["Gemini<br/>analysis + embeddings"]
    end

    Client -->|"REST, session cookie"| Router
    Router --> Services
    Services --> Repos
    Repos --> PG

    Services -->|"enqueue on submit"| Queue
    Queue --> Worker
    Worker --> YT
    Worker --> LLM
    Worker -->|"persist analysis, chunks, embeddings"| PG

    Client -.->|"poll status"| Router
```

The API path is synchronous and fast: submitting a sermon just validates the URL, writes a `pending` row, and enqueues a job — it never waits on YouTube or an LLM call. Ingestion runs entirely in the worker, is idempotent (safe to retry without duplicating rows), and the client polls `GET /v1/sermons/{id}` for status rather than holding a connection open.

## API reference

All responses are wrapped in a consistent envelope: `{ "success": bool, "data": T | null, "error": ErrorDetail | null }`. The current user is always derived from the session cookie, never from the request body or path.

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/auth/google` | Exchange a Google ID token for a session |
| `POST` | `/v1/auth/logout` | Invalidate the current session |
| `GET` | `/v1/auth/me` | Current authenticated user |
| `POST` | `/v1/sermons` | Submit a YouTube URL for ingestion |
| `GET` | `/v1/sermons` | List the current user's library, paginated, filterable by theme |
| `GET` | `/v1/sermons/{id}` | Full sermon detail: analysis, themes, references, notes |
| `DELETE` | `/v1/sermons/{id}` | Remove from the current user's library |
| `POST` | `/v1/sermons/{id}/notes` | Add a personal note to a sermon |
| `PATCH` | `/v1/notes/{id}` | Edit a note |
| `DELETE` | `/v1/notes/{id}` | Delete a note |
| `GET` | `/v1/search` | Semantic search across the user's library |
| `POST` | `/v1/ask` | Ask a question, answered from the user's library with cited sources |
| `GET` | `/healthz` | Liveness/readiness check — database connectivity |

Full request/response shapes: [`design-doc.md`](./design-doc.md).

## Stack

| Concern | Choice | Why |
|---|---|---|
| API | FastAPI | Async-native, typed request/response models via Pydantic |
| Database | PostgreSQL + `pgvector` | One system of record for relational and vector data — no separate vector database to operate |
| ORM / migrations | SQLAlchemy + Alembic | |
| Queue / worker | Celery + Redis | Decouples slow ingestion from the request/response cycle |
| Transcript source | `youtube_transcript_api` | Free, no ASR cost — see Known limitations |
| LLM / embeddings | Gemini, via an OpenAI-compatible endpoint | Behind a provider-agnostic client — swapping providers means changing config, not call sites |
| Auth | Google OAuth, backend-driven | Opaque session tokens, not JWTs — no signing or rotation to maintain |
| Error tracking | Sentry | No-op unless `SENTRY_DSN` is set |
| Package management | `uv` | |
| Lint / types | `ruff` + `ty` | Enforced in CI and pre-commit |

## Design decisions

- **Sermons are canonical, not per-user.** A `Sermon` is keyed by `youtube_video_id` and shared across every user who imports it — transcript retrieval and LLM analysis happen once per video, not once per user. `UserSermon` is the join table representing "this user has this in their library."
- **Business logic never touches SQL or HTTP.** Services hold business rules and call repositories; repositories hold queries and never commit; routers are thin and only translate HTTP in and out. Each layer is independently testable.
- **Repositories are split by bounded use-case, not strictly by entity.** `IngestionRepository` answers the worker's questions; `SermonRepository` answers the library's. Both touch `Sermon`, deliberately, rather than forcing one god-repository per table.
- **Every unexpected error is caught once, logged with full context, and never leaks internals to the client.** A raw ASGI middleware wraps the entire request — not `add_exception_handler`, which has a documented gap in how it interacts with other middleware — so nothing can slip past it.
- **A request's ID threads through its logs and its error response.** Set once per request, read by the logging formatter and the error handler alike — one ID to grep for the whole request's story.
- **Sources in a RAG answer are assembled from what was actually retrieved, never from what the model claims it used.** The LLM only ever returns the answer text; the citation list is built by the service from the retrieved chunks.

## Getting started

```bash
uv sync --all-extras --dev
docker compose up -d               # Postgres (pgvector) + Redis
cp .env.example .env               # fill in real values, see below
uv run alembic upgrade head
uv run pre-commit install
```

```bash
uv run uvicorn app.main:app --reload                          # API
uv run celery -A app.workers.celery_app worker --loglevel=info  # worker, separate terminal
```

### Environment variables

```
DATABASE_URL=postgresql://logos:logos@localhost:5432/logos
REDIS_URL=redis://localhost:6379/0

LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=
LLM_MODEL_NAME=gemini-2.0-flash
LLM_EMBEDDING_MODEL_NAME=gemini-embedding-001
LLM_EMBEDDING_DIMENSIONS=768

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/v1/auth/google/callback

# Optional
LOG_LEVEL=INFO
SENTRY_DSN=          # unset = no-op; set in staging/production only
```

## Testing

Built test-first throughout: one behavior, one failing test, minimal code to pass, refactor with tests green. Integration tests run against real PostgreSQL rather than mocks or SQLite, so constraints, cascades, and the vector index are proven to actually work, not just declared.

Tests use a separate database from dev (`logos_test`, same Postgres container) so manual testing via Postman or curl can never leak a row into a test run:

```bash
docker compose exec postgres psql -U logos -d logos -c "CREATE DATABASE logos_test;"
echo "DATABASE_URL=postgresql://logos:logos@localhost:5432/logos_test" > .env.test
DATABASE_URL=postgresql://logos:logos@localhost:5432/logos_test uv run alembic upgrade head
```

```bash
uv run pytest -m "not slow"   # fast suite, mocked externals — what CI runs
uv run pytest -m "slow"       # real YouTube/LLM calls — run manually
```

```bash
uv run python scripts/verify_ingestion.py "https://www.youtube.com/watch?v=VIDEO_ID"
```
runs the ingestion pipeline against a real video and a real LLM call outside the app entirely — useful for sanity-checking prompt quality or a provider change without touching the database or Celery.

## Deployment

Both processes shut down gracefully on `SIGTERM`, but the platform's own termination grace period has to exceed each process's shutdown window or its `SIGKILL` arrives first.

| Process | Shutdown behavior | Configure |
|---|---|---|
| API | Uvicorn drains in-flight requests; the DB connection pool is disposed on exit. | Platform defaults are sufficient. |
| Worker | Stops accepting new tasks on `SIGTERM`, gets up to 180s to finish the current one before a cold shutdown. | Set the platform's grace period (Kubernetes `terminationGracePeriodSeconds`, or equivalent) to at least 180s. |

A task hard-killed mid-flight is safely requeued rather than lost — `IngestionService.run` is idempotent, so a retried sermon never produces duplicate rows. `GET /healthz` checks database connectivity and is the right target for a platform's readiness/liveness probe.

## Known limitations

- **`youtube_transcript_api` is blocked outright from most cloud-provider IP ranges.** It scrapes caption data rather than calling an official API, and YouTube blocklists cloud ASNs — not a rate limit that backs off, a standing block. Confirmed in testing: works reliably from a residential IP, fails on essentially every request from a cloud host. The documented workaround is a rotating residential proxy; not yet implemented, and a real recurring cost rather than a one-time fix. This currently blocks deploying ingestion to any cloud platform.
- Chunk timestamp boundaries occasionally overlap slightly between consecutive chunks — not yet diagnosed as a chunking bug versus overlapping timing in the raw YouTube caption data.
- Action point completion tracking (marking a point done) is deferred — action points are generated and shown but stateless.

Full context for all three: [`design-doc.md`](./design-doc.md), Open Issues.