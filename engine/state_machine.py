import random
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QTimer


class PetState(Enum):
    IDLE = auto()
    INTERACTING = auto()
    PANICKED = auto()
    PLAYING = auto()
    AI_TALKING = auto()


class StateTransition:
    """状态转换"""

    def __init__(
        self,
        from_state: PetState,
        to_state: PetState,
        condition: Callable[[Dict], bool],
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition


class StateMachine:
    """状态机"""

    DEFAULT_IDLE_INTERVAL_MIN = 3000
    DEFAULT_IDLE_INTERVAL_MAX = 8000

    def __init__(self, animation_manager, expression_manager, resource_loader):
        self.animation_manager = animation_manager
        self.expression_manager = expression_manager
        self.resource_loader = resource_loader

        self._current_state: PetState = PetState.IDLE
        self._previous_state: Optional[PetState] = None
        self._state_start_time = 0

        self._idle_timer: Optional[QTimer] = None
        self._idle_interval_min = self.DEFAULT_IDLE_INTERVAL_MIN
        self._idle_interval_max = self.DEFAULT_IDLE_INTERVAL_MAX

        self._event_handlers: Dict[str, Callable] = {}
        self._state_callbacks: Dict[PetState, Callable] = {}
        self._event_queue: list = []

        self._is_active = True

        self._setup_default_transitions()
        self._setup_default_event_handlers()

    def start(self):
        """启动状态机"""
        self._state_start_time = 0
        self._start_idle_timer()

    def stop(self):
        """停止状态机"""
        self._stop_idle_timer()
        self._is_active = False

    def set_state(self, new_state: PetState, force: bool = False):
        """设置当前状态"""
        if self._current_state == new_state and not force:
            return

        old_state = self._current_state
        self._previous_state = old_state
        self._current_state = new_state
        self._state_start_time = 0

        if new_state in self._state_callbacks:
            try:
                self._state_callbacks[new_state](old_state)
            except Exception as e:
                pass

        if new_state == PetState.IDLE:
            self._start_idle_timer()
        else:
            self._stop_idle_timer()

    def get_current_state(self) -> PetState:
        """获取当前状态"""
        return self._current_state

    def get_previous_state(self) -> Optional[PetState]:
        """获取上一个状态"""
        return self._previous_state

    def notify_event(self, event_name: str, meta: Dict[str, Any] = None):
        """通知事件"""
        meta = meta or {}

        if event_name in self._event_handlers:
            handler = self._event_handlers[event_name]
            try:
                handler(meta)
            except Exception as e:
                pass
        else:
            self._event_queue.append((event_name, meta))

    def on_state_change(self, state: PetState, callback: Callable[[PetState], None]):
        """设置状态变化回调"""
        self._state_callbacks[state] = callback
        return self

    def register_event_handler(self, event_name: str, handler: Callable[[Dict], None]):
        """注册事件处理器"""
        self._event_handlers[event_name] = handler
        return self

    def set_idle_interval(self, min_ms: int, max_ms: int):
        """设置空闲间隔"""
        self._idle_interval_min = min_ms
        self._idle_interval_max = max_ms

    def trigger_random_idle_action(self):
        """触发随机空闲动作"""
        if not self._is_active:
            return

        if self._current_state != PetState.IDLE:
            return

        if self.expression_manager.get_current_expression() == "eye_roll":
            return

        action_type = random.choice(["motion", "expression"])
        if action_type == "motion":
            motion = self.resource_loader.get_random_motion()
            if motion:
                self.animation_manager.play_motion(
                    motion["name"], priority=0, loop=False
                )
                self.set_state(PetState.PLAYING)
        else:
            expression = self.resource_loader.get_random_expression()
            if expression:
                self.expression_manager.set_expression(
                    expression["name"], duration_ms=random.randint(2000, 5000)
                )

    def is_active(self) -> bool:
        """是否活跃"""
        return self._is_active

    def get_state_duration(self) -> float:
        """获取状态持续时间"""
        return 0

    def _setup_default_transitions(self):
        pass

    def _setup_default_event_handlers(self):
        self.register_event_handler("click", self._handle_click)
        self.register_event_handler("double_click", self._handle_double_click)
        self.register_event_handler("panic", self._handle_panic)
        self.register_event_handler("ai_response", self._handle_ai_response)
        self.register_event_handler("motion_end", self._handle_motion_end)
        self.register_event_handler("mouse_enter", self._handle_mouse_enter)
        self.register_event_handler("mouse_leave", self._handle_mouse_leave)

    def _handle_click(self, meta: Dict):
        if self.expression_manager.get_current_expression() == "eye_roll":
            return

        click_count = meta.get("click_count", 1)
        if click_count == 1:
            self.expression_manager.set_expression("shy", duration_ms=3000)
            self.set_state(PetState.INTERACTING)
        elif click_count == 3:
            self.expression_manager.set_expression("cry", duration_ms=5000)
            self.set_state(PetState.INTERACTING)
        elif click_count >= 5:
            self.expression_manager.set_expression("panic", duration_ms=None)
            self.set_state(PetState.PANICKED)
            self.notify_event("panic", {"duration": 3000})

    def _handle_double_click(self, meta: Dict):
        if self.expression_manager.get_current_expression() == "eye_roll":
            return

        self.expression_manager.set_expression("eye_roll", duration_ms=2000)

    def _handle_panic(self, meta: Dict):
        duration = meta.get("duration", 3000)
        from PyQt5.QtCore import QTimer

        QTimer.singleShot(duration, self._on_panic_end)

    def _on_panic_end(self):
        self.expression_manager.reset_expression()
        self.set_state(PetState.IDLE)

    def _handle_ai_response(self, meta: Dict):
        response_text = meta.get("text", "")
        if response_text:
            self.expression_manager.set_expression(
                "shy", duration_ms=len(response_text) * 100
            )
            self.set_state(PetState.AI_TALKING)

    def _handle_motion_end(self, meta: Dict):
        interrupted = meta.get("interrupted", False)
        if not interrupted:
            self.set_state(PetState.IDLE)

    def _handle_mouse_enter(self, meta: Dict):
        if self._current_state == PetState.IDLE:
            pass

    def _handle_mouse_leave(self, meta: Dict):
        if self._current_state == PetState.INTERACTING:
            self.set_state(PetState.IDLE)

    def _start_idle_timer(self):
        self._stop_idle_timer()
        if self._idle_interval_min <= 0:
            return

        interval = random.randint(self._idle_interval_min, self._idle_interval_max)

        self._idle_timer = QTimer()
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timer)
        self._idle_timer.start(interval)

    def _stop_idle_timer(self):
        if self._idle_timer:
            self._idle_timer.stop()
            self._idle_timer = None

    def _on_idle_timer(self):
        if self._current_state == PetState.IDLE:
            self.trigger_random_idle_action()

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "current_state": self._current_state.name,
            "previous_state": (
                self._previous_state.name if self._previous_state else None
            ),
            "is_active": self._is_active,
            "event_queue_size": len(self._event_queue),
            "idle_interval": f"{self._idle_interval_min}-{self._idle_interval_max}ms",
        }
