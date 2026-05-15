import os
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QTimer


class ExpressionManager:
    """表情管理器"""

    DEFAULT_EXPRESSION = "neutral"

    def __init__(self, resource_loader):
        self.resource_loader = resource_loader
        self._current_expression: Optional[str] = None
        self._expression_stack: list = []
        self._revert_timer: Optional[QTimer] = None
        self._revert_callback: Optional[Callable] = None
        self._is_temporarily_changed = False
        self._main_window = None

    def set_expression(
        self,
        name: str,
        duration_ms: Optional[int] = None,
        force: bool = False,
        priority: int = 0,
    ) -> bool:
        """设置表情，返回是否成功"""
        if not name or name.strip() == "" or name == "default" or name == "neutral":
            self.reset_expression()
            if self._main_window and hasattr(self._main_window, "live2d_widget"):
                self._main_window.live2d_widget.set_asleep(False)
            if (
                hasattr(self, "_expression_change_callback")
                and self._expression_change_callback
            ):
                try:
                    self._expression_change_callback(None)
                except Exception as e:
                    pass
            return True

        if name == "sleepy":
            if self._main_window and hasattr(self._main_window, "live2d_widget"):
                self._main_window.live2d_widget.set_asleep(True)
            self._current_expression = "sleepy"
            return True

        if self._current_expression == "sleepy" and name != "sleepy":
            if self._main_window and hasattr(self._main_window, "live2d_widget"):
                self._main_window.live2d_widget.set_asleep(False)

        expression_mapping = {
            "normal": "shy",
            "neutral": "shy",
            "idle": "shy",
            "default": "shy",
            "standard": "shy",
        }

        mapped_name = expression_mapping.get(name, name)

        expression_info = self.resource_loader.get_expression(mapped_name)
        if not expression_info:
            fallback_expressions = ["shy", "eye_roll", "panic"]
            for fallback in fallback_expressions:
                fallback_info = self.resource_loader.get_expression(fallback)
                if fallback_info:
                    mapped_name = fallback
                    break
            else:
                return False

        if mapped_name == self._current_expression and not force:
            if duration_ms and duration_ms > 0:
                self._start_revert_timer(duration_ms)
            return True

        if self._is_temporarily_changed and priority <= 0:
            self._expression_stack.append(self._current_expression)
        elif self._current_expression:
            if not self._is_temporarily_changed:
                self._expression_stack.append(self._current_expression)

        self._current_expression = mapped_name
        self._is_temporarily_changed = duration_ms is not None and duration_ms > 0

        if duration_ms and duration_ms > 0:
            self._start_revert_timer(duration_ms)

        self.trigger_expression_change_callback(mapped_name)

        return True

    def revert_expression(self):
        """恢复到上一个表情"""
        if self._revert_timer and self._revert_timer.isActive():
            self._revert_timer.stop()
            self._revert_timer = None

        if self._expression_stack:
            last_expression = self._expression_stack.pop()
            if last_expression and last_expression != self._current_expression:
                self._current_expression = last_expression
                self._is_temporarily_changed = False
                if self._revert_callback:
                    self._revert_callback(last_expression)
                return True

        if (
            self._current_expression
            and self._current_expression != self.DEFAULT_EXPRESSION
        ):
            self._current_expression = self.DEFAULT_EXPRESSION
            self._is_temporarily_changed = False
            if self._revert_callback:
                self._revert_callback(self.DEFAULT_EXPRESSION)
            return True

        return False

    def reset_expression(self):
        """重置表情到默认状态"""
        self.clear_stack()
        self._current_expression = None
        self._is_temporarily_changed = False
        if self._revert_timer:
            self._revert_timer.stop()
            self._revert_timer = None

    def clear_stack(self):
        """清空表情栈"""
        self._expression_stack.clear()

    def get_current_expression(self) -> Optional[str]:
        """获取当前表情名称"""
        return self._current_expression

    def is_temporarily_changed(self) -> bool:
        """是否处于临时表情状态"""
        return self._is_temporarily_changed

    def set_revert_callback(self, callback: Callable):
        """设置表情恢复回调"""
        self._revert_callback = callback

    def on_expression_change(self, callback: Callable):
        """设置表情变化回调"""
        self._expression_change_callback = callback
        return self

    def trigger_expression_change_callback(self, expression_name: str):
        """触发表情变化回调"""
        if (
            hasattr(self, "_expression_change_callback")
            and self._expression_change_callback
        ):
            try:
                self._expression_change_callback(expression_name)
            except Exception as e:
                pass

    def _start_revert_timer(self, duration_ms: int):
        if self._revert_timer:
            self._revert_timer.stop()

        self._revert_timer = QTimer()
        self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(self._on_revert_timeout)
        self._revert_timer.start(duration_ms)

    def _on_revert_timeout(self):
        self.revert_expression()

    def get_expression_info(self, name: str) -> Optional[Dict[str, Any]]:
        """获取表情信息"""
        return self.resource_loader.get_expression(name)

    def list_expressions(self) -> list:
        """列出所有表情名称"""
        return self.resource_loader.list_expression_names()

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "current_expression": self._current_expression,
            "stack_depth": len(self._expression_stack),
            "is_temporarily_changed": self._is_temporarily_changed,
            "expression_count": len(self.list_expressions()),
        }
