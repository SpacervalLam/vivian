from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger
from pydantic import BaseModel, Field


class History(BaseModel):
    """对话历史模型"""

    role: str = Field(..., description="角色，user或assistant")
    content: str = Field(..., description="对话内容")
    timestamp: float = Field(default_factory=lambda: time.time(), description="时间戳")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    def to_msg_tuple(self) -> Tuple[str, str]:
        """转换为消息元组"""
        return "ai" if self.role == "assistant" else "human", self.content

    @classmethod
    def from_data(cls, data: Union[List, Tuple, Dict]) -> "History":
        """从不同格式数据创建History对象"""
        try:
            if isinstance(data, (list, tuple)) and len(data) >= 2:
                return cls(role=data[0], content=data[1])
            elif isinstance(data, dict):
                return cls(**data)
            logger.error(f"无法从{type(data)}创建History对象，数据格式不支持")
            raise ValueError(f"无法从{type(data)}创建History对象")
        except Exception as e:
            logger.error(f"创建History对象失败: {e}", exc_info=True)
            raise


class DialogueManager:
    """对话管理器，负责对话历史管理和上下文处理"""

    def __init__(self, max_history_len: int = 10):
        """初始化对话管理器
        
        Args:
            max_history_len: 最大历史长度
        """
        try:
            self.max_history_len = max_history_len
            self.history: List[History] = []
            self.name_call_cooldown = 0
            self.user_name = "Master"
            
            self.topic_activeness = 10
            self.last_topic_initiator = "user"
            
            self.end_keywords = {"嗯", "哦", "好", "行", "ok", "收到", "知道了", "没问题",
                               "好的", "好哒", "嗯嗯", "哦哦", "对呀", "是的", "哈哈",
                               "嗯~", "哦~", "好~", "行~", "好哒~", "嗯嗯~"}
            
            logger.debug(f"对话管理器初始化完成，最大历史长度: {max_history_len}")
        except Exception as e:
            logger.error(f"初始化对话管理器失败: {e}", exc_info=True)
            raise

    def set_user_name(self, name: str) -> None:
        """
        设置用户名

        Args:
            name: 用户名称
        """
        try:
            self.user_name = name if name else "Master"
            logger.debug(f"设置用户名: {self.user_name}")
        except Exception as e:
            logger.error(f"设置用户名失败: {e}", exc_info=True)

    def get_user_name(self) -> str:
        """
        获取用户名

        Returns:
            用户名称
        """
        return self.user_name

    def is_in_cooldown(self) -> bool:
        """
        检查是否处于称呼冷却期

        Returns:
            True 如果处于冷却期，否则 False
        """
        return self.name_call_cooldown > 0

    def decrement_cooldown(self) -> None:
        """
        减少冷却计数器
        """
        if self.name_call_cooldown > 0:
            self.name_call_cooldown -= 1
            logger.debug(f"冷却计数器递减: {self.name_call_cooldown}")

    def reset_cooldown(self, turns: int = 4) -> None:
        """
        重置冷却计数器

        Args:
            turns: 冷却轮数，默认为4轮
        """
        self.name_call_cooldown = turns
        logger.debug(f"重置冷却计数器为: {turns}")

    def check_and_update_cooldown(self, response: str) -> bool:
        """
        检查响应中是否包含用户名，并更新冷却计数器

        Args:
            response: 响应文本

        Returns:
            True 如果响应中包含用户名，否则 False
        """
        try:
            contains_name = self.user_name in response
            if contains_name:
                self.reset_cooldown()
                logger.debug(f"响应中包含用户名，重置冷却计数器")
            else:
                self.decrement_cooldown()
            return contains_name
        except Exception as e:
            logger.error(f"检查用户名失败: {e}", exc_info=True)
            return False

    def is_pure_emoji(self, text: str) -> bool:
        """
        检测文本是否为纯表情符号

        Args:
            text: 输入文本

        Returns:
            True 如果是纯表情，否则 False
        """
        try:
            text = text.strip()
            if not text:
                return False
            
            emoji_pattern = r'[\u2700-\u27BF\uE000-\uF8FF\u2600-\u26FF\u1F300-\u1F6FF\u1F900-\u1F9FF]+'
            import re
            emojis = re.findall(emoji_pattern, text)
            return len(''.join(emojis)) == len(text)
        except Exception as e:
            logger.error(f"纯表情检测失败: {e}", exc_info=True)
            return False

    def should_generate_full_response(self, user_message: str) -> bool:
        """
        判断是否应该生成完整响应（话题终结检测）

        Args:
            user_message: 用户消息

        Returns:
            True 如果应该生成完整响应，False 如果只能简短回应，None 如果不回复
        """
        try:
            message = user_message.strip()
            
            # 空消息不回复
            if not message:
                return None
            
            # 纯表情检测
            if self.is_pure_emoji(message):
                return False
            
            # 单关键词检测
            if message.lower() in self.end_keywords:
                return False
            
            # 短消息检测（长度≤3且包含终结关键词）
            if len(message) <= 3:
                if any(keyword in message for keyword in self.end_keywords):
                    return False
            
            # 连续简短回应检测（用户连续2轮发简短消息）
            recent_user_messages = [msg for msg in self.history[-4:] if msg.role == "user"]
            if len(recent_user_messages) >= 2:
                prev1 = recent_user_messages[-1].content.strip()
                prev2 = recent_user_messages[-2].content.strip()
                if len(prev1) <= 3 and len(prev2) <= 3:
                    return None
            
            return True
        except Exception as e:
            logger.error(f"话题终结检测失败: {e}", exc_info=True)
            return True

    def update_topic_activeness(self, user_message: str, is_assistant_initiated: bool = False) -> None:
        """
        更新话题活跃度分数

        Args:
            user_message: 用户消息
            is_assistant_initiated: 是否是AI发起的话题
        """
        try:
            message = user_message.strip()
            
            # 更新话题发起者
            if not is_assistant_initiated:
                self.last_topic_initiator = "user"
            else:
                self.last_topic_initiator = "assistant"
            
            # 用户主动发起新话题（包含疑问词）
            question_words = {"吗", "呢", "什么", "怎么", "为什么", "哪", "谁", "多少", "几"}
            if any(word in message for word in question_words):
                self.topic_activeness += 10
                logger.debug(f"用户发起新话题，活跃度 +10，当前: {self.topic_activeness}")
            # 用户发送长消息
            elif len(message) > 10:
                self.topic_activeness += 3
                logger.debug(f"用户发送长消息，活跃度 +3，当前: {self.topic_activeness}")
            # 用户发送简短回应
            elif len(message) <= 3 or message.lower() in self.end_keywords:
                self.topic_activeness -= 5
                logger.debug(f"用户发送简短回应，活跃度 -5，当前: {self.topic_activeness}")
            
            # 每轮对话自然衰减
            self.topic_activeness -= 1
            logger.debug(f"自然衰减 -1，当前活跃度: {self.topic_activeness}")
            
            # 确保活跃度在合理范围内
            self.topic_activeness = max(0, min(20, self.topic_activeness))
        except Exception as e:
            logger.error(f"更新话题活跃度失败: {e}", exc_info=True)

    def is_topic_active(self) -> bool:
        """
        检查话题是否活跃

        Returns:
            True 如果话题活跃，否则 False
        """
        return self.topic_activeness > 0

    def reset_topic_activeness(self) -> None:
        """
        重置话题活跃度（用户发起新话题时调用）
        """
        self.topic_activeness = 10
        logger.debug(f"重置话题活跃度为: {self.topic_activeness}")

    def get_topic_activeness(self) -> int:
        """
        获取当前话题活跃度

        Returns:
            活跃度分数
        """
        return self.topic_activeness

    def add_message(
        self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        添加对话消息

        Args:
            role: 角色，user或assistant
            content: 对话内容
            metadata: 元数据
        """
        try:
            if metadata is None:
                metadata = {}

            # 验证角色
            if role not in ["user", "assistant"]:
                logger.warning(f"无效角色: {role}，将使用user角色")
                role = "user"

            message = History(role=role, content=content, metadata=metadata)
            self.history.append(message)

            # 保持历史长度不超过最大值
            if len(self.history) > self.max_history_len:
                removed_msg = self.history.pop(0)
                logger.debug(
                    f"历史消息超过最大长度，移除最早消息: {removed_msg.content[:20]}..."
                )

            logger.debug(f"添加对话消息: {role} -> {content[:20]}...")
        except Exception as e:
            logger.error(f"添加对话消息失败: {e}", exc_info=True)

    def get_history(self, max_len: Optional[int] = None) -> List[History]:
        """
        获取对话历史

        Args:
            max_len: 返回的最大历史长度，默认使用初始化时的max_history_len

        Returns:
            对话历史列表
        """
        try:
            if max_len is None:
                max_len = self.max_history_len

            result = self.history[-max_len:]
            logger.debug(f"获取对话历史，返回 {len(result)} 条消息")
            return result
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}", exc_info=True)
            return []

    def get_history_as_messages(
        self, max_len: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        获取对话历史，格式化为模型输入的消息格式

        Args:
            max_len: 返回的最大历史长度

        Returns:
            消息列表，每个消息包含role和content字段
        """
        try:
            history = self.get_history(max_len)
            result = [{"role": msg.role, "content": msg.content} for msg in history]
            logger.debug(f"获取格式化对话历史，返回 {len(result)} 条消息")
            return result
        except Exception as e:
            logger.error(f"获取格式化对话历史失败: {e}", exc_info=True)
            return []

    def get_context(self, user_input: str, max_len: Optional[int] = None) -> str:
        """
        构建上下文，包含对话历史和当前用户输入

        Args:
            user_input: 当前用户输入
            max_len: 使用的历史长度

        Returns:
            构建好的上下文字符串
        """
        try:
            history = self.get_history_as_messages(max_len)
            context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
            context += f"\nuser: {user_input}"

            logger.debug(f"构建上下文: {context[:100]}...")
            return context
        except Exception as e:
            logger.error(f"构建上下文失败: {e}", exc_info=True)
            return f"user: {user_input}"

    def clear_history(self) -> None:
        """
        清空对话历史
        """
        try:
            self.history.clear()
            logger.info("对话历史已清空")
        except Exception as e:
            logger.error(f"清空对话历史失败: {e}", exc_info=True)

    def get_history_length(self) -> int:
        """
        获取对话历史长度

        Returns:
            对话历史长度
        """
        try:
            length = len(self.history)
            logger.debug(f"获取对话历史长度: {length}")
            return length
        except Exception as e:
            logger.error(f"获取对话历史长度失败: {e}", exc_info=True)
            return 0

    def get_last_message(self) -> Optional[History]:
        """
        获取最后一条消息

        Returns:
            最后一条消息，如果没有则返回None
        """
        try:
            if self.history:
                last_msg = self.history[-1]
                logger.debug(
                    f"获取最后一条消息: {last_msg.role} -> {last_msg.content[:20]}..."
                )
                return last_msg
            logger.debug("没有对话历史，返回None")
            return None
        except Exception as e:
            logger.error(f"获取最后一条消息失败: {e}", exc_info=True)
            return None

    def is_pure_emoji(self, text: str) -> bool:
        """
        检测文本是否为纯表情符号

        Args:
            text: 输入文本

        Returns:
            True 如果是纯表情，否则 False
        """
        text = text.strip()
        if not text:
            return False
        
        emoji_pattern = r'[\u2700-\u27BF\uE000-\uF8FF\u2600-\u26FF\u1F300-\u1F6FF\u1F900-\u1F9FF]+'
        emojis = re.findall(emoji_pattern, text)
        return len(''.join(emojis)) == len(text)

    def get_topic_activeness(self) -> int:
        """
        获取当前话题活跃度（保持兼容性）

        Returns:
            活跃度分数
        """
        return self.topic_activeness

    def sync_to_memory(self) -> None:
        """
        同步对话历史到记忆系统（空实现，保持兼容性）
        """
        pass

    def _get_history_file_path(self) -> str:
        """
        获取对话历史保存文件路径
        """
        if os.name == 'nt':
            app_data = os.getenv("APPDATA") or os.path.expanduser("~")
            history_dir = os.path.join(app_data, "VivianDeskpet", "history")
        else:
            history_dir = os.path.join(
                os.path.expanduser("~"), ".vivian_deskpet", "history"
            )
        os.makedirs(history_dir, exist_ok=True)
        return os.path.join(history_dir, "dialogue_history.json")

    def save_history(self, max_entries: int = 24) -> None:
        """
        保存对话历史到文件
        
        Args:
            max_entries: 最大保存条目数，默认24条（12轮对话）
        """
        try:
            history_data = []
            # 只保存最近的 max_entries 条记录
            recent_history = self.history[-max_entries:]
            
            for msg in recent_history:
                history_data.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "metadata": msg.metadata,
                })
            
            file_path = self._get_history_file_path()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"对话历史已保存到 {file_path}，共 {len(history_data)} 条")
        except Exception as e:
            logger.error(f"保存对话历史失败: {e}", exc_info=True)

    def load_history(self) -> None:
        """
        从文件加载对话历史
        """
        try:
            file_path = self._get_history_file_path()
            if not os.path.exists(file_path):
                logger.debug(f"对话历史文件不存在: {file_path}")
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            for item in history_data:
                # 使用 from_data 方法创建 History 对象
                self.history.append(History.from_data(item))
            
            logger.info(f"从 {file_path} 加载了 {len(history_data)} 条对话历史")
        except Exception as e:
            logger.error(f"加载对话历史失败: {e}", exc_info=True)
