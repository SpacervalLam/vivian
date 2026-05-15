"""
Plugin capability registry - allows plugins to register their extensions.
"""

from __future__ import annotations

from typing import Any, Callable, Type


class PluginCapabilityRegistry:
    """Registry for plugin capabilities."""
    
    def __init__(self):
        self._llm_providers = {}
        self._tts_providers = {}
        self._asr_providers = {}
        self._t2i_providers = {}
        self._tools = {}
        self._message_handlers = []
        self._ui_handlers = []
        self._user_input_processors = []
        self._settings_contributions = []
    
    def register_llm_provider(self, name: str, adapter_class: Type):
        """Register an LLM provider adapter."""
        self._llm_providers[name] = adapter_class
    
    def register_tts_provider(self, name: str, adapter_class: Type):
        """Register a TTS provider adapter."""
        self._tts_providers[name] = adapter_class
    
    def register_asr_provider(self, name: str, adapter_class: Type):
        """Register an ASR provider adapter."""
        self._asr_providers[name] = adapter_class
    
    def register_t2i_provider(self, name: str, adapter_class: Type):
        """Register a T2I provider adapter."""
        self._t2i_providers[name] = adapter_class
    
    def register_tool(self, name: str, func: Callable, **kwargs):
        """Register an LLM tool."""
        self._tools[name] = {"func": func, "kwargs": kwargs}
    
    def register_message_handler(self, handler):
        """Register a message handler."""
        self._message_handlers.append(handler)
    
    def register_ui_handler(self, handler):
        """Register a UI output handler."""
        self._ui_handlers.append(handler)
    
    def register_user_input_processor(self, processor: Callable):
        """Register a user input processor."""
        self._user_input_processors.append(processor)
    
    def register_settings_contribution(self, contribution):
        """Register a settings UI contribution."""
        self._settings_contributions.append(contribution)
    
    def get_capabilities(self):
        """Get all registered capabilities."""
        return {
            "llm_providers": self._llm_providers,
            "tts_providers": self._tts_providers,
            "asr_providers": self._asr_providers,
            "t2i_providers": self._t2i_providers,
            "tools": self._tools,
            "message_handlers": self._message_handlers,
            "ui_handlers": self._ui_handlers,
            "user_input_processors": self._user_input_processors,
            "settings_contributions": self._settings_contributions,
        }