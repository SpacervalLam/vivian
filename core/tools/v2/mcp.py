"""
MCP协议支持框架 - 工具系统 V2

实现Model Context Protocol (MCP)的支持，包括：
- MCP服务器连接
- MCP工具基类
- MCP资源管理
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field
from loguru import logger

from .tool import Tool, build_tool
from .types import ToolResult, ToolUseContext, PermissionResult, PermissionBehavior


class MCPConnectionState(Enum):
    """MCP连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPServerInfo:
    """MCP服务器信息"""
    name: str
    description: str = ""
    version: str = "1.0.0"
    tools: List[str] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    capabilities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPToolInfo:
    """MCP工具信息"""
    server_name: str
    tool_name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPConnection:
    """
    MCP连接

    管理与MCP服务器的连接。
    """

    server_name: str
    server_info: Optional[MCPServerInfo] = None
    state: MCPConnectionState = MCPConnectionState.DISCONNECTED
    error: Optional[str] = None

    _client: Optional[Any] = None
    _tools: Dict[str, MCPToolInfo] = field(default_factory=dict)
    _resources: Dict[str, Any] = field(default_factory=dict)

    async def connect(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        连接到MCP服务器

        Args:
            config: 连接配置

        Returns:
            是否连接成功
        """
        self.state = MCPConnectionState.CONNECTING
        try:
            await self._do_connect(config)
            self.state = MCPConnectionState.CONNECTED
            await self._load_tools()
            await self._load_resources()
            logger.info(f"MCP server '{self.server_name}' connected")
            return True
        except Exception as e:
            self.state = MCPConnectionState.ERROR
            self.error = str(e)
            logger.error(f"MCP connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        try:
            if self._client:
                await self._do_disconnect()
            self.state = MCPConnectionState.DISCONNECTED
            logger.info(f"MCP server '{self.server_name}' disconnected")
        except Exception as e:
            logger.error(f"MCP disconnect error: {e}")

    async def _do_connect(self, config: Optional[Dict[str, Any]] = None) -> None:
        """实际连接逻辑（子类实现）"""
        pass

    async def _do_disconnect(self) -> None:
        """实际断开逻辑（子类实现）"""
        pass

    async def _load_tools(self) -> None:
        """加载工具列表"""
        pass

    async def _load_resources(self) -> None:
        """加载资源列表"""
        pass

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """
        调用MCP工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if self.state != MCPConnectionState.CONNECTED:
            return ToolResult(data={"error": f"Server '{self.server_name}' not connected"})

        try:
            result = await self._do_call_tool(tool_name, arguments)
            return ToolResult(data=result)
        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            return ToolResult(data={"error": str(e)})

    async def _do_call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        """实际工具调用逻辑（子类实现）"""
        raise NotImplementedError

    async def read_resource(self, uri: str) -> Any:
        """读取MCP资源"""
        if self.state != MCPConnectionState.CONNECTED:
            raise RuntimeError(f"Server '{self.server_name}' not connected")

        return await self._do_read_resource(uri)

    async def _do_read_resource(self, uri: str) -> Any:
        """实际资源读取逻辑（子类实现）"""
        raise NotImplementedError

    def get_tools(self) -> List[MCPToolInfo]:
        """获取工具列表"""
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> Optional[MCPToolInfo]:
        """获取工具信息"""
        return self._tools.get(tool_name)

    def get_resources(self) -> Dict[str, Any]:
        """获取资源列表"""
        return self._resources.copy()


class MCPToolBase(Tool):
    """
    MCP工具基类

    用于创建MCP工具的基类。
    """

    server_name: str = ""
    tool_name: str = ""
    _connection: Optional[MCPConnection] = None

    @property
    def is_mcp(self) -> bool:
        return True

    @property
    def mcp_info(self) -> Dict[str, str]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
        }

    def set_connection(self, connection: MCPConnection) -> None:
        """设置MCP连接"""
        self._connection = connection

    async def call(
        self,
        args,
        context: ToolUseContext,
        can_use_tool: Callable = None,
        parent_message: Any = None,
        on_progress: Callable = None,
    ) -> ToolResult:
        """调用MCP工具"""
        if not self._connection:
            return ToolResult(data={"error": "MCP connection not set"})

        arguments = args.model_dump() if hasattr(args, "model_dump") else args
        return await self._connection.call_tool(self.tool_name, arguments)

    async def check_permissions(
        self,
        input_data,
        context: ToolUseContext,
    ) -> PermissionResult:
        """检查权限"""
        return PermissionResult.passthrough(
            message=f"MCP tool '{self.tool_name}' from server '{self.server_name}' requires permission"
        )


def create_mcp_tool(
    server_name: str,
    tool_name: str,
    description: str,
    input_schema: Dict[str, Any],
    connection: Optional[MCPConnection] = None,
) -> Tool:
    """
    创建MCP工具

    Args:
        server_name: 服务器名称
        tool_name: 工具名称
        description: 工具描述
        input_schema: 输入Schema
        connection: MCP连接

    Returns:
        MCP工具实例
    """
    from pydantic import create_model

    fields = {}
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    for prop_name, prop_info in properties.items():
        prop_type = prop_info.get("type", "string")
        python_type = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }.get(prop_type, str)

        if prop_name in required:
            fields[prop_name] = (python_type, Field(..., description=prop_info.get("description", "")))
        else:
            fields[prop_name] = (Optional[python_type], Field(None, description=prop_info.get("description", "")))

    InputModel = create_model(f"{tool_name}Input", **fields)

    class DynamicMCPTool(MCPToolBase):
        pass

    tool = DynamicMCPTool()
    tool.name = f"mcp__{server_name}__{tool_name}"
    tool.server_name = server_name
    tool.tool_name = tool_name
    tool.description = description
    tool.input_schema = InputModel
    tool._connection = connection

    return tool


class MCPManager:
    """
    MCP管理器

    管理所有MCP连接和工具。
    """

    def __init__(self):
        self._connections: Dict[str, MCPConnection] = {}
        self._tools: Dict[str, Tool] = {}

    async def connect_server(
        self,
        server_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        连接MCP服务器

        Args:
            server_name: 服务器名称
            config: 连接配置

        Returns:
            是否连接成功
        """
        if server_name in self._connections:
            connection = self._connections[server_name]
            if connection.state == MCPConnectionState.CONNECTED:
                return True

        connection = MCPConnection(server_name=server_name)
        success = await connection.connect(config)

        if success:
            self._connections[server_name] = connection
            await self._register_tools(connection)

        return success

    async def disconnect_server(self, server_name: str) -> None:
        """断开MCP服务器"""
        if server_name in self._connections:
            await self._connections[server_name].disconnect()
            self._unregister_tools(server_name)
            del self._connections[server_name]

    async def _register_tools(self, connection: MCPConnection) -> None:
        """注册MCP工具"""
        for tool_info in connection.get_tools():
            tool = create_mcp_tool(
                server_name=connection.server_name,
                tool_name=tool_info.tool_name,
                description=tool_info.description,
                input_schema=tool_info.input_schema,
                connection=connection,
            )
            self._tools[tool.name] = tool
            logger.debug(f"MCP tool '{tool.name}' registered")

    def _unregister_tools(self, server_name: str) -> None:
        """注销MCP工具"""
        prefix = f"mcp__{server_name}__"
        to_remove = [name for name in self._tools if name.startswith(prefix)]
        for name in to_remove:
            del self._tools[name]

    def get_connection(self, server_name: str) -> Optional[MCPConnection]:
        """获取MCP连接"""
        return self._connections.get(server_name)

    def get_connections(self) -> Dict[str, MCPConnection]:
        """获取所有连接"""
        return self._connections.copy()

    def get_tools(self) -> List[Tool]:
        """获取所有MCP工具"""
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """获取MCP工具"""
        return self._tools.get(tool_name)

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        """调用MCP工具"""
        if tool_name not in self._tools:
            return ToolResult(data={"error": f"MCP tool '{tool_name}' not found"})

        tool = self._tools[tool_name]
        if isinstance(tool, MCPToolBase) and tool._connection:
            return await tool._connection.call_tool(tool.tool_name, arguments)

        return ToolResult(data={"error": "Invalid MCP tool"})

    async def disconnect_all(self) -> None:
        """断开所有连接"""
        for server_name in list(self._connections.keys()):
            await self.disconnect_server(server_name)


_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """获取MCP管理器单例"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager
