import logging
import time

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings
from app.llm.retry import retry_on_transient_error

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


@retry_on_transient_error()
def generate_structured(prompt: str, response_schema: type[BaseModel]) -> BaseModel | None:
    client = _client()
    started_at = time.perf_counter()
    try:
        completion = client.beta.chat.completions.parse(
            model=settings.llm_model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_schema,
        )
    except Exception:
        logger.warning(
            "External API call failed",
            exc_info=True,
            extra={
                "provider": "llm",
                "operation": "generate_structured",
                "model": settings.llm_model_name,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    logger.info(
        "External API call completed",
        extra={
            "provider": "llm",
            "operation": "generate_structured",
            "model": settings.llm_model_name,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return completion.choices[0].message.parsed


@retry_on_transient_error()
def embed_batch(texts: list[str]) -> list[list[float]]:
    client = _client()
    started_at = time.perf_counter()
    try:
        response = client.embeddings.create(
            model=settings.llm_embedding_model_name,
            input=texts,
            dimensions=settings.llm_embedding_dimensions,
        )
    except Exception:
        logger.warning(
            "External API call failed",
            exc_info=True,
            extra={
                "provider": "llm",
                "operation": "embed_batch",
                "model": settings.llm_embedding_model_name,
                "input_count": len(texts),
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        raise
    logger.info(
        "External API call completed",
        extra={
            "provider": "llm",
            "operation": "embed_batch",
            "model": settings.llm_embedding_model_name,
            "input_count": len(texts),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return [item.embedding for item in response.data]
