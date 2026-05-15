"""
Plugin host integration - loads plugins and manages their lifecycle.
"""

from pathlib import Path
from queue import Queue
from typing import Any, Callable, List, Optional

from core.sdk.manager import PluginManager

_MANIFEST = Path("data/config/plugins.yaml")
_loaded: bool = False
_plugin_manager: PluginManager | None = None
_plugin_tts_handlers: List = []
_plugin_ui_handlers: List = []


def get_plugin_manager() -> PluginManager | None:
    return _plugin_manager


def get_plugin_tts_handlers() -> List:
    return list(_plugin_tts_handlers)


def get_plugin_ui_handlers() -> List:
    return list(_plugin_ui_handlers)


def ensure_plugins_loaded(config=None) -> PluginManager | None:
    global _loaded, _plugin_manager, _plugin_tts_handlers, _plugin_ui_handlers
    
    if _loaded:
        return _plugin_manager
    
    mgr = PluginManager()
    
    if _MANIFEST.is_file():
        try:
            mgr.load_manifest_file(_MANIFEST)
        except Exception as e:
            print(f"Failed to load plugin manifest: {e}")
    
    mgr.instantiate_all()
    
    try:
        from core.adapters import (
            LLMAdapterFactory,
            TTSAdapterFactory,
            ASRAdapterFactory,
            T2IAdapterFactory,
        )
        
        mgr.apply_llm_providers(LLMAdapterFactory._adapters)
        mgr.apply_tts_providers(TTSAdapterFactory._adapters)
        mgr.apply_asr_providers(ASRAdapterFactory._adapters)
        mgr.apply_t2i_providers(T2IAdapterFactory._adapters)
    except Exception as e:
        print(f"Failed to apply providers: {e}")
    
    try:
        from core.tool_manager import ToolManager
        tm = ToolManager()
        mgr.apply_llm_tools(tm)
    except Exception as e:
        print(f"Failed to apply tools: {e}")
    
    try:
        tts_handlers, ui_handlers = mgr.collect_message_handlers()
        _plugin_tts_handlers = tts_handlers
        _plugin_ui_handlers = ui_handlers
    except Exception as e:
        print(f"Failed to collect handlers: {e}")
        _plugin_tts_handlers = []
        _plugin_ui_handlers = []
    
    _plugin_manager = mgr
    _loaded = True
    
    return _plugin_manager


def wire_user_input_plugins(user_input_queue: Queue) -> Callable[[str], None]:
    mgr = _plugin_manager
    processors: list[Callable[[str], str | None]] = []
    
    def emit_user_text(text: str) -> None:
        t = text
        for proc in processors:
            try:
                out = proc(t)
            except Exception as e:
                print(f"User input processor failed: {e}")
                return
            if out is None:
                return
            t = out
        user_input_queue.put(t)
    
    if mgr is not None:
        try:
            mgr.wire_user_input(emit_user_text, processors)
        except Exception as e:
            print(f"Failed to wire user input: {e}")
    
    return emit_user_text