"""
LLM Adapter Factory - creates LLM adapters based on provider type.
"""

from typing import Any, Dict, Type

from .llm_adapters import (
    BaseLLMAdapter,
    OpenAICompatibleAdapter,
    AnthropicAdapter,
    GeminiAdapter,
    LocalAdapter,
    UnifiedChatRequest,
    UnifiedChatResponse,
)
from ..local_model import LocalModel


class LLMAdapterFactory:
    _adapters: Dict[str, Type[BaseLLMAdapter]] = {
        "openai": OpenAICompatibleAdapter,
        "anthropic": AnthropicAdapter,
        "gemini": GeminiAdapter,
        "deepseek": OpenAICompatibleAdapter,
        "qwen": OpenAICompatibleAdapter,
        "kimi": OpenAICompatibleAdapter,
        "moonshot": OpenAICompatibleAdapter,
        "baidu": OpenAICompatibleAdapter,
        "doubao": OpenAICompatibleAdapter,
        "dashscope": OpenAICompatibleAdapter,
        "together": OpenAICompatibleAdapter,
        "ollama": OpenAICompatibleAdapter,
        "vllm": OpenAICompatibleAdapter,
        "custom": OpenAICompatibleAdapter,
        "local": LocalAdapter,
    }

    @staticmethod
    def register_adapter(provider: str, adapter_class: Type[BaseLLMAdapter]):
        """Register an LLM adapter class."""
        LLMAdapterFactory._adapters[provider] = adapter_class

    @staticmethod
    def create_adapter(provider: str, **kwargs) -> BaseLLMAdapter:
        """Create an LLM adapter instance."""
        adapter_class = LLMAdapterFactory._adapters.get(provider.lower())
        if not adapter_class:
            adapter_class = OpenAICompatibleAdapter
        return adapter_class(**kwargs)

    @staticmethod
    def get_supported_providers() -> list[str]:
        """Get list of supported LLM providers."""
        return list(LLMAdapterFactory._adapters.keys())

    @staticmethod
    def detect_adapter(provider: str) -> Type[BaseLLMAdapter]:
        """Detect adapter class based on provider name."""
        return LLMAdapterFactory._adapters.get(provider.lower(), OpenAICompatibleAdapter)