import logging
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
    matched_excerpt: str
    timestamp_seconds: int | None
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

    def _find_results(self, user: User, query: str, limit: int) -> list[SearchResult]:
        query_vector = embed_batch([query])[0]
        rows = self._search_repo.find_similar_chunks(user.id, query_vector, limit)

        return [
            SearchResult(
                sermon_id=sermon.id,
                sermon_title=sermon.title,
                speaker=sermon.speaker,
                matched_excerpt=self._truncate_excerpt(chunk.text),
                timestamp_seconds=chunk.start_timestamp,
                relevance_score=1 - distance,
            )
            for chunk, sermon, distance in rows
        ]

    def semantic_search(self, user: User, query: str, limit: int) -> SearchResponse:
        """Search the user's sermon library by meaning, not exact keywords.

        Scoped strictly to the current user's library - a chunk belonging
        to a sermon the user hasn't imported is never returned, even if
        it's the closest vector match. If the user has no sermons in their
        library yet, returns an empty result set with an explanatory
        message, without making an embedding call - there's nothing to
        search.
        """
        if self._has_empty_library(user):
            return SearchResponse(results=[], message=EMPTY_LIBRARY_MESSAGE)

        return SearchResponse(results=self._find_results(user, query, limit))

    @staticmethod
    def _build_excerpts_block(results: list[SearchResult]) -> str:
        return "\n\n".join(f'From "{r.sermon_title}": {r.matched_excerpt}' for r in results)

    def answer_question(self, user: User, question: str) -> AskResult:
        """Answer a question grounded in the user's sermon library, citing
        the sermons the answer was drawn from.

        Retrieval is scoped to the current user's library, same as
        semantic_search. If the user has no sermons in their library yet,
        returns a friendly message without making an embedding or LLM
        call - there's nothing to search, so paying for either would be
        wasted.
        """
        if self._has_empty_library(user):
            return AskResult(answer=EMPTY_LIBRARY_ANSWER, sources=[])

        results = self._find_results(user, question, RAG_CONTEXT_CHUNK_LIMIT)
        prompt = ASK_PROMPT.format(question=question, excerpts=self._build_excerpts_block(results))
        parsed = generate_structured(prompt=prompt, response_schema=AnswerResult)
        if parsed is None:
            raise AnswerParseError("LLM did not return a parseable structured answer")

        return AskResult(answer=parsed.answer, sources=results)
