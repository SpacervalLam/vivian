"""桌宠心情状态管理模块

负责管理桌宠的心情状态、状态变化规则、以及与LLM的交互协议。
所有状态100%存储在用户本地，不上传任何服务器。
"""

import json
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from enum import Enum

from loguru import logger
from PyQt5.QtCore import QObject, pyqtSignal


class PetState(Enum):
    """桌宠衍生状态"""
    HAPPY = "happy"       # 愉悦>70，精力>50
    EXCITED = "excited"   # 愉悦>80，精力>70
    TIRED = "tired"       # 精力<30
    SLEEPY = "sleepy"     # 精力<20，且在22:00-8:00
    BORED = "bored"       # 无聊>70
    SAD = "sad"           # 愉悦<30
    ANGRY = "angry"       # 愉悦<20
    NEUTRAL = "neutral"   # 默认状态


class Mood:
    """核心心情维度"""
    
    def __init__(self, happiness: int = 50, energy: int = 100, intimacy: int = 50, boredom: int = 0):
        self.happiness = max(0, min(100, happiness))  # 愉悦度：影响语气积极程度
        self.energy = max(0, min(100, energy))         # 精力值：影响回复长度和活跃度
        self.intimacy = max(0, min(100, intimacy))     # 亲密度：影响对话的亲密程度
        self.boredom = max(0, min(100, boredom))       # 无聊度：长时间无互动会上升
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "happiness": self.happiness,
            "energy": self.energy,
            "intimacy": self.intimacy,
            "boredom": self.boredom
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, int]) -> "Mood":
        return cls(
            happiness=data.get("happiness", 50),
            energy=data.get("energy", 100),
            intimacy=data.get("intimacy", 50),
            boredom=data.get("boredom", 0)
        )
    
    def apply_delta(self, delta: Dict[str, int]):
        """应用状态变化量"""
        if "happiness" in delta:
            self.happiness = max(0, min(100, self.happiness + delta["happiness"]))
        if "energy" in delta:
            self.energy = max(0, min(100, self.energy + delta["energy"]))
        if "intimacy" in delta:
            self.intimacy = max(0, min(100, self.intimacy + delta["intimacy"]))
        if "boredom" in delta:
            self.boredom = max(0, min(100, self.boredom + delta["boredom"]))


class PetStatus:
    """完整状态对象"""
    
    def __init__(self):
        self.mood = Mood()
        self.state = PetState.NEUTRAL
        self.last_interaction_time = time.time()
        self.awake_time = time.time()
        self.consecutive_days = 1
        self._last_save_time = 0
        self._save_interval = 60  # 每分钟自动保存一次
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mood": self.mood.to_dict(),
            "state": self.state.value,
            "last_interaction_time": self.last_interaction_time,
            "awake_time": self.awake_time,
            "consecutive_days": self.consecutive_days
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PetStatus":
        status = cls()
        status.mood = Mood.from_dict(data.get("mood", {}))
        status.state = PetState(data.get("state", "neutral"))
        status.last_interaction_time = data.get("last_interaction_time", time.time())
        status.awake_time = data.get("awake_time", time.time())
        status.consecutive_days = data.get("consecutive_days", 1)
        return status


class StatusSignalEmitter(QObject):
    """专为状态管理维护的 PyQt 跨线程安全信号站"""
    status_changed = pyqtSignal(dict)  # 发射前端所需的状态字典
    action_triggered = pyqtSignal(dict)  # 发射动作/表情指令

class PetStatusManager:
    """心情状态管理器（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    COMMAND_TAG_START = "<|PET_COMMAND|>"
    COMMAND_TAG_END = "<|/PET_COMMAND|>"
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self.status = PetStatus()
        self._persistence_path = self._get_persistence_path()
        self._update_thread = None
        self._running = True
        self._callback = None
        self.signals = StatusSignalEmitter()  # 替代原有的 self._callback = None
        
        self._load_status()
        self._start_update_thread()
    
    def _get_persistence_path(self) -> str:
        """获取持久化文件路径"""
        if os.name == "nt":
            app_data = os.getenv("APPDATA") or os.path.expanduser("~")
            user_data_dir = os.path.join(app_data, "Vivian", "status")
        else:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".vivian", "status")
        
        os.makedirs(user_data_dir, exist_ok=True)
        return os.path.join(user_data_dir, "pet_status.json")
    
    def _load_status(self):
        """加载持久化的状态"""
        try:
            if os.path.exists(self._persistence_path):
                with open(self._persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.status = PetStatus.from_dict(data)
                    self._check_consecutive_days()
                logger.info(f"[PetStatus] 已加载状态")
        except Exception as e:
            logger.error(f"[PetStatus] 加载状态失败: {e}")
    
    def _save_status(self):
        """持久化状态"""
        try:
            data = self.status.to_dict()
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[PetStatus] 状态已保存")
        except Exception as e:
            logger.error(f"[PetStatus] 保存状态失败: {e}")
    
    def _check_consecutive_days(self):
        """检查连续陪伴天数"""
        try:
            last_save_day = datetime.fromtimestamp(self.status.last_interaction_time).date()
            today = datetime.now().date()
            days_diff = (today - last_save_day).days
            
            if days_diff == 0:
                pass
            elif days_diff == 1:
                self.status.consecutive_days += 1
            else:
                self.status.consecutive_days = 1
            
            self.status.awake_time = time.time()
        except Exception as e:
            logger.error(f"[PetStatus] 检查连续天数失败: {e}")
    
    def _start_update_thread(self):
        """启动状态更新线程"""
        def update_loop():
            while self._running:
                self._update_status()
                time.sleep(60)  # 每分钟更新一次
        
        self._update_thread = threading.Thread(target=update_loop, daemon=True)
        self._update_thread.start()
        logger.info("[PetStatus] 状态更新线程已启动")
    
    def _update_status(self):
        """根据时间流逝更新状态"""
        now = time.time()
        time_since_last_interaction = now - self.status.last_interaction_time
        
        # 连续无互动处理
        hours_since_interaction = time_since_last_interaction / 3600
        
        if hours_since_interaction >= 1:
            # 连续1小时无互动：无聊+10，精力-2
            self.status.mood.boredom = min(100, self.status.mood.boredom + 10)
            self.status.mood.energy = max(0, self.status.mood.energy - 2)
            
            if hours_since_interaction >= 3:
                # 连续3小时无互动：无聊+20，精力-5
                self.status.mood.boredom = min(100, self.status.mood.boredom + 20)
                self.status.mood.energy = max(0, self.status.mood.energy - 5)
        
        # 夜间精力消耗（22:00-8:00）
        current_hour = datetime.now().hour
        if 22 <= current_hour or current_hour < 8:
            self.status.mood.energy = max(0, self.status.mood.energy - 10)
        
        # 心情趋向于平静
        if self.status.mood.happiness > 50:
            self.status.mood.happiness -= 1
        elif self.status.mood.happiness < 50:
            self.status.mood.happiness += 1
        
        # 更新衍生状态
        self._update_derived_state()
        
        # 自动保存
        if now - self.status._last_save_time >= self.status._save_interval:
            self._save_status()
            self.status._last_save_time = now
        
        # 发射信号，PyQt 会自动利用内部事件队列将请求投递至主线程执行
        frontend_data = self.get_status_for_frontend()
        self.signals.status_changed.emit(frontend_data)
    
    def _update_derived_state(self):
        """根据心情值计算衍生状态"""
        m = self.status.mood
        current_hour = datetime.now().hour
        is_night = 22 <= current_hour or current_hour < 8
        
        if m.happiness > 80 and m.energy > 70:
            self.status.state = PetState.EXCITED
        elif m.happiness > 70 and m.energy > 50:
            self.status.state = PetState.HAPPY
        elif m.energy < 20 and is_night:
            self.status.state = PetState.SLEEPY
        elif m.energy < 30:
            self.status.state = PetState.TIRED
        elif m.boredom > 70:
            self.status.state = PetState.BORED
        elif m.happiness < 20:
            self.status.state = PetState.ANGRY
        elif m.happiness < 30:
            self.status.state = PetState.SAD
        else:
            self.status.state = PetState.NEUTRAL
    
    def record_interaction(self, user_input: str):
        """记录用户交互，更新状态"""
        self.status.last_interaction_time = time.time()
        
        self.status.mood.boredom = max(0, self.status.mood.boredom - 5)
        
        self._update_derived_state()
    
    def record_click(self):
        """记录点击/抚摸交互"""
        self.status.last_interaction_time = time.time()
        self.status.mood.happiness = min(100, self.status.mood.happiness + 3)
        self.status.mood.boredom = max(0, self.status.mood.boredom - 5)
        logger.debug(f"[PetStatus] 检测到点击，愉悦度+3，无聊度-5")
        self._update_derived_state()
    
    def parse_llm_command(self, response: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """解析LLM响应中的命令块
        
        Args:
            response: LLM响应文本
            
        Returns:
            (清理后的文本, 命令数据)
        """
        if self.COMMAND_TAG_START not in response:
            return response, None
        
        try:
            start_idx = response.find(self.COMMAND_TAG_START)
            end_idx = response.find(self.COMMAND_TAG_END)
            
            if end_idx == -1:
                return response, None
            
            # 提取命令块
            command_text = response[start_idx + len(self.COMMAND_TAG_START):end_idx].strip()
            
            # 清理响应文本
            cleaned_response = response[:start_idx] + response[end_idx + len(self.COMMAND_TAG_END):]
            cleaned_response = cleaned_response.strip()
            
            # 解析JSON
            command_data = json.loads(command_text)
            return cleaned_response, command_data
            
        except json.JSONDecodeError as e:
            logger.error(f"[PetStatus] 解析命令JSON失败: {e}")
            return response, None
        except Exception as e:
            logger.error(f"[PetStatus] 解析LLM命令失败: {e}")
            return response, None
    
    def apply_command(self, command_data: Dict[str, Any]):
        """应用LLM命令更新状态"""
        try:
            # 处理心情更新
            if "mood_update" in command_data:
                self.status.mood.apply_delta(command_data["mood_update"])
                logger.debug(f"[PetStatus] 应用心情更新: {command_data['mood_update']}")
            
            # 处理动作指令（由前端处理）
            action = command_data.get("action")
            expression = command_data.get("expression")
            
            if action or expression:
                # 使用信号替代回调，确保跨线程安全
                self.signals.action_triggered.emit({
                    "action": action,
                    "expression": expression
                })
            
            self._update_derived_state()
            
            # 发射状态变化信号
            frontend_data = self.get_status_for_frontend()
            self.signals.status_changed.emit(frontend_data)
            
        except Exception as e:
            logger.error(f"[PetStatus] 应用命令失败: {e}")
    
    def update_status_values(self, happiness_delta: int = 0, energy_delta: int = 0, 
                            intimacy_delta: int = 0, boredom_delta: int = 0):
        """增量更新状态值（供MoodExtractionRunnable调用）"""
        delta = {}
        if happiness_delta != 0:
            delta["happiness"] = happiness_delta
        if energy_delta != 0:
            delta["energy"] = energy_delta
        if intimacy_delta != 0:
            delta["intimacy"] = intimacy_delta
        if boredom_delta != 0:
            delta["boredom"] = boredom_delta
        
        if delta:
            self.status.mood.apply_delta(delta)
            self._update_derived_state()
            logger.debug(f"[PetStatus] 增量更新状态: {delta}")
            
            # 发射状态变化信号
            frontend_data = self.get_status_for_frontend()
            self.signals.status_changed.emit(frontend_data)
    
    def get_status_prompt(self) -> str:
        """Get the status prompt for LLM"""
        state_names = {
            PetState.HAPPY: "happy",
            PetState.EXCITED: "excited",
            PetState.TIRED: "tired",
            PetState.SLEEPY: "sleepy",
            PetState.BORED: "bored",
            PetState.SAD: "sad",
            PetState.ANGRY: "angry",
            PetState.NEUTRAL: "neutral"
        }
        
        mood = self.status.mood
        state_name = state_names.get(self.status.state, "neutral")
        
        energy_desc = "energetic" if mood.energy > 70 else "normal" if mood.energy > 30 else "tired"
        intimacy_desc = "intimate" if mood.intimacy > 70 else "friendly" if mood.intimacy > 30 else "stranger"
        
        return f"""[Current Status]
Mood: {state_name} (happiness: {mood.happiness}/100)
Energy: {energy_desc} ({mood.energy}/100)
Intimacy: {intimacy_desc} ({mood.intimacy}/100)

Adjust your tone according to the current state:
- When happy/excited: Use more exclamation marks and cute expressions, lively tone
- When tired/sleepy: Short responses, lazy tone
- When bored: Show boredom, may need user's company
- When sad: Depressed tone
- When angry: Cold tone, short responses
- When neutral: Normal friendly tone"""
    
    def get_status_for_frontend(self) -> Dict[str, Any]:
        """获取状态信息供前端展示"""
        return {
            "mood": self.status.mood.to_dict(),
            "state": self.status.state.value,
            "state_label": {
                PetState.HAPPY: "开心",
                PetState.EXCITED: "兴奋",
                PetState.TIRED: "疲惫",
                PetState.SLEEPY: "困倦",
                PetState.BORED: "无聊",
                PetState.SAD: "难过",
                PetState.ANGRY: "生气",
                PetState.NEUTRAL: "平静"
            }.get(self.status.state, "平静"),
            "consecutive_days": self.status.consecutive_days,
            "last_interaction_time": self.status.last_interaction_time
        }
    
    def set_callback(self, callback):
        """设置状态变化回调"""
        self._callback = callback
    
    def shutdown(self):
        """关闭管理器"""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=1)
        self._save_status()
        logger.info("[PetStatus] 状态管理器已关闭")


def get_pet_status_manager() -> PetStatusManager:
    """获取状态管理器单例"""
    return PetStatusManager()