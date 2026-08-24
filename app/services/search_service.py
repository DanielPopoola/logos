import uuid
from dataclasses import dataclass

from app.llm.client import embed_batch
from app.models.user import User
from app.repositories.search_repository import SearchRepository

MATCHED_EXCERPT_MAX_CHARS = 200


@dataclass
class SearchResult:
    sermon_id: uuid.UUID
    sermon_title: str | None
    speaker: str | None
    matched_excerpt: str
    timestamp_seconds: int | None
    relevance_score: float


class SearchService:
    """Business rules for semantic search over a user's sermon library.
    Embeds the query, delegates retrieval to SearchRepository, and shapes
    raw chunk rows into result objects the API can return.
    """

    def __init__(self, search_repo: SearchRepository):
        self._search_repo = search_repo

    @staticmethod
    def _truncate_excerpt(text: str) -> str:
        if len(text) <= MATCHED_EXCERPT_MAX_CHARS:
            return text
        ellipsis = "..."
        truncate_at = MATCHED_EXCERPT_MAX_CHARS - len(ellipsis)
        return text[:truncate_at].rstrip() + ellipsis

    def semantic_search(self, user: User, query: str, limit: int) -> list[SearchResult]:
        """Search the user's sermon library by meaning, not exact keywords.

        Scoped strictly to the current user's library - a chunk belonging
        to a sermon the user hasn't imported is never returned, even if
        it's the closest vector match.
        """
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
