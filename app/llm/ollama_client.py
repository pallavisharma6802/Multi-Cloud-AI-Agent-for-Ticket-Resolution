"""Shared structured-output client for Ollama LLM calls.

One HTTP client, schema validation with retry, and latency/token metadata.
No business logic — agents own prompts and schemas.
"""
from __future__ import annotations

import json
import logging
import time
import typing
from typing import Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _field_placeholder(annotation, description: str | None):
    """Example placeholder for one schema field (unwraps Optional/List)."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin is typing.Union and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _field_placeholder(non_none[0], description)

    if origin is typing.Literal:
        return "|".join(str(a) for a in args)

    if origin in (list, typing.List):
        inner = args[0] if args else str
        return [_field_placeholder(inner, None)]

    if annotation is bool:
        return f"<true or false{': ' + description if description else ''}>"
    if annotation is float:
        return f"<number{': ' + description if description else ''}>"
    if annotation is int:
        return f"<integer{': ' + description if description else ''}>"
    return f"<{description or 'string'}>"


def _build_example_hint(schema: Type[BaseModel]) -> str:
    """Flat JSON example of the expected output shape.

    Prefer a concrete example over full JSON Schema: small local models often
    echo schema meta-keys (`properties`, `required`) instead of the answer.
    """
    example = {
        name: _field_placeholder(info.annotation, info.description)
        for name, info in schema.model_fields.items()
    }
    return json.dumps(example, indent=2)


class LLMCallMetadata(BaseModel):
    model: str
    role: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1
    raw_response_truncated: str = ""


class StructuredLLMResult(BaseModel):
    class Config:
        arbitrary_types_allowed = True

    parsed: object
    metadata: LLMCallMetadata


class OllamaStructuredClient:
    """Call Ollama /api/generate in JSON mode; validate against a Pydantic schema."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.endpoint = f"{self.base_url}/api/generate"

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        model: str,
        role: str,
        temperature: float = 0.2,
        num_predict: int = 400,
        max_retries: int = 2,
        timeout: int | None = None,
    ) -> tuple[T, LLMCallMetadata]:
        """Generate JSON, validate, and retry on parse errors. Raises if all attempts fail."""
        timeout = timeout or settings.request_timeout_seconds
        schema_hint = _build_example_hint(schema)
        current_prompt = (
            f"{prompt}\n\n"
            "Respond with ONLY a single valid JSON object shaped exactly like this example "
            f"(replace each placeholder value, keep the same keys, no markdown fences, no commentary):\n{schema_hint}"
        )

        last_error: Exception | None = None
        start = time.monotonic()
        attempts = 0

        for attempt in range(1, max_retries + 2):
            attempts = attempt
            payload = {
                "model": model,
                "prompt": current_prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": temperature,
                    "num_predict": num_predict,
                    "top_p": 0.9,
                },
            }
            try:
                response = requests.post(self.endpoint, json=payload, timeout=timeout)
                response.raise_for_status()
                result = response.json()
                raw_text = result.get("response", "").strip()
                parsed_json = json.loads(raw_text)
                parsed_obj = schema.model_validate(parsed_json)

                latency_ms = (time.monotonic() - start) * 1000
                metadata = LLMCallMetadata(
                    model=model,
                    role=role,
                    latency_ms=round(latency_ms, 1),
                    prompt_tokens=result.get("prompt_eval_count", 0),
                    completion_tokens=result.get("eval_count", 0),
                    attempts=attempts,
                    raw_response_truncated=raw_text[:500],
                )
                return parsed_obj, metadata

            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning(
                    "[%s] LLM output failed schema validation (attempt %d/%d): %s",
                    role,
                    attempt,
                    max_retries + 1,
                    e,
                )
                current_prompt = (
                    f"{prompt}\n\n"
                    "Your previous response did not match the required format. "
                    f"Error: {e}\n"
                    "Respond with ONLY a single valid JSON object shaped exactly like this example "
                    f"(replace each placeholder value, keep the same keys, no markdown fences, no commentary):\n{schema_hint}"
                )
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.error("[%s] Ollama request timed out (attempt %d)", role, attempt)
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.error("[%s] Ollama request failed (attempt %d): %s", role, attempt, e)

        raise RuntimeError(
            f"[{role}] LLM call failed after {attempts} attempt(s): {last_error}"
        )


_client: OllamaStructuredClient | None = None


def get_llm_client() -> OllamaStructuredClient:
    global _client
    if _client is None:
        _client = OllamaStructuredClient()
    return _client
