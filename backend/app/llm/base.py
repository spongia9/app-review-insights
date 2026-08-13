from abc import ABC, abstractmethod
from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel


StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class LLMProviderError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class LLMProvider(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[StructuredOutputT],
        schema_name: str,
    ) -> StructuredOutputT:
        raise NotImplementedError


def openai_compatible_json_payload(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    thinking_enabled: bool,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "stream": False,
    }
    if model.startswith("deepseek-v4"):
        payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
        if not thinking_enabled:
            payload["temperature"] = temperature
    else:
        payload["temperature"] = temperature
    return payload
