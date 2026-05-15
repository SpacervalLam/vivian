"""
Minimal plugin contract for lifecycle and metadata only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin_host_context import PluginHostContext
    from .register import PluginCapabilityRegistry


class PluginBase(ABC):
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique stable id, e.g. ``com.example.myplugin``."""

    @property
    def plugin_version(self) -> str:
        return "0.1.0"

    @property
    def plugin_name(self) -> str:
        pid = self.plugin_id
        tail = pid.rpartition(".")[-1]
        if tail:
            return tail.replace("_", " ").strip() or pid
        return pid

    @property
    def plugin_description(self) -> str:
        return ""

    @property
    def plugin_author(self) -> str:
        return ""

    @property
    def enabled(self) -> bool:
        return True

    @property
    def priority(self) -> int:
        return 100

    @abstractmethod
    def initialize(
        self,
        register: PluginCapabilityRegistry,
        plugin_root: Path,
        host: PluginHostContext,
    ) -> None:
        pass

    def shutdown(self) -> None:
        return None