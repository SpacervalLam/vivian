from enum import Enum
from typing import Any, Dict


class AITaskType(Enum):
    """AI任务类型枚举"""

    SIMPLE_CHAT = 1  # 简单闲聊
    COMPLEX_QUESTION = 2  # 复杂问题
    COMMAND = 3  # 控制指令
    SYSTEM_CONTROL = 4  # 系统控制指令
    EMOTION_ANALYSIS = 5  # 情感分析
    ENVIRONMENT_PERCEPTION = 6  # 环境感知


class AIResponse:
    """AI响应结果类"""

    def __init__(
        self,
        text: str,
        motion: str = "idle",
        expression: str = "smile",
        emotion_score: float = 0.0,
    ):
        self.text = text
        self.motion = motion
        self.expression = expression
        self.emotion_score = emotion_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "motion": self.motion,
            "expression": self.expression,
            "emotion_score": self.emotion_score,
        }
