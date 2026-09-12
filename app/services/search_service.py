import logging
import time
import uuid
from dataclasses import dataclass

from pydantic import BaseModel

from app.llm.client import embed_batch, generate_structured
from app.models.user import User
from app.repositories.search_repository import SearchRepository
from app.repositories.sermon_repository import SermonRepository

logger = logging.getLogger(__name__)

MATCHED_EXCERPT_MAX_CHARS = 200
RAG_CONTEXT_CHUNK_LIMIT = 8

ASK_PROMPT = """You are answering a question using excerpts from gospel sermons the listener \
has personally saved to their library. Answer using ONLY what these excerpts say — do not add \
teaching, interpretation, or Bible references that aren't grounded in the excerpts below. If the \
excerpts don't address the question, say so plainly rather than guessing.

Question: {question}

Sermon excerpts:
{excerpts}
"""


class AnswerResult(BaseModel):
    answer: str


class AnswerParseError(Exception):
    """Raised when the LLM does not return a parseable structured answer."""


@dataclass
class SearchResult:
    sermon_id: uuid.UUID
    sermon_title: str | None
    speaker: str | None
    duration_seconds: int | None
    relevance_score: float


@dataclass
class AskResult:
    answer: str
    sources: list[SearchResult]


@dataclass
class SearchResponse:
    results: list[SearchResult]
    message: str | None = None


EMPTY_LIBRARY_MESSAGE = (
    "You don't have any sermons in your library yet. Add a sermon first, then search across it."
)
EMPTY_LIBRARY_ANSWER = (
    "You don't have any sermons in your library yet. Add a sermon first, "
    "then I can answer questions grounded in what it teaches."
)


class SearchService:
    """Business rules for semantic search and RAG question-answering over a
    user's sermon library. Embeds queries, delegates retrieval to
    SearchRepository, and shapes raw chunk rows into result objects the API
    can return. For answer_question, sources are always assembled from what
    was actually retrieved - never from what the LLM claims it used - so
    citations stay grounded.
    """

    def __init__(self, search_repo: SearchRepository, sermons: SermonRepository):
        self._search_repo = search_repo
        self._sermons = sermons

    def _has_empty_library(self, user: User) -> bool:
        return self._sermons.count_library(user.id, theme=None) == 0

    @staticmethod
    def _truncate_excerpt(text: str) -> str:
        if len(text) <= MATCHED_EXCERPT_MAX_CHARS:
            return text
        ellipsis = "..."
        truncate_at = MATCHED_EXCERPT_MAX_CHARS - len(ellipsis)
        return text[:truncate_at].rstrip() + ellipsis

    def _find_results_by_title_or_theme(self, user: User, query: str, limit: int) -> list[SearchResult]:
        """Cheap tier: exact/substring match against title or theme name,
        no embedding call. relevance_score is 1.0 for every hit here -
        there's no distance to compare, and a title/theme match is a more
        certain signal than any embedding similarity score could be.
        """
        sermons = self._search_repo.find_by_title_or_theme(user.id, query, limit)
        return [
            SearchResult(
                sermon_id=sermon.id,
                sermon_title=sermon.title,
                speaker=sermon.speaker,
                duration_seconds=sermon.duration_seconds,
                relevance_score=1.0,
            )
            for sermon in sermons
        ]

    def _find_results(self, user: User, query: str, limit: int) -> tuple[list[SearchResult], list[str]]:
        """Retrieval still happens at the chunk level (embeddings are the
        only way to find *which* sermons are relevant), but the returned
        SearchResult list is collapsed to one row per sermon - a sermon
        discussing the same topic across 3 matching chunks should appear
        once, not three times, now that individual excerpts/timestamps
        aren't shown to the user. Keeps each sermon's best (closest) match;
        ranking across sermons is preserved by relevance_score, since rows
        arrive from the repository already ordered by distance.

        Also returns the raw excerpt text for each kept chunk (not
        deduped/truncated the same way) - answer_question still needs real
        transcript text to ground the LLM's answer, even though that text
        is no longer part of what's shown to the user in `sources`.
        """
        query_vector = embed_batch([query])[0]
        # Over-fetch chunks before deduping, since multiple close chunks
        # can belong to the same sermon - without this, a single sermon
        # with several strong matches could crowd out `limit` distinct
        # sermons even though the caller asked for `limit` results.
        rows = self._search_repo.find_similar_chunks(user.id, query_vector, limit * 4)

        results: list[SearchResult] = []
        excerpts: list[str] = []
        seen_sermon_ids: set[uuid.UUID] = set()
        for chunk, sermon, distance in rows:
            if sermon.id in seen_sermon_ids:
                continue
            seen_sermon_ids.add(sermon.id)
            results.append(
                SearchResult(
                    sermon_id=sermon.id,
                    sermon_title=sermon.title,
                    speaker=sermon.speaker,
                    duration_seconds=sermon.duration_seconds,
                    relevance_score=1 - distance,
                )
            )
            excerpts.append(f'From "{sermon.title}": {self._truncate_excerpt(chunk.text)}')
            if len(results) == limit:
                break

        return results, excerpts

    def semantic_search(self, user: User, query: str, limit: int) -> SearchResponse:
        """Search the user's sermon library, cheapest signal first.

        Three tiers, in order, stopping at the first one that finds
        anything:
        1. Title/theme substring match - cheap, exact, no embedding call.
        2. Embedding similarity over transcript chunks - only reached if
           tier 1 finds zero matches. This is deliberately NOT a top-up:
           if title/theme find *any* results, embeddings are skipped
           entirely for this search, even if fewer than `limit` were
           found - trusting an exact signal over guessing further.

        Scoped strictly to the current user's library at every tier. If
        the user has no sermons in their library yet, returns an empty
        result set with an explanatory message before trying either tier.
        """
        started_at = time.perf_counter()
        if self._has_empty_library(user):
            response = SearchResponse(results=[], message=EMPTY_LIBRARY_MESSAGE)
            logger.info(
                "Semantic search completed",
                extra={
                    "user_id": str(user.id),
                    "result_count": 0,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            return response

        title_or_theme_results = self._find_results_by_title_or_theme(user, query, limit)
        if title_or_theme_results:
            response = SearchResponse(results=title_or_theme_results)
        else:
            results, _excerpts = self._find_results(user, query, limit)
            response = SearchResponse(results=results)

        logger.info(
            "Semantic search completed",
            extra={
                "user_id": str(user.id),
                "result_count": len(response.results),
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return response

    def answer_question(self, user: User, question: str) -> AskResult:
        """Answer a question grounded in the user's sermon library, citing
        the sermons the answer was drawn from.

        Retrieval is scoped to the current user's library, same as
        semantic_search. If the user has no sermons in their library yet,
        returns a friendly message without making an embedding or LLM
        call - there's nothing to search, so paying for either would be
        wasted.
        """
        started_at = time.perf_counter()
        if self._has_empty_library(user):
            result = AskResult(answer=EMPTY_LIBRARY_ANSWER, sources=[])
            logger.info(
                "Question answering completed without library content",
                extra={
                    "user_id": str(user.id),
                    "source_count": 0,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            return result

        results, excerpts = self._find_results(user, question, RAG_CONTEXT_CHUNK_LIMIT)
        prompt = ASK_PROMPT.format(question=question, excerpts="\n\n".join(excerpts))
        parsed = generate_structured(prompt=prompt, response_schema=AnswerResult)
        if parsed is None:
            raise AnswerParseError("LLM did not return a parseable structured answer")

        result = AskResult(answer=parsed.answer, sources=results)
        logger.info(
            "Question answering completed",
            extra={
                "user_id": str(user.id),
                "source_count": len(results),
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        return result
