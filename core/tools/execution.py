"""
工具执行流程模块
实现完整的工具调用执行流程：查找工具 → 验证输入 → 检查权限 → 执行工具
"""

from typing import Dict, Any, Optional, Callable, AsyncGenerator
from loguru import logger

from core.tools.v2 import (
    Tool,
    ToolSystem,
    ToolUseContext,
    ToolResult,
    PermissionResult,
    ValidationResult,
    PermissionBehavior,
)


async def execute_tool_use(
    tool_name: str,
    arguments: Dict[str, Any],
    tool_system: ToolSystem,
    context: ToolUseContext,
    can_use_tool: Optional[Callable] = None,
) -> ToolResult:
    """
    执行工具调用
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数
        tool_system: 工具系统
        context: 工具使用上下文
        can_use_tool: 权限检查函数（可选）
        
    Returns:
        工具执行结果
    """
    # 1. 根据工具名查找工具
    logger.debug(f"[ToolExecution] Looking for tool: {tool_name}")
    tool = tool_system.find_tool(tool_name)
    if not tool:
        logger.error(f"[ToolExecution] Tool not found: {tool_name}")
        return ToolResult(data=f"工具 {tool_name} 未找到")
    
    # 2. 验证输入
    logger.debug(f"[ToolExecution] Validating input for tool: {tool_name}")
    validation: ValidationResult = await tool.validate_input(arguments, context)
    if not validation.result:
        logger.error(f"[ToolExecution] Input validation failed for {tool_name}: {validation.message}")
        return ToolResult(data=f"输入验证失败: {validation.message}")
    
    # 3. 检查权限
    logger.debug(f"[ToolExecution] Checking permissions for tool: {tool_name}")
    if can_use_tool:
        permission: PermissionResult = await can_use_tool(tool, validation.data, context)
    else:
        permission: PermissionResult = await tool.check_permissions(validation.data, context)
    
    if permission.behavior == PermissionBehavior.DENY:
        logger.error(f"[ToolExecution] Permission denied for {tool_name}: {permission.message}")
        return ToolResult(data=f"权限拒绝: {permission.message}")
    
    if permission.behavior in (PermissionBehavior.ASK, PermissionBehavior.PASSTHROUGH):
        logger.info(f"[ToolExecution] Permission requires user confirmation for {tool_name}: {permission.message}")
        return ToolResult(data=f"需要用户确认: {permission.message}")
    
    # 使用更新后的输入参数
    final_args = permission.updated_input if permission.updated_input else validation.data
    
    # 4. 执行工具
    try:
        logger.info(f"[ToolExecution] Executing tool: {tool_name}, args: {final_args}")
        result: ToolResult = await tool.call(final_args, context, can_use_tool)
        logger.info(f"[ToolExecution] Tool {tool_name} executed successfully")
        return result
    except Exception as e:
        logger.error(f"[ToolExecution] Failed to execute tool {tool_name}: {e}", exc_info=True)
        return ToolResult(data=f"工具执行失败: {str(e)}")


async def execute_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    tool_system: ToolSystem,
    context: ToolUseContext,
) -> Dict[str, Any]:
    """
    执行工具调用并返回格式化结果
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数
        tool_system: 工具系统
        context: 工具使用上下文
        
    Returns:
        格式化的工具执行结果
    """
    result = await execute_tool_use(tool_name, arguments, tool_system, context)
    
    return {
        "tool_name": tool_name,
        "success": True,
        "data": result.data,
        "message": "",
    }


async def run_tool_use(
    tool_name: str,
    tool_use_id: str,
    arguments: Dict[str, Any],
    tool_system: ToolSystem,
    context: ToolUseContext,
    can_use_tool: Optional[Callable] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    执行工具调用（生成器版本）
    
    Args:
        tool_name: 工具名称
        tool_use_id: 工具调用 ID
        arguments: 工具参数
        tool_system: 工具系统
        context: 工具使用上下文
        can_use_tool: 权限检查函数（可选）
        
    Yields:
        工具执行进度和结果
    """
    # 1. 查找工具
    logger.debug(f"[runToolUse] Looking for tool: {tool_name}")
    tool = tool_system.find_tool(tool_name)
    if not tool:
        yield {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Tool {tool_name} not found",
            "success": False,
        }
        return
    
    # 2. 验证输入
    logger.debug(f"[runToolUse] Validating input for tool: {tool_name}")
    validation: ValidationResult = await tool.validate_input(arguments, context)
    if not validation.result:
        yield {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Invalid input: {validation.message}",
            "success": False,
        }
        return
    
    # 3. 检查权限
    logger.debug(f"[runToolUse] Checking permissions for tool: {tool_name}")
    if can_use_tool:
        permission: PermissionResult = await can_use_tool(tool, validation.data, context)
    else:
        permission: PermissionResult = await tool.check_permissions(validation.data, context)
    
    if permission.behavior == PermissionBehavior.DENY:
        yield {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Permission denied: {permission.message}",
            "success": False,
        }
        return
    
    if permission.behavior in (PermissionBehavior.ASK, PermissionBehavior.PASSTHROUGH):
        yield {
            "type": "permission_request",
            "tool_use_id": tool_use_id,
            "content": f"Requires user confirmation: {permission.message}",
            "success": False,
        }
        return
    
    # 使用更新后的输入参数
    final_args = permission.updated_input if permission.updated_input else validation.data
    
    # 4. 执行工具
    try:
        logger.info(f"[runToolUse] Executing tool: {tool_name}, args: {final_args}")
        
        # 发送进度更新
        yield {
            "type": "progress",
            "tool_use_id": tool_use_id,
            "content": f"Executing {tool_name}...",
            "percentage": 0,
        }
        
        result: ToolResult = await tool.call(final_args, context, can_use_tool)
        
        # 发送完成结果
        yield {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result.data,
            "success": True,
            "percentage": 100,
        }
        
        logger.info(f"[runToolUse] Tool {tool_name} executed successfully")
        
    except Exception as e:
        logger.error(f"[runToolUse] Failed to execute tool {tool_name}: {e}", exc_info=True)
        yield {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Tool execution failed: {str(e)}",
            "success": False,
        }