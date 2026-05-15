"""
LLM Adapter Factory - creates LLM adapters based on provider type.
"""

from typing import Any, Dict, Type

from ..llm.local_model import LocalModel


class LLMAdapterFactory:
    _adapters: Dict[str, Type] = {
        "local": LocalModel,
    }
    
    @staticmethod
    def register_adapter(provider: str, adapter_class: Type):
        """Register an LLM adapter class."""
        LLMAdapterFactory._adapters[provider] = adapter_class
    
    @staticmethod
    def create_adapter(provider: str, **kwargs) -> Any:
        """Create an LLM adapter instance."""
        adapter_class = LLMAdapterFactory._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        return adapter_class(**kwargs)
    
    @staticmethod
    def get_supported_providers() -> list[str]:
        """Get list of supported LLM providers."""
        return list(LLMAdapterFactory._adapters.keys())