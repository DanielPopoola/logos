# Logos
 
## Metadata
 
- **Author:** Daniel Popoola
- **Created:** 2026-08-22
- **Status:** Draft — pending resolution of open issues
## Objective
 
Build a consumer application that turns YouTube sermons into a searchable, personal knowledge base — so users can capture, understand, organize, and revisit what they've learned across every message they've listened to.
 
## Background
 
Listening to gospel messages regularly produces a retention problem: content is consumed once and largely forgotten. There's no structured way to recall what a specific sermon taught, search across everything you've heard by theme or Scripture, or ask a question spanning your entire listening history.
 
An earlier project, ChurchScribe, solved a narrower version of this: single-tenant, push-based sermon processing (audio → transcript → LLM summary → notification via email/Telegram/WhatsApp) for one church's use. It proved the ingestion pipeline works, but it has no concept of a user, a persistent library, or search — it delivers a result once and is done.
 
This project is a deliberate rebuild as a separate, multi-tenant, pull-based product: users authenticate, build a personal library over time, and return to search and query it.
 
## Goals
 
- Let users capture a sermon's key teachings without manually taking notes.
- Let users search their sermon library using natural language, not just keywords.
- Let users ask questions and get answers grounded in their own sermon library, with sources cited.
- Let users add personal notes and reflections alongside AI-generated analysis.
- Clearly distinguish AI-generated interpretation from content the preacher actually said.
## Non-goals
 
- **Social/community features** (sharing, public libraries, collaborative collections) — deferred to a post-MVP phase; not needed to validate the core loop.
- **Recommendations/discovery** — deferred; requires a working library first.
- **Subscription billing / usage quotas** — deferred until there's evidence of demand.
- **Advanced Bible-study tooling** (passage-to-sermon discovery, scripture context) — deferred.
- **Personal knowledge base over the user's own notes/reflections** (as opposed to sermon content) — deferred to a later phase.
- **Non-YouTube ingestion** (audio upload, podcasts, ASR fallback) — YouTube captions only for MVP.
- **Action point completion tracking** — explicitly deferred; action points are generated and shown but not yet stateful per-user.
## Scenarios
 
**Scenario: First sermon**
1. Daniel pastes a YouTube sermon URL into the app.
2. The app confirms the submission and shows a processing status.
3. A few minutes later, Daniel returns to see a summary, key teachings, themes, and Bible references generated from the sermon.
4. Daniel adds a personal note reflecting on how the message applies to him.
**Scenario: Returning to search**
1. Weeks later, Daniel wants to recall what he's learned about trusting God during hardship.
2. He searches "messages about trusting God when things aren't going well."
3. The app returns sermons whose content is semantically related, even without exact keyword matches, each with the relevant transcript excerpt.
**Scenario: Asking a question across sermons**
1. Daniel asks, "What have these messages taught about prayer?"
2. The app retrieves relevant chunks from multiple sermons in his library, generates an answer grounded in that content, and cites which sermons it drew from.
**Scenario: Duplicate submission (cost optimization, not MVP-critical)**
1. Two different users each submit the same viral sermon URL.
2. The second submission recognizes the sermon has already been processed (same YouTube video ID) and skips re-transcription and re-analysis, instead linking the existing sermon into the second user's library.
## Diagrams
 
### High-level architecture
 
```
                         Client
                           │
                           ▼
                      API Server (FastAPI)
                           │
             ┌─────────────┼──────────────┐
             │             │              │
             ▼             ▼              ▼
         PostgreSQL      pgvector      Job Queue (Celery + Redis)
             │                            │
             │                            ▼
             │                     Processing Worker
             │                       │          │
             │                       ▼          ▼
             │                  YouTube      Gemini
             │                  Transcript   (analysis + embeddings)
             │                       │
             │                       ▼
             └──────────────── PostgreSQL (persist results)
```
 
### Ingestion data flow
 
```
1. User submits YouTube URL
2. API validates URL, extracts video_id
3. Sermon with this video_id exists & status = completed?
       Yes → create UserSermon(user, sermon), return immediately
       No  → create Sermon(video_id, status=pending), enqueue ProcessingJob
4. Worker: fetch transcript (youtube_transcript_api)
5. Worker: clean/chunk transcript
6. Worker: Gemini call → summary, key teachings, themes, bible references, action points, reflection questions
7. Worker: upsert Theme / BibleReference rows, link to Sermon
8. Worker: generate chunk embeddings (Gemini text-embedding-004), store on SermonChunk
9. Worker: set Sermon.status = completed (or failed + reason)
10. Create UserSermon(user, sermon)
```
 
### Entity relationships
 
```
             Canonical Sermon
              /      |      \
             /       |       \
        User A    User B    User C
          │         │          │
     UserSermon  UserSermon  UserSermon
     UserNote    UserNote    UserNote
```
 
Shared (canonical, one copy regardless of how many users import it): `Sermon`, `SermonAnalysis`, `SermonChunk`, `Theme`, `BibleReference`.
User-specific: `UserSermon`, `UserNote`.
 
## Glossary
 
- **Sermon (canonical):** A single processed YouTube video, keyed by `youtube_video_id`. Shared across all users who import it.
- **UserSermon:** The join record representing "this user has this sermon in their library." Where per-user state like save status will live.
- **RAG (Retrieval-Augmented Generation):** Answering a user's question by first retrieving relevant sermon chunks via vector similarity, then passing them to an LLM as context.
- **Chunk:** A segment of a sermon transcript, embedded independently, so search/RAG can retrieve the relevant section rather than the whole transcript.
## Constraints
 
- Transcript source is limited to what YouTube exposes via `youtube_transcript_api` — sermons without captions cannot be processed at MVP (no ASR fallback).
- Must respect YouTube's terms of service around content processing; no video/audio downloading or scraping.
- Solo development, no existing user base — designs should stay simple over speculative scale.
## Service Level Objectives (SLOs)
 
- Sermon metadata / library requests: **< 300ms**
- Semantic search: **< 1s**
- RAG responses: **< 5–10s** (LLM generation is inherently slower; this endpoint does not share the CRUD latency target)
- Ingestion has no latency SLO — it's asynchronous by design; the user is notified on completion rather than waiting.
## Non-Functional Requirements
 
- **Availability over consistency.** Eventually consistent is acceptable everywhere. A sermon appearing in the library a few seconds after submission is a non-issue.
- **Asynchronous processing.** Ingestion must never block the submitting request. `POST /sermons` returns immediately; a worker does the slow work.
- **Availability independent of AI provider.** If Gemini is down, existing sermons remain readable and searchable; new submissions enter a retryable pending state rather than failing the whole app.
- **Durability.** Sermons (costly to reprocess) and user notes (personally costly to lose) must persist in Postgres as the source of truth. Any cache (e.g. Redis) is a performance layer only — the app must keep functioning if it disappears.
- **Cost efficiency.** Avoid repeating transcript retrieval and LLM analysis for the same YouTube video across multiple users — canonical `Sermon`, keyed by `youtube_video_id`, deduplicates this.
- **Data isolation.** A user's saved sermons, notes, and reflections must be accessible only to that user. Shared sermon content (transcript, analysis, themes) may be reused across users without leaking personal data between them.
- **Read-heavy.** Writes (ingesting a sermon) are infrequent per user; reads (browsing/searching the library) happen every session. Optimize for cheap reads.
## Interfaces
 
REST. The current user is always derived from the session, never from the request body or path. Processing status is surfaced via polling `GET /v1/sermons/{sermonId}` — no websockets/SSE at MVP.
 
### Auth
 
```
POST /v1/auth/google
  Request:  { "id_token": "<google id token from frontend OAuth flow>" }
  Response 200:
    {
      "user": { "id", "email", "full_name", "avatar_url" },
      "session_token": "opaque-session-string"
    }
  Also sets an httpOnly session cookie.
 
POST /v1/auth/logout        -> 204
GET  /v1/auth/me            -> { "id", "email", "full_name", "avatar_url" }
```
 
### Sermons
 
```
POST /v1/sermons
  Request:  { "youtube_url": "https://youtube.com/watch?v=ABC123" }
  Response 201: { "id", "status": "pending", "youtube_url" }
  Response 200: already in this user's library -> full sermon, current status
  Response 409: video processing (elsewhere) but not yet in this user's library
                -> { "id", "status": "processing" }
 
GET /v1/sermons?theme=faith&sort=recent&page=1&page_size=20
  Response 200:
    {
      "items": [
        {
          "id", "title", "speaker", "status", "duration_seconds",
          "summary_excerpt": "server-truncated ~150 chars",
          "themes": ["faith", "trust"],
          "saved_at"
        }
      ],
      "page", "page_size", "total"
    }
 
GET /v1/sermons/{sermonId}
  Response 200 (completed):
    {
      "id", "youtube_url", "title", "speaker", "duration_seconds",
      "status", "failure_reason", "saved_at",
      "analysis": {
        "summary", "key_teachings": [...], "action_points": [...],
        "reflection_questions": [...]
      },
      "themes": ["faith", "trust"],
      "bible_references": ["Romans 8:28", "Psalm 23:1-4"],
      "notes": [ { "id", "content", "created_at" } ]
    }
  Response 202 (still processing): { "id", "status": "processing", "analysis": null }
  Response 404: sermon not in this user's library
 
DELETE /v1/sermons/{sermonId}   -> 204
  (Removes UserSermon only; canonical Sermon persists if other users hold it.)
```
 
### Notes
 
```
POST   /v1/sermons/{sermonId}/notes   { "content" } -> { "id", "content", "created_at" }
PATCH  /v1/notes/{noteId}             { "content" } -> { "id", "content", "updated_at" }
DELETE /v1/notes/{noteId}             -> 204
```
 
### Search
 
```
GET /v1/search?q={query}&limit=10
  Response 200:
    {
      "results": [
        {
          "sermon_id", "sermon_title", "speaker",
          "matched_excerpt", "timestamp_seconds", "relevance_score"
        }
      ]
    }
```
 
### Ask (RAG)
 
```
POST /v1/ask
  Request:  { "question": "What have these messages taught about prayer?" }
  Response 200:
    {
      "answer": "...",
      "sources": [
        { "sermon_id", "sermon_title", "matched_excerpt", "timestamp_seconds" }
      ]
    }
```
 
**Design note:** the library list (`GET /v1/sermons`) intentionally returns a truncated `summary_excerpt` and flat `themes`/`bible_references` string arrays, not full analysis or nested join objects — the frontend shouldn't need to know these are separate relational tables, and keeping the list payload light matches the `<300ms` library SLO. Full detail is only paid for on the single-sermon `GET`. Search and RAG results always include `matched_excerpt`/`timestamp_seconds` — a source without "why this matched" isn't useful to the user.
 
## Dependencies / Infrastructure
 
- **Language:** Python (FastAPI)
- **Database:** PostgreSQL + `pgvector` extension — one system of record for relational and vector data; no separate vector database at MVP.
- **Queue/Worker:** Celery + Redis broker, for asynchronous ingestion.
- **Transcript source:** `youtube_transcript_api` (free, no ASR cost, no fallback at MVP).
- **LLM / embeddings:** Gemini (`text-embedding-004`, 768-dim) — chosen for free-tier support.
- **Migrations:** Alembic, from the first model onward.
- **ORM:** SQLAlchemy.
- **Auth:** Google OAuth (frontend-driven sign-in, server-side ID token verification), backed by an app-issued opaque session token — no owned password storage, no JWT signing/rotation to maintain.
## Security
 
- Authentication is delegated to Google OAuth — the app never stores a password. The frontend performs the Google sign-in flow and hands the resulting ID token to `POST /v1/auth/google`, which verifies it server-side and creates/looks up the `User` by `google_id`.
- The app issues its own opaque session token on top of the verified Google identity (random string, stored server-side, returned as an httpOnly cookie) rather than managing JWT signing, rotation, or refresh tokens — session validity is a single table lookup.
- All endpoints derive the current user from the session, never from a client-supplied user ID in the body or path.
- Foreign keys enforce `ON DELETE CASCADE` from `User` → `UserSermon`/`UserNote`, so account deletion cleanly removes personal data without orphaning rows.
- No password storage, password reset flow, or credential-stuffing surface — meaningfully reduced attack surface for a solo-maintained project.
## Privacy
 
- Sermon content (transcript, analysis, themes, embeddings) is shared/canonical and not considered private — it's derived from public YouTube videos.
- User-specific data (notes, reflections, library membership) is private to the owning user and isolated at the query layer, never joined across users.
## Data Model
 
Core entities:
 
- `User` (keyed by `google_id`, no stored password)
- `Session` (opaque token → user, backing cookie auth; not a JWT)
- `Sermon` (canonical, keyed by `youtube_video_id`)
- `UserSermon` (association: user_id, sermon_id, saved_at)
- `SermonAnalysis` (1:1 with Sermon — summary, key_teachings, action_points as JSON, reflection_questions, model_version)
- `Theme` + `sermon_themes` (plain association)
- `BibleReference` + `sermon_bible_references` (plain association)
- `SermonChunk` (transcript segment, timestamps, embedding)
- `UserNote`
- `ProcessingJob` (durable record of ingestion outcome — status, attempt_count, error_message — distinct from Celery's own transient task state, since NFR on durability rules out relying on the Celery result backend alone)
Full schema: see accompanying `schema.sql`.
 
## Open Issues
 
**Open Issue: Association table for Theme/BibleReference — plain or with metadata?**
Decision: plain association tables (sermon_id + theme_id only, no confidence score or mention timestamp). Confidence scoring belongs to the "recurring themes" future extension, not MVP — resolved, moving to Resolved Issues.
 
**Open Issue: ActionPoint per-user completion state**
Action points are currently a JSON field on the shared `SermonAnalysis`, with no per-user completed/incomplete tracking (FR-5.4 deferred). When this is picked up, the fix is additive — a `UserActionPoint` join table (user_id, action_point_id, completed), mirroring the `UserSermon` pattern — not a redesign. Deferred, not blocking MVP.
 
**Open Issue: ProcessingJob vs. Celery task state**
Resolved — see Resolved Issues.
 
## Resolved Issues
 
**Resolved: Should `ProcessingJob` be a separate table given Celery already tracks task state?**
Decision: keep `ProcessingJob` as a slim Postgres table (sermon_id, status, attempt_count, error_message, timestamps). Celery's result backend is transient and typically Redis-backed — relying on it alone would violate the durability NFR, and `GET /sermons/{id}` needs to show status in the same query as the rest of the sermon's data without a second lookup into the broker.
 
**Resolved: Separate project or extend ChurchScribe?**
Decision: separate project. ChurchScribe's ingestion code was written for a single always-on script (push-based, single-tenant); this product is pull-based and multi-tenant (user accounts, isolated libraries, persistent search). The architectural shape differs enough that reusing the pipeline in place would mean rewriting how it's invoked anyway — a fresh build informed by ChurchScribe's lessons is simpler than retrofitting.
 
**Resolved: Transcript source — AssemblyAI or YouTube captions?**
Decision: `youtube_transcript_api`, free tier, no ASR fallback at MVP. Sermons without available captions fail processing with a clear reason (FR-2.6) rather than triggering a paid fallback.
 
## Alternatives Considered
 
**Dedicated vector database (e.g. standalone Chroma) instead of pgvector**
Rejected for MVP — introduces a second system to operate and keep consistent with Postgres, for no benefit at current scale. Revisit only if search load or vector volume genuinely outgrows what `pgvector` handles well (see Future Extensions).
 
**Storing themes/Bible references as free-text fields on Sermon instead of normalized entities**
Rejected — would make theme-based and passage-based search (FR-7.2, FR-9.1) a fragile string-matching problem instead of an indexed join, and blocks future cross-sermon theme analytics entirely.
 
## Future Extensions
 
Grouped by theme, to be prioritized after MVP validation:
 
**Advanced Retrieval:** hybrid keyword + semantic search, reranking, better chunking, Bible passage retrieval, personal note retrieval.
 
**Advanced RAG:** cross-sermon synthesis, sermon comparison, recurring teaching detection, multi-turn conversations, multi-step retrieval.
 
**Personal Knowledge Base:** search personal reflections, learning timeline, recurring themes, saved insights, personal recommendations.
 
**Product Features:** recommendations, sharing, collaborative collections, church/ministry accounts, subscription tiers, usage quotas.
 
**Architecture:** transcript/analysis/embedding versioning (regenerate analysis when the model or prompt improves, without treating the sermon as a new entity); ASR fallback for sermons without captions; dedicated vector infrastructure if pgvector search no longer scales.