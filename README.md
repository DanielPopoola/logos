# Logos

Turn YouTube sermons into a searchable, personal knowledge base.

Paste a sermon URL, get back a structured summary, key teachings, themes, and Bible references — then search across everything you've listened to in natural language, and ask questions answered from your own library with sources cited.

Full product context, requirements, and API contracts live in [`design-doc.md`](./design-doc.md). Epic/ticket breakdown lives in [`epics-tickets.md`](./epics-tickets.md).

## Status

Built ticket-by-ticket with TDD (red → green per behavior; see `epics-tickets.md` for the working method).

- [x] **Epic 1 — Foundations**: models, migrations, constraints, all proven with tests
- [x] **Epic 2 — Auth**: Google OAuth (backend-driven redirect + code exchange), opaque sessions, unified `APIResponse` envelope for all endpoints
- [x] **Epic 3 — Ingestion pipeline**: transcript fetch, chunking, LLM analysis, embeddings, Celery worker orchestration, idempotency + failure handling — verified against real YouTube and real LLM calls, not just mocks
- [x] **Epic 4 — Sermon API**: submit, library, detail, delete
- [x] **Epic 5 — Notes**: CRUD with ownership checks
- [x] **Epic 6 — Search & RAG**: semantic search (`pgvector` cosine similarity), question-answering grounded in retrieved sermon chunks, empty-library guards on both
- [x] **Epic 7 — Production readiness**: request-ID tracing, structured JSON logging, unhandled-exception handling, Sentry, graceful shutdown, health checks

## Stack

- **API**: FastAPI
- **Database**: PostgreSQL + `pgvector` — relational and vector data in one system of record
- **ORM / migrations**: SQLAlchemy + Alembic
- **Queue / worker**: Celery + Redis
- **Transcript source**: `youtube_transcript_api` — free, no ASR fallback at MVP
- **LLM / embeddings**: Gemini via an OpenAI-compatible endpoint, behind a provider-agnostic client (`app/llm/client.py`) — swappable without touching ingestion or RAG logic
- **Auth**: Google OAuth (backend-driven), opaque session tokens, not JWTs
- **Error tracking**: Sentry — a no-op unless `SENTRY_DSN` is set
- **Package management**: `uv`
- **Lint / types**: `ruff` + `ty`, enforced via `pre-commit` and CI

## Project structure

```
app/
├── main.py                    # FastAPI app: middleware, routers, lifespan
├── config.py                  # Settings, read once from .env
├── database.py                 # Engine, session factory, get_db dependency
├── errors.py                    # AppException + its handler
├── logging_config.py             # JSON log formatter, configure_logging()
├── request_context.py             # Per-request ID, shared by logs and error responses
├── sentry_config.py                # init_sentry() — no-op when SENTRY_DSN unset
│
├── models/            # SQLAlchemy models, one file per entity group
├── schemas/            # Pydantic request/response models
├── repositories/         # Persistence access, one repo per bounded use-case
├── services/               # Business rules — no SQL, no HTTP, unit-testable alone
├── api/                       # Routers — thin, call services only
│   └── deps.py                  # get_current_user and other DI providers
├── middleware/                   # Request-ID tagging, last-resort exception catch
│
├── llm/                             # Provider-agnostic LLM client
│   └── client.py                     # generate_structured(), embed_batch()
│
├── ingestion/                          # The async pipeline's pure logic
│   ├── youtube.py                        # Transcript extraction
│   ├── chunking.py                       # Transcript → timestamped chunks
│   ├── analysis.py                       # Structured sermon analysis
│   ├── embeddings.py                     # Chunk embeddings
│   └── bible_reference.py                 # Reference string parsing (book/chapter/verse)
│
├── auth/
│   └── google_client.py    # Google OAuth code exchange + userinfo fetch
│
└── workers/
    ├── celery_app.py          # Celery config, logging/Sentry/shutdown wiring
    └── tasks.py                 # process_sermon — thin delivery wrapper

scripts/
└── verify_ingestion.py    # Manual smoke test: real YouTube URL → real LLM,
                             # no DB or Celery involved

tests/
├── models/           # Constraint/behavior tests
├── api/               # Endpoint tests, external calls mocked
├── services/            # Business-rule tests
├── ingestion/             # Pipeline stage tests
├── llm/                     # LLM client tests
└── workers/                   # Worker orchestration and signal-handler tests
```

## Setup

```bash
# Install dependencies
uv sync --all-extras --dev

# Start Postgres (pgvector) + Redis
docker compose up -d

# Configure environment
cp .env.example .env   # fill in real values, see below

# Run migrations
uv run alembic upgrade head

# Install git hooks
uv run pre-commit install
```

### Required environment variables

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
```

### Optional environment variables

```
LOG_LEVEL=INFO   # defaults to INFO

SENTRY_DSN=      # unset = no-op; set only in staging/production
```

## Running

```bash
# API server
uv run uvicorn app.main:app --reload

# Worker (separate terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info
```

`GET /healthz` checks database connectivity and returns 200/503 — useful as a manual smoke check that both are wired up correctly.

## Testing

Tests run against a **separate database from dev** (`logos_test`, same Postgres container). This is what keeps a row created while manually testing via Postman or curl from leaking into a test run, and vice versa.

One-time setup:

```bash
docker compose exec postgres psql -U logos -d logos -c "CREATE DATABASE logos_test;"

# Only DATABASE_URL needs to differ from your regular .env:
echo "DATABASE_URL=postgresql://logos:logos@localhost:5432/logos_test" > .env.test

DATABASE_URL=postgresql://logos:logos@localhost:5432/logos_test uv run alembic upgrade head
```

`tests/conftest.py` loads `.env.test` automatically and overrides any `DATABASE_URL` already in your shell or `.env` — nothing to export manually before running `pytest`.

```bash
# Fast suite — mocked external calls, what CI runs
uv run pytest -m "not slow"

# Real network calls (YouTube, LLM) — run manually, not in CI
uv run pytest -m "slow"

# Everything
uv run pytest
```

Working method is TDD throughout: one behavior, one failing test (RED), minimal code to pass (GREEN), refactor with tests still green. See `epics-tickets.md` for the full ticket-by-ticket behavior breakdown.

### Manually verifying the ingestion pipeline

Against a real sermon and real LLM calls, outside the test suite:

```bash
uv run python scripts/verify_ingestion.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Prints transcript stats, chunk boundaries, full structured analysis, and embedding dimensions — useful for sanity-checking prompt quality or provider changes without touching the DB or Celery.

## Design notes

Decisions worth knowing before reading the code:

- **Sermons are canonical, not per-user.** A `Sermon` is keyed by `youtube_video_id` and shared across every user who imports it — transcript retrieval and LLM analysis happen once per video, not once per user. `UserSermon` is the join table representing "this user has this in their library." See `design-doc.md`'s Alternatives Considered / NFRs for the reasoning.
- **`app/llm/client.py` is the only place that knows about the LLM provider.** Ingestion (`analysis.py`, `embeddings.py`) and search/RAG (`search_service.py`) all depend on this one module — swapping providers or endpoints means changing config, not call sites.
- **Every API response is wrapped in `APIResponse[T]`** (`{success, data, error}`), and every expected error path raises `AppException` rather than a bare `HTTPException` — one consistent shape for the frontend to depend on, including a `code` field for programmatic handling and a `request_id` for tracing.
- **A request's `request_id` is shared by its logs and its error response.** Set once per request by `RequestIDMiddleware`, read by both `logging_config.py`'s formatter and `errors.py` — grep one ID, see the whole request's story.
- **Repositories are split by bounded use-case, not strictly by entity.** `IngestionRepository` (the worker's questions) and `SermonRepository` (the library's questions) both touch `Sermon`, deliberately — see `IngestionRepository`'s docstring.
- **Auth is backend-driven OAuth**, not frontend-token-verification. The API owns the full redirect and code exchange with Google, then issues its own opaque session token — no JWT signing or rotation to maintain.

## Deployment notes (container platforms)

Both processes handle `SIGTERM` gracefully, but **the platform's own termination grace period must exceed each process's shutdown window**, or its `SIGKILL` arrives before cleanup finishes.

| Process | Shutdown behavior | What to configure |
|---|---|---|
| API (`app.main:app`) | Uvicorn stops accepting new connections and finishes in-flight requests; `lifespan` disposes the DB connection pool on exit. | No extra config needed beyond uvicorn's own defaults. |
| Worker (`app.workers.celery_app:celery_app`) | On `SIGTERM`, stops accepting new tasks and gets up to `worker_soft_shutdown_timeout` (180s) to finish the current one before a cold shutdown. | Set the platform's grace period (e.g. Kubernetes `terminationGracePeriodSeconds`, or the Fly/Render equivalent) to **at least 180s**. |

`task_acks_late` + `task_reject_on_worker_lost` mean a task hard-killed mid-flight gets requeued rather than lost — safe here because `IngestionService.run` is idempotent (a retried sermon doesn't produce duplicate rows).

`GET /healthz` checks DB connectivity and returns 200/503 — point the platform's readiness/liveness check here. Unauthenticated, outside `/v1`.

**Known gap, intentionally deferred:** a `ProcessingJob` stuck in `processing` from a worker that was hard-killed anyway (grace period exceeded, or an infra-level force-kill) has no automatic reconciliation. It stays `processing` until manually retried. Tracked as a follow-up, not solved here.

## Known open issues

Tracked in `design-doc.md` under Open Issues:

- Chunk timestamp boundaries occasionally overlap slightly between consecutive chunks — not yet diagnosed as a chunking bug vs. overlapping timing in raw YouTube caption data. Deferred.
- Action point completion tracking (mark as done/not done) is deferred post-MVP — action points are currently generated and shown but stateless.