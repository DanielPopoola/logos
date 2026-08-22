from openai import OpenAI
from pydantic import BaseModel

from app.config import settings


def _client() -> OpenAI:
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def generate_structured(prompt: str, response_schema: type[BaseModel]) -> BaseModel | None:
    client = _client()
    completion = client.beta.chat.completions.parse(
        model=settings.llm_model_name,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_schema,
    )
    return completion.choices[0].message.parsed


def embed_batch(texts: list[str]) -> list[list[float]]:
    client = _client()
    response = client.embeddings.create(
        model=settings.llm_embedding_model_name,
        input=texts,
    )
    return [item.embedding for item in response.data]
