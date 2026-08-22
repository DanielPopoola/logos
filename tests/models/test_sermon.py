import pytest
from sqlalchemy.exc import IntegrityError

from app.models.sermon import Sermon


def test_duplicate_youtube_video_id_raises_integrity_error(db_session):
    db_session.add(
        Sermon(youtube_video_id="ABC123", youtube_url="https://youtube.com/watch?v=ABC123")
    )
    db_session.commit()

    db_session.add(Sermon(youtube_video_id="ABC123", youtube_url="https://youtu.be/ABC123"))
    with pytest.raises(IntegrityError):
        db_session.commit()
