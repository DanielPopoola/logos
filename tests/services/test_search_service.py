from unittest.mock import patch

from app.models.sermon import ProcessingStatus, Sermon
from app.models.sermon_chunk import SermonChunk
from app.models.taxonomy import Theme
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


def _tag_theme(db_session, sermon: Sermon, theme_name: str) -> Theme:
    theme = db_session.query(Theme).filter_by(name=theme_name).first()
    if theme is None:
        theme = Theme(name=theme_name)
        db_session.add(theme)
        db_session.flush()
    sermon.themes.append(theme)
    db_session.commit()
    return theme


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
    assert results[0].sermon_id == sermon.id
    assert results[0].sermon_title == "Test Sermon"
    assert results[0].speaker == "Pastor Jane"


def test_semantic_search_matches_title_before_trying_embeddings(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Walking by Faith")

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "walking by faith", limit=10)

    mock_embed.assert_not_called()
    assert len(response.results) == 1
    assert response.results[0].sermon_id == sermon.id
    assert response.results[0].relevance_score == 1.0


def test_semantic_search_title_match_is_case_insensitive_substring(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Walking by Faith")

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "FAITH", limit=10)

    mock_embed.assert_not_called()
    assert response.results[0].sermon_id == sermon.id


def test_semantic_search_matches_theme_before_trying_embeddings(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Something Else Entirely")
    _tag_theme(db_session, sermon, "Perseverance")

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "perseverance", limit=10)

    mock_embed.assert_not_called()
    assert len(response.results) == 1
    assert response.results[0].sermon_id == sermon.id


def test_semantic_search_theme_match_does_not_duplicate_sermon_with_multiple_matching_themes(
    db_session,
):
    """A sermon tagged with two themes that both match the query (e.g.
    "Grace" and "Amazing Grace") must appear once in results, not twice -
    regression test for a real bug where the underlying multi-table join
    produced one row per matching theme rather than one row per sermon."""
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Something Else")
    _tag_theme(db_session, sermon, "Grace")
    _tag_theme(db_session, sermon, "Amazing Grace")

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "grace", limit=10)

    mock_embed.assert_not_called()
    assert len(response.results) == 1
    assert response.results[0].sermon_id == sermon.id


def test_semantic_search_title_matches_and_theme_matches_are_both_returned_up_to_limit(
    db_session,
):
    """Title matches are ranked first, but theme matches fill any
    remaining slots up to `limit` in the same tier - both are still the
    cheap tier, distinct sermons just found by different signals."""
    service = _search_service(db_session)
    user = _user(db_session)
    title_match = _sermon_in_library(db_session, user, "V1", title="Faith in Hard Times")
    theme_match = _sermon_in_library(db_session, user, "V2", title="Unrelated Title")
    _tag_theme(db_session, theme_match, "Faith")

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "faith", limit=10)

    mock_embed.assert_not_called()
    result_ids = {r.sermon_id for r in response.results}
    assert result_ids == {title_match.id, theme_match.id}
    # title match ranked first
    assert response.results[0].sermon_id == title_match.id


def test_semantic_search_falls_back_to_embeddings_when_title_and_theme_find_nothing(db_session):
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Walking by Faith")
    _tag_theme(db_session, sermon, "Obedience")

    query_vector = [0.1] * 768
    _chunk(db_session, sermon, 0, "a chunk about something unrelated to the query", query_vector)

    with patch("app.services.search_service.embed_batch", return_value=[query_vector]) as mock_embed:
        response = service.semantic_search(user, "a completely different topic", limit=10)

    mock_embed.assert_called_once()
    assert len(response.results) == 1
    assert response.results[0].sermon_id == sermon.id


def test_semantic_search_does_not_top_up_title_matches_with_embeddings(db_session):
    """If title/theme find even one result, embeddings are skipped
    entirely for that search - not used to fill remaining slots up to
    `limit`, even if fewer than `limit` sermons were found."""
    service = _search_service(db_session)
    user = _user(db_session)
    _sermon_in_library(db_session, user, "V1", title="Walking by Faith")

    with patch("app.services.search_service.embed_batch") as mock_embed:
        response = service.semantic_search(user, "walking by faith", limit=10)

    mock_embed.assert_not_called()
    assert len(response.results) == 1


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


def test_semantic_search_title_match_never_returns_other_users_sermons(db_session):
    service = _search_service(db_session)
    user = _user(db_session, google_id="u1")
    other_user = _user(db_session, google_id="u2")

    # user needs a non-empty library so this test exercises tier
    # isolation, not the separate empty-library guard.
    _sermon_in_library(db_session, user, "MINE", title="Something Unrelated")
    _sermon_in_library(db_session, other_user, "THEIRS", title="Walking by Faith")

    with patch("app.services.search_service.embed_batch", return_value=[[0.1] * 768]) as mock_embed:
        response = service.semantic_search(user, "walking by faith", limit=10)

    # Title tier found nothing in *my* library, so it correctly falls
    # through to embeddings - which also find nothing, since my only
    # sermon has no chunks and the other user's sermon is out of scope.
    mock_embed.assert_called_once()
    assert response.results == []


def test_semantic_search_respects_limit(db_session):
    service = _search_service(db_session)
    user = _user(db_session)

    # 5 distinct sermons, each with one chunk - limit should cap the
    # number of *sermons* returned, which is now the unit of a result.
    for i in range(5):
        sermon = _sermon_in_library(db_session, user, f"V{i}", title=f"Sermon {i}")
        _chunk(db_session, sermon, 0, f"chunk {i}", [0.1 * i] * 768, start=i * 10)

    query_vector = [0.0] * 768
    with patch("app.services.search_service.embed_batch", return_value=[query_vector]):
        response = service.semantic_search(user, "anything", limit=2)

    assert len(response.results) == 2


def test_semantic_search_collapses_multiple_matches_from_same_sermon(db_session):
    """A sermon with several chunks that all match well should appear once
    in results, not once per matching chunk - now that individual
    excerpts/timestamps aren't part of what's shown, duplicate rows for
    the same sermon would be indistinguishable and just noise."""
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="One Sermon")

    query_vector = [0.1] * 768
    _chunk(db_session, sermon, 0, "first close chunk", query_vector, start=0)
    _chunk(db_session, sermon, 1, "second close chunk", [0.11] * 768, start=60)
    _chunk(db_session, sermon, 2, "third close chunk", [0.12] * 768, start=120)

    with patch("app.services.search_service.embed_batch", return_value=[query_vector]):
        response = service.semantic_search(user, "anything", limit=10)

    assert len(response.results) == 1
    assert response.results[0].sermon_id == sermon.id


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


def test_answer_question_prompt_is_still_grounded_in_real_excerpt_text(db_session):
    """sources no longer carries excerpt text (see SearchResult), but the
    LLM prompt still needs real transcript content to ground its answer -
    that's an internal grounding concern, separate from what's shown to
    the user. This locks in that the excerpt text still reaches the
    prompt even though it's absent from the public-facing sources."""
    service = _search_service(db_session)
    user = _user(db_session)
    sermon = _sermon_in_library(db_session, user, "V1", title="Faith Under Fire")

    vector = [0.1] * 768
    _chunk(db_session, sermon, 0, "a very specific and unusual phrase", vector, start=5)

    with (
        patch("app.services.search_service.embed_batch", return_value=[vector]),
        patch(
            "app.services.search_service.generate_structured",
            return_value=AnswerResult(answer="Some answer."),
        ) as mock_generate,
    ):
        service.answer_question(user, "anything")

    prompt_used = mock_generate.call_args.kwargs["prompt"]
    assert "a very specific and unusual phrase" in prompt_used
    assert "Faith Under Fire" in prompt_used


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
