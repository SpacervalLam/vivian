"""
ASR Adapter Factory - creates ASR adapters based on provider type.
"""

from typing import Any, Dict, Type


class ASRAdapterFactory:
    _adapters: Dict[str, Type] = {}
    
    @staticmethod
    def register_adapter(provider: str, adapter_class: Type):
        """Register an ASR adapter class."""
        ASRAdapterFactory._adapters[provider] = adapter_class
    
    @staticmethod
    def create_adapter(provider: str, **kwargs) -> Any:
        """Create an ASR adapter instance."""
        adapter_class = ASRAdapterFactory._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Unsupported ASR provider: {provider}")
        return adapter_class(**kwargs)
    
    @staticmethod
    def get_supported_providers() -> list[str]:
        """Get list of supported ASR providers."""
        return list(ASRAdapterFactory._adapters.keys())