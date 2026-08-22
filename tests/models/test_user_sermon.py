import pytest
from sqlalchemy.exc import IntegrityError

from app.models.sermon import Sermon
from app.models.user import User
from app.models.user_sermon import UserSermon


def test_duplicate_user_sermon_pair_raises_integrity_error(db_session):
    user = User(google_id="u1", email="u1@example.com")
    sermon = Sermon(youtube_video_id="V5", youtube_url="https://youtu.be/V5")
    db_session.add_all([user, sermon])
    db_session.commit()

    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()

    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
