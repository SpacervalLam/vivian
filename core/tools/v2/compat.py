"""
工具系统兼容性层

提供与原有 ToolManager/BaseTool 接口的向后兼容支持。
原有代码可以继续使用旧接口，同时也可以访问新系统的功能。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints
from loguru import logger

from core.tool_manager import BaseTool as OldBaseTool, ToolManager as OldToolManager
from core.tools.v2 import (
    Tool,
    ToolSystem,
    ToolResult,
    ToolUseContext,
    build_tool,
    register_tool,
    get_tool,
    list_tools,
    ExecutionResult,
)


class V2ToolAdapter(Tool):
    """
    将V1工具适配为V2工具
    
    允许旧的BaseTool实现无缝集成到新的工具系统中。
    """

    def __init__(self, v1_tool: OldBaseTool):
        super().__init__()
        self._v1_tool = v1_tool
        self.name = v1_tool.name
        self.description = v1_tool.description
        self.aliases = []
        self.search_hint = ""

    async def call(
        self,
        args,
        context: ToolUseContext,
        can_use_tool: Callable = None,
        parent_message: Any = None,
        on_progress: Callable = None,
    ) -> ToolResult:
        """调用V1工具"""
        try:
            if isinstance(args, dict):
                result = await self._v1_tool.arun(**args)
            else:
                result = await self._v1_tool.arun(**args.model_dump())
            
            return ToolResult(data=result)
        except Exception as e:
            logger.error(f"V1 tool call failed: {e}")
            return ToolResult(data={"error": str(e)})

    async def get_description(
        self,
        input_data: Optional[Any] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.description

    async def get_prompt(self, options: Optional[Dict[str, Any]] = None) -> str:
        return f"Use {self.name} tool. {self.description}"


class V1ToolAdapter(OldBaseTool):
    """
    将V2工具适配为V1工具
    
    允许新的V2工具在旧代码中使用。
    """

    def __init__(self, v2_tool: Tool):
        self._v2_tool = v2_tool
        self.name = v2_tool.name
        self.description = v2_tool.description
        self.return_direct = False
        self.parameters = {}

        if hasattr(v2_tool, 'input_schema') and v2_tool.input_schema:
            schema = v2_tool.get_json_schema()
            for param_name, param_info in schema.get('properties', {}).items():
                self.parameters[param_name] = {
                    "name": param_name,
                    "type": param_info.get('type', 'string'),
                    "description": param_info.get('description', ''),
                    "required": param_name in schema.get('required', []),
                    "default": None,
                }

    def run(self, **kwargs) -> Any:
        """同步执行工具"""
        return asyncio.run(self.arun(**kwargs))

    async def arun(self, **kwargs) -> Any:
        """异步执行工具"""
        context = ToolUseContext()
        result = await self._v2_tool.call(
            args=kwargs,
            context=context,
            can_use_tool=lambda *args: {"behavior": "allow"},
        )
        return result.data


class CompatibleToolManager(OldToolManager):
    """
    兼容的工具管理器
    
    同时支持V1和V2工具，提供无缝迁移体验。
    """

    def __init__(self, use_v2_backend: bool = False):
        super().__init__()
        self._use_v2_backend = use_v2_backend
        self._v2_system = None
        
        if use_v2_backend:
            self._init_v2_system()

    def _init_v2_system(self):
        """初始化V2工具系统"""
        from core.tools.v2 import get_tool_system, register_builtin_tools
        
        self._v2_system = get_tool_system()
        register_builtin_tools()

    def register_tool(self, tool: OldBaseTool) -> None:
        """注册工具（支持V1和V2）"""
        if isinstance(tool, Tool):
            if self._use_v2_backend and self._v2_system:
                self._v2_system.register_tool(tool)
            super().register_tool(V1ToolAdapter(tool))
        else:
            super().register_tool(tool)
            
            if self._use_v2_backend and self._v2_system:
                v2_adapter = V2ToolAdapter(tool)
                self._v2_system.register_tool(v2_adapter)

    def run_tool(self, name: str, *args, **kwargs) -> Any:
        """执行工具"""
        if self._use_v2_backend and self._v2_system:
            result = asyncio.run(self.arun_tool(name, *args, **kwargs))
            return result
        return super().run_tool(name, *args, **kwargs)

    async def arun_tool(self, name: str, *args, **kwargs) -> Any:
        """异步执行工具"""
        if self._use_v2_backend and self._v2_system:
            result = await self._v2_system.execute_tool(
                tool_name=name,
                input_data=kwargs if kwargs else (args[0] if args else {}),
            )
            return result.result if result.success else {"error": result.error}
        return await super().arun_tool(name, *args, **kwargs)

    def get_v2_tool(self, name: str) -> Optional[Tool]:
        """获取V2工具实例"""
        if self._v2_system:
            return self._v2_system.get_tool(name)
        return None

    def get_v2_system(self) -> Optional[ToolSystem]:
        """获取V2工具系统"""
        return self._v2_system

    def enable_v2_features(self) -> None:
        """启用V2功能"""
        if not self._v2_system:
            self._init_v2_system()
        self._use_v2_backend = True


def migrate_to_v2(tool_manager: OldToolManager) -> ToolSystem:
    """
    将旧工具管理器迁移到V2系统
    
    Args:
        tool_manager: 旧的ToolManager实例
        
    Returns:
        V2工具系统
    """
    v2_system = ToolSystem()
    
    for name, v1_tool in tool_manager.tools.items():
        adapter = V2ToolAdapter(v1_tool)
        v2_system.register_tool(adapter)
    
    return v2_system


def create_compatible_tool(
    name: str,
    description: str,
    func: Callable,
    return_direct: bool = False,
    v2_options: Optional[Dict[str, Any]] = None,
) -> OldBaseTool:
    """
    创建兼容的工具（同时支持V1和V2）
    
    Args:
        name: 工具名称
        description: 工具描述
        func: 工具函数
        return_direct: 是否直接返回
        v2_options: V2选项
        
    Returns:
        兼容的工具实例
    """
    v2_options = v2_options or {}
    
    # 使用闭包变量
    tool_name = name
    tool_description = description
    tool_return_direct = return_direct
    tool_func = func
    
    class DualTool(OldBaseTool):
        name = tool_name
        description = tool_description
        return_direct = tool_return_direct
        
        def run(self, **kwargs) -> Any:
            return tool_func(**kwargs)
        
        async def arun(self, **kwargs) -> Any:
            if asyncio.iscoroutinefunction(tool_func):
                return await tool_func(**kwargs)
            return tool_func(**kwargs)
    
    return DualTool()


def get_compatible_tool_manager(use_v2: bool = True) -> CompatibleToolManager:
    """
    获取兼容的工具管理器
    
    Args:
        use_v2: 是否使用V2后端
        
    Returns:
        兼容的工具管理器
    """
    return CompatibleToolManager(use_v2_backend=use_v2)


# 保持与原有接口的兼容性
ToolManager = CompatibleToolManager
tool = lambda name, description, return_direct=False: lambda func: create_compatible_tool(
    name, description, func, return_direct
)
