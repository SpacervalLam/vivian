"""
打扰控制器 (InterruptionController)

核心功能：
1. 监测用户活动状态（键盘、鼠标、窗口）
2. 根据用户状态动态调整打扰阈值
3. 决定是否允许桌宠主动打扰用户
4. 维护打扰频率和冷却机制

灵感来源：用户建议的"打扰控制器"架构
"""

import random
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from PyQt5.QtCore import QObject, QTimer

from loguru import logger


class UserActivityLevel(Enum):
    """用户活动级别"""
    VERY_ACTIVE = "very_active"      # 频繁操作
    ACTIVE = "active"               # 正常操作
    IDLE = "idle"                   # 空闲
    VERY_IDLE = "very_idle"         # 长时间空闲
    BUSY = "busy"                   # 专注状态（特定窗口）


class UserInterruptionTolerance(Enum):
    """用户打扰容忍度"""
    HIGH = "high"           # 欢迎打扰
    NORMAL = "normal"       # 适度打扰
    LOW = "low"             # 尽量不打扰
    VERY_LOW = "very_low"   # 除非重要，否则不打扰


class InterruptionController(QObject):
    """
    打扰控制器 - 控制桌宠何时可以主动打扰用户

    设计原则：
    - 用户忙时：少说话
    - 用户空闲时：主动一点
    - 用户多次无视：降低频率
    - 用户回应后：短暂活跃
    - 深夜：更安静
    """

    # 活动检测参数
    IDLE_THRESHOLD_MS = 5000           # 5秒无活动视为空闲
    VERY_IDLE_THRESHOLD_MS = 30000     # 30秒无活动视为长时间空闲
    VERY_ACTIVE_KEYSTROKES = 10        # 10次按键/秒为频繁操作

    # 打扰冷却参数
    MIN_INTERRUPTION_INTERVAL = 30      # 最小打扰间隔（秒）
    MAX_INTERRUPTIONS_PER_HOUR = 12    # 每小时最大打扰次数
    NIGHT_HOUR_START = 23              # 深夜开始时间（23点）
    NIGHT_HOUR_END = 8                 # 深夜结束时间（8点）

    def __init__(self):
        super().__init__()
        self._reset()
        self._start_monitoring()

    def _reset(self):
        """重置状态"""
        self._last_activity_time = time.time()
        self._last_interruption_time = 0
        self._interruption_count_today = 0
        self._last_reset_date = datetime.now().date()
        self._unanswered_count = 0  # 连续未回应次数
        self._consecutive_responses = 0  # 连续回应次数

        self._activity_level = UserActivityLevel.ACTIVE
        self._tolerance = UserInterruptionTolerance.NORMAL

        self._is_monitoring = False

    def _start_monitoring(self):
        """启动状态监测"""
        if self._is_monitoring:
            return

        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._update_activity_level)
        self._monitor_timer.start(2000)  # 每2秒检查一次

        self._reset_daily_timer = QTimer(self)
        self._reset_daily_timer.timeout.connect(self._check_daily_reset)
        self._reset_daily_timer.start(60000)  # 每分钟检查是否需要重置

        self._is_monitoring = True
        logger.info("打扰控制器已启动")

    def _check_daily_reset(self):
        """检查是否需要每日重置"""
        today = datetime.now().date()
        if today > self._last_reset_date:
            self._interruption_count_today = 0
            self._last_reset_date = today
            logger.debug("打扰计数已重置（新的一天）")

    def _update_activity_level(self):
        """更新用户活动级别"""
        current_time = time.time()
        time_since_activity = (current_time - self._last_activity_time) * 1000

        if time_since_activity < self.IDLE_THRESHOLD_MS:
            self._activity_level = UserActivityLevel.VERY_ACTIVE
        elif time_since_activity < self.IDLE_THRESHOLD_MS * 2:
            self._activity_level = UserActivityLevel.ACTIVE
        elif time_since_activity < self.VERY_IDLE_THRESHOLD_MS:
            self._activity_level = UserActivityLevel.IDLE
        else:
            self._activity_level = UserActivityLevel.VERY_IDLE

        self._adjust_tolerance_based_on_pattern()

    def _adjust_tolerance_based_on_pattern(self):
        """根据用户行为模式调整打扰容忍度"""
        if self._unanswered_count >= 3:
            self._tolerance = UserInterruptionTolerance.LOW
        elif self._unanswered_count >= 5:
            self._tolerance = UserInterruptionTolerance.VERY_LOW
        elif self._consecutive_responses >= 3:
            self._tolerance = UserInterruptionTolerance.HIGH
        else:
            self._tolerance = UserInterruptionTolerance.NORMAL

    def record_user_activity(self):
        """记录用户活动（由外部调用）"""
        self._last_activity_time = time.time()
        self._activity_level = UserActivityLevel.VERY_ACTIVE

    def record_user_response(self):
        """记录用户回应（桌宠主动说话后用户有响应）"""
        self._unanswered_count = 0
        self._consecutive_responses = min(self._consecutive_responses + 1, 5)

    def record_user_ignored(self):
        """记录用户无视（桌宠主动说话后用户无响应）"""
        self._unanswered_count += 1
        self._consecutive_responses = 0

    def should_interrupt(self, priority: str = "normal") -> tuple[bool, str]:
        """
        判断当前是否可以打扰用户

        Args:
            priority: 优先级 ("low", "normal", "high", "urgent")

        Returns:
            (是否可以打扰, 原因)
        """
        current_time = time.time()

        # 1. 检查深夜模式
        if self._is_night_time():
            if priority not in ["urgent", "high"]:
                return False, "深夜模式，限制打扰"

        # 2. 检查打扰频率限制
        if self._interruption_count_today >= self.MAX_INTERRUPTIONS_PER_HOUR:
            return False, "今日打扰次数已达上限"

        # 3. 检查最小间隔
        time_since_last = current_time - self._last_interruption_time
        min_interval = self._get_min_interval()
        if time_since_last < min_interval:
            remaining = int(min_interval - time_since_last)
            return False, f"打扰冷却中，还需{remaining}秒"

        # 4. 根据用户活动级别判断
        can_interrupt, reason = self._check_by_activity_level(priority)
        if not can_interrupt:
            return False, reason

        # 5. 根据容忍度判断
        if not self._check_tolerance(priority):
            return False, f"用户打扰容忍度较低（{self._tolerance.value}）"

        return True, "允许打扰"

    def _is_night_time(self) -> bool:
        """检查是否深夜"""
        hour = datetime.now().hour
        return hour >= self.NIGHT_HOUR_START or hour < self.NIGHT_HOUR_END

    def _get_min_interval(self) -> int:
        """根据状态获取最小打扰间隔"""
        base = self.MIN_INTERRUPTION_INTERVAL

        # 根据容忍度调整
        if self._tolerance == UserInterruptionTolerance.HIGH:
            return int(base * 0.7)
        elif self._tolerance == UserInterruptionTolerance.LOW:
            return int(base * 2)
        elif self._tolerance == UserInterruptionTolerance.VERY_LOW:
            return int(base * 3)

        # 根据活动级别调整
        if self._activity_level == UserActivityLevel.VERY_ACTIVE:
            return int(base * 1.5)
        elif self._activity_level == UserActivityLevel.BUSY:
            return int(base * 2)

        return base

    def _check_by_activity_level(self, priority: str) -> tuple[bool, str]:
        """根据活动级别检查"""
        if self._activity_level == UserActivityLevel.VERY_ACTIVE:
            if priority in ["low", "normal"]:
                return False, "用户非常活跃，稍后再打扰"
            return True, "用户活跃但优先级高"

        elif self._activity_level == UserActivityLevel.BUSY:
            if priority != "urgent":
                return False, "用户正在专注工作"
            return True, "用户忙碌但有紧急事项"

        elif self._activity_level == UserActivityLevel.IDLE:
            return True, "用户空闲，适合打扰"

        elif self._activity_level == UserActivityLevel.VERY_IDLE:
            if priority == "low":
                return False, "用户可能已离开"
            return True, "用户长时间空闲"

        return True, "状态检查通过"

    def _check_tolerance(self, priority: str) -> bool:
        """检查容忍度"""
        if self._tolerance == UserInterruptionTolerance.VERY_LOW:
            return priority in ["high", "urgent"]
        elif self._tolerance == UserInterruptionTolerance.LOW:
            return priority in ["normal", "high", "urgent"]
        return True

    def record_interruption(self):
        """记录一次打扰"""
        self._last_interruption_time = time.time()
        self._interruption_count_today += 1
        logger.debug(f"打扰已记录，今日累计: {self._interruption_count_today}次")

    def get_interruption_readiness(self) -> dict:
        """
        获取打扰就绪状态（供AI决策使用）

        Returns:
            包含各种状态信息的字典
        """
        return {
            "can_interrupt": self.should_interrupt("normal")[0],
            "activity_level": self._activity_level.value,
            "tolerance": self._tolerance.value,
            "unanswered_count": self._unanswered_count,
            "consecutive_responses": self._consecutive_responses,
            "is_night": self._is_night_time(),
            "today_interruptions": self._interruption_count_today,
            "time_since_last_interrupt": int(time.time() - self._last_interruption_time),
            "suggested_action": self._get_suggested_action()
        }

    def _get_suggested_action(self) -> str:
        """获取建议的行动"""
        if self._is_night_time():
            return "保持安静，仅响应用户主动交互"

        if self._activity_level == UserActivityLevel.VERY_ACTIVE:
            return "保持安静，等待用户主动交互"

        if self._activity_level == UserActivityLevel.BUSY:
            return "保持安静，或仅做轻微动作（如表情变化）"

        if self._unanswered_count >= 3:
            return "停止主动打扰，改为被动等待"

        if self._consecutive_responses >= 3:
            return "可以适当主动，但保持克制"

        return "可以正常主动交互"

    def get_current_status(self) -> str:
        """获取当前状态描述"""
        parts = [
            f"活动级别: {self._activity_level.value}",
            f"打扰容忍度: {self._tolerance.value}",
            f"连续无视: {self._unanswered_count}次",
            f"连续回应: {self._consecutive_responses}次",
            f"今日打扰: {self._interruption_count_today}次",
        ]

        if self._is_night_time():
            parts.append("🌙 深夜模式")

        return " | ".join(parts)


# 全局单例
_interruption_controller: Optional[InterruptionController] = None


def get_interruption_controller() -> InterruptionController:
    """获取打扰控制器单例"""
    global _interruption_controller
    if _interruption_controller is None:
        _interruption_controller = InterruptionController()
    return _interruption_controller