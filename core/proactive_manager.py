"""
主动交互管理器 (ProactiveInteractionManager)

核心功能：
1. 基于状态机的"内心独白"系统
2. 时间驱动的主动交互
3. 环境感知触发的交互
4. 基于概率的闲聊机制

灵感来源：用户建议的"主动交互"架构
"""

import asyncio
import random
import time
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QTimer

from loguru import logger

from core.interruption_controller import (
    UserActivityLevel,
    get_interruption_controller
)


class PetMindState(Enum):
    """桌宠心理状态"""
    CURIOUS = "curious"           # 好奇
    BORED = "bored"             # 无聊
    EXCITED = "excited"         # 兴奋
    SLEEPY = "sleepy"           # 困倦
    CARING = "caring"           # 关心
    PLAYFUL = "playful"         # 玩耍
    TIRED = "tired"            # 疲惫
    CONTENT = "content"         # 满足


class ProactiveInteractionManager(QObject):
    """
    主动交互管理器 - 让桌宠更像"有生命的个体"

    设计原则：
    - 不要每秒都在说话，要像真实生命一样有分寸感
    - 结合环境、时间、用户状态决定何时主动交互
    - 让大模型决定"脑子"，程序负责"动作"
    """

    # 状态转换参数
    BORED_THRESHOLD_SECONDS = 600  # 10分钟无聊触发主动交互
    EXCITED_PROBABILITY = 0.3      # 兴奋状态概率
    IDLE_TALK_PROBABILITY = 0.15   # 空闲时主动说话概率（15%）

    def __init__(self, brain, main_window):
        super().__init__()
        self.brain = brain
        self.main_window = main_window

        self._current_mind_state = PetMindState.CONTENT
        self._last_interaction_time = time.time()
        self._last_bored_check = time.time()
        self._is_active = False

        self._callback_on_proactive_action: Optional[Callable] = None

        self._start_monitoring()

    def _start_monitoring(self):
        """启动主动监测"""
        if self._is_active:
            return

        # 心理状态检查定时器
        self._mind_timer = QTimer(self)
        self._mind_timer.timeout.connect(self._update_mind_state)
        self._mind_timer.start(30000)  # 每30秒检查一次

        # 无聊检测定时器
        self._bored_timer = QTimer(self)
        self._bored_timer.timeout.connect(self._check_boredom)
        self._bored_timer.start(60000)  # 每分钟检查一次

        # 环境触发检测定时器
        self._env_timer = QTimer(self)
        self._env_timer.timeout.connect(self._check_environment_triggers)
        self._env_timer.start(10000)  # 每10秒检查一次

        self._is_active = True
        logger.info("主动交互管理器已启动")

    def set_proactive_callback(self, callback: Callable):
        """设置主动行为回调"""
        self._callback_on_proactive_action = callback

    def _update_mind_state(self):
        """更新心理状态"""
        hour = datetime.now().hour

        # 基于时间的心理状态
        if 23 <= hour or hour < 7:
            self._current_mind_state = PetMindState.SLEEPY
        elif 7 <= hour < 9:
            self._current_mind_state = PetMindState.CURIOUS  # 刚起床，好奇今天
        elif 12 <= hour < 14:
            self._current_mind_state = PetMindState.SLEEPY  # 午休
        elif 17 <= hour < 19:
            self._current_mind_state = PetMindState.EXCITED  # 快下班/放学
        else:
            # 基于活动的心理状态
            readiness = get_interruption_controller().get_interruption_readiness()
            activity = readiness["activity_level"]

            if activity in ["very_active", "active"]:
                self._current_mind_state = PetMindState.CURIOUS
            elif activity == "very_idle":
                self._current_mind_state = PetMindState.BORED
            else:
                self._current_mind_state = PetMindState.CONTENT

    def _check_boredom(self):
        """检查是否无聊 - 已迁移到 LocalProactiveService"""
        # 旧版无聊交互已废弃，使用 LocalProactiveService 替代
        pass

    def _check_environment_triggers(self):
        """检查环境触发因素"""
        if not self._is_active:
            return

        try:
            # 获取环境信息
            env_info = self._get_environment_context()

            # 检查特定触发条件
            triggers = []

            # 时间相关触发
            triggers.extend(self._check_time_triggers())

            # 窗口相关触发
            triggers.extend(self._check_window_triggers(env_info))

            # 剪贴板相关触发
            triggers.extend(self._check_clipboard_triggers())

            # 如果有触发条件，考虑主动交互
            if triggers:
                readiness = get_interruption_controller().get_interruption_readiness()
                if readiness["can_interrupt"] and random.random() < 0.3:
                    best_trigger = random.choice(triggers)
                    self._trigger_environment_interaction(best_trigger)

        except Exception as e:
            logger.debug(f"环境触发检查失败: {e}")

    def _check_time_triggers(self) -> list:
        """检查时间相关触发（已迁移到 LocalProactiveService）"""
        return []

    def _check_window_triggers(self, env_info: dict) -> list:
        """检查窗口相关触发"""
        triggers = []

        # 监测特定应用
        focused_app = env_info.get("focused_app", "").lower()

        if "code" in focused_app or "vscode" in focused_app:
            triggers.append({
                "type": "window",
                "trigger": "VS Code",
                "priority": "low",
                "message": "在写代码呀，看起来很专注呢~",
                "action": "expression",
                "action_data": "focused"
            })

        elif "原神" in focused_app or "genshin" in focused_app:
            triggers.append({
                "type": "window",
                "trigger": "原神",
                "priority": "normal",
                "message": "又要去提瓦特冒险了吗？帮我看看有没有温迪~",
                "action": "expression",
                "action_data": "excited"
            })

        elif "星穹铁道" in focused_app or "honkai" in focused_app:
            triggers.append({
                "type": "window",
                "trigger": "星穹铁道",
                "priority": "normal",
                "message": "星铁启动！宇宙很大，一起去看看~",
                "action": "expression",
                "action_data": "excited"
            })

        elif "浏览器" in focused_app or "chrome" in focused_app or "edge" in focused_app:
            triggers.append({
                "type": "window",
                "trigger": "浏览器",
                "priority": "low",
                "message": "在浏览什么呢？",
                "action": "curious"
            })

        return triggers

    def _check_clipboard_triggers(self) -> list:
        """检查剪贴板相关触发"""
        triggers = []

        try:
            # 注意：实际实现需要通过全局钩子或定期检查
            # 这里只是一个占位实现
            pass
        except Exception as e:
            logger.debug(f"剪贴板检查失败: {e}")

        return triggers

    def _get_environment_context(self) -> dict:
        """获取环境上下文"""
        try:
            if hasattr(self.brain, "environment_manager"):
                return self.brain.environment_manager.get_current_state()
        except Exception as e:
            logger.debug(f"获取环境上下文失败: {e}")

        return {}

    # _trigger_bored_interaction 已迁移到 LocalProactiveService

    def _trigger_environment_interaction(self, trigger: dict):
        """触发环境驱动的交互"""
        message = trigger.get("message", "")

        if not message:
            return

        logger.info(f"触发环境交互 [{trigger.get('trigger')}]: {message}")

        self._emit_proactive_action(
            message=message,
            priority=trigger.get("priority", "normal"),
            emotion=trigger.get("action_data", "curious")
        )

    def _emit_proactive_action(self, message: str, priority: str = "normal", emotion: str = "curious"):
        """发射主动行为"""
        # 检查打扰控制器
        readiness = get_interruption_controller().get_interruption_readiness()

        if not readiness["can_interrupt"]:
            logger.debug("打扰控制器阻止了主动交互")
            return

        # 记录打扰
        get_interruption_controller().record_interruption()

        # 更新交互时间
        self._last_interaction_time = time.time()

        # 调用回调
        if self._callback_on_proactive_action:
            self._callback_on_proactive_action({
                "type": "proactive",
                "message": message,
                "priority": priority,
                "emotion": emotion,
                "mind_state": self._current_mind_state.value,
                "context": self._get_environment_context()
            })

    def record_user_interaction(self):
        """记录用户交互（外部调用）"""
        self._last_interaction_time = time.time()
        get_interruption_controller().record_user_response()

        # 重置无聊感
        if self._current_mind_state == PetMindState.BORED:
            self._current_mind_state = PetMindState.CONTENT

    def get_current_state(self) -> dict:
        """获取当前状态"""
        return {
            "mind_state": self._current_mind_state.value,
            "last_interaction": int(time.time() - self._last_interaction_time),
            "interruption_readiness": get_interruption_controller().get_interruption_readiness(),
            "suggestion": get_interruption_controller().get_interruption_readiness()["suggested_action"]
        }


# 全局单例
_proactive_manager: Optional[ProactiveInteractionManager] = None


def get_proactive_manager() -> ProactiveInteractionManager:
    """获取主动交互管理器单例"""
    return _proactive_manager


def init_proactive_manager(brain, main_window) -> ProactiveInteractionManager:
    """初始化主动交互管理器"""
    global _proactive_manager
    _proactive_manager = ProactiveInteractionManager(brain, main_window)
    return _proactive_manager