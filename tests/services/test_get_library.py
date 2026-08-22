from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_analysis import SermonAnalysis
from app.models.taxonomy import Theme
from app.models.user import User
from app.models.user_sermon import UserSermon
from app.services.sermon_service import SUMMARY_EXCERPT_MAX_CHARS, get_library


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _completed_sermon(db_session, video_id: str, summary: str, title: str = "A Sermon") -> Sermon:
    sermon = Sermon(
        youtube_video_id=video_id,
        youtube_url=f"https://youtu.be/{video_id}",
        title=title,
        status=ProcessingStatus.COMPLETED,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(SermonAnalysis(sermon_id=sermon.id, summary=summary, model_version="v1"))
    db_session.commit()
    return sermon


def _save_to_library(db_session, user: User, sermon: Sermon) -> None:
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()


def test_only_returns_current_users_sermons(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    sermon = _completed_sermon(db_session, "LIB1", "Summary text")
    _save_to_library(db_session, owner, sermon)

    result = get_library(db_session, other, page=1, page_size=20, theme=None)

    assert result.total == 0
    assert result.items == []


def test_returns_only_this_users_sermons_not_others(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    mine = _completed_sermon(db_session, "LIB2", "Mine")
    theirs = _completed_sermon(db_session, "LIB3", "Theirs")
    _save_to_library(db_session, owner, mine)
    _save_to_library(db_session, other, theirs)

    result = get_library(db_session, owner, page=1, page_size=20, theme=None)

    assert result.total == 1
    assert result.items[0].id == mine.id


def test_summary_excerpt_is_truncated_and_full_summary_not_leaked(db_session):
    user = _user(db_session)
    long_summary = "word " * 100  # far exceeds SUMMARY_EXCERPT_MAX_CHARS
    sermon = _completed_sermon(db_session, "LIB4", long_summary)
    _save_to_library(db_session, user, sermon)

    result = get_library(db_session, user, page=1, page_size=20, theme=None)

    excerpt = result.items[0].summary_excerpt
    assert len(excerpt) <= SUMMARY_EXCERPT_MAX_CHARS  # ty: ignore[invalid-argument-type]
    assert excerpt != long_summary


def test_theme_filter_returns_only_matching_sermons(db_session):
    user = _user(db_session)
    faith_theme = Theme(name="faith")
    prayer_theme = Theme(name="prayer")
    db_session.add_all([faith_theme, prayer_theme])
    db_session.commit()

    faith_sermon = _completed_sermon(db_session, "LIB5", "About faith")
    prayer_sermon = _completed_sermon(db_session, "LIB6", "About prayer")
    faith_sermon.themes.append(faith_theme)
    prayer_sermon.themes.append(prayer_theme)
    db_session.commit()
    _save_to_library(db_session, user, faith_sermon)
    _save_to_library(db_session, user, prayer_sermon)

    result = get_library(db_session, user, page=1, page_size=20, theme="faith")

    assert result.total == 1
    assert result.items[0].id == faith_sermon.id


def test_pagination_returns_correct_total_and_page_slice(db_session):
    user = _user(db_session)
    for i in range(5):
        sermon = _completed_sermon(db_session, f"LIB7{i}", f"Summary {i}")
        _save_to_library(db_session, user, sermon)

    page_1 = get_library(db_session, user, page=1, page_size=2, theme=None)
    page_2 = get_library(db_session, user, page=2, page_size=2, theme=None)

    assert page_1.total == 5
    assert len(page_1.items) == 2
    assert len(page_2.items) == 2
    assert {i.id for i in page_1.items}.isdisjoint({i.id for i in page_2.items})


def test_sorted_by_most_recently_saved_first(db_session):
    import time

    user = _user(db_session)
    first = _completed_sermon(db_session, "LIB8A", "First")
    _save_to_library(db_session, user, first)
    time.sleep(0.01)
    second = _completed_sermon(db_session, "LIB8B", "Second")
    _save_to_library(db_session, user, second)

    result = get_library(db_session, user, page=1, page_size=20, theme=None)

    assert result.items[0].id == second.id
    assert result.items[1].id == first.id
