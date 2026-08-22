from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from app.llm.client import embed_batch, generate_structured


class DummySchema(BaseModel):
    foo: str
    bar: int


def test_generate_structured_returns_parsed_pydantic_instance():
    mock_parsed = DummySchema(foo="hello", bar=42)

    with patch("app.llm.client.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value.choices = [
            MagicMock(message=MagicMock(parsed=mock_parsed))
        ]

        result = generate_structured(prompt="say something", response_schema=DummySchema)

    assert result == mock_parsed


def test_generate_structured_returns_none_when_unparseable():
    with patch("app.llm.client.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value.choices = [
            MagicMock(message=MagicMock(parsed=None))
        ]

        result = generate_structured(prompt="say something", response_schema=DummySchema)

    assert result is None


def test_embed_batch_returns_correct_dimension():
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 768)]

    with patch("app.llm.client.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = mock_response

        result = embed_batch(["some text"])

    assert len(result) == 1
    assert len(result[0]) == 768


def test_embed_batch_preserves_order_for_multiple_inputs():
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1] * 768),
        MagicMock(embedding=[0.2] * 768),
        MagicMock(embedding=[0.3] * 768),
    ]

    with patch("app.llm.client.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = mock_response

        result = embed_batch(["first", "second", "third"])

    assert len(result) == 3
    assert result[0][0] == 0.1
    assert result[1][0] == 0.2
    assert result[2][0] == 0.3


def test_embed_batch_requests_configured_dimension():
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 768)]

    with patch("app.llm.client.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.return_value = mock_response

        embed_batch(["some text"])

    mock_client.embeddings.create.assert_called_once()
    _, kwargs = mock_client.embeddings.create.call_args
    assert kwargs.get("dimensions") == 768
