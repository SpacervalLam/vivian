"""
工具池管理器 - 工具系统 V2

实现工具池的组装和管理功能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from loguru import logger

from .tool import Tool, tool_matches_name, find_tool_by_name
from .permission import PermissionContext, PermissionChecker, get_permission_manager
from .registry import ToolRegistry, get_registry
from .types import ToolDefinition


@dataclass
class ToolPool:
    """
    工具池

    管理一组可用工具，支持权限过滤和动态加载。
    """

    tools: List[Tool] = field(default_factory=list)
    _deferred_tools: Set[str] = field(default_factory=set)
    _always_load_tools: Set[str] = field(default_factory=set)

    def __iter__(self):
        return iter(self.tools)

    def __len__(self) -> int:
        return len(self.tools)

    def __getitem__(self, index: int) -> Tool:
        return self.tools[index]

    def add(self, tool: Tool) -> None:
        """添加工具"""
        if tool.should_defer:
            self._deferred_tools.add(tool.name)
        if tool.always_load:
            self._always_load_tools.add(tool.name)
        self.tools.append(tool)

    def add_all(self, tools: List[Tool]) -> None:
        """添加多个工具"""
        for tool in tools:
            self.add(tool)

    def remove(self, name: str) -> bool:
        """移除工具"""
        for i, tool in enumerate(self.tools):
            if tool.name == name:
                self.tools.pop(i)
                self._deferred_tools.discard(name)
                self._always_load_tools.discard(name)
                return True
        return False

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return find_tool_by_name(self.tools, name)

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return any(tool_matches_name(t, name) for t in self.tools)

    def filter(self, predicate: Callable[[Tool], bool]) -> "ToolPool":
        """过滤工具"""
        return ToolPool(tools=[t for t in self.tools if predicate(t)])

    def filter_by_permission(
        self,
        permission_context: PermissionContext,
    ) -> "ToolPool":
        """按权限过滤工具"""
        checker = PermissionChecker(permission_context)

        def is_allowed(tool: Tool) -> bool:
            result = checker._find_deny_rule(tool.name)
            return result is None

        return self.filter(is_allowed)

    def filter_enabled(self) -> "ToolPool":
        """过滤启用的工具"""
        return self.filter(lambda t: t.is_enabled())

    def get_deferred_tools(self) -> List[Tool]:
        """获取延迟加载的工具"""
        return [t for t in self.tools if t.should_defer]

    def get_always_load_tools(self) -> List[Tool]:
        """获取始终加载的工具"""
        return [t for t in self.tools if t.always_load]

    def get_tool_names(self) -> List[str]:
        """获取工具名称列表"""
        return [t.name for t in self.tools]

    def get_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义列表"""
        return [t.to_definition() for t in self.tools]

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取OpenAI格式的工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.get_json_schema(),
                }
            }
            for t in self.tools
        ]

    def get_anthropic_tools(self) -> List[Dict[str, Any]]:
        """获取Anthropic格式的工具定义"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.get_json_schema(),
            }
            for t in self.tools
        ]

    def sort_by_name(self) -> "ToolPool":
        """按名称排序"""
        return ToolPool(tools=sorted(self.tools, key=lambda t: t.name))

    def deduplicate(self) -> "ToolPool":
        """去重"""
        seen = set()
        unique = []
        for tool in self.tools:
            if tool.name not in seen:
                seen.add(tool.name)
                unique.append(tool)
        return ToolPool(tools=unique)


def assemble_tool_pool(
    built_in_tools: List[Tool],
    mcp_tools: Optional[List[Tool]] = None,
    permission_context: Optional[PermissionContext] = None,
) -> ToolPool:
    """
    组装工具池

    合并内置工具和MCP工具，并按权限过滤。

    Args:
        built_in_tools: 内置工具列表
        mcp_tools: MCP工具列表
        permission_context: 权限上下文

    Returns:
        组装好的工具池
    """
    pool = ToolPool()
    pool.add_all(built_in_tools)

    if mcp_tools:
        pool.add_all(mcp_tools)

    pool = pool.sort_by_name().deduplicate()

    if permission_context:
        pool = pool.filter_by_permission(permission_context)

    pool = pool.filter_enabled()

    return pool


class ToolPoolManager:
    """
    工具池管理器

    管理多个工具池实例。
    """

    def __init__(self):
        self._pools: Dict[str, ToolPool] = {}
        self._default_tools: List[Tool] = []

    def set_default_tools(self, tools: List[Tool]) -> None:
        """设置默认工具"""
        self._default_tools = tools

    def get_pool(
        self,
        pool_id: str = "default",
        permission_context: Optional[PermissionContext] = None,
        mcp_tools: Optional[List[Tool]] = None,
    ) -> ToolPool:
        """
        获取工具池

        Args:
            pool_id: 工具池ID
            permission_context: 权限上下文
            mcp_tools: MCP工具列表

        Returns:
            工具池实例
        """
        if pool_id not in self._pools:
            self._pools[pool_id] = assemble_tool_pool(
                built_in_tools=self._default_tools,
                mcp_tools=mcp_tools,
                permission_context=permission_context,
            )
        return self._pools[pool_id]

    def refresh_pool(
        self,
        pool_id: str,
        permission_context: Optional[PermissionContext] = None,
        mcp_tools: Optional[List[Tool]] = None,
    ) -> ToolPool:
        """刷新工具池"""
        self._pools[pool_id] = assemble_tool_pool(
            built_in_tools=self._default_tools,
            mcp_tools=mcp_tools,
            permission_context=permission_context,
        )
        return self._pools[pool_id]

    def clear_pool(self, pool_id: str) -> bool:
        """清除工具池"""
        if pool_id in self._pools:
            del self._pools[pool_id]
            return True
        return False

    def clear_all(self) -> None:
        """清除所有工具池"""
        self._pools.clear()


_pool_manager: Optional[ToolPoolManager] = None


def get_pool_manager() -> ToolPoolManager:
    """获取工具池管理器单例"""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ToolPoolManager()
    return _pool_manager
