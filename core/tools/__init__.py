"""
工具模块 - Tools

包含系统工具和工具调用管理：
1. system_tools - 系统工具集
2. tool_call_manager - 工具调用管理器
"""

from .system_tools import (
    SYSTEM_TOOLS,
    get_all_tools_list,
    execute_system_tool,
    open_application,
    close_application,
    open_folder,
    open_url,
    set_wallpaper,
    take_screenshot,
    get_system_info,
    get_clipboard_text,
    set_clipboard_text,
    search_files,
    copy_file,
    move_file,
    delete_file,
    minimize_window,
    maximize_window,
    close_window,
    get_running_processes,
)

from .tool_call_manager import (
    ToolCallManager,
    ToolCallStatus,
    ToolCall,
    ToolCallResult,
    ToolListTool,
    get_tool_call_manager,
    init_tool_call_manager,
)

__all__ = [
    # 系统工具
    "SYSTEM_TOOLS",
    "get_all_tools_list",
    "execute_system_tool",
    "open_application",
    "close_application",
    "open_folder",
    "open_url",
    "set_wallpaper",
    "take_screenshot",
    "get_system_info",
    "get_clipboard_text",
    "set_clipboard_text",
    "search_files",
    "copy_file",
    "move_file",
    "delete_file",
    "minimize_window",
    "maximize_window",
    "close_window",
    "get_running_processes",
    # 工具调用管理器
    "ToolCallManager",
    "ToolCallStatus",
    "ToolCall",
    "ToolCallResult",
    "ToolListTool",
    "get_tool_call_manager",
    "init_tool_call_manager",
]