"""Amazon Bedrock Runtime client (Converse API) — sole LLM transport.

Structured JSON + free-text generation with schema retry and throttle backoff.
Agents obtain the process singleton via ``get_llm_client()``.
"""
from __future__ import annotations

import json
import logging
import time
import typing
from typing import Optional, Type, TypeVar

from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.llm.model_router import resolve_model_for_role

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_THROTTLE_CODES = frozenset({
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
})


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
    """Flat JSON example of the expected output shape."""
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


class BedrockStructuredClient:
    """Call Bedrock Converse; validate structured JSON against a Pydantic schema."""

    def __init__(self, region_name: str | None = None):
        import boto3

        self.region_name = (region_name or settings.aws_region or "us-east-1").strip()
        timeout = settings.request_timeout_seconds
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region_name,
            config=BotoConfig(
                connect_timeout=timeout,
                read_timeout=timeout,
                retries={"max_attempts": 0},  # we own retry / backoff
            ),
        )

    def _resolve_model(self, model: str | None, role: str) -> str:
        return resolve_model_for_role(role, explicit_model=model if model else None)

    def _converse(self, *, model: str, prompt: str, temperature: float, num_predict: int) -> tuple[str, dict]:
        """Single Converse call. Returns (text, raw_response). Raises RuntimeError on hard failures."""
        try:
            response = self._client.converse(
                modelId=model,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={
                    "maxTokens": int(num_predict),
                    "temperature": float(temperature),
                    "topP": 0.9,
                },
            )
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code", "")
            msg = (e.response.get("Error") or {}).get("Message", str(e))
            if code in ("AccessDeniedException", "UnauthorizedOperation"):
                raise RuntimeError(
                    f"[bedrock] Access denied for model {model!r} in {self.region_name}. "
                    "Enable model access in the Amazon Bedrock console "
                    "(Model access → request/enable Nova Lite/Micro), then retry. "
                    f"Details: {msg}"
                ) from e
            if code == "ValidationException":
                raise RuntimeError(
                    f"[bedrock] ValidationException for model {model!r} (bad request params — "
                    f"fix the client code, not credentials): {msg}"
                ) from e
            if code in _THROTTLE_CODES:
                raise _BedrockThrottleError(f"[bedrock] throttled ({code}): {msg}") from e
            raise RuntimeError(f"[bedrock] ClientError ({code}): {msg}") from e
        except BotoCoreError as e:
            raise RuntimeError(f"[bedrock] transport error: {e}") from e

        content = (
            ((response.get("output") or {}).get("message") or {}).get("content") or []
        )
        texts = [block.get("text", "") for block in content if isinstance(block, dict)]
        raw_text = "".join(texts).strip()
        return raw_text, response

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        model: str | None,
        role: str,
        temperature: float = 0.2,
        num_predict: int = 400,
        max_retries: int = 2,
        timeout: int | None = None,
    ) -> tuple[T, LLMCallMetadata]:
        """Generate JSON via Converse, validate, retry on parse/schema errors."""
        _ = timeout  # boto client already configured with request_timeout_seconds
        resolved_model = self._resolve_model(model, role)
        schema_hint = _build_example_hint(schema)
        current_prompt = (
            f"{prompt}\n\n"
            "Respond with ONLY a single valid JSON object shaped exactly like this example "
            f"(replace each placeholder value, keep the same keys, no markdown fences, no commentary):\n{schema_hint}"
        )

        last_error: Exception | None = None
        start = time.monotonic()
        attempts = 0
        usage_in = 0
        usage_out = 0

        for attempt in range(1, max_retries + 2):
            attempts = attempt
            try:
                raw_text, raw_resp = self._converse(
                    model=resolved_model,
                    prompt=current_prompt,
                    temperature=temperature,
                    num_predict=num_predict,
                )
                usage = raw_resp.get("usage") or {}
                usage_in = int(usage.get("inputTokens") or 0)
                usage_out = int(usage.get("outputTokens") or 0)

                parsed_json = json.loads(raw_text)
                parsed_obj = schema.model_validate(parsed_json)

                latency_ms = (time.monotonic() - start) * 1000
                metadata = LLMCallMetadata(
                    model=resolved_model,
                    role=role,
                    latency_ms=round(latency_ms, 1),
                    prompt_tokens=usage_in,
                    completion_tokens=usage_out,
                    attempts=attempts,
                    raw_response_truncated=raw_text[:500],
                )
                return parsed_obj, metadata

            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e
                logger.warning(
                    "[%s] Bedrock output failed schema validation (attempt %d/%d): %s",
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
            except _BedrockThrottleError as e:
                last_error = e
                sleep_s = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "[%s] Bedrock throttled (attempt %d/%d), backoff %ss: %s",
                    role,
                    attempt,
                    max_retries + 1,
                    sleep_s,
                    e,
                )
                time.sleep(sleep_s)
            except RuntimeError:
                # AccessDenied / ValidationException / non-retryable — do not loop.
                raise

        raise RuntimeError(
            f"[{role}] LLM call failed after {attempts} attempt(s) model={resolved_model}: {last_error}"
        )

    def generate_text(
        self,
        prompt: str,
        model: str | None,
        role: str,
        temperature: float = 0.6,
        num_predict: int = 500,
        max_retries: int = 2,
        timeout: int | None = None,
    ) -> tuple[str, LLMCallMetadata]:
        """Free-text generation (no JSON schema) — for drafting_agent."""
        _ = timeout
        resolved_model = self._resolve_model(model, role)
        last_error: Exception | None = None
        start = time.monotonic()
        attempts = 0

        for attempt in range(1, max_retries + 2):
            attempts = attempt
            try:
                raw_text, raw_resp = self._converse(
                    model=resolved_model,
                    prompt=prompt,
                    temperature=temperature,
                    num_predict=num_predict,
                )
                usage = raw_resp.get("usage") or {}
                latency_ms = (time.monotonic() - start) * 1000
                metadata = LLMCallMetadata(
                    model=resolved_model,
                    role=role,
                    latency_ms=round(latency_ms, 1),
                    prompt_tokens=int(usage.get("inputTokens") or 0),
                    completion_tokens=int(usage.get("outputTokens") or 0),
                    attempts=attempts,
                    raw_response_truncated=raw_text[:300],
                )
                return raw_text, metadata
            except _BedrockThrottleError as e:
                last_error = e
                sleep_s = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "[%s] Bedrock throttled on generate_text (attempt %d/%d), backoff %ss",
                    role,
                    attempt,
                    max_retries + 1,
                    sleep_s,
                )
                time.sleep(sleep_s)
            except RuntimeError:
                raise

        raise RuntimeError(
            f"[{role}] generate_text failed after {attempts} attempt(s) model={resolved_model}: {last_error}"
        )


class _BedrockThrottleError(RuntimeError):
    """Transient Bedrock capacity / rate limit — safe to retry same model."""


_client: BedrockStructuredClient | None = None


def get_llm_client() -> BedrockStructuredClient:
    """Return the process-wide Bedrock client singleton."""
    global _client
    if _client is None:
        logger.info(
            "[llm] using BedrockStructuredClient (region=%s)",
            settings.aws_region,
        )
        _client = BedrockStructuredClient()
    return _client


def reset_llm_client() -> None:
    """Test helper — drop the cached client so the next get_llm_client() rebuilds."""
    global _client
    _client = None
