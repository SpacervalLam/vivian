from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints

from loguru import logger
from pydantic import BaseModel, Field


class BaseTool(ABC):
    """工具基类，支持参数验证和文档解析"""

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    args_schema: Optional[Type[BaseModel]] = Field(default=None, description="参数模式")
    return_direct: bool = Field(default=False, description="是否直接返回结果")

    def __init__(self):
        """初始化工具"""
        self._extract_parameters()

    def _extract_parameters(self) -> None:
        """自动提取工具参数信息"""
        try:
            sig = inspect.signature(self.run)
            type_hints = get_type_hints(self.run)

            parameters = {}
            for name, param in sig.parameters.items():
                if name in ["self", "args", "kwargs"]:
                    continue

                description = self._get_param_description(name, param)

                param_info = {
                    "name": name,
                    "type": str(type_hints.get(name, Any)),
                    "required": param.default == inspect.Parameter.empty,
                    "default": (
                        param.default
                        if param.default != inspect.Parameter.empty
                        else None
                    ),
                    "description": description,
                }
                parameters[name] = param_info

            self.parameters = parameters
        except Exception as e:
            logger.error(f"提取工具{self.name}的参数信息失败: {e}")
            self.parameters = {}

    def _get_param_description(self, param_name: str, param: inspect.Parameter) -> str:
        """获取参数描述"""
        docstring = inspect.getdoc(self.run)
        if docstring:
            lines = docstring.split('\n')
            in_args = False
            for line in lines:
                line = line.strip()
                if line.startswith('Args:') or line.startswith('Arguments:'):
                    in_args = True
                    continue
                elif in_args and line.startswith(param_name + ':'):
                    return line.split(':', 1)[1].strip()
                elif in_args and line == '':
                    continue
                elif in_args and not line.startswith(' '):
                    break

        return f"Parameter {param_name}"

    @property
    def args(self) -> Dict[str, Any]:
        """
        获取工具参数的schema定义，用于LLM调用
        """
        return {
            "type": "object",
            "properties": {
                name: {
                    "type": self._map_type_to_json(param["type"]),
                    "description": param["description"],
                }
                for name, param in self.parameters.items()
            },
            "required": [name for name, param in self.parameters.items() if param["required"]],
        }

    def _map_type_to_json(self, type_str: str) -> str:
        """
        将Python类型映射到JSON schema类型
        """
        type_mapping = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }
        return type_mapping.get(type_str, "string")

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        """同步执行工具
        
        Returns:
            工具执行结果
        """
        pass

    async def arun(self, *args, **kwargs) -> Any:
        """异步执行工具
        
        Returns:
            工具执行结果
        """
        return self.run(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"


class ToolResult(BaseModel):
    """工具执行结果模型"""

    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(..., description="执行结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class ToolManager:
    """
    工具管理器，负责工具的注册、发现和调用
    """

    def __init__(self):
        """
        初始化工具管理器
        """
        self.tools: Dict[str, BaseTool] = {}
        self._tool_count = 0

    def register_tool(self, tool: BaseTool) -> None:
        """
        注册工具

        Args:
            tool: 要注册的工具实例
        """
        self.tools[tool.name] = tool
        self._tool_count += 1
        logger.debug(f"工具'{tool.name}'注册成功，描述: {tool.description[:50]}...")

    def register_tool_class(self, tool_class: Type[BaseTool]) -> None:
        """
        注册工具类

        Args:
            tool_class: 要注册的工具类
        """
        try:
            tool = tool_class()
            self.register_tool(tool)
        except Exception as e:
            logger.error(f"注册工具类{tool_class.__name__}失败: {e}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        获取工具实例

        Args:
            name: 工具名称

        Returns:
            工具实例，如果不存在则返回None
        """
        return self.tools.get(name)

    def list_tools(self) -> List[str]:
        """
        获取所有工具名称

        Returns:
            工具名称列表
        """
        return list(self.tools.keys())

    def get_tool_description(self, name: str) -> Optional[str]:
        """
        获取工具描述

        Args:
            name: 工具名称

        Returns:
            工具描述，如果工具不存在则返回None
        """
        tool = self.get_tool(name)
        if tool:
            return tool.description
        return None

    def get_all_tools_info(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有工具的详细信息

        Returns:
            工具信息字典，包含名称、描述和参数
        """
        tools_info = {}
        for name, tool in self.tools.items():
            tools_info[name] = {
                "name": name,
                "description": tool.description,
                "parameters": tool.parameters,
                "args_schema": tool.args if hasattr(tool, 'args') else {},
                "return_direct": tool.return_direct,
            }
        return tools_info

    def run_tool(self, name: str, *args, **kwargs) -> ToolResult:
        """
        执行工具

        Args:
            name: 工具名称
            *args: 工具参数
            **kwargs: 工具关键字参数

        Returns:
            工具执行结果
        """
        tool = self.get_tool(name)
        if not tool:
            logger.error(f"工具'{name}'不存在")
            return ToolResult(success=False, result=None, error=f"工具'{name}'不存在")

        try:
            logger.info(f"执行工具'{name}'，参数: {args}, {kwargs}")
            result = tool.run(*args, **kwargs)
            logger.debug(f"工具'{name}'执行成功，结果: {result}")
            return ToolResult(success=True, result=result)
        except Exception as e:
            logger.error(f"工具'{name}'执行失败: {e}", exc_info=True)
            return ToolResult(success=False, result=None, error=str(e))

    async def arun_tool(self, name: str, *args, **kwargs) -> ToolResult:
        """
        异步执行工具

        Args:
            name: 工具名称
            *args: 工具参数
            **kwargs: 工具关键字参数

        Returns:
            工具执行结果
        """
        tool = self.get_tool(name)
        if not tool:
            logger.error(f"工具'{name}'不存在")
            return ToolResult(success=False, result=None, error=f"工具'{name}'不存在")

        try:
            logger.info(f"异步执行工具'{name}'，参数: {args}, {kwargs}")
            result = await tool.arun(*args, **kwargs)
            logger.debug(f"工具'{name}'异步执行成功，结果: {result}")
            return ToolResult(success=True, result=result)
        except Exception as e:
            logger.error(f"工具'{name}'异步执行失败: {e}", exc_info=True)
            return ToolResult(success=False, result=None, error=str(e))

    def run_tool_from_json(self, tool_call_json: Dict[str, Any]) -> ToolResult:
        """
        从JSON格式执行工具调用

        Args:
            tool_call_json: 工具调用JSON，包含name和arguments字段

        Returns:
            工具执行结果
        """
        try:
            name = tool_call_json.get("name")
            arguments = tool_call_json.get("arguments", {})

            if not name:
                return ToolResult(success=False, result=None, error="工具名称不能为空")

            # 将字符串参数转换为字典
            if isinstance(arguments, str):
                import json

                arguments = json.loads(arguments)

            return self.run_tool(name, **arguments)
        except Exception as e:
            logger.error(f"从JSON执行工具调用失败: {e}", exc_info=True)
            return ToolResult(success=False, result=None, error=str(e))

    async def arun_tool_from_json(self, tool_call_json: Dict[str, Any]) -> ToolResult:
        """
        异步从JSON格式执行工具调用

        Args:
            tool_call_json: 工具调用JSON，包含name和arguments字段

        Returns:
            工具执行结果
        """
        try:
            name = tool_call_json.get("name")
            arguments = tool_call_json.get("arguments", {})

            if not name:
                return ToolResult(success=False, result=None, error="工具名称不能为空")

            # 将字符串参数转换为字典
            if isinstance(arguments, str):
                import json

                arguments = json.loads(arguments)

            return await self.arun_tool(name, **arguments)
        except Exception as e:
            logger.error(f"异步从JSON执行工具调用失败: {e}", exc_info=True)
            return ToolResult(success=False, result=None, error=str(e))

    def get_tools_by_prefix(self, prefix: str) -> List[BaseTool]:
        """
        根据前缀获取工具

        Args:
            prefix: 工具名称前缀

        Returns:
            工具列表
        """
        return [tool for name, tool in self.tools.items() if name.startswith(prefix)]

    def get_tools_by_description(self, keyword: str) -> List[BaseTool]:
        """
        根据描述关键字获取工具

        Args:
            keyword: 描述关键字

        Returns:
            工具列表
        """
        return [tool for tool in self.tools.values() if keyword in tool.description]

    def unregister_tool(self, name: str) -> bool:
        """
        注销工具

        Args:
            name: 工具名称

        Returns:
            是否注销成功
        """
        if name in self.tools:
            del self.tools[name]
            logger.info(f"工具'{name}'已注销")
            return True
        logger.warning(f"尝试注销不存在的工具'{name}'")
        return False


# 工具装饰器，用于简化工具创建
def tool(name: str, description: str, return_direct: bool = False) -> Callable:
    """
    工具装饰器，将函数转换为工具

    Args:
        name: 工具名称
        description: 工具描述
        return_direct: 是否直接返回结果

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Type[BaseTool]:
        # 创建工具类
        # 使用不同的变量名来避免闭包变量绑定问题
        tool_name = name
        tool_description = description
        tool_return_direct = return_direct

        class FuncTool(BaseTool):
            name = tool_name
            description = tool_description
            return_direct = tool_return_direct

            def __init__(self):
                # 调用父类初始化方法前，确保所有字段都已设置
                super().__init__()

            def run(self, *args, **kwargs) -> Any:
                return func(*args, **kwargs)

            async def arun(self, *args, **kwargs) -> Any:
                # 如果函数是协程函数，直接调用
                if (
                    hasattr(func, "__code__") and func.__code__.co_flags & 0x80
                ):  # 检查是否是协程函数
                    return await func(*args, **kwargs)
                # 否则调用同步方法
                return func(*args, **kwargs)

        return FuncTool

    return decorator


# 示例工具
@tool(name="calculate", description="计算器工具，用于执行数学计算")
def calculate_tool(expression: str) -> str:
    """
    计算器工具，用于执行数学计算

    Args:
        expression: 数学表达式

    Returns:
        计算结果
    """
    try:
        result = eval(expression)
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算失败: {str(e)}"


@tool(name="echo", description="回显工具，用于返回输入内容")
def echo_tool(content: str) -> str:
    """
    回显工具，用于返回输入内容

    Args:
        content: 输入内容

    Returns:
        输入内容
    """
    return content
