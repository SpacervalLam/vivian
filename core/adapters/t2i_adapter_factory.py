"""
T2I Adapter Factory - creates T2I adapters based on provider type.
"""

from typing import Any, Dict, Type


class T2IAdapterFactory:
    _adapters: Dict[str, Type] = {}
    
    @staticmethod
    def register_adapter(provider: str, adapter_class: Type):
        """Register a T2I adapter class."""
        T2IAdapterFactory._adapters[provider] = adapter_class
    
    @staticmethod
    def create_adapter(provider: str, **kwargs) -> Any:
        """Create a T2I adapter instance."""
        adapter_class = T2IAdapterFactory._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Unsupported T2I provider: {provider}")
        return adapter_class(**kwargs)
    
    @staticmethod
    def get_supported_providers() -> list[str]:
        """Get list of supported T2I providers."""
        return list(T2IAdapterFactory._adapters.keys())