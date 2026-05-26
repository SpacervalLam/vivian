"""
输出解析器模块

为Vivian提供结构化响应解析功能
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import json
import re

from loguru import logger
from pydantic import BaseModel, ValidationError


class BaseOutputParser(ABC):
    """
    基础输出解析器
    """

    @abstractmethod
    def parse(self, text: str) -> Any:
        """
        解析输出文本

        Args:
            text: 要解析的文本

        Returns:
            解析后的结果
        """
        pass

    def get_format_instructions(self) -> str:
        """
        获取格式化指令

        Returns:
            格式指令字符串
        """
        return "Please respond with a valid output format."

    @property
    def _type(self) -> str:
        """输出解析器类型"""
        return self.__class__.__name__


class JSONOutputParser(BaseOutputParser):
    """
    JSON输出解析器
    """

    def parse(self, text: str) -> Dict[str, Any]:
        """
        解析JSON格式的输出

        Args:
            text: JSON字符串

        Returns:
            解析后的字典

        Raises:
            ValueError: 当JSON格式无效时
        """
        try:
            # 清理文本，移除可能的markdown代码块标记
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 文本: {text[:200]}...")
            raise ValueError(f"Invalid JSON format: {e}")

    def get_format_instructions(self) -> str:
        """
        获取JSON格式指令
        """
        return """Please respond with a valid JSON object. The response should be parseable JSON, without any additional text or formatting."""


class VivianResponseParser(BaseOutputParser):
    """
    Vivian专用响应解析器，支持工具调用和聊天响应
    """

    def parse(self, text: str) -> Dict[str, Any]:
        """
        解析Vivian的响应格式

        支持两种格式：
        1. 工具调用: {"tool": "tool_name", "arguments": {...}}
        2. 聊天响应: {"text": "...", "motion": "...", "expression": "...", "importance_user": 0.5}

        Args:
            text: 响应文本

        Returns:
            解析后的响应字典
        """
        try:
            # 先尝试JSON解析
            json_parser = JSONOutputParser()
            result = json_parser.parse(text)

            # 验证响应格式
            self._validate_vivian_response(result)
            return result

        except (ValueError, ValidationError) as e:
            logger.warning(f"JSON解析失败，尝试修复: {e}")
            # 尝试修复常见的JSON格式问题
            fixed_text = self._fix_common_json_issues(text)
            if fixed_text != text:
                try:
                    result = json_parser.parse(fixed_text)
                    self._validate_vivian_response(result)
                    return result
                except Exception:
                    pass

            # 如果都失败，返回默认响应
            logger.error(f"无法解析响应: {text[:200]}...")
            return self._get_default_response()

    def _validate_vivian_response(self, response: Dict[str, Any]) -> None:
        """
        验证Vivian响应格式

        Args:
            response: 响应字典

        Raises:
            ValueError: 当格式无效时
        """
        # 检查是否是工具调用
        if "tool" in response:
            if not isinstance(response.get("tool"), str):
                raise ValueError("Tool name must be a string")
            if "arguments" not in response:
                raise ValueError("Tool call must include arguments")
            if not isinstance(response["arguments"], dict):
                raise ValueError("Tool arguments must be a dictionary")

        # 检查是否是聊天响应
        elif "text" in response:
            required_fields = ["text", "motion", "expression", "importance_user"]
            for field in required_fields:
                if field not in response:
                    raise ValueError(f"Chat response missing required field: {field}")

            if not isinstance(response.get("importance_user"), (int, float)):
                raise ValueError("importance_user must be a number")

        else:
            raise ValueError("Response must contain either 'tool' or 'text' field")

    def _fix_common_json_issues(self, text: str) -> str:
        """
        修复常见的JSON格式问题

        Args:
            text: 原始文本

        Returns:
            修复后的文本
        """
        # 移除可能的markdown代码块
        text = re.sub(r'```\w*\n?', '', text)

        # 修复未转义的引号
        # 注意：这只是基本修复，更复杂的需要更智能的处理
        text = text.replace('\\"', '"')

        # 移除尾随逗号
        text = re.sub(r',(\s*[}\]])', r'\1', text)

        return text.strip()

    def _get_default_response(self) -> Dict[str, Any]:
        """
        获取默认响应

        Returns:
            默认聊天响应
        """
        return {
            "text": "抱歉，我没有理解你的请求。",
            "motion": "idle",
            "expression": "",
            "importance_user": 0.3
        }

    def get_format_instructions(self) -> str:
        """
        获取Vivian响应格式指令
        """
        return """**Output ONLY JSON**:
For tool calls: {"tool": "tool_name", "arguments": {"param": "value"}}
For chat responses: {"text": "reply", "motion": "idle", "expression": "", "importance_user": 0.5}

**Available expressions**: shy, angry, cry, panic, eye_roll, umbrella_close
**importance_user**: 0.9-1=hard_constraint/health/identity, 0.6-0.8=project/decision/preferences, 0.3-0.5=general_facts, 0-0.2=casual"""


class StructuredOutputParser(BaseOutputParser):
    """
    结构化输出解析器，支持Pydantic模型
    """

    def __init__(self, pydantic_model: type[BaseModel]):
        """
        初始化结构化解析器

        Args:
            pydantic_model: 用于解析的Pydantic模型
        """
        self.pydantic_model = pydantic_model

    def parse(self, text: str) -> BaseModel:
        """
        解析为Pydantic模型

        Args:
            text: JSON字符串

        Returns:
            解析后的模型实例
        """
        json_parser = JSONOutputParser()
        data = json_parser.parse(text)

        try:
            return self.pydantic_model(**data)
        except ValidationError as e:
            logger.error(f"Pydantic验证失败: {e}")
            raise ValueError(f"Output does not match expected structure: {e}")

    def get_format_instructions(self) -> str:
        """
        获取格式指令
        """
        schema = self.pydantic_model.model_json_schema()
        return f"Please respond with a JSON object matching this schema: {json.dumps(schema, indent=2)}"