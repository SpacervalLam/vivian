"""
进度追踪系统 - 工具系统 V2

实现完整的进度追踪功能，包括：
- 进度数据类型
- 进度追踪器
- 进度回调
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field
from loguru import logger

from .types import ToolProgressData, BashProgress, FileReadProgress, MCPProgress, AgentProgress, WebSearchProgress


T = TypeVar("T", bound=ToolProgressData)


class ProgressStatus(Enum):
    """进度状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressEvent(Generic[T]):
    """进度事件"""
    tool_use_id: str
    tool_name: str
    data: T
    status: ProgressStatus = ProgressStatus.RUNNING
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_use_id": self.tool_use_id,
            "tool_name": self.tool_name,
            "data": self.data.model_dump() if isinstance(self.data, BaseModel) else self.data,
            "status": self.status.value,
            "timestamp": self.timestamp,
        }


ProgressCallback = Callable[[ProgressEvent], None]


class ProgressTracker:
    """
    进度追踪器

    追踪工具执行的进度，支持多个回调监听。
    """

    def __init__(self):
        self._callbacks: List[ProgressCallback] = []
        self._progress_history: Dict[str, List[ProgressEvent]] = {}
        self._active_progress: Dict[str, ProgressEvent] = {}

    def register_callback(self, callback: ProgressCallback) -> Callable[[], None]:
        """
        注册进度回调

        Returns:
            取消注册的函数
        """
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback) if callback in self._callbacks else None

    def emit(self, event: ProgressEvent) -> None:
        """发送进度事件"""
        if event.tool_use_id not in self._progress_history:
            self._progress_history[event.tool_use_id] = []
        self._progress_history[event.tool_use_id].append(event)
        self._active_progress[event.tool_use_id] = event

        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    def emit_progress(
        self,
        tool_use_id: str,
        tool_name: str,
        data: ToolProgressData,
        status: ProgressStatus = ProgressStatus.RUNNING,
    ) -> None:
        """发送进度更新"""
        event = ProgressEvent(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            data=data,
            status=status,
        )
        self.emit(event)

    def start(
        self,
        tool_use_id: str,
        tool_name: str,
        initial_data: Optional[ToolProgressData] = None,
    ) -> None:
        """开始进度追踪"""
        data = initial_data or ToolProgressData(message=f"Starting {tool_name}")
        self.emit_progress(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            data=data,
            status=ProgressStatus.RUNNING,
        )

    def update(
        self,
        tool_use_id: str,
        tool_name: str,
        data: ToolProgressData,
    ) -> None:
        """更新进度"""
        self.emit_progress(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            data=data,
            status=ProgressStatus.RUNNING,
        )

    def complete(
        self,
        tool_use_id: str,
        tool_name: str,
        message: str = "Completed",
    ) -> None:
        """完成进度"""
        self.emit_progress(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            data=ToolProgressData(message=message, percentage=100.0),
            status=ProgressStatus.COMPLETED,
        )
        if tool_use_id in self._active_progress:
            del self._active_progress[tool_use_id]

    def fail(
        self,
        tool_use_id: str,
        tool_name: str,
        error: str,
    ) -> None:
        """标记失败"""
        self.emit_progress(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            data=ToolProgressData(message=f"Failed: {error}"),
            status=ProgressStatus.FAILED,
        )
        if tool_use_id in self._active_progress:
            del self._active_progress[tool_use_id]

    def cancel(
        self,
        tool_use_id: str,
        tool_name: str,
        reason: str = "Cancelled",
    ) -> None:
        """取消进度"""
        self.emit_progress(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            data=ToolProgressData(message=reason),
            status=ProgressStatus.CANCELLED,
        )
        if tool_use_id in self._active_progress:
            del self._active_progress[tool_use_id]

    def get_history(self, tool_use_id: str) -> List[ProgressEvent]:
        """获取进度历史"""
        return self._progress_history.get(tool_use_id, [])

    def get_active(self) -> Dict[str, ProgressEvent]:
        """获取活动进度"""
        return self._active_progress.copy()

    def clear_history(self, tool_use_id: Optional[str] = None) -> None:
        """清除历史"""
        if tool_use_id:
            self._progress_history.pop(tool_use_id, None)
        else:
            self._progress_history.clear()


class ProgressBuilder:
    """
    进度构建器

    用于构建特定类型的进度数据。
    """

    @staticmethod
    def bash(
        command: str,
        output: str = "",
        exit_code: Optional[int] = None,
        is_running: bool = True,
        percentage: float = 0.0,
    ) -> BashProgress:
        """构建Bash进度"""
        return BashProgress(
            command=command,
            output=output,
            exit_code=exit_code,
            is_running=is_running,
            percentage=percentage,
        )

    @staticmethod
    def file_read(
        file_path: str,
        bytes_read: int = 0,
        total_bytes: int = 0,
        lines_read: int = 0,
        percentage: float = 0.0,
    ) -> FileReadProgress:
        """构建文件读取进度"""
        return FileReadProgress(
            file_path=file_path,
            bytes_read=bytes_read,
            total_bytes=total_bytes,
            lines_read=lines_read,
            percentage=percentage,
        )

    @staticmethod
    def mcp(
        server_name: str,
        tool_name: str,
        status: str = "pending",
        message: str = "",
        percentage: float = 0.0,
    ) -> MCPProgress:
        """构建MCP进度"""
        return MCPProgress(
            server_name=server_name,
            tool_name=tool_name,
            status=status,
            message=message,
            percentage=percentage,
        )

    @staticmethod
    def agent(
        agent_name: str,
        status: str = "running",
        sub_steps: int = 0,
        completed_steps: int = 0,
        message: str = "",
    ) -> AgentProgress:
        """构建Agent进度"""
        percentage = (completed_steps / sub_steps * 100) if sub_steps > 0 else 0.0
        return AgentProgress(
            agent_name=agent_name,
            status=status,
            sub_steps=sub_steps,
            completed_steps=completed_steps,
            message=message,
            percentage=percentage,
        )

    @staticmethod
    def web_search(
        query: str,
        results_found: int = 0,
        status: str = "searching",
        message: str = "",
    ) -> WebSearchProgress:
        """构建Web搜索进度"""
        return WebSearchProgress(
            query=query,
            results_found=results_found,
            status=status,
            message=message,
        )


class ProgressContext:
    """
    进度上下文

    用于在工具执行过程中追踪进度。
    """

    def __init__(
        self,
        tracker: ProgressTracker,
        tool_use_id: str,
        tool_name: str,
    ):
        self.tracker = tracker
        self.tool_use_id = tool_use_id
        self.tool_name = tool_name
        self._start_time = time.time()

    def __enter__(self) -> "ProgressContext":
        self.tracker.start(
            tool_use_id=self.tool_use_id,
            tool_name=self.tool_name,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.tracker.fail(
                tool_use_id=self.tool_use_id,
                tool_name=self.tool_name,
                error=str(exc_val),
            )
        else:
            self.tracker.complete(
                tool_use_id=self.tool_use_id,
                tool_name=self.tool_name,
            )

    def update(self, data: ToolProgressData) -> None:
        """更新进度"""
        self.tracker.update(
            tool_use_id=self.tool_use_id,
            tool_name=self.tool_name,
            data=data,
        )

    def report_progress(
        self,
        message: str = "",
        percentage: float = 0.0,
    ) -> None:
        """报告进度"""
        self.update(ToolProgressData(
            message=message,
            percentage=percentage,
        ))

    def elapsed_time(self) -> float:
        """获取已用时间"""
        return time.time() - self._start_time


_progress_tracker: Optional[ProgressTracker] = None


def get_progress_tracker() -> ProgressTracker:
    """获取进度追踪器单例"""
    global _progress_tracker
    if _progress_tracker is None:
        _progress_tracker = ProgressTracker()
    return _progress_tracker
