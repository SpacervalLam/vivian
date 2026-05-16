"""
Vivian 工具系统 V2 - 完整功能版本

灵感来源：ClaudeCode 的工具系统设计
特性：
- 基于 Pydantic 的强类型 Schema 验证
- 完整的权限上下文系统
- 工具进度追踪
- MCP 协议支持
- 工具搜索和延迟加载
- UI 渲染支持
"""

from .types import (
    ToolResult,
    ToolProgress,
    ToolProgressData,
    ValidationResult,
    PermissionResult,
    PermissionBehavior,
    ToolUseContext,
    ToolInputSchema,
    ToolOutputSchema,
    BashProgress,
    FileReadProgress,
    MCPProgress,
    AgentProgress,
    WebSearchProgress,
    ToolExecutionRecord,
    ToolDefinition,
)
from .tool import Tool, ToolDef, build_tool, tool_matches_name, find_tool_by_name, tool_decorator
from .permission import (
    PermissionContext,
    PermissionMode,
    ToolPermissionRules,
    PermissionRule,
    PermissionChecker,
    PermissionManager,
    get_empty_permission_context,
    get_permission_manager,
)
from .progress import (
    ProgressTracker,
    ProgressCallback,
    ProgressBuilder,
    ProgressContext,
    get_progress_tracker,
)
from .pool import ToolPool, assemble_tool_pool, ToolPoolManager, get_pool_manager
from .registry import ToolRegistry, register_tool, get_tool, list_tools, unregister_tool
from .mcp import MCPToolBase, MCPConnection, MCPServerInfo, MCPManager, get_mcp_manager
from .search import ToolSearchEngine, ToolSearchResult, DeferredToolLoader, create_tool_search_tool
from .builtin_tools import get_all_builtin_tools, register_builtin_tools
from .executor import (
    ToolExecutor,
    ToolSystem,
    ToolExecutionConfig,
    ExecutionResult,
    get_tool_system,
    init_tool_system,
)
from .ui import (
    ToolUIRenderer,
    ToolUIManager,
    ToolUIMessage,
    MessageStyle,
    MessageStatus,
    format_tool_result_for_display,
    format_progress_for_display,
)
from .compat import (
    CompatibleToolManager,
    V2ToolAdapter,
    V1ToolAdapter,
    migrate_to_v2,
    create_compatible_tool,
    get_compatible_tool_manager,
)

__all__ = [
    # Types
    "ToolResult",
    "ToolProgress",
    "ToolProgressData",
    "ValidationResult",
    "PermissionResult",
    "PermissionBehavior",
    "ToolUseContext",
    "ToolInputSchema",
    "ToolOutputSchema",
    "BashProgress",
    "FileReadProgress",
    "MCPProgress",
    "AgentProgress",
    "WebSearchProgress",
    "ToolExecutionRecord",
    "ToolDefinition",
    # Tool
    "Tool",
    "ToolDef",
    "build_tool",
    "tool_matches_name",
    "find_tool_by_name",
    "tool_decorator",
    # Permission
    "PermissionContext",
    "PermissionMode",
    "ToolPermissionRules",
    "PermissionRule",
    "PermissionChecker",
    "PermissionManager",
    "get_empty_permission_context",
    "get_permission_manager",
    # Progress
    "ProgressTracker",
    "ProgressCallback",
    "ProgressBuilder",
    "ProgressContext",
    "get_progress_tracker",
    # Pool
    "ToolPool",
    "assemble_tool_pool",
    "ToolPoolManager",
    "get_pool_manager",
    # Registry
    "ToolRegistry",
    "register_tool",
    "get_tool",
    "list_tools",
    "unregister_tool",
    # MCP
    "MCPToolBase",
    "MCPConnection",
    "MCPServerInfo",
    "MCPManager",
    "get_mcp_manager",
    # Search
    "ToolSearchEngine",
    "ToolSearchResult",
    "DeferredToolLoader",
    "create_tool_search_tool",
    "get_all_builtin_tools",
    "register_builtin_tools",
    # Executor
    "ToolExecutor",
    "ToolSystem",
    "ToolExecutionConfig",
    "ExecutionResult",
    "get_tool_system",
    "init_tool_system",
    # UI
    "ToolUIRenderer",
    "ToolUIManager",
    "ToolUIMessage",
    "MessageStyle",
    "MessageStatus",
    "format_tool_result_for_display",
    "format_progress_for_display",
    # Compatibility
    "CompatibleToolManager",
    "V2ToolAdapter",
    "V1ToolAdapter",
    "migrate_to_v2",
    "create_compatible_tool",
    "get_compatible_tool_manager",
]
