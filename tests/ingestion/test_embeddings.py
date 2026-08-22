from unittest.mock import patch

from app.ingestion.embeddings import embed_chunks


def test_embed_chunks_delegates_to_llm_client_and_preserves_order():
    with patch("app.ingestion.embeddings.embed_batch") as mock_embed:
        mock_embed.return_value = [[0.1] * 768, [0.2] * 768]

        result = embed_chunks(["chunk one", "chunk two"])

    assert result == [[0.1] * 768, [0.2] * 768]
    mock_embed.assert_called_once_with(["chunk one", "chunk two"])
