import json
from typing import Any, Dict, Type

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import (
    LLMProvider,
    LLMProviderError,
    StructuredOutputT,
    openai_compatible_json_payload,
)


class DeepSeekProvider(LLMProvider):
    provider_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
        temperature: float,
        thinking_enabled: bool,
        trust_environment_proxy: bool,
    ) -> None:
        if not api_key:
            raise LLMProviderError(
                "LLM_NOT_CONFIGURED",
                "LLM_API_KEY is required for runtime semantic analysis.",
                retryable=False,
            )
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.thinking_enabled = thinking_enabled
        self.trust_environment_proxy = trust_environment_proxy
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[StructuredOutputT],
        schema_name: str,
    ) -> StructuredOutputT:
        payload = openai_compatible_json_payload(
            model=self.model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            thinking_enabled=self.thinking_enabled,
        )
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                trust_env=self.trust_environment_proxy,
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise LLMProviderError("LLM_TIMEOUT", "The LLM request timed out.") from error
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            retryable = status == 429 or status >= 500
            raise LLMProviderError(
                "LLM_PROVIDER_ERROR",
                f"The LLM provider returned HTTP {status}.",
                retryable=retryable,
            ) from error
        except httpx.HTTPError as error:
            raise LLMProviderError("LLM_PROVIDER_ERROR", "The LLM provider request failed.") from error

        try:
            data: Dict[str, Any] = response.json()
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMProviderError(
                "LLM_INVALID_RESPONSE",
                "The LLM provider returned an invalid response envelope.",
                details={"schema_name": schema_name},
            ) from error

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        finish_reason = choice.get("finish_reason")
        content = message.get("content") if isinstance(message, dict) else None
        diagnostics = {
            "schema_name": schema_name,
            "response_id": data.get("id"),
            "finish_reason": finish_reason,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "max_output_tokens": self.max_output_tokens,
            "content_chars": len(content) if isinstance(content, str) else 0,
        }

        if finish_reason == "length":
            completion_tokens = diagnostics.get("completion_tokens")
            raise LLMProviderError(
                "LLM_OUTPUT_TRUNCATED",
                (
                    "The LLM output reached the configured token limit before the "
                    f"{schema_name} JSON object was complete "
                    f"(completion_tokens={completion_tokens}, limit={self.max_output_tokens})."
                ),
                retryable=False,
                details=diagnostics,
            )
        if finish_reason == "content_filter":
            raise LLMProviderError(
                "LLM_CONTENT_FILTERED",
                "The LLM provider filtered the structured response.",
                retryable=False,
                details=diagnostics,
            )
        if finish_reason == "insufficient_system_resource":
            raise LLMProviderError(
                "LLM_INSUFFICIENT_RESOURCE",
                "The LLM provider could not complete the request because capacity was unavailable.",
                details=diagnostics,
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError(
                "LLM_EMPTY_CONTENT",
                f"The LLM provider returned empty {schema_name} content.",
                details=diagnostics,
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMProviderError(
                "LLM_INVALID_JSON",
                (
                    f"The LLM returned malformed {schema_name} JSON at "
                    f"line {error.lineno}, column {error.colno}."
                ),
                details={
                    **diagnostics,
                    "json_error_line": error.lineno,
                    "json_error_column": error.colno,
                },
            ) from error

        try:
            return response_model.model_validate(parsed)
        except ValidationError as error:
            validation_errors = [
                {
                    "location": ".".join(str(part) for part in item["loc"]),
                    "type": item["type"],
                }
                for item in error.errors(include_input=False)[:12]
            ]
            locations = ", ".join(item["location"] for item in validation_errors[:4])
            raise LLMProviderError(
                "LLM_SCHEMA_VALIDATION_FAILED",
                (
                    f"The LLM returned JSON that does not match {schema_name}"
                    f"{f' at {locations}' if locations else ''}."
                ),
                details={**diagnostics, "validation_errors": validation_errors},
            ) from error
