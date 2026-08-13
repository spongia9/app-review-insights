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
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty model content")
            return response_model.model_validate(json.loads(content))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            raise LLMProviderError(
                "INVALID_STRUCTURED_OUTPUT",
                f"The provider returned invalid {schema_name} structured output.",
            ) from error
