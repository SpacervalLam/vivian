"""
Read-only host context snapshot passed to plugins during initialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginHostContext:
    """Read-only snapshot of host environment for plugins."""
    
    project_root: Path
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    app_version: str = "1.0.0"
    
    @property
    def plugin_data_dir(self) -> Path:
        return self.data_dir / "plugins"
    
    @property
    def plugin_cache_dir(self) -> Path:
        return self.cache_dir / "plugins"