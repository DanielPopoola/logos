import pytest
from sqlalchemy.exc import IntegrityError

from app.models.sermon import Sermon
from app.models.taxonomy import Theme, sermon_themes


def test_duplicate_sermon_theme_link_raises_integrity_error(db_session):
    sermon = Sermon(
        youtube_video_id="V2",
        youtube_url="https://youtu.be/V2",
    )
    theme = Theme(name="faith")

    db_session.add_all([sermon, theme])
    db_session.commit()

    sermon.themes.append(theme)
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(
            sermon_themes.insert().values(
                sermon_id=sermon.id,
                theme_id=theme.id,
            )
        )

    db_session.rollback()


def test_deleting_sermon_leaves_theme_intact(db_session):
    sermon = Sermon(youtube_video_id="V3", youtube_url="https://youtu.be/V3")
    theme = Theme(name="prayer")
    db_session.add_all([sermon, theme])
    db_session.commit()

    sermon.themes.append(theme)
    db_session.commit()

    db_session.delete(sermon)
    db_session.commit()

    remaining = db_session.query(Theme).filter_by(name="prayer").first()
    assert remaining is not None
