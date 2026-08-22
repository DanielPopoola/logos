from unittest.mock import patch

import pytest

from app.ingestion.analysis import AnalysisParseError, SermonAnalysisResult, analyze_transcript

MOCK_VALID_RESULT = SermonAnalysisResult(
    summary="A message about trusting God through hardship.",
    key_teachings=["God is faithful even in trials", "Faith grows through testing"],
    themes=["faith", "trust", "perseverance"],
    bible_references=["Romans 8:28", "Psalm 23:1-4"],
    action_points=["Spend 15 minutes in prayer this week", "Read Romans 8 again"],
    reflection_questions=["Where have you seen God's faithfulness in hardship?"],
)


def test_returns_sermon_analysis_result_with_all_six_fields():
    with patch("app.ingestion.analysis.generate_structured") as mock_generate:
        mock_generate.return_value = MOCK_VALID_RESULT

        result = analyze_transcript("some transcript text")

    assert isinstance(result, SermonAnalysisResult)
    assert result.summary == MOCK_VALID_RESULT.summary
    assert result.themes == MOCK_VALID_RESULT.themes


def test_none_response_raises_typed_error():
    with patch("app.ingestion.analysis.generate_structured") as mock_generate:
        mock_generate.return_value = None

        with pytest.raises(AnalysisParseError):
            analyze_transcript("some transcript text")
