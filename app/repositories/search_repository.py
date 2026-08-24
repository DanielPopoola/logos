import uuid

from sqlalchemy.orm import Session as DBSession

from app.models.sermon import Sermon
from app.models.sermon_chunk import SermonChunk
from app.models.user_sermon import UserSermon


class SearchRepository:
    """Persistence access for chunk-similarity retrieval. Serves search and
    RAG, both of which need the same query: sermon chunks ordered by vector
    distance to a query embedding, scoped to a single user's library.
    Callers own the transaction (commit/rollback) - this repository never
    commits.
    """

    def __init__(self, db: DBSession):
        self._db = db

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
