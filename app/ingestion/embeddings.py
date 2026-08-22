from app.llm.client import embed_batch


def embed_chunks(chunk_texts: list[str]) -> list[list[float]]:
    return embed_batch(chunk_texts)
