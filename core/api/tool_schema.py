"""
工具 Schema 序列化模块

将工具定义转换为 LLM API 可接受的 Schema 格式
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from loguru import logger

from core.tools.v2 import Tool


class ToolSchema(BaseModel):
    """工具 Schema 定义（符合标准 API 格式）"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    is_mcp: bool = False
    is_lsp: bool = False


def tool_to_api_schema(tool: Tool) -> Dict[str, Any]:
    """
    将工具转换为 API Schema 格式
    
    Args:
        tool: 工具实例
        
    Returns:
        API Schema 字典
    """
    try:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.get_json_schema(),
            "output_schema": tool.get_output_json_schema(),
            "is_mcp": tool.is_mcp,
            "is_lsp": tool.is_lsp,
        }
    except Exception as e:
        logger.error(f"Failed to convert tool {tool.name} to schema: {e}")
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": {"type": "object", "properties": {}},
        }


def tools_to_api_schemas(tools: List[Tool]) -> List[Dict[str, Any]]:
    """
    将工具列表转换为 API Schema 列表
    
    Args:
        tools: 工具实例列表
        
    Returns:
        API Schema 字典列表
    """
    return [tool_to_api_schema(tool) for tool in tools]