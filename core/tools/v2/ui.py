"""
UI渲染支持 - 工具系统 V2

为桌面应用提供UI渲染支持，包括：
- 工具消息渲染
- 进度显示
- 结果展示
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from loguru import logger

from .types import (
    ToolProgressData,
    ToolResult,
    ToolExecutionRecord,
    BashProgress,
    FileReadProgress,
    MCPProgress,
    AgentProgress,
)
from .tool import Tool


class MessageStyle(Enum):
    """消息样式"""
    DEFAULT = "default"
    CONDENSED = "condensed"
    VERBOSE = "verbose"
    MINIMAL = "minimal"


class MessageStatus(Enum):
    """消息状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolUIMessage:
    """工具UI消息"""
    tool_name: str
    tool_use_id: str
    status: MessageStatus
    input_data: Dict[str, Any]
    output_data: Optional[Any] = None
    error: Optional[str] = None
    progress: List[ToolProgressData] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0

    def is_complete(self) -> bool:
        """是否完成"""
        return self.status in (
            MessageStatus.SUCCESS,
            MessageStatus.ERROR,
            MessageStatus.CANCELLED,
        )

    def get_summary(self) -> str:
        """获取摘要"""
        if self.error:
            return f"❌ {self.tool_name}: {self.error}"
        elif self.is_complete():
            return f"✅ {self.tool_name} ({self.duration_ms:.0f}ms)"
        else:
            progress_pct = self._get_progress_percentage()
            if progress_pct > 0:
                return f"⏳ {self.tool_name} ({progress_pct:.0f}%)"
            return f"⏳ {self.tool_name}..."

    def _get_progress_percentage(self) -> float:
        """获取进度百分比"""
        if self.progress:
            return max(p.percentage for p in self.progress)
        return 0.0


class ToolUIRenderer:
    """
    工具UI渲染器

    负责将工具执行状态转换为可显示的UI元素。
    """

    def __init__(self, style: MessageStyle = MessageStyle.DEFAULT):
        self.style = style
        self._messages: Dict[str, ToolUIMessage] = {}

    def create_message(
        self,
        tool_name: str,
        tool_use_id: str,
        input_data: Dict[str, Any],
    ) -> ToolUIMessage:
        """创建工具消息"""
        message = ToolUIMessage(
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            status=MessageStatus.PENDING,
            input_data=input_data,
        )
        self._messages[tool_use_id] = message
        return message

    def update_status(
        self,
        tool_use_id: str,
        status: MessageStatus,
    ) -> Optional[ToolUIMessage]:
        """更新状态"""
        if tool_use_id in self._messages:
            self._messages[tool_use_id].status = status
            return self._messages[tool_use_id]
        return None

    def update_progress(
        self,
        tool_use_id: str,
        progress: ToolProgressData,
    ) -> Optional[ToolUIMessage]:
        """更新进度"""
        if tool_use_id in self._messages:
            message = self._messages[tool_use_id]
            message.progress.append(progress)
            message.status = MessageStatus.RUNNING
            return message
        return None

    def complete_message(
        self,
        tool_use_id: str,
        output_data: Any,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Optional[ToolUIMessage]:
        """完成消息"""
        if tool_use_id in self._messages:
            message = self._messages[tool_use_id]
            message.output_data = output_data
            message.error = error
            message.end_time = datetime.now()
            message.duration_ms = (
                message.end_time - message.start_time
            ).total_seconds() * 1000
            message.status = MessageStatus.SUCCESS if success else MessageStatus.ERROR
            return message
        return None

    def get_message(self, tool_use_id: str) -> Optional[ToolUIMessage]:
        """获取消息"""
        return self._messages.get(tool_use_id)

    def get_all_messages(self) -> List[ToolUIMessage]:
        """获取所有消息"""
        return list(self._messages.values())

    def clear_messages(self) -> None:
        """清除所有消息"""
        self._messages.clear()

    def render_message(
        self,
        message: ToolUIMessage,
        style: Optional[MessageStyle] = None,
    ) -> str:
        """
        渲染消息为文本

        Args:
            message: 工具消息
            style: 渲染样式

        Returns:
            渲染后的文本
        """
        style = style or self.style

        if style == MessageStyle.MINIMAL:
            return self._render_minimal(message)
        elif style == MessageStyle.CONDENSED:
            return self._render_condensed(message)
        elif style == MessageStyle.VERBOSE:
            return self._render_verbose(message)
        else:
            return self._render_default(message)

    def _render_minimal(self, message: ToolUIMessage) -> str:
        """最小样式渲染"""
        status_icon = {
            MessageStatus.SUCCESS: "✓",
            MessageStatus.ERROR: "✗",
            MessageStatus.RUNNING: "⋯",
            MessageStatus.PENDING: "○",
            MessageStatus.CANCELLED: "⊘",
        }.get(message.status, "○")

        return f"{status_icon} {message.tool_name}"

    def _render_condensed(self, message: ToolUIMessage) -> str:
        """紧凑样式渲染"""
        lines = [self._render_minimal(message)]

        if message.duration_ms > 0:
            lines.append(f"  ⏱ {message.duration_ms:.0f}ms")

        if message.error:
            lines.append(f"  ⚠ {message.error[:100]}")

        return "\n".join(lines)

    def _render_default(self, message: ToolUIMessage) -> str:
        """默认样式渲染"""
        lines = [
            f"{'='*40}",
            f"🔧 {message.tool_name}",
            f"   Status: {message.status.value}",
        ]

        if message.input_data:
            lines.append("   Input:")
            for key, value in message.input_data.items():
                value_str = str(value)[:50]
                lines.append(f"     - {key}: {value_str}")

        if message.progress:
            latest = message.progress[-1]
            lines.append(f"   Progress: {latest.message} ({latest.percentage:.0f}%)")

        if message.output_data:
            lines.append("   Output:")
            output_str = str(message.output_data)[:200]
            lines.append(f"     {output_str}")

        if message.error:
            lines.append(f"   Error: {message.error}")

        if message.duration_ms > 0:
            lines.append(f"   Duration: {message.duration_ms:.0f}ms")

        lines.append(f"{'='*40}")
        return "\n".join(lines)

    def _render_verbose(self, message: ToolUIMessage) -> str:
        """详细样式渲染"""
        lines = [self._render_default(message)]

        if message.progress:
            lines.append("\n   Progress History:")
            for i, p in enumerate(message.progress[-10:]):
                lines.append(f"     [{i+1}] {p.message} ({p.percentage:.0f}%)")

        return "\n".join(lines)

    def render_progress_spinner(
        self,
        message: ToolUIMessage,
        frame: int = 0,
    ) -> str:
        """
        渲染进度动画

        Args:
            message: 工具消息
            frame: 动画帧索引

        Returns:
            动画文本
        """
        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        spinner = spinner_frames[frame % len(spinner_frames)]

        progress_pct = message._get_progress_percentage()
        bar_width = 20
        filled = int(progress_pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        latest_progress = message.progress[-1] if message.progress else None
        progress_msg = latest_progress.message if latest_progress else "Processing..."

        return f"{spinner} {message.tool_name} [{bar}] {progress_pct:.0f}% - {progress_msg}"


class ToolUIManager:
    """
    工具UI管理器

    管理工具的UI渲染和状态更新。
    """

    def __init__(self, style: MessageStyle = MessageStyle.DEFAULT):
        self.renderer = ToolUIRenderer(style)
        self._callbacks: List[Callable[[ToolUIMessage], None]] = []

    def register_callback(
        self,
        callback: Callable[[ToolUIMessage], None],
    ) -> Callable[[], None]:
        """
        注册UI更新回调

        Returns:
            取消注册的函数
        """
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback) if callback in self._callbacks else None

    def _notify_callbacks(self, message: ToolUIMessage) -> None:
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"UI callback error: {e}")

    def on_tool_start(
        self,
        tool_name: str,
        tool_use_id: str,
        input_data: Dict[str, Any],
    ) -> ToolUIMessage:
        """工具开始"""
        message = self.renderer.create_message(
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            input_data=input_data,
        )
        message.status = MessageStatus.RUNNING
        self._notify_callbacks(message)
        return message

    def on_tool_progress(
        self,
        tool_use_id: str,
        progress: ToolProgressData,
    ) -> Optional[ToolUIMessage]:
        """工具进度"""
        message = self.renderer.update_progress(tool_use_id, progress)
        if message:
            self._notify_callbacks(message)
        return message

    def on_tool_complete(
        self,
        tool_use_id: str,
        output_data: Any,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Optional[ToolUIMessage]:
        """工具完成"""
        message = self.renderer.complete_message(
            tool_use_id=tool_use_id,
            output_data=output_data,
            success=success,
            error=error,
        )
        if message:
            self._notify_callbacks(message)
        return message

    def get_message(self, tool_use_id: str) -> Optional[ToolUIMessage]:
        """获取消息"""
        return self.renderer.get_message(tool_use_id)

    def get_all_messages(self) -> List[ToolUIMessage]:
        """获取所有消息"""
        return self.renderer.get_all_messages()

    def render_all(self, style: Optional[MessageStyle] = None) -> str:
        """渲染所有消息"""
        messages = self.renderer.get_all_messages()
        return "\n\n".join(
            self.renderer.render_message(msg, style)
            for msg in messages
        )

    def clear(self) -> None:
        """清除所有消息"""
        self.renderer.clear_messages()


def format_tool_result_for_display(
    tool_name: str,
    result: Any,
    style: MessageStyle = MessageStyle.DEFAULT,
) -> str:
    """
    格式化工具结果用于显示

    Args:
        tool_name: 工具名称
        result: 工具结果
        style: 显示样式

    Returns:
        格式化后的字符串
    """
    if style == MessageStyle.MINIMAL:
        return f"✓ {tool_name}"

    lines = [f"📋 {tool_name} Result:"]

    if isinstance(result, dict):
        if "error" in result:
            lines.append(f"  ❌ Error: {result['error']}")
        else:
            for key, value in result.items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                elif isinstance(value, (list, dict)):
                    value = f"<{type(value).__name__}({len(value)})>"
                lines.append(f"  • {key}: {value}")
    elif isinstance(result, str):
        if len(result) > 200:
            result = result[:200] + "..."
        lines.append(f"  {result}")
    else:
        lines.append(f"  {str(result)[:200]}")

    return "\n".join(lines)


def format_progress_for_display(
    progress: ToolProgressData,
) -> str:
    """
    格式化进度用于显示

    Args:
        progress: 进度数据

    Returns:
        格式化后的字符串
    """
    if isinstance(progress, BashProgress):
        return f"💻 Running: {progress.command[:50]}"
    elif isinstance(progress, FileReadProgress):
        return f"📄 Reading: {progress.file_path} ({progress.bytes_read}/{progress.total_bytes} bytes)"
    elif isinstance(progress, MCPProgress):
        return f"🔌 MCP [{progress.server_name}]: {progress.tool_name} - {progress.status}"
    elif isinstance(progress, AgentProgress):
        return f"🤖 Agent [{progress.agent_name}]: {progress.completed_steps}/{progress.sub_steps} steps"
    else:
        return f"⏳ {progress.message} ({progress.percentage:.0f}%)"
