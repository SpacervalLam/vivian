"""
系统工具包装器 - 用于正确地将系统工具注册到工具管理器
"""
from typing import Dict, Any
from core.tool_manager import BaseTool
from core.tools.system_tools import SYSTEM_TOOLS, execute_system_tool


class SystemTool(BaseTool):
    """
    系统工具的通用包装类
    """
    def __init__(self, tool_info: Dict[str, Any]):
        self.name = tool_info["name"]
        self.description = tool_info["description"]
        self.return_direct = False
        self.parameters = {}
        
        # 从工具信息中提取参数
        for param_name, param_info in tool_info.get("parameters", {}).items():
            self.parameters[param_name] = {
                "name": param_name,
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
                "required": param_info.get("required", True),
                "default": param_info.get("default"),
            }
    
    def run(self, **kwargs) -> Any:
        """执行工具"""
        return execute_system_tool(self.name, **kwargs)
    
    async def arun(self, **kwargs) -> Any:
        """异步执行工具（同步包装）"""
        return execute_system_tool(self.name, **kwargs)


def create_system_tool(tool_info: Dict[str, Any]) -> BaseTool:
    """
    从工具信息创建工具实例
    
    Args:
        tool_info: 工具信息字典
        
    Returns:
        BaseTool实例
    """
    return SystemTool(tool_info)


def register_all_system_tools(tool_manager) -> int:
    """
    注册所有系统工具到工具管理器
    
    Args:
        tool_manager: ToolManager实例
        
    Returns:
        注册的工具数量
    """
    count = 0
    for tool_info in SYSTEM_TOOLS:
        try:
            tool_instance = create_system_tool(tool_info)
            tool_manager.register_tool(tool_instance)
            count += 1
        except Exception as e:
            from loguru import logger
            logger.error(f"注册工具 {tool_info['name']} 失败: {e}")
    
    return count
