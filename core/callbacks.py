"""
回调系统模块

为Vivian提供可观察性和监控功能
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import time
from collections.abc import AsyncIterator, Iterator

from loguru import logger
from pydantic import BaseModel


class BaseCallbackHandler(ABC):
    """
    基础回调处理器
    """

    @abstractmethod
    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        """链开始时调用"""

    @abstractmethod
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """链结束时调用"""

    @abstractmethod
    def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        """链出错时调用"""

    @abstractmethod
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """工具开始时调用"""

    @abstractmethod
    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        """工具结束时调用"""

    @abstractmethod
    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        """工具出错时调用"""


class CallbackManager:
    """
    回调管理器，管理多个回调处理器
    """

    def __init__(self, handlers: Optional[List[BaseCallbackHandler]] = None):
        """
        初始化回调管理器

        Args:
            handlers: 回调处理器列表
        """
        self.handlers = handlers or []

    def add_handler(self, handler: BaseCallbackHandler) -> None:
        """
        添加回调处理器

        Args:
            handler: 回调处理器
        """
        self.handlers.append(handler)

    def remove_handler(self, handler: BaseCallbackHandler) -> None:
        """
        移除回调处理器

        Args:
            handler: 回调处理器
        """
        self.handlers.remove(handler)

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        """触发链开始事件"""
        for handler in self.handlers:
            try:
                handler.on_chain_start(serialized, inputs, **kwargs)
            except Exception as e:
                logger.error(f"回调处理器错误: {e}")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """触发链结束事件"""
        for handler in self.handlers:
            try:
                handler.on_chain_end(outputs, **kwargs)
            except Exception as e:
                logger.error(f"回调处理器错误: {e}")

    def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        """触发链错误事件"""
        for handler in self.handlers:
            try:
                handler.on_chain_error(error, **kwargs)
            except Exception as e:
                logger.error(f"回调处理器错误: {e}")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """触发工具开始事件"""
        for handler in self.handlers:
            try:
                handler.on_tool_start(serialized, input_str, **kwargs)
            except Exception as e:
                logger.error(f"回调处理器错误: {e}")

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        """触发工具结束事件"""
        for handler in self.handlers:
            try:
                handler.on_tool_end(output, **kwargs)
            except Exception as e:
                logger.error(f"回调处理器错误: {e}")

    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        """触发工具错误事件"""
        for handler in self.handlers:
            try:
                handler.on_tool_error(error, **kwargs)
            except Exception as e:
                logger.error(f"回调处理器错误: {e}")


class LoggingCallbackHandler(BaseCallbackHandler):
    """
    日志回调处理器
    """

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        logger.info(f"链开始: {serialized.get('name', 'Unknown')}")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        logger.info("链结束")

    def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        logger.error(f"链错误: {error}")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        logger.info(f"工具开始: {serialized.get('name', 'Unknown')} - {input_str[:50]}...")

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        logger.info("工具结束")

    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        logger.error(f"工具错误: {error}")


class MetricsCallbackHandler(BaseCallbackHandler):
    """
    指标回调处理器，用于收集性能指标
    """

    def __init__(self):
        self.metrics = {
            "chain_starts": 0,
            "chain_ends": 0,
            "chain_errors": 0,
            "tool_starts": 0,
            "tool_ends": 0,
            "tool_errors": 0,
            "total_duration": 0.0,
        }
        self._start_times = {}

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        chain_id = kwargs.get("run_id", "default")
        self._start_times[chain_id] = time.time()
        self.metrics["chain_starts"] += 1

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        chain_id = kwargs.get("run_id", "default")
        if chain_id in self._start_times:
            duration = time.time() - self._start_times[chain_id]
            self.metrics["total_duration"] += duration
            del self._start_times[chain_id]
        self.metrics["chain_ends"] += 1

    def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        self.metrics["chain_errors"] += 1

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        self.metrics["tool_starts"] += 1

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self.metrics["tool_ends"] += 1

    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        self.metrics["tool_errors"] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """获取指标数据"""
        return self.metrics.copy()


class VivianCallbackManager:
    """
    Vivian专用回调管理器
    """

    def __init__(self):
        self.callback_manager = CallbackManager()
        # 添加默认处理器
        self.callback_manager.add_handler(LoggingCallbackHandler())
        self.callback_manager.add_handler(MetricsCallbackHandler())

    def get_callback_manager(self) -> CallbackManager:
        """获取回调管理器"""
        return self.callback_manager

    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        for handler in self.callback_manager.handlers:
            if isinstance(handler, MetricsCallbackHandler):
                return handler.get_metrics()
        return {}


# 全局回调管理器实例
_vivian_callback_manager = None

def get_vivian_callback_manager() -> VivianCallbackManager:
    """
    获取全局Vivian回调管理器实例

    Returns:
        VivianCallbackManager实例
    """
    global _vivian_callback_manager
    if _vivian_callback_manager is None:
        _vivian_callback_manager = VivianCallbackManager()
    return _vivian_callback_manager