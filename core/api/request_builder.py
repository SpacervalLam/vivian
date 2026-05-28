"""
API 请求构建模块
构建包含工具 Schema 的完整 API 请求
"""

from typing import List, Dict, Any, Optional
from loguru import logger

from core.tools.v2 import ToolSystem
from .tool_schema import tools_to_api_schemas


def build_api_request(
    model: str,
    messages: List[Dict],
    system_prompt: str,
    tool_system: Optional[ToolSystem] = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    stream: bool = True,
) -> Dict[str, Any]:
    """
    构建包含工具的 API 请求
    
    Args:
        model: 模型名称
        messages: 消息列表
        system_prompt: 系统提示词
        tool_system: 工具系统（可选）
        max_tokens: 最大 token 数
        temperature: 温度参数
        stream: 是否流式响应
        
    Returns:
        API 请求参数字典
    """
    request = {
        "model": model,
        "messages": messages,
        "system": system_prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    
    # 如果有工具系统，添加工具参数
    if tool_system:
        try:
            tools = tool_system.list_tools()
            request["tools"] = tools_to_api_schemas(tools)
            logger.debug(f"Added {len(tools)} tools to API request")
        except Exception as e:
            logger.error(f"Failed to add tools to API request: {e}")
    
    return request


def build_anthropic_request(
    model: str,
    messages: List[Dict],
    system_prompt: str,
    tool_system: Optional[ToolSystem] = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    stream: bool = True,
) -> Dict[str, Any]:
    """
    构建 Anthropic API 请求
    
    Args:
        model: 模型名称
        messages: 消息列表
        system_prompt: 系统提示词
        tool_system: 工具系统（可选）
        max_tokens: 最大 token 数
        temperature: 温度参数
        stream: 是否流式响应
        
    Returns:
        Anthropic API 请求参数字典
    """
    request = {
        "model": model,
        "messages": messages,
        "system": system_prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    
    if tool_system:
        try:
            tools = tool_system.list_tools()
            request["tools"] = tools_to_api_schemas(tools)
            logger.debug(f"Added {len(tools)} tools to Anthropic request")
        except Exception as e:
            logger.error(f"Failed to add tools to Anthropic request: {e}")
    
    return request