"""
时间戳记忆系统

支持时间感知的记忆管理，包括时间戳、记忆总结、长期偏好等功能。
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any, Dict, List, Optional, Callable

from loguru import logger
from pydantic import BaseModel, Field


class TimeStampedMessage(BaseModel):
    """带时间戳的消息"""
    content: str = Field(..., description="消息内容")
    message_type: str = Field(..., description="消息类型: 'human' 或 'ai'")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now, description="时间戳")
    is_summarized: bool = Field(default=False, description="是否已总结")
    importance: float = Field(default=0.5, description="重要性")


class TimeStampedSummary(BaseModel):
    """记忆总结"""
    content: str = Field(..., description="总结内容")
    start_time: datetime.datetime = Field(..., description="开始时间")
    end_time: datetime.datetime = Field(..., description="结束时间")


class TimeStampedMemory:
    """
    时间戳记忆系统
    """
    
    def __init__(
        self,
        llm=None,
        summary_threshold: int = 40,
        temp_memory_hours: int = 2,
        summary_memory_hours: int = 24,
        memory_manager=None
    ):
        self.llm = llm
        self.summary_threshold = summary_threshold
        self.temp_memory_hours = temp_memory_hours
        self.summary_memory_hours = summary_memory_hours
        self.memory_manager = memory_manager
        
        self.raw_messages: List[TimeStampedMessage] = []
        self.summaries: List[TimeStampedSummary] = []
        self._last_interaction_time: Optional[datetime.datetime] = None
        
        if self.memory_manager:
            self._load_existing_memories(self.memory_manager)
    
    def _detect_name_in_content(self, content: str) -> bool:
        """检测名字信息"""
        name_patterns = [
            r'我是[\u4e00-\u9fa5]{2,}(?!谁|什么|哪|几)',
            r'我的名字是[\u4e00-\u9fa5]{2,}',
            r'叫我[\u4e00-\u9fa5]{2,}',
            r'名字是[\u4e00-\u9fa5]{2,}',
            r'称呼我[\u4e00-\u9fa5]{2,}',
            r'我叫[\u4e00-\u9fa5]{2,}',
            r'我是[A-Za-z]{2,}(?!谁|什么|哪|几)',
            r'我的名字是[A-Za-z]{2,}',
            r'叫我[A-Za-z]{2,}',
            r'名字是[A-Za-z]{2,}',
            r'称呼我[A-Za-z]{2,}',
            r'我叫[A-Za-z]{2,}',
        ]
        import re
        for pattern in name_patterns:
            if re.search(pattern, content):
                return True
        return False

    def _load_existing_memories(self, memory_manager):
        """加载已有记忆"""
        try:
            short_term_memories = memory_manager.list_short_term_memories()
            long_term_memories = memory_manager.list_long_term_memories()
            
            for memory in short_term_memories:
                try:
                    created_at = memory.created_at
                    if isinstance(created_at, str):
                        created_at = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    
                    message_type = "human" if memory.role == "user" else "ai"
                    
                    message = TimeStampedMessage(
                        content=memory.content,
                        message_type=message_type,
                        timestamp=created_at
                    )
                    self.raw_messages.append(message)
                    
                    if self._last_interaction_time is None or created_at > self._last_interaction_time:
                        self._last_interaction_time = created_at
                except Exception as e:
                    logger.warning(f"加载短期记忆失败: {e}")
            
            logger.info(f"已加载 {len(short_term_memories)} 条短期记忆和 {len(long_term_memories)} 条长期记忆")
        
        except Exception as e:
            logger.warning(f"加载已有记忆失败: {e}")
    
    def add_message(
        self,
        content: str,
        message_type: str = "human",
        importance: float = 0.5,
        timestamp: Optional[datetime.datetime] = None
    ) -> None:
        """添加消息"""
        if timestamp is None:
            timestamp = datetime.datetime.now()
        
        message = TimeStampedMessage(
            content=content,
            message_type=message_type,
            timestamp=timestamp,
            importance=importance
        )
        self.raw_messages.append(message)
        self._last_interaction_time = timestamp
        
        if len(self.raw_messages) >= self.summary_threshold:
            self._summarize_old_messages()
    
    def _summarize_old_messages(self) -> None:
        """总结旧消息"""
        if len(self.raw_messages) < self.summary_threshold:
            return
        
        keep_count = 8
        messages_to_summarize = self.raw_messages[:-keep_count]
        self.raw_messages = self.raw_messages[-keep_count:]
        
        if not messages_to_summarize:
            return
        
        for msg in messages_to_summarize:
            msg.is_summarized = True
        
        start_time = min(m.timestamp for m in messages_to_summarize)
        end_time = max(m.timestamp for m in messages_to_summarize)
        
        summary_content = self._generate_summary(messages_to_summarize)
        
        summary = TimeStampedSummary(
            content=summary_content,
            start_time=start_time,
            end_time=end_time
        )
        self.summaries.append(summary)
        
        logger.debug(f"[TimeStampedMemory] 总结 {len(messages_to_summarize)} 条消息到: {summary_content[:100]}...")
    
    def _generate_summary(self, messages: List[TimeStampedMessage]) -> str:
        """生成总结"""
        if not messages:
            return ""
        
        dialogue_parts = []
        for msg in messages:
            role = "用户" if msg.message_type == "human" else "AI"
            dialogue_parts.append(f"{role}: {msg.content}")
        
        dialogue_text = "\n".join(dialogue_parts)
        
        if self.llm:
            try:
                prompt = f"""请总结以下对话的核心内容（用中文回复）：

{dialogue_text}

总结要求：
1. 提取关键信息和重要结论
2. 保留重要的用户偏好和习惯
3. 简洁明了，不超过100字"""
                
                from core.ai_manager import ai_manager
                if ai_manager:
                    response = ai_manager.query_short(prompt, use_history=False)
                    if response and not response.startswith("嗯"):
                        return response.strip()
            except Exception as e:
                logger.warning(f"LLM总结失败: {e}")
        
        key_topics = []
        for msg in messages:
            if msg.message_type == "human":
                words = msg.content.split()
                key_topics.extend(words[:10])
        
        summary = f"对话总结：{' '.join(key_topics[:20])}"
        return summary
    
    def get_context_window(self, hours: int = 2) -> List[TimeStampedMessage]:
        """获取时间窗口内的消息"""
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
        return [
            msg for msg in self.raw_messages
            if msg.timestamp >= cutoff_time and not msg.is_summarized
        ]
    
    def load_memory_variables(self, current_input: str) -> Dict[str, Any]:
        """加载记忆变量"""
        recent_summary = ""
        if self.summaries:
            recent_summary = self.summaries[-1].content
        
        context_window = self.get_context_window(hours=self.temp_memory_hours)
        
        history_lines = []
        if recent_summary:
            history_lines.append(f"[历史总结] {recent_summary}")
        
        for msg in context_window[-10:]:
            role = "用户" if msg.message_type == "human" else "AI"
            history_lines.append(f"{role}: {msg.content}")
        
        for summary in self.summaries[-3:]:
            if summary.content not in history_lines:
                history_lines.append(f"[记忆] {summary.content}")
        
        return {
            "recent_summary": recent_summary,
            "context_window": "\n".join(history_lines),
            "history": "\n".join(history_lines),
            "last_interaction": self._last_interaction_time
        }
    
    def get_system_prompt_additions(self) -> str:
        """获取系统提示词补充"""
        return ""
    
    def clear(self) -> None:
        """清除所有记忆"""
        self.raw_messages.clear()
        self.summaries.clear()
        self._last_interaction_time = None


def build_time_aware_system_prompt(base_prompt: str, memory_vars: Dict[str, Any]) -> str:
    """构建时间感知的系统提示词"""
    prompt_parts = [base_prompt]
    
    if memory_vars.get("recent_summary"):
        prompt_parts.append("\n最近的对话总结:")
        prompt_parts.append(memory_vars["recent_summary"])
    
    return "\n".join(prompt_parts)
