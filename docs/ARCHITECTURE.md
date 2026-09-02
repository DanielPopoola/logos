# Logos Architecture

## System Overview

Logos is a Python/FastAPI backend that turns YouTube sermons into a searchable, personal knowledge base — multi-tenant by design, with a canonical/shared sermon layer separated from per-user library and note data.

```mermaid
graph TB
    subgraph "Client Layer"
        WB[Web Browser<br/>Frontend Client]
    end

    subgraph "External: Auth"
        GOOGLE[Google OAuth<br/>Identity Provider]
    end

    subgraph "External: Content"
        YT[YouTube<br/>Transcript Source]
    end

    subgraph "External: AI"
        LLM[Gemini<br/>OpenAI-compatible API<br/>analysis + embeddings]
    end

    subgraph "API Layer (FastAPI)"
        AUTHR[auth.py<br/>Login / Callback / Session]
        SERMR[sermons.py<br/>Submit / Library / Detail / Notes]
        NOTER[notes.py<br/>Patch / Delete]
        SEARCHR[search.py<br/>Semantic Search]
        ASKR[ask.py<br/>RAG Q&A]
        HEALTHR[health.py<br/>Liveness]
        MW[Request-ID + Unhandled<br/>Exception Middleware]
    end

    subgraph "Service Layer (business rules, HTTP-agnostic)"
        AUTHS[AuthService]
        SERMS[SermonService]
        NOTES[NoteService]
        SEARCHS[SearchService]
        INGESTS[IngestionService]
    end

    subgraph "Repository Layer (persistence, no business rules)"
        USERREPO[UserRepository]
        SESSREPO[SessionRepository]
        SERMREPO[SermonRepository]
        NOTEREPO[NoteRepository]
        SEARCHREPO[SearchRepository]
        INGESTREPO[IngestionRepository]
    end

    subgraph "Async Worker (Celery + Redis)"
        TASK[process_sermon task<br/>thin delivery wrapper]
    end

    subgraph "Data Layer"
        PG[(PostgreSQL + pgvector<br/>one system of record)]
    end

    WB --> AUTHR
    WB --> SERMR
    WB --> NOTER
    WB --> SEARCHR
    WB --> ASKR

    AUTHR --> AUTHS
    SERMR --> SERMS
    NOTER --> NOTES
    SEARCHR --> SEARCHS
    ASKR --> SEARCHS

    AUTHS --> USERREPO
    AUTHS --> SESSREPO
    SERMS --> SERMREPO
    SERMS --> NOTEREPO
    NOTES --> NOTEREPO
    NOTES --> SERMREPO
    SEARCHS --> SEARCHREPO
    SEARCHS --> SERMREPO

    AUTHR -.google login/callback.-> GOOGLE

    SERMS -- enqueues --> TASK
    TASK --> INGESTS
    INGESTS --> INGESTREPO
    INGESTS -. fetch transcript .-> YT
    INGESTS -. analyze + embed .-> LLM
    SEARCHS -. embed query .-> LLM

    USERREPO --> PG
    SESSREPO --> PG
    SERMREPO --> PG
    NOTEREPO --> PG
    SEARCHREPO --> PG
    INGESTREPO --> PG

    classDef client fill:#e3f2fd,stroke:#1976d2
    classDef api fill:#f3e5f5,stroke:#7b1fa2
    classDef service fill:#e8f5e9,stroke:#388e3c
    classDef repo fill:#fce4ec,stroke:#c2185b
    classDef worker fill:#fff3e0,stroke:#f57c00
    classDef data fill:#fff3e0,stroke:#f57c00
    classDef external fill:#ffe0b2,stroke:#e65100

    class WB client
    class AUTHR,SERMR,NOTER,SEARCHR,ASKR,HEALTHR,MW api
    class AUTHS,SERMS,NOTES,SEARCHS,INGESTS service
    class USERREPO,SESSREPO,SERMREPO,NOTEREPO,SEARCHREPO,INGESTREPO repo
    class TASK worker
    class PG data
    class GOOGLE,YT,LLM external
```

**Tech Stack:**

- **Backend:** Python (FastAPI), layered handler → service → repository architecture
- **Database:** PostgreSQL + `pgvector` — one system of record for relational and vector data; no separate vector database
- **ORM/Migrations:** SQLAlchemy + Alembic
- **Async Processing:** Celery + Redis broker, for ingestion only (no websockets/SSE — status is polled)
- **Auth:** Google OAuth (backend-driven redirect + authorization-code exchange), opaque server-issued session tokens via httpOnly cookie — not JWTs
- **AI:** Gemini via an OpenAI-compatible client (`app/llm/client.py`), used for structured analysis generation and 768-dim embeddings
- **Transcript source:** `youtube_transcript_api` (free, caption-only, no ASR fallback)
- **Observability:** Sentry (FastAPI + Starlette + Celery integrations), structured JSON logging, request-ID propagation
- **Tooling:** `uv`, `ruff`, `ty`, `pre-commit`, GitHub Actions CI

## Architecture Patterns

### Request Flow

**Handler (`app/api/*`) → Service (`app/services/*`) → Repository (`app/repositories/*`) → Database**

- **Handlers:** HTTP request/response shape only — parse the request, call one service method, translate typed domain exceptions into `AppException` (which becomes the HTTP status/error code). No SQLAlchemy, no business rules.
- **Services:** Business rules, orchestration, and the transaction boundary. Every service takes its `DBSession` and repositories via constructor injection and calls `db.commit()` itself — repositories never commit. Services raise plain typed exceptions (`SermonNotFoundError`, `InvalidSessionError`, `AnswerParseError`, etc.) and know nothing about HTTP.
- **Repositories:** One per aggregate (`SermonRepository`, `NoteRepository`, `SessionRepository`, `UserRepository`, `SearchRepository`, `IngestionRepository`). Pure data access — queries, adds, deletes. No business rules, no commits. `SearchRepository` and `IngestionRepository` are intentionally separate from `SermonRepository` even though they touch the same tables: each serves a distinct bounded use case (vector retrieval; worker-side ingestion bookkeeping) rather than being a general-purpose "sermon" grab-bag.

All dependency wiring — `DBSession` → repository → service — happens through FastAPI's `Depends()` chains in `app/api/deps.py`. Nothing is instantiated as a global or reached for directly inside business logic.

### Async Ingestion Flow

Ingestion is decoupled from the request that triggers it:

1. `POST /v1/sermons` → `SermonService.submit_sermon` creates a `Sermon` (pending) + `ProcessingJob`, commits, then calls `process_sermon.delay(...)` and returns immediately.
2. The Celery task (`app/workers/tasks.py`) is a ~12-line wrapper: open a DB session, construct `IngestionService(db, IngestionRepository(db))`, call `.run(sermon_id)`, close the session. All business logic — the pending → processing → completed/failed state machine, retry-limit enforcement, idempotent persistence — lives in `IngestionService`, not in the task.
3. `IngestionService.run` is deliberately Celery-agnostic: it's callable identically from the task, a script, or a test. It runs `get_transcript → chunk_transcript → analyze_transcript → embed_chunks`, persists results idempotently (checks `has_analysis`/`has_chunks` before inserting, so retries never duplicate rows), and updates `Sermon.status` accordingly.
4. Failures (e.g. no captions available) are caught, logged with `exc_info`, reported to Sentry, and recorded on both `Sermon.failure_reason` and `ProcessingJob.error_message`/`attempt_count` — capped at `MAX_ATTEMPTS = 3`.

## Database Design

### Schema Overview

**Canonical (shared) entities** — one row regardless of how many users import the sermon:

- `sermons` — keyed by unique `youtube_video_id`; this uniqueness constraint is what the whole dedup design rests on
- `sermon_analyses` — 1:1 with `sermons`
- `sermon_chunks` — transcript segments with `vector(768)` embeddings, `ivfflat` cosine index
- `themes`, `bible_references` + their plain many-to-many association tables

**Per-user entities:**

- `users`, `sessions` (opaque token auth, not JWT)
- `user_sermons` — the library-membership join (`user_id` + `sermon_id`, composite PK)
- `user_notes`

**Worker bookkeeping:**

- `processing_jobs` — a durable Postgres record of ingestion status/attempts/errors, kept deliberately separate from Celery's own (transient, Redis-backed) task state. `GET /v1/sermons/{id}` needs status in the same query as the rest of the sermon's data, and the durability NFR rules out relying on the broker alone.

### Relationships

- `User` → `Session` (1:many, cascade delete)
- `User` ↔ `Sermon` via `UserSermon` (many:many, per-user membership)
- `User` → `UserNote` (1:many, scoped to a sermon within that user's library)
- `Sermon` → `SermonAnalysis` (1:1)
- `Sermon` → `SermonChunk` (1:many, embedded independently for retrieval)
- `Sermon` ↔ `Theme`, `Sermon` ↔ `BibleReference` (many:many, shared taxonomy)
- `Sermon` → `ProcessingJob` (1:1 in practice, one job row per sermon)

## Security & Privacy

### Authentication

1. **OAuth flow (backend-driven redirect):**
   - `GET /v1/auth/google/login` redirects to Google's consent screen
   - `GET /v1/auth/google/callback` exchanges the authorization `code` for tokens (`app/auth/google_client.py`), fetches the profile, finds-or-creates the `User` by `google_id`, and issues a session — no ID-token-verification-on-frontend flow, no passwords stored anywhere
   - Any failure in the exchange or profile fetch is caught and surfaces as a single `401 google_auth_failed` — deliberately opaque to the client; real cause goes to logs

2. **Session management:**
   - Opaque, server-issued token (`secrets.token_urlsafe(32)`), stored in `sessions`, returned as an httpOnly cookie — session validity is a single row lookup, not JWT signature verification
   - 7-day TTL (`SESSION_TTL_DAYS`), checked lazily in `AuthService.get_authenticated_user` — an expired-but-still-present row is treated as invalid (`SessionExpiredError`), distinct from a nonexistent one (`InvalidSessionError`), each mapped to its own 401 error code in `deps.py`

### Multi-Tenant Data Isolation

1. **Enforced at the repository layer, never left to the caller:** every user-scoped repository method takes `user_id` as a required parameter (`get_owned_with_saved_at(user_id, sermon_id)`, `get_owned_by_user(note_id, user_id)`, etc.) — there's no method that fetches a sermon or note without a user filter.
2. **Non-leaking 404s by design:** `SermonNotFoundError` and note ownership failures are raised identically whether the resource doesn't exist or simply isn't the caller's — a non-owner can never distinguish "not found" from "not yours" via the API. This is a deliberate, documented choice in `SermonService`'s docstrings, not an oversight.
3. **The canonical `Sermon` is not a cache.** It exists to avoid re-transcribing/re-analyzing a video multiple users submit — it is not deduplicated user data. Deleting a sermon from a library only ever removes the `UserSermon` row; the canonical row and any other user's membership survive untouched.

### Error Handling & Observability

- **`AppException`** is the one typed exception the API layer raises for all expected failure modes (`404 sermon_not_found`, `401 invalid_session`, `400 invalid_youtube_url`, etc.), caught by a single `app_exception_handler` that shapes the standard error envelope and echoes the request ID.
- **`UnhandledExceptionMiddleware`** is a true last-resort net for anything else — implemented as raw ASGI middleware rather than Starlette's `BaseHTTPMiddleware`, because of a documented Starlette limitation where outer `BaseHTTPMiddleware` header mutations aren't reliably applied on the exception-handler response path. It logs the full traceback server-side and returns a generic, non-leaking `500 internal_error` to the client.
- **Request ID propagation:** `RequestIDMiddleware` reuses an incoming `X-Request-ID` header or generates one, binds it to a `contextvars.ContextVar` for the life of the request, and echoes it on every response (success, handled error, or unhandled error) — so a single ID correlates a client-side report with server logs regardless of how the request ended.
- **Sentry** is wired for FastAPI, Starlette, and Celery (`celeryd_init`-based init so it's ready before worker processes spawn) — a no-op if `SENTRY_DSN` is unset.

## API Design

### RESTful Endpoints

All routes below `/v1`, session-cookie authenticated unless noted. Full request/response shapes: see `docs/API.md`.

```plaintext
# Auth
GET    /v1/auth/google/login       # Redirect to Google consent screen
GET    /v1/auth/google/callback    # OAuth callback, issues session cookie
POST   /v1/auth/logout             # Delete session (idempotent)
GET    /v1/auth/me                 # Current user profile

# Sermons
POST   /v1/sermons                 # Submit YouTube URL (5-way dedup branching)
GET    /v1/sermons                 # Paginated library, theme filter
GET    /v1/sermons/{id}            # Full detail (202 while still processing)
DELETE /v1/sermons/{id}            # Remove from library only

# Notes
POST   /v1/sermons/{id}/notes      # Create note
PATCH  /v1/notes/{id}               # Update (owner-only, 404 for non-owner)
DELETE /v1/notes/{id}               # Delete (owner-only, 404 for non-owner)

# Search & RAG
GET    /v1/search                  # Semantic search, user-scoped
POST   /v1/ask                     # RAG Q&A with cited sources

# System
GET    /healthz                    # Unauthenticated liveness/readiness check
```

### Response Envelope

Every response — success or error — is wrapped consistently (`app/schemas/response.py`):

```json
{ "success": true, "data": { ... }, "error": null }
```

```json
{ "success": false, "data": null, "error": { "code": "...", "message": "...", "request_id": "..." } }
```

## AI Integration

### Service Architecture

- **`IngestionService`** — runs the pending → processing → completed/failed pipeline: transcript fetch, chunking, structured analysis (summary, key teachings, themes, Bible references, action points, reflection questions), and batch embedding.
- **`SearchService`** — embeds the user's query, retrieves nearest chunks scoped to their library (`SearchRepository`), and for `/ask`, builds a grounded prompt from only the retrieved excerpts before calling the LLM.
- **LLM client (`app/llm/client.py`)** — a thin, provider-agnostic wrapper: `generate_structured(prompt, response_schema)` for structured JSON output and `embed_batch(texts)` for embeddings, both against an OpenAI-compatible endpoint (currently Gemini). Retried on transient errors only (`app/llm/retry.py` — connection issues, timeouts, rate limits, 5xx) with exponential backoff; auth/bad-request errors propagate immediately since retrying them can't help.

### AI Flow (ingestion)

1. `IngestionService.run` fetches the transcript, then calls `analyze_transcript` and `embed_chunks` in sequence
2. Analysis is validated against a typed Pydantic schema — a malformed/non-JSON LLM response raises rather than silently persisting garbage
3. Results are persisted idempotently: `has_analysis`/`has_chunks` checks mean a retried task never creates duplicate rows
4. Bible references that fail to parse (e.g. numbered books) are logged and skipped individually — one bad reference doesn't fail the whole sermon

### AI Flow (RAG)

1. `SearchService.answer_question` embeds the question, retrieves up to `RAG_CONTEXT_CHUNK_LIMIT = 8` chunks scoped to the user's library
2. Retrieved excerpts are formatted into a prompt that explicitly instructs the model to answer only from what's given
3. `sources` returned to the client are always the retrieved chunks themselves — never anything the LLM claims to have used — so citations stay grounded and can't be hallucinated
4. An empty library short-circuits before any embedding or LLM call is made, since there's nothing to search

## Configuration

Centralized in a single `pydantic-settings` object (`app/config.py`), loaded once at import time and injected everywhere via `Depends()` — no `os.getenv()` calls scattered through business logic.

```bash
# Database / Queue
DATABASE_URL=postgresql://logos:logos@localhost:5432/logos
REDIS_URL=redis://localhost:6379

# LLM (OpenAI-compatible endpoint)
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL_NAME=...
LLM_EMBEDDING_MODEL_NAME=...
LLM_EMBEDDING_DIMENSIONS=768

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=...

# Environment / Observability
ENVIRONMENT=production   # "test"/"development" opts into test-only routes — never implicit
LOG_LEVEL=INFO
SENTRY_DSN=              # unset = no-op
```

## Testing Strategy

### Test Levels

1. **Unit/integration tests against a real Postgres** — the project deliberately avoids mocking the database; `conftest.py` provides a transactional session fixture that rolls back after each test
2. **Slow tests** — real network calls to YouTube/Gemini are marked `@pytest.mark.slow` and excluded from the default run, kept for manual/CI-only verification
3. **TDD, vertical-slice style** — one red→green behavior at a time per ticket, not batched test-then-implement; see `epics-tickets.md` for the full ticket breakdown this codebase was built against

### Running Tests

```bash
uv run pytest                        # fast suite (slow tests excluded by marker)
uv run pytest -m slow                # real YouTube/Gemini calls
uv run pytest --cov=app              # with coverage
uv run ruff check .                  # lint
uv run ty check                      # type check
```

## Deployment Architecture

### Local Development

```bash
docker compose up          # Postgres (pgvector/pgvector:pg16) + Redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run celery -A app.workers.celery_app worker --loglevel=info
```

### Graceful Shutdown

Celery is configured for safe SIGTERM handling on container platforms: `worker_prefetch_multiplier=1` (never more than one in-flight task per worker), `task_acks_late=True` + `task_reject_on_worker_lost=True` (a hard-killed mid-flight task is requeued, not lost — safe specifically because `IngestionService.run` is idempotent), and a `worker_soft_shutdown_timeout` set above `process_sermon`'s worst-case duration. FastAPI's own `lifespan` disposes the DB connection pool on shutdown.

## Code Organization Best Practices

1. **One repository per aggregate** — `SermonRepository` and `IngestionRepository` both touch `sermons`, but serve different bounded use cases and are never merged into one "God repository"
2. **Services own the transaction boundary** — repositories never call `commit()`; that's a service-layer decision
3. **HTTP-agnostic services** — every service exception is a plain Python exception, translated to a status code only at the API layer, so services are testable without spinning up FastAPI
4. **Celery tasks are thin delivery wrappers** — `process_sermon` is ~12 lines; all logic lives in `IngestionService`, callable and testable independent of Celery entirely
5. **Idempotency is load-bearing, not incidental** — `has_analysis`/`has_chunks` checks exist specifically because `task_acks_late` + `task_reject_on_worker_lost` mean a task can genuinely run twice
6. **Non-leaking error semantics** — ownership failures (sermon, note) return the same 404 whether the resource is missing or just not the caller's; this is enforced at the service layer, not left to handler discipline

## Application Entry Points

### Main Entry Point (`app/main.py`)

- Configures logging and initializes Sentry (`StarletteIntegration` + `FastApiIntegration` — both required together per Sentry's docs, or route-level context is lost) before the `FastAPI` app is constructed
- Registers middleware in a specific, load-bearing order: `RequestIDMiddleware` first, `UnhandledExceptionMiddleware` last — Starlette's `add_middleware` prepends, so the last one added ends up outermost, guaranteeing `request_id` is already set by the time any exception reaches the last-resort handler
- Registers `AppException`'s handler, then includes each router under its `/v1` prefix
- In `test`/`development` environments only, registers two fixture-only routes (`/v1/_protected_ping`, `/v1/_boom`) for exercising auth and the unhandled-exception path through real HTTP requests — never present in production, gated by `settings.environment`

### Lifespan

A single `asynccontextmanager` lifespan logs startup, yields control to the running app, then on shutdown logs and calls `engine.dispose()` to cleanly release the DB connection pool — no separate `App` struct or multi-phase `New()/Setup()/Run()` split; FastAPI's own lifespan hook is sufficient at this scope.

### Worker Entry Point (`app/workers/celery_app.py`)

- Constructs the `Celery` app with Redis as both broker and result backend
- Replaces Celery's own logging setup with the app's structured logging (`setup_logging` signal) rather than letting the two race
- Initializes Sentry's `CeleryIntegration` on `celeryd_init` — early enough to catch worker startup errors, not just in-task ones
- A `task_failure` signal handler logs a structured, correlatable line for any exception a task doesn't catch itself — the counterpart to `UnhandledExceptionMiddleware` on the API side, and the direct fix for a real earlier incident (a Bible-reference parsing bug whose traceback only ever reached the worker's console)

This architecture keeps the shared/canonical sermon layer and the per-user library layer strictly separated at every level — schema, repository, and service — so multi-tenancy isn't a filter bolted on top but a property enforced structurally from the data model up.
