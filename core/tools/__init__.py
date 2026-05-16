"""
工具模块 - Tools

包含工具调用管理和V2工具系统：
1. tool_call_manager - 工具调用管理器
2. v2 - V2工具系统
"""

from .tool_call_manager import (
    ToolCallManager,
    ToolCallStatus,
    ToolCall,
    ToolCallResult,
    ToolListTool,
    get_tool_call_manager,
    init_tool_call_manager,
)

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
    "ToolListTool",
    "get_tool_call_manager",
    "init_tool_call_manager",
    # V2工具系统
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