"""
流式JSON解析器

核心功能：
1. 在流式输出中优先识别text字段并实时提取
2. text字段内容流式显示给用户
3. 同时完整收集其他JSON字段
4. 支持嵌套的JSON对象和顶级数组
"""

from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from enum import Enum, auto
from dataclasses import dataclass
from loguru import logger
import json


class ParserState(Enum):
    """解析器状态"""
    WAITING = auto()           # 等待JSON开始
    IN_OBJECT = auto()         # 在对象中
    IN_KEY = auto()            # 解析字段名
    AFTER_KEY = auto()         # 冒号后
    IN_STRING = auto()         # 字符串中
    IN_TEXT_STRING = auto()    # text字段值
    IN_ARRAY = auto()          # 在数组中
    ESCAPE_SEQUENCE = auto()   # 转义字符


@dataclass
class StreamingResult:
    """流式解析结果"""
    text_content: str = ""
    full_json: Optional[Dict[str, Any]] = None
    full_array: Optional[List[Any]] = None  # 顶级数组
    is_complete: bool = False
    has_text: bool = False
    error: Optional[str] = None


class StreamingJsonParser:
    """流式JSON解析器"""
    
    def __init__(
        self,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        self.on_text_chunk = on_text_chunk
        self.on_complete = on_complete
        self.on_error = on_error
        
        self.state = ParserState.WAITING
        self.buffer = ""
        self.current_key = ""
        self.text_accumulator = ""
        self.result = StreamingResult()
        
        self._object_buffer = ""
        self._is_text_field = False
        self._brace_depth = 0
        self._bracket_depth = 0
        self._in_array = False  # 标记是否在数组中
    
    def reset(self):
        """重置解析器"""
        self.state = ParserState.WAITING
        self.buffer = ""
        self.current_key = ""
        self.text_accumulator = ""
        self.result = StreamingResult()
        self._object_buffer = ""
        self._is_text_field = False
        self._brace_depth = 0
        self._bracket_depth = 0
        self._in_array = False
    
    def feed(self, chunk: str) -> StreamingResult:
        """处理一个新的字符块"""
        for char in chunk:
            self._process_char(char)
        return self.result
    
    def _process_char(self, char: str):
        """处理单个字符"""
        self.buffer += char
        
        if self.state == ParserState.ESCAPE_SEQUENCE:
            self._handle_escape_char(char)
            return
        
        if char == '\\':
            self.state = ParserState.ESCAPE_SEQUENCE
            return
        
        # 处理顶级JSON开始
        if self.state == ParserState.WAITING:
            if char == '{':
                self.state = ParserState.IN_OBJECT
                self._brace_depth = 1
            elif char == '[':
                self.state = ParserState.IN_ARRAY
                self._bracket_depth = 1
                self._in_array = True
            self._object_buffer += char
            return
        
        # 始终添加到buffer
        self._object_buffer += char
        
        # 处理数组
        if self.state == ParserState.IN_ARRAY:
            if char == ']':
                self._bracket_depth -= 1
                if self._bracket_depth == 0:
                    self._finalize_array()
            elif char == '[':
                # 嵌套数组
                self._bracket_depth += 1
            elif char == '{':
                self._brace_depth = 1
                self.state = ParserState.IN_OBJECT
            return
        
        # 处理对象
        if self.state == ParserState.IN_OBJECT:
            if char == '}':
                self._brace_depth -= 1
                if self._brace_depth == 0:
                    if self._in_array:
                        self.state = ParserState.IN_ARRAY
                    else:
                        self._finalize_object()
            elif char == '"':
                self.state = ParserState.IN_KEY
                self.current_key = ""
            elif char in [',', ' ', '\t', '\n']:
                pass  # 忽略
            return
        
        # 处理键
        if self.state == ParserState.IN_KEY:
            if char == '"':
                self._is_text_field = (self.current_key == "text")
                self.state = ParserState.AFTER_KEY
            else:
                self.current_key += char
            return
        
        # 处理键后
        if self.state == ParserState.AFTER_KEY:
            if char == ':':
                pass  # 忽略冒号
            elif char == '"':
                self.state = ParserState.IN_TEXT_STRING if self._is_text_field else ParserState.IN_STRING
            elif char == '{':
                self._brace_depth = 1
                self.state = ParserState.IN_OBJECT
            elif char not in [' ', '\t', '\n']:
                self.state = ParserState.IN_OBJECT
            return
        
        # 处理字符串
        if self.state in [ParserState.IN_STRING, ParserState.IN_TEXT_STRING]:
            if char == '"':
                self._finish_string()
            elif self.state == ParserState.IN_TEXT_STRING:
                self.text_accumulator += char
                self.result.text_content = self.text_accumulator
                self.result.has_text = True
                if self.on_text_chunk:
                    self.on_text_chunk(char)
            return
    
    def _handle_escape_char(self, char: str):
        """处理转义字符"""
        if self.state == ParserState.IN_TEXT_STRING:
            escaped = self._unescape_char(char)
            self.text_accumulator += escaped
            self.result.text_content = self.text_accumulator
            self.result.has_text = True
            if self.on_text_chunk:
                self.on_text_chunk(escaped)
        
        self.state = ParserState.IN_TEXT_STRING if self._is_text_field else ParserState.IN_STRING
    
    def _unescape_char(self, char: str) -> str:
        """处理转义字符"""
        escape_map = {
            'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f',
            '\\': '\\', '"': '"', "'": "'"
        }
        return escape_map.get(char, char)
    
    def _finish_string(self):
        """完成字符串值"""
        if self.current_key == "text":
            self.result.text_content = self.text_accumulator
            self.result.has_text = True
        
        self.current_key = ""
        self._is_text_field = False
        self.state = ParserState.IN_OBJECT
    
    def _finalize_object(self):
        """完成对象解析"""
        try:
            self.result.full_json = json.loads(self._object_buffer)
            self.result.is_complete = True
            
            if self.on_complete:
                try:
                    self.on_complete(self.result.full_json)
                except Exception as e:
                    logger.error(f"Complete callback error: {e}")
            
            logger.debug(f"Object complete: {list(self.result.full_json.keys())}")
        except Exception as e:
            logger.debug(f"Failed to parse JSON: {e}")
            self.result.error = str(e)
        
        self._brace_depth = 0
        self.state = ParserState.WAITING
    
    def _finalize_array(self):
        """完成数组解析"""
        try:
            self.result.full_array = json.loads(self._object_buffer)
            self.result.is_complete = True
            
            if self.on_complete:
                try:
                    self.on_complete(self.result.full_array)
                except Exception as e:
                    logger.error(f"Complete callback error: {e}")
            
            logger.debug(f"Array complete: {len(self.result.full_array)} elements")
        except Exception as e:
            logger.debug(f"Failed to parse array: {e}")
            self.result.error = str(e)
        
        self._bracket_depth = 0
        self._brace_depth = 0
        self._in_array = False
        self.state = ParserState.WAITING
    
    async def feed_async(self, chunk_generator: AsyncGenerator[str, None]) -> AsyncGenerator[StreamingResult, None]:
        """异步处理字符流"""
        async for chunk in chunk_generator:
            result = self.feed(chunk)
            yield result
    
    def get_result(self) -> StreamingResult:
        """获取最终结果"""
        return self.result


class StreamingResponseHandler:
    """流式响应处理器"""
    
    def __init__(
        self,
        on_text_update: Callable[[str], None],
        on_tool_call: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.on_text_update = on_text_update
        self.on_tool_call = on_tool_call
        self.on_complete = on_complete
        self.parser = StreamingJsonParser(
            on_text_chunk=self._handle_text_chunk,
            on_complete=self._handle_complete_json
        )
        self.full_text = ""
        self.text_buffer = ""
    
    def _handle_text_chunk(self, chunk: str):
        """处理text字段的新内容块"""
        self.text_buffer += chunk
        self.full_text = self.text_buffer
        self.on_text_update(self.full_text)
    
    def _handle_complete_json(self, json_obj: Any):
        """处理完整JSON对象或数组"""
        if isinstance(json_obj, dict) and "tool" in json_obj and self.on_tool_call:
            self.on_tool_call(json_obj)
        
        if self.on_complete:
            self.on_complete(json_obj)
    
    async def _process_stream(self, chunk_generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        """内部处理流"""
        async for chunk in chunk_generator:
            self.parser.feed(chunk)
            yield self.full_text
    
    def get_full_json(self) -> Optional[Any]:
        """获取完整的JSON结果"""
        if self.parser.result.full_array:
            return self.parser.result.full_array
        return self.parser.result.full_json


def create_streaming_response_handler(
    text_callback: Callable[[str], None],
    tool_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    complete_callback: Optional[Callable[[Any], None]] = None
) -> StreamingResponseHandler:
    """创建流式响应处理器"""
    return StreamingResponseHandler(text_callback, tool_callback, complete_callback)
