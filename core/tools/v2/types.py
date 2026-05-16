"""
核心类型定义 - 工具系统 V2

定义工具系统的所有核心类型，包括：
- 工具结果类型
- 验证结果类型
- 权限结果类型
- 工具上下文类型
- 进度数据类型
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
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

from pydantic import BaseModel, Field


class PermissionBehavior(Enum):
    """权限行为枚举"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    PASSTHROUGH = "passthrough"


class InterruptBehavior(Enum):
    """中断行为枚举"""
    BLOCK = "block"
    CANCEL = "cancel"


@dataclass
class ValidationResult:
    """验证结果"""
    result: bool
    message: str = ""
    error_code: int = 0

    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(result=True)

    @classmethod
    def failure(cls, message: str, error_code: int = 1) -> "ValidationResult":
        return cls(result=False, message=message, error_code=error_code)


@dataclass
class PermissionResult:
    """权限检查结果"""
    behavior: PermissionBehavior
    message: str = ""
    updated_input: Optional[Dict[str, Any]] = None

    @classmethod
    def allow(cls, updated_input: Optional[Dict[str, Any]] = None) -> "PermissionResult":
        return cls(behavior=PermissionBehavior.ALLOW, updated_input=updated_input)

    @classmethod
    def deny(cls, message: str = "") -> "PermissionResult":
        return cls(behavior=PermissionBehavior.DENY, message=message)

    @classmethod
    def ask(cls, message: str = "") -> "PermissionResult":
        return cls(behavior=PermissionBehavior.ASK, message=message)

    @classmethod
    def passthrough(cls, message: str = "") -> "PermissionResult":
        return cls(behavior=PermissionBehavior.PASSTHROUGH, message=message)

    def is_allowed(self) -> bool:
        return self.behavior == PermissionBehavior.ALLOW

    def is_denied(self) -> bool:
        return self.behavior == PermissionBehavior.DENY

    def requires_confirmation(self) -> bool:
        return self.behavior in (PermissionBehavior.ASK, PermissionBehavior.PASSTHROUGH)


T = TypeVar("T")
Input = TypeVar("Input", bound=BaseModel)
Output = TypeVar("Output")
Progress = TypeVar("Progress", bound="ToolProgressData")


class ToolProgressData(BaseModel):
    """工具进度数据基类"""
    type: str = "progress"
    message: str = ""
    percentage: float = 0.0

    class Config:
        extra = "allow"


class BashProgress(ToolProgressData):
    """Bash命令进度"""
    type: str = "bash_progress"
    command: str = ""
    output: str = ""
    exit_code: Optional[int] = None
    is_running: bool = True


class FileReadProgress(ToolProgressData):
    """文件读取进度"""
    type: str = "file_read_progress"
    file_path: str = ""
    bytes_read: int = 0
    total_bytes: int = 0
    lines_read: int = 0


class MCPProgress(ToolProgressData):
    """MCP工具进度"""
    type: str = "mcp_progress"
    server_name: str = ""
    tool_name: str = ""
    status: str = "pending"


class AgentProgress(ToolProgressData):
    """Agent工具进度"""
    type: str = "agent_progress"
    agent_name: str = ""
    status: str = "running"
    sub_steps: int = 0
    completed_steps: int = 0


class WebSearchProgress(ToolProgressData):
    """Web搜索进度"""
    type: str = "web_search_progress"
    query: str = ""
    results_found: int = 0
    status: str = "searching"


@dataclass
class ToolResult(Generic[Output]):
    """工具执行结果"""
    data: Output
    new_messages: List[Any] = field(default_factory=list)
    context_modifier: Optional[Callable[["ToolUseContext"], "ToolUseContext"]] = None
    mcp_meta: Optional[Dict[str, Any]] = None

    @classmethod
    def success(cls, data: Output) -> "ToolResult[Output]":
        return cls(data=data)

    @classmethod
    def error(cls, error_message: str) -> "ToolResult[str]":
        return cls(data=error_message)


@dataclass
class ToolProgress(Generic[Progress]):
    """工具进度包装"""
    tool_use_id: str
    data: Progress


ProgressCallback = Callable[[ToolProgress[ToolProgressData]], None]


@runtime_checkable
class ToolInputSchema(Protocol):
    """工具输入Schema协议"""
    def validate(self, data: Dict[str, Any]) -> BaseModel:
        """验证输入数据"""
        ...

    def json_schema(self) -> Dict[str, Any]:
        """返回JSON Schema"""
        ...


@runtime_checkable
class ToolOutputSchema(Protocol):
    """工具输出Schema协议"""
    def validate(self, data: Any) -> Any:
        """验证输出数据"""
        ...

    def json_schema(self) -> Dict[str, Any]:
        """返回JSON Schema"""
        ...


class SearchOrReadResult(BaseModel):
    """搜索或读取结果标识"""
    is_search: bool = False
    is_read: bool = False
    is_list: bool = False


class AppState(Protocol):
    """应用状态协议"""
    def get(self, key: str, default: Any = None) -> Any:
        ...

    def set(self, key: str, value: Any) -> None:
        ...

    def update(self, updates: Dict[str, Any]) -> None:
        ...


@dataclass
class ToolUseContext:
    """
    工具使用上下文

    包含工具执行所需的所有上下文信息
    """
    options: Dict[str, Any] = field(default_factory=lambda: {
        "commands": [],
        "debug": False,
        "main_loop_model": "",
        "tools": [],
        "verbose": False,
        "thinking_config": {},
        "mcp_clients": [],
        "mcp_resources": {},
        "is_non_interactive_session": False,
        "agent_definitions": {"active_agents": [], "all_agents": []},
        "max_budget_usd": None,
        "custom_system_prompt": None,
        "append_system_prompt": None,
    })

    abort_controller: asyncio.Event = field(default_factory=asyncio.Event)
    read_file_state: Dict[str, Any] = field(default_factory=dict)
    get_app_state: Optional[Callable[[], AppState]] = None
    set_app_state: Optional[Callable[[Callable[[AppState], AppState]], None]] = None
    user_modified: bool = False
    messages: List[Any] = field(default_factory=list)
    set_in_progress_tool_use_ids: Optional[Callable[[Callable[[set], set]], None]] = None
    set_has_interruptible_tool_in_progress: Optional[Callable[[bool], None]] = None
    set_response_length: Optional[Callable[[Callable[[int], int]], None]] = None
    tool_use_id: Optional[str] = None

    nested_memory_attachment_triggers: set = field(default_factory=set)
    loaded_nested_memory_paths: set = field(default_factory=set)
    dynamic_skill_dir_triggers: set = field(default_factory=set)
    discovered_skill_names: set = field(default_factory=set)

    file_reading_limits: Optional[Dict[str, int]] = None
    glob_limits: Optional[Dict[str, int]] = None
    tool_decisions: Optional[Dict[str, Dict[str, Any]]] = None

    def get_option(self, key: str, default: Any = None) -> Any:
        """获取选项值"""
        return self.options.get(key, default)

    def set_option(self, key: str, value: Any) -> None:
        """设置选项值"""
        self.options[key] = value

    def is_interactive(self) -> bool:
        """是否为交互式会话"""
        return not self.options.get("is_non_interactive_session", False)

    def is_debug(self) -> bool:
        """是否为调试模式"""
        return self.options.get("debug", False)

    def is_verbose(self) -> bool:
        """是否为详细模式"""
        return self.options.get("verbose", False)

    def get_mcp_clients(self) -> List[Any]:
        """获取MCP客户端列表"""
        return self.options.get("mcp_clients", [])

    def get_tools(self) -> List[Any]:
        """获取工具列表"""
        return self.options.get("tools", [])


class ToolUseMessage(BaseModel):
    """工具使用消息"""
    tool_name: str
    tool_use_id: str
    input_data: Dict[str, Any]
    status: str = "pending"


class ToolResultMessage(BaseModel):
    """工具结果消息"""
    tool_name: str
    tool_use_id: str
    result: Any
    success: bool = True
    error: Optional[str] = None


class ToolError(BaseModel):
    """工具错误"""
    code: int
    message: str
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f"[Error {self.code}] {self.message}"


class ToolExecutionRecord(BaseModel):
    """工具执行记录"""
    tool_name: str
    tool_use_id: str
    input_data: Dict[str, Any]
    output_data: Optional[Any] = None
    success: bool = False
    error: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    token_usage: Optional[Dict[str, int]] = None


class ToolDefinition(BaseModel):
    """工具定义（用于序列化和传输）"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    aliases: List[str] = Field(default_factory=list)
    search_hint: str = ""
    is_read_only: bool = False
    is_destructive: bool = False
    is_mcp: bool = False
    requires_confirmation: bool = False

    def to_openai_format(self) -> Dict[str, Any]:
        """转换为OpenAI工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            }
        }

    def to_anthropic_format(self) -> Dict[str, Any]:
        """转换为Anthropic工具格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
