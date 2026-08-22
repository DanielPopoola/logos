import pytest
from sqlalchemy.exc import IntegrityError

from app.models.user import User


def test_duplicate_google_id_raises_integrity_error(db_session):
    db_session.add(User(google_id="abc123", email="a@example.com", full_name="A"))
    db_session.commit()

    db_session.add(User(google_id="abc123", email="b@example.com", full_name="B"))
    with pytest.raises(IntegrityError):
        db_session.commit()
