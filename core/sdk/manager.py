"""
Plugin manager - loads and manages plugins.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .plugin import PluginBase
from .plugin_host_context import PluginHostContext
from .register import PluginCapabilityRegistry

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(self):
        self._plugins: Dict[str, PluginBase] = {}
        self._capabilities = {
            "llm_providers": {},
            "tts_providers": {},
            "asr_providers": {},
            "t2i_providers": {},
            "tools": {},
            "message_handlers": [],
            "ui_handlers": [],
            "user_input_processors": [],
            "settings_contributions": [],
        }
    
    def load_manifest_file(self, path: Path):
        """Load plugins from a YAML manifest file."""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        
        for item in manifest:
            if item.get("enabled", True):
                entry = item.get("entry")
                if entry:
                    self._load_plugin(entry)
    
    def _load_plugin(self, entry: str):
        """Load a plugin from entry string."""
        try:
            module_path, class_name = entry.rsplit(":", 1)
            module = importlib.import_module(module_path)
            plugin_class: Type[PluginBase] = getattr(module, class_name)
            
            host_context = PluginHostContext(
                project_root=Path.cwd(),
                config_dir=Path.cwd() / "data" / "config",
                data_dir=Path.cwd() / "data",
                cache_dir=Path.cwd() / "data" / "cache",
            )
            
            plugin_root = self._get_plugin_root(module_path)
            plugin = plugin_class()
            
            registry = PluginCapabilityRegistry()
            plugin.initialize(registry, plugin_root, host_context)
            
            self._plugins[plugin.plugin_id] = plugin
            self._merge_capabilities(registry.get_capabilities())
            
            logger.info(f"Loaded plugin: {plugin.plugin_id} ({plugin.plugin_name})")
        except Exception as e:
            logger.error(f"Failed to load plugin {entry}: {e}")
    
    def _get_plugin_root(self, module_path: str) -> Path:
        """Get the plugin root directory from module path."""
        if module_path.startswith("plugins."):
            return Path("plugins") / module_path[len("plugins."):].split(".")[0]
        return Path(".")
    
    def _merge_capabilities(self, capabilities: Dict[str, Any]):
        """Merge plugin capabilities into the manager."""
        for key, value in capabilities.items():
            if isinstance(value, dict):
                self._capabilities[key].update(value)
            elif isinstance(value, list):
                self._capabilities[key].extend(value)
    
    def instantiate_all(self):
        """Instantiate all plugins (called after loading manifests)."""
        pass
    
    def load_own_config_all(self, app_config):
        """Load plugin-specific configurations."""
        for plugin in self._plugins.values():
            try:
                if hasattr(plugin, "load_config"):
                    plugin.load_config(app_config)
            except Exception as e:
                logger.error(f"Failed to load config for {plugin.plugin_id}: {e}")
    
    def apply_llm_providers(self, factory_adapters: Dict[str, Type]):
        """Apply registered LLM providers to the factory."""
        factory_adapters.update(self._capabilities["llm_providers"])
    
    def apply_tts_providers(self, factory_adapters: Dict[str, Type]):
        """Apply registered TTS providers to the factory."""
        factory_adapters.update(self._capabilities["tts_providers"])
    
    def apply_asr_providers(self, factory_adapters: Dict[str, Type]):
        """Apply registered ASR providers to the factory."""
        factory_adapters.update(self._capabilities["asr_providers"])
    
    def apply_t2i_providers(self, factory_adapters: Dict[str, Type]):
        """Apply registered T2I providers to the factory."""
        factory_adapters.update(self._capabilities["t2i_providers"])
    
    def apply_llm_tools(self, tool_manager):
        """Apply registered tools to the tool manager."""
        for name, tool_info in self._capabilities["tools"].items():
            tool_manager.register_tool(name, tool_info["func"], **tool_info["kwargs"])
    
    def collect_message_handlers(self) -> tuple[List, List]:
        """Collect all message handlers from plugins."""
        return (
            self._capabilities["message_handlers"],
            self._capabilities["ui_handlers"],
        )
    
    def wire_user_input(self, emit_user_text, processors):
        """Wire user input processors."""
        processors.extend(self._capabilities["user_input_processors"])
    
    def shutdown_all(self):
        """Shut down all plugins."""
        for plugin in self._plugins.values():
            try:
                plugin.shutdown()
            except Exception as e:
                logger.error(f"Failed to shutdown {plugin.plugin_id}: {e}")
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)
    
    def list_plugins(self) -> List[PluginBase]:
        """List all loaded plugins."""
        return list(self._plugins.values())