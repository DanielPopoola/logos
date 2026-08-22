# Logos

Turn YouTube sermons into a searchable, personal knowledge base.

Paste a sermon URL, get back a structured summary, key teachings, themes, and Bible references — then search across everything you've listened to in natural language, and ask questions answered from your own library with sources cited.

Full product context, requirements, and API contracts live in [`design-doc.md`](./design-doc.md). Epic/ticket breakdown lives in [`epics-tickets.md`](./epics-tickets.md).

## Status

Actively in development, built ticket-by-ticket with TDD (red → green per behavior, see `epics-tickets.md` for the working method).

- [x] **Epic 1 — Foundations**: models, migrations, constraints (all proven with tests)
- [x] **Epic 2 — Auth**: Google OAuth (backend-driven redirect + code exchange), opaque sessions, unified `APIResponse` envelope for all endpoints
- [x] **Epic 3 — Ingestion pipeline**: transcript fetch, chunking, LLM analysis, embeddings, Celery worker orchestration, idempotency + failure handling — verified against real YouTube + real LLM calls, not just mocks
- [ ] **Epic 4 — Sermon API**: submit, library, detail, delete
- [ ] **Epic 5 — Notes**
- [ ] **Epic 6 — Search & RAG**

## Stack

- **API**: FastAPI
- **Database**: PostgreSQL + `pgvector` (relational + vector data in one system of record)
- **ORM / Migrations**: SQLAlchemy + Alembic
- **Queue / Worker**: Celery + Redis
- **Transcript source**: `youtube_transcript_api` (free, no ASR fallback at MVP)
- **LLM / Embeddings**: Gemini via an OpenAI-compatible endpoint, behind a provider-agnostic client (`app/llm/client.py`) — swappable without touching ingestion or RAG logic
- **Auth**: Google OAuth (backend-driven), opaque session tokens (not JWTs)
- **Package management**: `uv`
- **Lint / Types**: `ruff` + `ty`, enforced via `pre-commit` and CI

## Project structure

```
app/
├── main.py            # FastAPI app, router mounting, exception handler
├── config.py           # settings from .env
├── database.py         # engine, session factory, get_db dependency
├── errors.py            # AppException + unified error handler
├── schemas/
│   └── response.py       # APIResponse[T] envelope (success/data/error)
│
├── models/                # SQLAlchemy models, one file per entity group
├── schemas/                # Pydantic request/response models
├── api/                     # routers — thin, call services only
│   └── deps.py                # get_current_user
│
├── llm/                       # provider-agnostic LLM client
│   └── client.py                # generate_structured(), embed_batch()
│
├── ingestion/                  # the async pipeline — separate from services
│   ├── youtube.py                # transcript extraction
│   ├── chunking.py               # transcript → timestamped chunks
│   ├── analysis.py               # structured sermon analysis
│   └── embeddings.py             # chunk embeddings
│
└── workers/
    ├── celery_app.py              # Celery config
    └── tasks.py                    # process_sermon orchestration task

scripts/
└── verify_ingestion.py    # manual smoke test: real YouTube URL → real LLM,
                             # no DB/Celery involved

tests/
├── models/                 # constraint/behavior tests
├── api/                     # endpoint tests (mocked external calls)
├── ingestion/                # pipeline stage tests
├── llm/                       # LLM client tests
└── workers/                    # worker orchestration tests
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

## Running

```bash
# API server
uv run uvicorn app.main:app --reload

# Worker (separate terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info
```

## Testing

```bash
# Fast suite (mocked external calls — this is what CI runs)
uv run pytest -m "not slow"

# Include real network calls (YouTube, LLM) — run manually, not in CI
uv run pytest -m "slow"

# Everything
uv run pytest
```

Working method is TDD throughout: one behavior → one failing test (RED) → minimal code to pass (GREEN) → refactor with tests still green. See `epics-tickets.md` for the full ticket-by-ticket behavior breakdown.

### Manually verifying the ingestion pipeline

Outside the test suite, against a real sermon and real LLM calls:

```bash
uv run python scripts/verify_ingestion.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Prints transcript stats, chunk boundaries, full structured analysis, and embedding dimensions — useful for sanity-checking prompt quality or provider changes without touching the DB or Celery.

## Design notes

A few decisions worth knowing about before reading the code:

- **Sermons are canonical, not per-user.** A `Sermon` is keyed by `youtube_video_id` and shared across every user who imports it — transcript retrieval and LLM analysis happen once per video, not once per user. `UserSermon` is the join table representing "this user has this in their library." See design-doc.md's Alternatives Considered / NFRs for the reasoning.
- **`app/llm/client.py` is the only place that knows about the LLM provider.** Both ingestion (`analysis.py`, `embeddings.py`) and, later, RAG depend on this one module — swapping providers or endpoints means changing config, not call sites.
- **Every API response is wrapped in `APIResponse[T]`** (`{success, data, error}`), and every error path raises `AppException` rather than a bare `HTTPException` — consistent shape for the frontend to depend on, including a `code` field for programmatic handling and a `request_id` for tracing.
- **Auth is backend-driven OAuth**, not frontend-token-verification — the API owns the full redirect + code exchange with Google, then issues its own opaque session token. No JWT signing/rotation to maintain.

## Known open issues

Tracked in `design-doc.md` under Open Issues:

- Chunk timestamp boundaries occasionally overlap slightly between consecutive chunks — not yet diagnosed whether it's a chunking bug or reflects overlapping timing in raw YouTube caption data. Deferred.
- Action point completion tracking (mark as done/not done) is deferred post-MVP — action points are currently generated and shown but stateless.