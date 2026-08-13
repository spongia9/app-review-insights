from app.core.config import Settings
from app.llm.base import LLMProvider, LLMProviderError
from app.llm.deepseek import DeepSeekProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider = (settings.llm_provider or "").lower()
    if provider != "deepseek":
        raise LLMProviderError(
            "LLM_NOT_CONFIGURED",
            "LLM_PROVIDER must be configured as deepseek for Phase 3.",
            retryable=False,
        )
    if not settings.llm_model:
        raise LLMProviderError(
            "LLM_NOT_CONFIGURED",
            "LLM_MODEL is required for runtime semantic analysis.",
            retryable=False,
        )
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
    return DeepSeekProvider(
        api_key=api_key,
        model_name=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_request_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        thinking_enabled=settings.llm_thinking_enabled,
        trust_environment_proxy=settings.llm_trust_environment_proxy,
    )
