from unittest.mock import patch

from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_chunk import SermonChunk
from app.models.user import User
from app.models.user_sermon import UserSermon
from app.repositories.search_repository import SearchRepository
from app.repositories.sermon_repository import SermonRepository
from app.services.search_service import AnswerResult, SearchService


def _search_service(db_session) -> SearchService:
    return SearchService(SearchRepository(db_session), SermonRepository(db_session))


def _user(db_session, google_id="u1") -> User:
    user = User(google_id=google_id, email=f"{google_id}@example.com")
    db_session.add(user)
    db_session.commit()
    return user


def _sermon_in_library(
    db_session, user: User, video_id: str, title: str = "Test Sermon", speaker: str = "Pastor Jane"
) -> Sermon:
    sermon = Sermon(
        youtube_video_id=video_id,
        youtube_url=f"https://youtu.be/{video_id}",
        status=ProcessingStatus.COMPLETED,
        title=title,
        speaker=speaker,
    )
    db_session.add(sermon)
    db_session.flush()
    db_session.add(UserSermon(user_id=user.id, sermon_id=sermon.id))
    db_session.commit()
    return sermon


def _chunk(db_session, sermon: Sermon, index: int, text: str, embedding: list[float], start=0):
    chunk = SermonChunk(
        sermon_id=sermon.id,
        chunk_index=index,
        text=text,
        start_timestamp=start,
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.commit()
    return chunk


def test_semantic_search_returns_closest_chunk_first(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1")

    close_vector = [0.1] * 768
    far_vector = [0.9] * 768
    _chunk(db_session, sermon, 0, "on trusting God in hardship", close_vector, start=42)
    _chunk(db_session, sermon, 1, "on tithing and generosity", far_vector, start=100)

    query_vector = [0.11] * 768
    with patch("app.services.search_service.embed_batch", return_value=[query_vector]):
        response = service.semantic_search(user, "trusting God when things are hard", limit=10)

    results = response.results
    assert results[0].matched_excerpt.startswith("on trusting God in hardship")
    assert results[0].timestamp_seconds == 42
    assert results[0].sermon_id == sermon.id
    assert results[0].sermon_title == "Test Sermon"
    assert results[0].speaker == "Pastor Jane"


def test_semantic_search_never_returns_chunks_outside_users_library(db_session):
    service = _search_service(db_session)
    user = _user(db_session, google_id="u1")
    other_user = _user(db_session, google_id="u2")

    my_sermon = _sermon_in_library(db_session, user, "MINE")
    other_sermon = _sermon_in_library(db_session, other_user, "THEIRS")

    query_vector = [0.1] * 768
    # The other user's chunk is the closest possible match - if isolation
    # is broken, it would win top spot despite not being in user's library.
    _chunk(db_session, other_sermon, 0, "closest match, not mine", query_vector, start=0)
    _chunk(db_session, my_sermon, 0, "further match, but mine", [0.5] * 768, start=10)

    with patch("app.services.search_service.embed_batch", return_value=[query_vector]):
        response = service.semantic_search(user, "anything", limit=10)

    assert len(response.results) == 1
    assert response.results[0].sermon_id == my_sermon.id


def test_semantic_search_respects_limit(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1")

    for i in range(5):
        _chunk(db_session, sermon, i, f"chunk {i}", [0.1 * i] * 768, start=i * 10)

    query_vector = [0.0] * 768
    with patch("app.services.search_service.embed_batch", return_value=[query_vector]):
        response = service.semantic_search(user, "anything", limit=2)

    assert len(response.results) == 2


def test_semantic_search_with_empty_library_skips_embedding_call(db_session):
    service = _search_service(db_session)
    user = _user(db_session)

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "anything", limit=10)

    mock_embed.assert_not_called()
    assert response.results == []
    assert "don't have any sermons" in response.message  # ty: ignore[unsupported-operator]


def test_answer_question_returns_answer_grounded_in_retrieved_sources(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1")

    vector = [0.1] * 768
    _chunk(db_session, sermon, 0, "on trusting God in hardship", vector, start=42)

    with (
        patch("app.services.search_service.embed_batch", return_value=[vector]),
        patch(
            "app.services.search_service.generate_structured",
            return_value=AnswerResult(answer="Trust God through hardship, as taught in Romans 8."),
        ),
    ):
        result = service.answer_question(user, "What have these messages taught about prayer?")

    assert result.answer == "Trust God through hardship, as taught in Romans 8."
    assert result.sources[0].sermon_id == sermon.id
    assert result.sources[0].matched_excerpt == "on trusting God in hardship"
    assert result.sources[0].timestamp_seconds == 42


def test_answer_question_retrieval_is_isolated_to_users_library(db_session):
    service = _search_service(db_session)
    user = _user(db_session, google_id="u1")
    other_user = _user(db_session, google_id="u2")

    my_sermon = _sermon_in_library(db_session, user, "MINE")
    other_sermon = _sermon_in_library(db_session, other_user, "THEIRS")

    query_vector = [0.1] * 768
    _chunk(db_session, other_sermon, 0, "not mine, closest match", query_vector, start=0)
    _chunk(db_session, my_sermon, 0, "mine, further match", [0.5] * 768, start=10)

    with (
        patch("app.services.search_service.embed_batch", return_value=[query_vector]),
        patch(
            "app.services.search_service.generate_structured",
            return_value=AnswerResult(answer="Some answer."),
        ),
    ):
        result = service.answer_question(user, "anything")

    assert len(result.sources) == 1
    assert result.sources[0].sermon_id == my_sermon.id


def test_answer_question_sources_map_to_sermon_id_and_title(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Faith Under Fire")

    vector = [0.1] * 768
    _chunk(db_session, sermon, 0, "excerpt text", vector, start=5)

    with (
        patch("app.services.search_service.embed_batch", return_value=[vector]),
        patch(
            "app.services.search_service.generate_structured",
            return_value=AnswerResult(answer="Some answer."),
        ),
    ):
        result = service.answer_question(user, "anything")

    assert result.sources[0].sermon_id == sermon.id
    assert result.sources[0].sermon_title == "Faith Under Fire"


def test_answer_question_with_empty_library_skips_llm_call(db_session):
    service = _search_service(db_session)
    user = _user(db_session)

    with (
        patch("app.services.search_service.embed_batch") as mock_embed,
        patch("app.services.search_service.generate_structured") as mock_generate,
    ):
        result = service.answer_question(user, "What did I learn about prayer?")

    mock_embed.assert_not_called()
    mock_generate.assert_not_called()
    assert result.sources == []
    assert "don't have any sermons" in result.answer
