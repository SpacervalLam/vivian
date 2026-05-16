"""
工具执行管理器 - 工具系统 V2

整合所有工具系统组件，提供统一的工具执行接口。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from pydantic import BaseModel, ValidationError
from loguru import logger

from .tool import Tool, build_tool, find_tool_by_name
from .types import (
    ToolResult,
    ToolUseContext,
    ValidationResult,
    PermissionResult,
    PermissionBehavior,
    ToolProgressData,
    ToolExecutionRecord,
)
from .permission import PermissionContext, PermissionChecker, get_permission_manager
from .progress import ProgressTracker, ProgressContext, get_progress_tracker
from .pool import ToolPool, assemble_tool_pool, get_pool_manager
from .registry import ToolRegistry, get_registry, register_tool
from .search import ToolSearchEngine, DeferredToolLoader
from .mcp import MCPManager, get_mcp_manager


@dataclass
class ToolExecutionConfig:
    """工具执行配置"""
    max_iterations: int = 10
    timeout_seconds: float = 300.0
    enable_progress: bool = True
    enable_validation: bool = True
    enable_permissions: bool = True
    strict_mode: bool = False


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    result: Any
    tool_name: str
    tool_use_id: str
    error: Optional[str] = None
    duration_ms: float = 0.0
    records: List[ToolExecutionRecord] = field(default_factory=list)


class ToolExecutor:
    """
    工具执行器

    负责工具的验证、权限检查、执行和结果处理。
    """

    def __init__(
        self,
        config: Optional[ToolExecutionConfig] = None,
    ):
        self.config = config or ToolExecutionConfig()
        self._registry = get_registry()
        self._progress_tracker = get_progress_tracker()
        self._permission_manager = get_permission_manager()
        self._mcp_manager = get_mcp_manager()
        self._deferred_loader = DeferredToolLoader()
        self._execution_history: List[ToolExecutionRecord] = []

    async def execute(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        context: Optional[ToolUseContext] = None,
        permission_context: Optional[PermissionContext] = None,
        on_progress: Optional[Callable[[ToolProgressData], None]] = None,
    ) -> ExecutionResult:
        """
        执行工具

        Args:
            tool_name: 工具名称
            input_data: 输入数据
            context: 工具使用上下文
            permission_context: 权限上下文
            on_progress: 进度回调

        Returns:
            执行结果
        """
        tool_use_id = str(uuid.uuid4())
        start_time = time.time()

        record = ToolExecutionRecord(
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            input_data=input_data,
            start_time=start_time,
        )

        try:
            tool = self._get_tool(tool_name)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found")

            if self.config.enable_validation:
                validation = await tool.validate_input(input_data, context or ToolUseContext())
                if not validation.result:
                    raise ValueError(validation.message)

            if self.config.enable_permissions and permission_context:
                permission = await self._check_permissions(
                    tool, input_data, context, permission_context
                )
                if permission.is_denied():
                    raise PermissionError(permission.message)
                if permission.requires_confirmation():
                    return ExecutionResult(
                        success=False,
                        result=None,
                        tool_name=tool_name,
                        tool_use_id=tool_use_id,
                        error=f"Permission required: {permission.message}",
                    )
                if permission.updated_input:
                    input_data = permission.updated_input

            validated_input = self._validate_input_schema(tool, input_data)

            if self.config.enable_progress:
                progress_ctx = ProgressContext(
                    tracker=self._progress_tracker,
                    tool_use_id=tool_use_id,
                    tool_name=tool_name,
                )
                with progress_ctx:
                    if on_progress:
                        self._progress_tracker.register_callback(
                            lambda e: on_progress(e.data) if e.tool_use_id == tool_use_id else None
                        )

                    result = await tool.call(
                        args=validated_input,
                        context=context or ToolUseContext(),
                        can_use_tool=lambda *args: {"behavior": "allow"},
                        on_progress=on_progress,
                    )
            else:
                result = await tool.call(
                    args=validated_input,
                    context=context or ToolUseContext(),
                    can_use_tool=lambda *args: {"behavior": "allow"},
                )

            end_time = time.time()
            record.end_time = end_time
            record.duration_ms = (end_time - start_time) * 1000
            record.output_data = result.data
            record.success = True
            self._execution_history.append(record)

            return ExecutionResult(
                success=True,
                result=result.data,
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                duration_ms=record.duration_ms,
            )

        except Exception as e:
            end_time = time.time()
            record.end_time = end_time
            record.duration_ms = (end_time - start_time) * 1000
            record.error = str(e)
            record.success = False
            self._execution_history.append(record)

            logger.error(f"Tool execution failed: {e}")
            return ExecutionResult(
                success=False,
                result=None,
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                error=str(e),
                duration_ms=record.duration_ms,
            )

    async def execute_multi(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Optional[ToolUseContext] = None,
        permission_context: Optional[PermissionContext] = None,
        on_progress: Optional[Callable[[str, ToolProgressData], None]] = None,
    ) -> List[ExecutionResult]:
        """
        执行多个工具调用

        Args:
            tool_calls: 工具调用列表，每个元素包含 tool_name 和 arguments
            context: 工具使用上下文
            permission_context: 权限上下文
            on_progress: 进度回调

        Returns:
            执行结果列表
        """
        results = []
        for call in tool_calls:
            tool_name = call.get("tool_name") or call.get("name")
            arguments = call.get("arguments") or call.get("args", {})

            result = await self.execute(
                tool_name=tool_name,
                input_data=arguments,
                context=context,
                permission_context=permission_context,
                on_progress=lambda p, tn=tool_name: on_progress(tn, p) if on_progress else None,
            )
            results.append(result)

        return results

    async def execute_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Optional[ToolUseContext] = None,
        permission_context: Optional[PermissionContext] = None,
        on_progress: Optional[Callable[[str, ToolProgressData], None]] = None,
    ) -> List[ExecutionResult]:
        """
        并行执行多个工具调用

        Args:
            tool_calls: 工具调用列表
            context: 工具使用上下文
            permission_context: 权限上下文
            on_progress: 进度回调

        Returns:
            执行结果列表
        """
        tasks = []
        for call in tool_calls:
            tool_name = call.get("tool_name") or call.get("name")
            arguments = call.get("arguments") or call.get("args", {})

            task = self.execute(
                tool_name=tool_name,
                input_data=arguments,
                context=context,
                permission_context=permission_context,
                on_progress=lambda p, tn=tool_name: on_progress(tn, p) if on_progress else None,
            )
            tasks.append(task)

        return await asyncio.gather(*tasks)

    def _get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        tool = self._registry.get(name)
        if tool:
            return tool

        mcp_tool = self._mcp_manager.get_tool(name)
        if mcp_tool:
            return mcp_tool

        if self._deferred_loader.is_deferred(name):
            return self._deferred_loader.load(name)

        return None

    async def _check_permissions(
        self,
        tool: Tool,
        input_data: Dict[str, Any],
        context: Optional[ToolUseContext],
        permission_context: PermissionContext,
    ) -> PermissionResult:
        """检查权限"""
        checker = PermissionChecker(permission_context)

        general_permission = await checker.check_tool_permission(
            tool_name=tool.name,
            input_data=input_data,
            tool_info={"mcp_info": getattr(tool, "mcp_info", None)},
        )

        if general_permission.is_denied():
            return general_permission

        tool_permission = await tool.check_permissions(input_data, context or ToolUseContext())

        return tool_permission

    def _validate_input_schema(
        self,
        tool: Tool,
        input_data: Dict[str, Any],
    ) -> BaseModel:
        """验证输入Schema"""
        if hasattr(tool, "input_schema") and tool.input_schema:
            return tool.input_schema(**input_data)
        return input_data

    def get_execution_history(self) -> List[ToolExecutionRecord]:
        """获取执行历史"""
        return self._execution_history.copy()

    def clear_history(self) -> None:
        """清除执行历史"""
        self._execution_history.clear()


class ToolSystem:
    """
    工具系统

    整合所有工具组件的统一入口。
    """

    def __init__(self, config: Optional[ToolExecutionConfig] = None):
        self.config = config or ToolExecutionConfig()
        self.executor = ToolExecutor(self.config)
        self.registry = get_registry()
        self.pool_manager = get_pool_manager()
        self.permission_manager = get_permission_manager()
        self.progress_tracker = get_progress_tracker()
        self.mcp_manager = get_mcp_manager()
        self.search_engine: Optional[ToolSearchEngine] = None

    def register_tool(self, tool: Tool, category: Optional[str] = None) -> None:
        """注册工具"""
        self.registry.register(tool, category)
        self._invalidate_search_engine()

    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        result = self.registry.unregister(name)
        if result:
            self._invalidate_search_engine()
        return result

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.registry.get(name)

    def list_tools(self) -> List[Tool]:
        """列出所有工具"""
        return self.registry.list_all()

    def search_tools(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """搜索工具"""
        if not self.search_engine:
            self.search_engine = ToolSearchEngine(self.registry.list_all())

        results = self.search_engine.search(query, max_results)
        return [
            {
                "name": r.tool.name,
                "description": r.tool.description,
                "score": r.score,
                "match_type": r.match_type.value,
            }
            for r in results
        ]

    async def execute_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        context: Optional[ToolUseContext] = None,
        permission_context: Optional[PermissionContext] = None,
        on_progress: Optional[Callable[[ToolProgressData], None]] = None,
    ) -> ExecutionResult:
        """执行工具"""
        return await self.executor.execute(
            tool_name=tool_name,
            input_data=input_data,
            context=context,
            permission_context=permission_context,
            on_progress=on_progress,
        )

    def get_tool_pool(
        self,
        permission_context: Optional[PermissionContext] = None,
    ) -> ToolPool:
        """获取工具池"""
        return self.pool_manager.get_pool(permission_context=permission_context)

    def create_permission_context(
        self,
        mode: str = "default",
        working_directories: Optional[List[str]] = None,
        allow_tools: Optional[List[str]] = None,
        deny_tools: Optional[List[str]] = None,
    ) -> PermissionContext:
        """创建权限上下文"""
        from .permission import PermissionMode

        mode_enum = PermissionMode(mode)
        return self.permission_manager.create_context(
            mode=mode_enum,
            working_directories=working_directories,
            allow_tools=allow_tools,
            deny_tools=deny_tools,
        )

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """获取OpenAI格式的工具定义"""
        return self.registry.get_definitions()

    def get_anthropic_tools(self) -> List[Dict[str, Any]]:
        """获取Anthropic格式的工具定义"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.get_json_schema(),
            }
            for t in self.registry.list_all()
        ]

    def _invalidate_search_engine(self) -> None:
        """使搜索引擎缓存失效"""
        self.search_engine = None


_tool_system: Optional[ToolSystem] = None


def get_tool_system() -> ToolSystem:
    """获取工具系统单例"""
    global _tool_system
    if _tool_system is None:
        _tool_system = ToolSystem()
    return _tool_system


def init_tool_system(config: Optional[ToolExecutionConfig] = None) -> ToolSystem:
    """初始化工具系统"""
    global _tool_system
    _tool_system = ToolSystem(config)
    return _tool_system
