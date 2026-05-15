"""
TTS Adapter Factory - creates TTS adapters based on provider type.
"""

from typing import Any, Dict, Type


class TTSAdapterFactory:
    _adapters: Dict[str, Type] = {}
    
    @staticmethod
    def register_adapter(provider: str, adapter_class: Type):
        """Register a TTS adapter class."""
        TTSAdapterFactory._adapters[provider] = adapter_class
    
    @staticmethod
    def create_adapter(provider: str, **kwargs) -> Any:
        """Create a TTS adapter instance."""
        adapter_class = TTSAdapterFactory._adapters.get(provider)
        if not adapter_class:
            raise ValueError(f"Unsupported TTS provider: {provider}")
        return adapter_class(**kwargs)
    
    @staticmethod
    def get_supported_providers() -> list[str]:
        """Get list of supported TTS providers."""
        return list(TTSAdapterFactory._adapters.keys())