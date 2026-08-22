from app.models.sermon import Sermon
from app.models.sermon_chunk import SermonChunk


def test_embedding_roundtrip_via_cosine_similarity(db_session):
    sermon = Sermon(youtube_video_id="V4", youtube_url="https://youtu.be/V4")
    db_session.add(sermon)
    db_session.commit()

    vec = [0.1] * 768
    chunk = SermonChunk(sermon_id=sermon.id, chunk_index=0, text="hello", embedding=vec)
    db_session.add(chunk)
    db_session.commit()

    from sqlalchemy import select

    result = db_session.execute(
        select(SermonChunk).order_by(SermonChunk.embedding.cosine_distance(vec)).limit(1)
    ).scalar_one()
    assert result.id == chunk.id
