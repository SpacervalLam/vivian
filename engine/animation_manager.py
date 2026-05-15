import os
import time
from enum import IntEnum
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QTimer
from loguru import logger

from .motion_player import MotionPlayer


class MotionPriority(IntEnum):
    IDLE = 0
    LOW = 10
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


class MotionState:
    """动作状态"""

    def __init__(self, name: str, priority: int, motion_path: str):
        self.name = name
        self.priority = priority
        self.motion_path = motion_path
        self.start_time = time.time()
        self.duration = 0
        self.interruptible = True
        self.is_looping = False
        self._callbacks: Dict[str, Callable] = {}

    def on_start(self, callback: Callable):
        self._callbacks["on_start"] = callback
        return self

    def on_end(self, callback: Callable):
        self._callbacks["on_end"] = callback
        return self

    def on_loop(self, callback: Callable):
        self._callbacks["on_loop"] = callback
        return self

    def trigger_callback(self, event: str, *args, **kwargs):
        if event in self._callbacks:
            try:
                self._callbacks[event](*args, **kwargs)
            except Exception:
                pass


class AnimationManager:
    """动作动画管理器"""

    PRIORITY_THRESHOLD = {
        MotionPriority.IDLE: MotionPriority.LOW,
        MotionPriority.LOW: MotionPriority.NORMAL,
        MotionPriority.NORMAL: MotionPriority.HIGH,
        MotionPriority.HIGH: MotionPriority.CRITICAL,
        MotionPriority.CRITICAL: float("inf"),
    }

    def __init__(self, resource_loader):
        self.resource_loader = resource_loader
        self._current_motion: Optional[MotionState] = None
        self._motion_queue: list = []
        self._is_playing = False
        self._last_motion_name = None
        self._motion_count = 0
        self._motion_player = MotionPlayer()
        self._on_frame_callback: Optional[Callable[[Dict[str, float]], None]] = None

    def set_on_frame_callback(self, callback: Callable[[Dict[str, float]], None]):
        """设置每帧回调"""
        self._on_frame_callback = callback

    def play_motion(
        self,
        name: str,
        priority: int = MotionPriority.NORMAL,
        interruptible: bool = True,
        loop: bool = False,
    ) -> Optional[MotionState]:
        """播放动作，返回动作状态"""
        motion_info = self.resource_loader.get_motion(name)
        if not motion_info:
            logger.warning(f"[AnimationManager] 未找到动作: {name}")
            return None

        new_motion = MotionState(
            name=name, priority=priority, motion_path=motion_info["path"]
        )
        new_motion.duration = motion_info.get("duration", 0)
        new_motion.is_looping = loop or motion_info.get("loop", False)
        new_motion.interruptible = interruptible

        if self._current_motion:
            if not self._can_interrupt(self._current_motion.priority, priority):
                if interruptible:
                    self._motion_queue.append(new_motion)
                    logger.debug(f"[AnimationManager] 动作 '{name}' 已加入队列 (优先级: {priority})")
                else:
                    logger.debug(f"[AnimationManager] 无法播放动作 '{name}': 当前有更高优先级动作")
                return None

            logger.debug(f"[AnimationManager] 打断当前动作 '{self._current_motion.name}' -> 播放 '{name}'")
            self._current_motion.trigger_callback("on_end", interrupted=True)
            self._stop_current_motion()

        self._start_motion(new_motion)
        return new_motion

    def play_random_motion(
        self,
        min_priority: int = MotionPriority.IDLE,
        max_priority: int = MotionPriority.NORMAL,
    ) -> Optional[MotionState]:
        """随机播放动作"""
        motions = self.resource_loader.get_all_motions()
        if not motions:
            return None

        import random

        valid_motions = [
            name
            for name, info in motions.items()
            if min_priority
            <= info.get("priority", MotionPriority.NORMAL)
            <= max_priority
        ]
        if valid_motions:
            return self.play_motion(random.choice(valid_motions))
        return None

    def stop_motion(self, force: bool = False):
        """停止当前动作"""
        if self._current_motion:
            if not force and not self._current_motion.interruptible:
                logger.debug(f"[AnimationManager] 无法停止动作 '{self._current_motion.name}': 不可中断")
                return False

            self._current_motion.trigger_callback("on_end", interrupted=False)
            self._stop_current_motion()
            self._process_queue()
            return True
        return False

    def stop_all_motions(self):
        """停止所有动作"""
        while self._current_motion or self._motion_queue:
            self.stop_motion(force=True)
        self._motion_queue.clear()

    def is_playing(self, motion_name: Optional[str] = None) -> bool:
        """是否正在播放"""
        if motion_name:
            return (
                self._current_motion is not None
                and self._current_motion.name == motion_name
            )
        return self._current_motion is not None

    def get_current_motion(self) -> Optional[MotionState]:
        """获取当前动作"""
        return self._current_motion

    def get_motion_queue(self) -> list:
        """获取动作队列"""
        return self._motion_queue.copy()

    def on_motion_end(
        self,
        motion_name: str,
        callback: Callable,
        priority: int = MotionPriority.NORMAL,
    ):
        """设置动作结束回调"""
        motion_info = self.resource_loader.get_motion(motion_name)
        if motion_info:
            motion_state = MotionState(
                name=motion_name, priority=priority, motion_path=motion_info["path"]
            )
            motion_state.on_end(callback)
            return motion_state
        return None

    def _can_interrupt(self, current_priority: int, new_priority: int) -> bool:
        return new_priority > current_priority

    def _start_motion(self, motion: MotionState):
        self._current_motion = motion
        self._is_playing = True
        self._last_motion_name = motion.name
        self._motion_count += 1

        logger.debug(f"[AnimationManager] 开始播放动作: {motion.name} (优先级: {motion.priority})")
        motion.trigger_callback("on_start")

        if self._motion_player.load_motion(motion.motion_path):
            self._motion_player.play(loop=motion.is_looping)
            logger.debug(f"[AnimationManager] 动作播放器已启动: {motion.name}")
        else:
            logger.warning(f"[AnimationManager] 无法加载动作文件: {motion.motion_path}")

        if not motion.is_looping and motion.duration > 0:
            QTimer.singleShot(int(motion.duration * 1000), self._on_motion_timer_end)

    def _stop_current_motion(self):
        self._motion_player.stop()
        self._current_motion = None
        self._is_playing = False

    def _on_motion_timer_end(self):
        if self._current_motion:
            self._current_motion.trigger_callback("on_end", completed=True)
            logger.debug(f"[AnimationManager] 动作播放完成: {self._current_motion.name}")

            current_motion = self._current_motion
            self._stop_current_motion()

            if current_motion.is_looping:
                self._start_motion(current_motion)
            else:
                self._process_queue()

    def _process_queue(self):
        if self._motion_queue and not self._current_motion:
            self._motion_queue.sort(key=lambda m: m.priority, reverse=True)
            next_motion = self._motion_queue.pop(0)
            self._start_motion(next_motion)
            logger.debug(f"[AnimationManager] 从队列播放动作: {next_motion.name}")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "is_playing": self._is_playing,
            "current_motion": (
                self._current_motion.name if self._current_motion else None
            ),
            "queue_length": len(self._motion_queue),
            "total_motions_played": self._motion_count,
            "last_motion": self._last_motion_name,
        }

    def clear_statistics(self):
        """清空统计信息"""
        self._motion_count = 0
        self._last_motion_name = None
