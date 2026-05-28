"""
Time-Stamped Memory System

Supports time-aware memory management, including timestamps, memory summarization, long-term preferences, and more.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any, Dict, List, Optional, Callable

from loguru import logger
from pydantic import BaseModel, Field


class TimeStampedMessage(BaseModel):
    """Time-stamped message"""
    content: str = Field(..., description="Message content")
    message_type: str = Field(..., description="Message type: 'human' or 'ai'")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now, description="Timestamp")
    is_summarized: bool = Field(default=False, description="Whether summarized")
    importance: float = Field(default=0.5, description="Importance")


class MemorySummary(BaseModel):
    """Memory summary"""
    content: str = Field(..., description="Summary content")
    start_time: datetime.datetime = Field(..., description="Start time")
    end_time: datetime.datetime = Field(..., description="End time")


class TimeStampedMemory:
    """
    Time-stamped memory system
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
        """Detect name information"""
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
        """Load existing memories"""
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
                    logger.warning(f"Failed to load short-term memory: {e}")
            logger.info(f"Loaded {len(short_term_memories)} short-term memories and {len(long_term_memories)} long-term memories")
        except Exception as e:
            logger.warning(f"Failed to load existing memory: {e}")
    
    def add_message(
        self,
        content: str,
        message_type: str = "human",
        importance: float = 0.5,
        timestamp: Optional[datetime.datetime] = None
    ) -> None:
        """Add message"""
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
        """Summarize old messages"""
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
        
        logger.debug(f"[TimeStampedMemory] Summarized {len(messages_to_summarize)} messages to: {summary_content[:100]}...")
    
    def _generate_summary(self, messages: List[TimeStampedMessage]) -> str:
        """Generate summary"""
        if not messages:
            return ""
        
        dialogue_parts = []
        for msg in messages:
            role = "User" if msg.message_type == "human" else "AI"
            dialogue_parts.append(f"{role}: {msg.content}")
        
        dialogue_text = "\n".join(dialogue_parts)
        
        if self.llm:
            try:
                prompt = f"""Please summarize the core content of the following conversation (reply in English):

{dialogue_text}

Summary Requirements:
1. Extract key information and important conclusions
2. Preserve important user preferences and habits
3. Be concise and clear, within 100 words"""
                
                from core.ai_manager import ai_manager
                if ai_manager:
                    response = ai_manager.query_short(prompt, use_history=False)
                    if response and not response.startswith("Hmm"):
                        return response.strip()
            except Exception as e:
                logger.warning(f"LLM summary failed: {e}")
        
        key_topics = []
        for msg in messages:
            if msg.message_type == "human":
                words = msg.content.split()
                key_topics.extend(words[:10])
        
        summary = f"Conversation Summary: {' '.join(key_topics[:20])}"
        return summary
    
    def get_context_window(self, hours: int = 2) -> List[TimeStampedMessage]:
        """Get messages within time window"""
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
        return [
            msg for msg in self.raw_messages
            if msg.timestamp >= cutoff_time and not msg.is_summarized
        ]
    
    def load_memory_variables(self, current_input: str) -> Dict[str, Any]:
        """Load memory variables - optimized for token efficiency"""
        recent_summary = ""
        if self.summaries:
            recent_summary = self.summaries[-1].content
        
        context_window = self.get_context_window(hours=self.temp_memory_hours)
        
        history_lines = []
        if recent_summary:
            history_lines.append(f"[Summary] {recent_summary}")
        
        history_count = 3 if recent_summary else 5
        
        for msg in context_window[-history_count:]:
            role = "User" if msg.message_type == "human" else "AI"
            truncated_content = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
            history_lines.append(f"{role}: {truncated_content}")
        
        for summary in self.summaries[-2:]:
            if summary.content not in recent_summary:
                history_lines.append(f"[Summary] {summary.content[:100]}")
        
        return {
            "recent_summary": recent_summary,
            "context_window": "\n".join(history_lines),
            "history": "\n".join(history_lines),
            "last_interaction": self._last_interaction_time
        }
    
    def get_system_prompt_additions(self) -> str:
        """Get system prompt additions"""
        return ""
    
    def clear(self) -> None:
        """Clear all memories"""
        self.raw_messages.clear()
        self.summaries.clear()
        self._last_interaction_time = None


def build_time_aware_system_prompt(base_prompt: str, memory_vars: Dict[str, Any]) -> str:
    """Build time-aware system prompt"""
    prompt_parts = [base_prompt]
    
    if memory_vars.get("recent_summary"):
        prompt_parts.append("\nRecent conversation summary:")
        prompt_parts.append(memory_vars["recent_summary"])
    
    return "\n".join(prompt_parts)
