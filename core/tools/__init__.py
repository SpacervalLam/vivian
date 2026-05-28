"""
工具模块 - Tools

工具系统
"""

from .tool_call_manager_v2 import (
    ToolCallManager,
    ToolCallStatus,
    ToolCall,
    ToolCallResult,
    get_tool_call_manager,
    init_tool_call_manager,
)

from .execution import execute_tool_use, execute_tool_call, run_tool_use

from .v2 import (
    Tool,
    ToolSystem,
    ToolResult,
    ToolUseContext,
    PermissionContext,
    PermissionMode,
    PermissionResult,
    ValidationResult,
    build_tool,
    register_tool,
    get_tool_system,
    register_builtin_tools,
)

__all__ = [
    # 工具调用管理器
    "ToolCallManager",
    "ToolCallStatus",
    "ToolCall",
    "ToolCallResult",
    "get_tool_call_manager",
    "init_tool_call_manager",
    # 工具执行流程
    "execute_tool_use",
    "execute_tool_call",
    "run_tool_use",
    # 工具系统
    "Tool",
    "ToolSystem",
    "ToolResult",
    "ToolUseContext",
    "PermissionContext",
    "PermissionMode",
    "PermissionResult",
    "ValidationResult",
    "build_tool",
    "register_tool",
    "get_tool_system",
    "register_builtin_tools",
]