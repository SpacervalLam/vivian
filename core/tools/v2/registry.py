"""
工具注册表 - 工具系统 V2

实现工具的注册和管理功能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, Union

from loguru import logger

from .tool import Tool, tool_matches_name, find_tool_by_name
from .types import ToolDefinition


@dataclass
class ToolRegistry:
    """
    工具注册表

    管理所有已注册的工具。
    """

    _tools: Dict[str, Tool] = field(default_factory=dict)
    _aliases: Dict[str, str] = field(default_factory=dict)
    _categories: Dict[str, List[str]] = field(default_factory=dict)

    def register(self, tool: Tool, category: Optional[str] = None) -> None:
        """
        注册工具

        Args:
            tool: 工具实例
            category: 工具类别
        """
        self._tools[tool.name] = tool

        for alias in tool.aliases:
            self._aliases[alias] = tool.name

        if category:
            if category not in self._categories:
                self._categories[category] = []
            self._categories[category].append(tool.name)

        logger.debug(f"Tool '{tool.name}' registered" + (f" in category '{category}'" if category else ""))

    def unregister(self, name: str) -> bool:
        """
        注销工具

        Args:
            name: 工具名称

        Returns:
            是否成功注销
        """
        if name in self._tools:
            tool = self._tools[name]
            for alias in tool.aliases:
                self._aliases.pop(alias, None)
            del self._tools[name]
            logger.debug(f"Tool '{name}' unregistered")
            return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """
        获取工具

        Args:
            name: 工具名称或别名

        Returns:
            工具实例，如果不存在则返回None
        """
        if name in self._tools:
            return self._tools[name]

        if name in self._aliases:
            return self._tools.get(self._aliases[name])

        return None

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools or name in self._aliases

    def list_all(self) -> List[Tool]:
        """获取所有工具列表"""
        return list(self._tools.values())

    def list_names(self) -> List[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    def list_by_category(self, category: str) -> List[Tool]:
        """按类别获取工具"""
        names = self._categories.get(category, [])
        return [self._tools[name] for name in names if name in self._tools]

    def get_categories(self) -> List[str]:
        """获取所有类别"""
        return list(self._categories.keys())

    def search(self, query: str) -> List[Tool]:
        """
        搜索工具

        Args:
            query: 搜索查询

        Returns:
            匹配的工具列表
        """
        query_lower = query.lower()
        results = []

        for tool in self._tools.values():
            if query_lower in tool.name.lower():
                results.append(tool)
                continue

            if query_lower in tool.description.lower():
                results.append(tool)
                continue

            if query_lower in tool.search_hint.lower():
                results.append(tool)
                continue

            for alias in tool.aliases:
                if query_lower in alias.lower():
                    results.append(tool)
                    break

        return results

    def get_definitions(self) -> List[ToolDefinition]:
        """获取所有工具定义"""
        return [
            ToolDefinition(**tool.to_definition())
            for tool in self._tools.values()
        ]

    def clear(self) -> None:
        """清除所有工具"""
        self._tools.clear()
        self._aliases.clear()
        self._categories.clear()


_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool: Tool, category: Optional[str] = None) -> None:
    """注册工具"""
    get_registry().register(tool, category)


def get_tool(name: str) -> Optional[Tool]:
    """获取工具"""
    return get_registry().get(name)


def list_tools() -> List[Tool]:
    """获取所有工具"""
    return get_registry().list_all()


def unregister_tool(name: str) -> bool:
    """注销工具"""
    return get_registry().unregister(name)
