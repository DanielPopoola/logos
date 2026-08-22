import pytest
from sqlalchemy.exc import IntegrityError

from app.models.sermon import Sermon
from app.models.sermon_analysis import SermonAnalysis


def test_second_analysis_for_same_sermon_raises_integrity_error(db_session):
    sermon = Sermon(youtube_video_id="V1", youtube_url="https://youtu.be/V1")
    db_session.add(sermon)
    db_session.commit()

    db_session.add(SermonAnalysis(sermon_id=sermon.id, model_version="gemini-1"))
    db_session.commit()

    db_session.add(SermonAnalysis(sermon_id=sermon.id, model_version="gemini-1"))
    with pytest.raises(IntegrityError):
        db_session.commit()
