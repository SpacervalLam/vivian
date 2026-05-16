"""
工具基类定义 - 工具系统 V2

实现完整的工具接口，包括：
- 工具基类
- build_tool函数
- 工具定义类型
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

from pydantic import BaseModel, Field, ValidationError
from loguru import logger

from .types import (
    Input,
    Output,
    Progress,
    PermissionBehavior,
    PermissionResult,
    ToolProgress,
    ToolProgressData,
    ToolResult,
    ToolUseContext,
    ValidationResult,
    SearchOrReadResult,
    InterruptBehavior,
)


T = TypeVar("T")
InputSchema = TypeVar("InputSchema", bound=BaseModel)
OutputSchema = TypeVar("OutputSchema")
ProgressSchema = TypeVar("ProgressSchema", bound=ToolProgressData)


class Tool(
    ABC,
    Generic[InputSchema, OutputSchema, ProgressSchema],
):
    """
    工具基类

    完整的工具接口，包含所有必要的方法和属性。
    参考 ClaudeCode 的 Tool 接口设计。
    """

    name: str
    description: str
    aliases: List[str] = field(default_factory=list)
    search_hint: str = ""
    input_schema: Type[BaseModel]
    output_schema: Optional[Type[BaseModel]] = None
    max_result_size_chars: int = 100_000
    strict: bool = False

    def __init__(self):
        self._progress_callbacks: List[Callable[[ToolProgress], None]] = []

    @abstractmethod
    async def call(
        self,
        args: InputSchema,
        context: ToolUseContext,
        can_use_tool: Callable,
        parent_message: Optional[Any] = None,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult[OutputSchema]:
        """
        执行工具

        Args:
            args: 工具输入参数
            context: 工具使用上下文
            can_use_tool: 权限检查函数
            parent_message: 父消息
            on_progress: 进度回调

        Returns:
            工具执行结果
        """
        pass

    @abstractmethod
    async def get_description(
        self,
        input_data: Optional[InputSchema] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """获取工具描述"""
        pass

    @abstractmethod
    async def get_prompt(self, options: Optional[Dict[str, Any]] = None) -> str:
        """获取工具提示词"""
        pass

    def is_enabled(self) -> bool:
        """工具是否启用"""
        return True

    def is_concurrency_safe(self, input_data: InputSchema) -> bool:
        """是否并发安全"""
        return False

    def is_read_only(self, input_data: InputSchema) -> bool:
        """是否只读操作"""
        return False

    def is_destructive(self, input_data: InputSchema) -> bool:
        """是否破坏性操作"""
        return False

    def interrupt_behavior(self) -> InterruptBehavior:
        """中断行为"""
        return InterruptBehavior.BLOCK

    def is_search_or_read_command(self, input_data: InputSchema) -> SearchOrReadResult:
        """是否为搜索或读取命令"""
        return SearchOrReadResult()

    def is_open_world(self, input_data: InputSchema) -> bool:
        """是否开放世界操作（如网络请求）"""
        return False

    def requires_user_interaction(self) -> bool:
        """是否需要用户交互"""
        return False

    @property
    def is_mcp(self) -> bool:
        """是否为MCP工具"""
        return False

    @property
    def is_lsp(self) -> bool:
        """是否为LSP工具"""
        return False

    @property
    def should_defer(self) -> bool:
        """是否延迟加载"""
        return False

    @property
    def always_load(self) -> bool:
        """是否始终加载"""
        return False

    async def validate_input(
        self,
        input_data: Dict[str, Any],
        context: ToolUseContext,
    ) -> ValidationResult:
        """
        验证输入

        在权限检查之前调用，用于验证输入参数的有效性。
        """
        try:
            if hasattr(self, "input_schema") and self.input_schema:
                validated = self.input_schema(**input_data)
                return ValidationResult.success()
        except ValidationError as e:
            errors = e.errors()
            messages = [f"{err['loc'][0]}: {err['msg']}" for err in errors]
            return ValidationResult.failure("; ".join(messages), error_code=1)
        except Exception as e:
            return ValidationResult.failure(str(e), error_code=1)
        return ValidationResult.success()

    async def check_permissions(
        self,
        input_data: InputSchema,
        context: ToolUseContext,
    ) -> PermissionResult:
        """
        检查权限

        在validate_input之后调用，用于检查用户权限。
        """
        return PermissionResult.allow(
            updated_input=input_data.model_dump() if isinstance(input_data, BaseModel) else input_data
        )

    def get_path(self, input_data: InputSchema) -> Optional[str]:
        """获取工具操作的路径（如果有）"""
        return None

    def user_facing_name(self, input_data: Optional[InputSchema] = None) -> str:
        """用户可见的工具名称"""
        return self.name

    def get_tool_use_summary(self, input_data: Optional[InputSchema] = None) -> Optional[str]:
        """获取工具使用摘要"""
        return None

    def get_activity_description(self, input_data: Optional[InputSchema] = None) -> Optional[str]:
        """获取活动描述（用于spinner显示）"""
        return f"Executing {self.name}"

    def to_auto_classifier_input(self, input_data: InputSchema) -> Any:
        """转换为自动分类器输入"""
        return ""

    def map_tool_result_to_tool_result_block_param(
        self,
        content: OutputSchema,
        tool_use_id: str,
    ) -> Dict[str, Any]:
        """
        将工具结果映射为API格式

        用于将工具输出转换为LLM API可接受的格式。
        """
        if isinstance(content, str):
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            }
        elif isinstance(content, BaseModel):
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content.model_dump(),
            }
        elif isinstance(content, dict):
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            }
        else:
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": str(content),
            }

    def backfill_observable_input(self, input_data: Dict[str, Any]) -> None:
        """
        回填可观察输入

        在观察者看到输入之前调用，用于添加遗留/派生字段。
        """
        pass

    async def prepare_permission_matcher(
        self,
        input_data: InputSchema,
    ) -> Callable[[str], bool]:
        """
        准备权限匹配器

        用于hook的if条件匹配。
        """
        return lambda pattern: pattern == self.name or pattern in self.aliases

    def get_json_schema(self) -> Dict[str, Any]:
        """获取输入的JSON Schema"""
        if hasattr(self, "input_schema") and self.input_schema:
            return self.input_schema.model_json_schema()
        return {"type": "object", "properties": {}}

    def get_output_json_schema(self) -> Optional[Dict[str, Any]]:
        """获取输出的JSON Schema"""
        if self.output_schema:
            return self.output_schema.model_json_schema()
        return None

    def to_definition(self) -> Dict[str, Any]:
        """转换为工具定义"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_json_schema(),
            "output_schema": self.get_output_json_schema(),
            "aliases": self.aliases,
            "search_hint": self.search_hint,
            "is_read_only": self.is_read_only.__code__ != Tool.is_read_only.__code__,
            "is_destructive": self.is_destructive.__code__ != Tool.is_destructive.__code__,
            "is_mcp": self.is_mcp,
        }

    def _emit_progress(self, progress: ToolProgress) -> None:
        """发送进度更新"""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")


def tool_matches_name(tool: Union[Tool, Dict[str, Any]], name: str) -> bool:
    """
    检查工具名称是否匹配

    Args:
        tool: 工具实例或工具定义字典
        name: 要匹配的名称

    Returns:
        是否匹配
    """
    if isinstance(tool, dict):
        tool_name = tool.get("name", "")
        aliases = tool.get("aliases", [])
    else:
        tool_name = tool.name
        aliases = tool.aliases

    return tool_name == name or name in aliases


def find_tool_by_name(tools: List[Tool], name: str) -> Optional[Tool]:
    """
    根据名称查找工具

    Args:
        tools: 工具列表
        name: 工具名称

    Returns:
        找到的工具，如果未找到则返回None
    """
    for tool in tools:
        if tool_matches_name(tool, name):
            return tool
    return None


class ToolDef(Generic[InputSchema, OutputSchema, ProgressSchema]):
    """
    工具定义类

    用于定义工具的部分实现，build_tool会填充默认值。
    """

    pass


TOOL_DEFAULTS = {
    "is_enabled": lambda: True,
    "is_concurrency_safe": lambda input_data: False,
    "is_read_only": lambda input_data: False,
    "is_destructive": lambda input_data: False,
    "check_permissions": lambda input_data, context: PermissionResult.allow(),
    "to_auto_classifier_input": lambda input_data: "",
    "user_facing_name": lambda input_data=None: "",
    "interrupt_behavior": lambda: InterruptBehavior.BLOCK,
}


def build_tool(
    name: str,
    description: str,
    input_schema: Type[BaseModel],
    call: Callable,
    output_schema: Optional[Type[BaseModel]] = None,
    aliases: Optional[List[str]] = None,
    search_hint: str = "",
    max_result_size_chars: int = 100_000,
    strict: bool = False,
    is_enabled: Optional[Callable[[], bool]] = None,
    is_concurrency_safe: Optional[Callable[[Any], bool]] = None,
    is_read_only: Optional[Callable[[Any], bool]] = None,
    is_destructive: Optional[Callable[[Any], bool]] = None,
    check_permissions: Optional[Callable[[Any, ToolUseContext], PermissionResult]] = None,
    validate_input: Optional[Callable[[Dict[str, Any], ToolUseContext], ValidationResult]] = None,
    get_prompt: Optional[Callable[[Optional[Dict[str, Any]]], str]] = None,
    user_facing_name: Optional[Callable[[Optional[Any]], str]] = None,
    get_tool_use_summary: Optional[Callable[[Optional[Any]], Optional[str]]] = None,
    get_activity_description: Optional[Callable[[Optional[Any]], Optional[str]]] = None,
    interrupt_behavior: Optional[Callable[[], InterruptBehavior]] = None,
    is_mcp: bool = False,
    is_lsp: bool = False,
    should_defer: bool = False,
    always_load: bool = False,
    **extra_methods,
) -> Tool:
    """
    构建工具实例

    类似于ClaudeCode的buildTool函数，用于从部分定义创建完整的工具实例。

    Args:
        name: 工具名称
        description: 工具描述
        input_schema: 输入Schema（Pydantic模型）
        call: 工具调用函数
        output_schema: 输出Schema（可选）
        aliases: 别名列表
        search_hint: 搜索提示
        max_result_size_chars: 最大结果字符数
        strict: 是否严格模式
        is_enabled: 启用检查函数
        is_concurrency_safe: 并发安全检查函数
        is_read_only: 只读检查函数
        is_destructive: 破坏性检查函数
        check_permissions: 权限检查函数
        validate_input: 输入验证函数
        get_prompt: 获取提示词函数
        user_facing_name: 用户可见名称函数
        get_tool_use_summary: 获取摘要函数
        get_activity_description: 获取活动描述函数
        interrupt_behavior: 中断行为函数
        is_mcp: 是否MCP工具
        is_lsp: 是否LSP工具
        should_defer: 是否延迟加载
        always_load: 是否始终加载
        **extra_methods: 额外的方法

    Returns:
        完整的工具实例
    """

    class BuiltTool(Tool):
        def __init__(self):
            self._is_mcp = is_mcp
            self._is_lsp = is_lsp
            self._should_defer = should_defer
            self._always_load = always_load

        async def call(
            self,
            args,
            context: ToolUseContext,
            can_use_tool: Callable = None,
            parent_message: Any = None,
            on_progress: Callable = None,
        ) -> ToolResult:
            if asyncio.iscoroutinefunction(call):
                result = await call(args, context)
            else:
                result = call(args, context)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(data=result)

        async def get_description(
            self,
            input_data: Optional[BaseModel] = None,
            options: Optional[Dict[str, Any]] = None,
        ) -> str:
            return description

        async def get_prompt(self, options: Optional[Dict[str, Any]] = None) -> str:
            if get_prompt:
                if asyncio.iscoroutinefunction(get_prompt):
                    return await get_prompt(options)
                return get_prompt(options)
            return f"Use {name} tool. {description}"

        @property
        def is_mcp(self):
            return self._is_mcp

        @property
        def is_lsp(self):
            return self._is_lsp

        @property
        def should_defer(self):
            return self._should_defer

        @property
        def always_load(self):
            return self._always_load

    tool = BuiltTool()
    tool.name = name
    tool.description = description
    tool.input_schema = input_schema
    tool.output_schema = output_schema
    tool.aliases = aliases or []
    tool.search_hint = search_hint
    tool.max_result_size_chars = max_result_size_chars
    tool.strict = strict

    if is_enabled:
        tool.is_enabled = is_enabled
    if is_concurrency_safe:
        tool.is_concurrency_safe = is_concurrency_safe
    if is_read_only:
        tool.is_read_only = is_read_only
    if is_destructive:
        tool.is_destructive = is_destructive
    if check_permissions:
        async def wrapped_check_permissions(input_data, context):
            if asyncio.iscoroutinefunction(check_permissions):
                return await check_permissions(input_data, context)
            return check_permissions(input_data, context)
        tool.check_permissions = wrapped_check_permissions
    if validate_input:
        async def wrapped_validate_input(input_data, context):
            if asyncio.iscoroutinefunction(validate_input):
                return await validate_input(input_data, context)
            return validate_input(input_data, context)
        tool.validate_input = wrapped_validate_input
    if user_facing_name:
        tool.user_facing_name = user_facing_name
    if get_tool_use_summary:
        tool.get_tool_use_summary = get_tool_use_summary
    if get_activity_description:
        tool.get_activity_description = get_activity_description
    if interrupt_behavior:
        tool.interrupt_behavior = interrupt_behavior

    for method_name, method in extra_methods.items():
        setattr(tool, method_name, method)

    return tool


def tool_decorator(
    name: str,
    description: str,
    input_schema: Type[BaseModel],
    output_schema: Optional[Type[BaseModel]] = None,
    **kwargs,
) -> Callable:
    """
    工具装饰器

    用于将函数转换为工具。

    Usage:
        @tool_decorator(
            name="calculate",
            description="计算器工具",
            input_schema=CalculateInput,
        )
        async def calculate(input_data: CalculateInput, context: ToolUseContext) -> str:
            return str(eval(input_data.expression))
    """

    def decorator(func: Callable) -> Tool:
        return build_tool(
            name=name,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            call=func,
            **kwargs,
        )

    return decorator
