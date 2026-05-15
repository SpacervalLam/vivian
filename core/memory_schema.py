import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MemoryNode:
    """记忆单元：智能体的最小记忆原子"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""  # 记忆内容
    role: str = "user"  # user / assistant / system (观察到的)
    timestamp: float = field(default_factory=time.time)

    # 元数据 (Meta Data) - 关键改进
    importance: float = 0.5  # 重要性打分 (0-1)，决定是否会被遗忘
    emotion: str = "neutral"  # 当时的情感状态
    keywords: List[str] = field(
        default_factory=list
    )  # 实体标签 (e.g., ["Python", "ProjectA"])
    source: str = "chat"  # chat / vision / document
    metadata: Dict = field(default_factory=dict)  # 额外的元数据，可存储更多信息

    def to_dict(self):
        return self.__dict__
