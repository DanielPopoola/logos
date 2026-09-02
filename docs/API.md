# Logos API Reference

Generated from the current implementation (`app/api/*`, `app/schemas/*`, `app/errors.py`) — this reflects actual behavior, not the original design doc, where the two have diverged.

## Conventions

### Base URL

All routes except `/healthz` are mounted under `/v1`.

### Response envelope

Every JSON response (success or error) is wrapped in the same shape:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

On failure:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "sermon_not_found",
    "message": "...",
    "request_id": "..."
  }
}
```

`request_id` is also echoed back on the `X-Request-ID` response header for every request (see `app/middleware/request_id.py`), whether the client sent one or not — useful for correlating a support report with server logs.

### Authentication

Session-based, via an httpOnly `session_token` cookie — not a bearer token. There is no `Authorization` header anywhere in this API.

Every protected route depends on `get_current_user` (`app/api/deps.py`), which can fail in three distinct ways, each a 401 with a different `error.code`:

| `error.code` | Cause |
|---|---|
| `missing_session` | No `session_token` cookie present |
| `invalid_session` | Cookie present but doesn't match any session row |
| `session_expired` | Cookie matches a session, but `expires_at` has passed |

### Errors

All handled errors use the envelope above with an HTTP status set by the raising code (`AppException`). Unhandled exceptions are caught by `UnhandledExceptionMiddleware`, logged with the request ID, and returned as a generic 500 — internal details are never leaked into the response body.

---

## Auth

### `GET /v1/auth/google/login`

Starts the Google OAuth flow. Not called directly by API clients — a browser redirect target.

**Response:** `307` redirect to Google's consent screen.

---

### `GET /v1/auth/google/callback`

Google's OAuth redirect target. Exchanges the authorization `code` for tokens, fetches the Google profile, finds-or-creates the local `User`, issues a session, and sets the `session_token` cookie.

**Query params:** `code` (from Google)

**Response:** `307` redirect to `/`, with `Set-Cookie: session_token=...; HttpOnly`.

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 401 | `google_auth_failed` | Token exchange or userinfo fetch with Google failed |

---

### `POST /v1/auth/logout`

Deletes the current session. Idempotent — calling it with no session, or a stale one, still succeeds.

**Auth:** session cookie (optional — no-ops if absent)

**Response:** `204 No Content`, with `Set-Cookie` clearing `session_token`.

---

### `GET /v1/auth/me`

Returns the authenticated user's own profile.

**Auth:** required

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "email": "string",
    "full_name": "string | null",
    "avatar_url": "string | null"
  }
}
```

---

## Sermons

### `POST /v1/sermons`

Submit a YouTube sermon URL into the current user's library. Dedupes on the canonical `Sermon.youtube_video_id` — a given video is only ever transcribed and analyzed once, regardless of how many users submit it.

**Auth:** required

**Request:**
```json
{ "youtube_url": "https://youtube.com/watch?v=ABC123" }
```

**Response body** (all cases, varying `status_code`):
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "status": "pending | processing | completed | failed",
    "youtube_url": "string"
  }
}
```

Five distinct outcomes, driven by `SermonService.submit_sermon`:

| HTTP status | Meaning |
|---|---|
| `201` | Brand-new video. `Sermon` + `ProcessingJob` created, ingestion enqueued. |
| `200` | Video already in **this user's** library — returned as-is, no side effects. |
| `200` | Video already processed (`completed`) by someone else — linked into this user's library immediately, no reprocessing. |
| `202` | Video previously `failed` for everyone — reset to `pending` and **re-enqueued**, then linked into this user's library. |
| `409` | Video is currently `pending`/`processing` (someone else's in-flight submission) and not yet in this user's library. Poll `GET /v1/sermons/{id}` or resubmit later. |

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 400 | `invalid_youtube_url` | URL couldn't be parsed into a video ID |

---

### `GET /v1/sermons`

List the current user's library, paginated.

**Auth:** required

**Query params:**
| Param | Default | Notes |
|---|---|---|
| `theme` | — | Optional exact-match filter |
| `page` | `1` | `>= 1` |
| `page_size` | `20` | `1`–`100` |

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "uuid",
        "title": "string | null",
        "speaker": "string | null",
        "status": "pending | processing | completed | failed",
        "duration_seconds": 1234,
        "summary_excerpt": "server-truncated string | null",
        "themes": ["faith", "trust"],
        "saved_at": "2026-08-01T12:00:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 42
  }
}
```

Scoped strictly to the current user — never returns another user's library entries. `summary_excerpt` is deliberately truncated; the full analysis is only returned by the detail endpoint.

---

### `GET /v1/sermons/{sermon_id}`

Full detail for one sermon in the current user's library.

**Auth:** required

**Response `200`** (status is `completed`):
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "youtube_url": "string",
    "title": "string | null",
    "speaker": "string | null",
    "duration_seconds": 1234,
    "status": "completed",
    "failure_reason": null,
    "saved_at": "2026-08-01T12:00:00Z",
    "analysis": {
      "summary": "string | null",
      "key_teachings": ["..."],
      "action_points": ["..."],
      "reflection_questions": ["..."]
    },
    "themes": ["faith", "trust"],
    "bible_references": ["Romans 8:28", "Psalm 23:1-4"],
    "notes": [
      { "id": "uuid", "content": "string", "created_at": "2026-08-01T12:00:00Z" }
    ]
  }
}
```

**Response `202`** (status is `pending` or `processing`):
```json
{
  "success": true,
  "data": { "id": "uuid", "status": "pending", "analysis": null }
}
```
Note: this shape is intentionally partial — no `themes`, `notes`, etc. Poll again later.

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 404 | `sermon_not_found` | Sermon doesn't exist, or exists but isn't in this user's library (these are indistinguishable by design — never confirms existence to a non-owner) |

---

### `DELETE /v1/sermons/{sermon_id}`

Removes the sermon from the current user's library only. The canonical `Sermon` row (and any other user's copy) is untouched.

**Auth:** required

**Response:** `204 No Content`

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 404 | `sermon_not_found` | Not in this user's library |

---

### `POST /v1/sermons/{sermon_id}/notes`

Create a personal note on a sermon in the current user's library.

**Auth:** required

**Request:**
```json
{ "content": "string" }
```

**Response `201`:**
```json
{
  "success": true,
  "data": { "id": "uuid", "content": "string", "created_at": "2026-08-01T12:00:00Z" }
}
```

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 404 | `sermon_not_found` | Sermon not in this user's library |

---

## Notes

### `PATCH /v1/notes/{note_id}`

Update a note's content. Owner-only.

**Auth:** required

**Request:**
```json
{ "content": "string" }
```

**Response `200`:**
```json
{
  "success": true,
  "data": { "id": "uuid", "content": "string", "updated_at": "2026-08-01T12:00:00Z" }
}
```

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 404 | `note_not_found` | Note doesn't exist, or belongs to a different user (never a 403 — existence isn't confirmed to a non-owner) |

---

### `DELETE /v1/notes/{note_id}`

Delete a note. Owner-only.

**Auth:** required

**Response:** `204 No Content`

**Errors:**
| Status | Code | Cause |
|---|---|---|
| 404 | `note_not_found` | Same non-owner semantics as `PATCH` above |

---

## Search

### `GET /v1/search`

Semantic search over the current user's sermon library.

**Auth:** required

**Query params:**
| Param | Required | Notes |
|---|---|---|
| `q` | yes | min length 1 |
| `limit` | no | default `10`, `1`–`50` |

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "sermon_id": "uuid",
        "sermon_title": "string | null",
        "speaker": "string | null",
        "matched_excerpt": "string",
        "timestamp_seconds": 245,
        "relevance_score": 0.83
      }
    ],
    "message": "optional string, e.g. shown when the library is empty"
  }
}
```

Scoped strictly to the current user's library — a chunk belonging to a sermon the user hasn't imported is never returned, even if it's the closest vector match. On an empty library, `results` is `[]` and `message` explains why; no embedding/LLM call is made in that case.

---

## Ask (RAG)

### `POST /v1/ask`

Ask a question answered from the current user's sermon library, with cited sources.

**Auth:** required

**Request:**
```json
{ "question": "What have these messages taught about prayer?" }
```

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "answer": "string",
    "sources": [
      {
        "sermon_id": "uuid",
        "sermon_title": "string | null",
        "matched_excerpt": "string",
        "timestamp_seconds": 245
      }
    ]
  }
}
```

`sources` are drawn from the retrieved chunks used to ground the answer — never generated or embellished by the LLM. Same per-user isolation and empty-library guard as `/v1/search`.

---

## Health

### `GET /healthz`

Unauthenticated liveness/readiness check for the deploy platform. Excluded from the OpenAPI schema and from the `/v1` prefix — not part of the public API surface.

**Response `200`:** `{ "status": "ok" }`
**Response `503`:** `{ "status": "error" }` — the DB connectivity check (`SELECT 1`) failed.

---

## Not yet implemented

Present in the design doc but not (yet) reflected in the routes above:

- `POST /v1/auth/google` (ID-token-in-body flow) — superseded by the implemented backend-driven redirect flow (`GET /v1/auth/google/login` + `/callback`)
