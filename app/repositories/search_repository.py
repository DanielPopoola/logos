import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.sermon import Sermon
from app.models.sermon_chunk import SermonChunk
from app.models.taxonomy import Theme, sermon_themes
from app.models.user_sermon import UserSermon


class SearchRepository:
    """Persistence access for sermon retrieval by search query. Serves
    search and RAG, both of which need the same two-tier lookup: a cheap
    exact/substring match against title or theme first, falling back to
    chunk-embedding similarity only when that finds nothing. Callers own
    the transaction (commit/rollback) - this repository never commits.
    """

    def __init__(self, db: DBSession):
        self._db = db

    def find_by_title_or_theme(self, user_id: uuid.UUID, query: str, limit: int) -> list[Sermon]:
        """Sermons in the user's library whose title or any tagged theme
        name contains `query` (case-insensitive substring), title matches
        ranked first. Cheap and exact - no embedding call - so this is
        tried before falling back to semantic search.

        Implemented as two separate simple queries rather than one query
        with an OR across a joined table: a sermon tagged with more than
        one theme matching the query would otherwise produce duplicate
        joined rows that differ only in which theme matched, which
        DISTINCT (keyed on the full row) does not collapse, and ordering
        by a ranking expression not in the (deduplicated) select list is
        also rejected by Postgres. Two plain queries, merged in Python
        with title hits first and de-duplicated by id, sidesteps both
        issues and is easier to reason about correctness-wise.
        """
        pattern = f"%{query}%"

        title_matches = (
            self._db.query(Sermon)
            .join(UserSermon, UserSermon.sermon_id == Sermon.id)
            .filter(UserSermon.user_id == user_id)
            .filter(Sermon.title.ilike(pattern))
            .limit(limit)
            .all()
        )

        remaining = limit - len(title_matches)
        theme_matches: list[Sermon] = []
        if remaining > 0:
            theme_matches = (
                self._db.query(Sermon)
                .join(UserSermon, UserSermon.sermon_id == Sermon.id)
                .join(sermon_themes, sermon_themes.c.sermon_id == Sermon.id)
                .join(Theme, Theme.id == sermon_themes.c.theme_id)
                .filter(UserSermon.user_id == user_id)
                .filter(Theme.name.ilike(pattern))
                .distinct()
                .limit(remaining)
                .all()
            )

        seen_ids = {sermon.id for sermon in title_matches}
        deduped_theme_matches = [s for s in theme_matches if s.id not in seen_ids]
        return title_matches + deduped_theme_matches

    def find_similar_chunks(
        self, user_id: uuid.UUID, query_vector: list[float], limit: int
    ) -> list[tuple[SermonChunk, Sermon, float]]:
        """Return the chunks closest to query_vector, restricted to sermons
        in the given user's library, closest first.

        Each result is (chunk, sermon, cosine_distance) - shaping distance
        into a relevance score is the service's job, not this repository's.
        """
        distance = SermonChunk.embedding.cosine_distance(query_vector)
        return (
            self._db.query(SermonChunk, Sermon, distance.label("distance"))
            .join(Sermon, SermonChunk.sermon_id == Sermon.id)
            .join(UserSermon, UserSermon.sermon_id == Sermon.id)
            .filter(UserSermon.user_id == user_id)
            .order_by(distance)
            .limit(limit)
            .all()
        )
