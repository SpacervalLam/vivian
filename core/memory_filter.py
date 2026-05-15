"""
记忆过滤器模块 - 解决跨会话强行关联话题的问题

核心功能：
1. 检测新会话（超过1小时无对话或用户发送问候语）
2. 在新会话时自动过滤临时话题记忆
3. 只保留长期偏好记忆
4. 实现时间衰减机制
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.memory.base import Memory, MemoryNode
from core.memory_manager import MemoryManager


class MemoryFilter:
    """
    记忆过滤器 - 解决跨会话强行关联话题的核心组件
    
    问题描述：
    - 用户早上聊了奶茶口味，晚上发"晚上好"，智能体回复"晚上好啊，今天有没有顺路买奶茶啊"
    - 原因：记忆系统没有区分临时话题和长期偏好
    
    解决方案：
    1. 检测新会话（超过1小时无对话或用户发送问候语）
    2. 新会话时过滤掉所有临时话题记忆
    3. 只保留长期偏好记忆（喜欢、爱、讨厌、偏好等关键词）
    """
    
    def __init__(self, memory_manager: MemoryManager):
        """
        初始化记忆过滤器
        
        Args:
            memory_manager: 记忆管理器实例
        """
        self.memory_manager = memory_manager
        self.last_interaction_time: Optional[datetime.datetime] = None
        
        # 新会话阈值：超过1小时没有对话视为新会话
        self.new_session_threshold = datetime.timedelta(hours=1)
        
        # 使用泛化的启发式规则，不再依赖预设关键词
        
        logger.debug("记忆过滤器初始化完成")
    
    def is_new_session(self, user_input: str) -> bool:
        """
        判断当前是否是新会话
        
        判断条件：
        1. 用户输入简短且不含具体内容（可能是问候或打招呼）
        2. 距离上次交互超过1小时
        
        Args:
            user_input: 用户输入
            
        Returns:
            True 如果是新会话，否则 False
        """
        # 条件1：泛化的问候检测 - 输入较短且不含具体问题或话题
        is_short_input = len(user_input) <= 15
        has_no_specific_topic = len(user_input) <= 15 and not any(q in user_input for q in ["?", "？", "吗", "呢", "怎么", "什么", "为什么"])
        
        if is_short_input and has_no_specific_topic:
            logger.debug(f"检测到可能是问候的短输入 '{user_input}'，视为新会话")
            return True
        
        # 条件2：距离上次交互超过阈值
        if self.last_interaction_time is None:
            # 首次交互，视为新会话
            logger.debug("首次交互，视为新会话")
            return True
        
        time_since_last = datetime.datetime.now() - self.last_interaction_time
        if time_since_last > self.new_session_threshold:
            logger.debug(f"距离上次交互 {time_since_last}，超过阈值 {self.new_session_threshold}，视为新会话")
            return True
        
        return False
    
    def is_long_term_preference(self, content: str) -> bool:
        """
        判断记忆内容是否为长期偏好（基于文本结构而非关键词）
        
        Args:
            content: 记忆内容
            
        Returns:
            True 如果是长期偏好，否则 False
        """
        # 第一人称陈述更可能是长期偏好
        first_person_indicators = ["我", "俺", "人家"]
        has_first_person = any(indicator in content for indicator in first_person_indicators)
        
        # 有一定长度，更可能是有意义的陈述
        has_reasonable_length = len(content) >= 8
        
        # 不是问题
        is_not_question = not any(q in content for q in ["?", "？", "吗", "呢"])
        
        return has_first_person and has_reasonable_length and is_not_question
    
    def is_temporary_topic(self, content: str) -> bool:
        """
        判断记忆内容是否为临时话题（基于文本结构而非关键词）
        
        Args:
            content: 记忆内容
            
        Returns:
            True 如果是临时话题，否则 False
        """
        # 时间相关的词（更泛化的检测）
        time_indicators = [
            "今天", "昨天", "明天", "刚才", "现在", "一会儿", "最近",
            "刚刚", "等下", "马上", "立刻", "下午", "晚上", "早上", "中午"
        ]
        has_time_indicator = any(indicator in content for indicator in time_indicators)
        
        # 较短的陈述更可能是临时话题
        is_short_statement = len(content) < 20
        
        return has_time_indicator or is_short_statement
    
    def get_memory_age(self, memory: Memory) -> datetime.timedelta:
        """
        获取记忆的年龄
        
        Args:
            memory: 记忆对象
            
        Returns:
            记忆创建时间距离现在的时间差
        """
        if hasattr(memory, 'timestamp'):
            if isinstance(memory.timestamp, float):
                # 时间戳格式
                memory_time = datetime.datetime.fromtimestamp(memory.timestamp)
            elif isinstance(memory.timestamp, datetime.datetime):
                memory_time = memory.timestamp
            else:
                memory_time = datetime.datetime.now()
            return datetime.datetime.now() - memory_time
        return datetime.timedelta(hours=0)
    
    def calculate_memory_weight(self, memory: Memory) -> float:
        """
        计算记忆的权重（考虑时间衰减和类型）
        
        权重计算规则：
        - 长期偏好：基础权重 1.0，时间衰减慢
        - 临时话题：基础权重 0.3，时间衰减快
        
        Args:
            memory: 记忆对象
            
        Returns:
            记忆权重（0-1之间）
        """
        age = self.get_memory_age(memory)
        hours_since_created = age.total_seconds() / 3600
        
        # 基础权重
        if self.is_long_term_preference(memory.content):
            base_weight = 1.0
            # 长期偏好衰减慢：24小时衰减到0.8
            decay_rate = 0.2 / 24  # 每小时衰减0.2/24
        else:
            base_weight = 0.3
            # 临时话题衰减快：2小时衰减到0.05
            decay_rate = 0.25 / 2  # 每小时衰减0.25/2
        
        # 计算衰减后的权重
        time_decay = max(0.0, 1.0 - hours_since_created * decay_rate)
        final_weight = base_weight * time_decay
        
        # 额外的新会话惩罚：超过1小时的临时话题权重减半
        if hours_since_created > 1.0 and self.is_temporary_topic(memory.content):
            final_weight *= 0.5
        
        logger.debug(f"记忆权重计算 - 内容: {memory.content[:30]}... 年龄: {age} 权重: {final_weight:.4f}")
        
        return max(0.0, min(1.0, final_weight))
    
    def get_filtered_memories(
        self,
        user_input: str,
        k: int = 5,
        force_full: bool = False
    ) -> List[Tuple[Memory, float]]:
        """
        获取过滤后的记忆列表
        
        新会话时的过滤规则：
        1. 如果是新会话且用户没有主动提起之前的话题，只返回长期偏好记忆
        2. 如果不是新会话，返回所有相关记忆（按权重排序）
        3. 如果用户主动提起之前的话题（关键词匹配），返回所有相关记忆
        
        Args:
            user_input: 用户输入
            k: 返回记忆数量
            force_full: 是否强制返回全部记忆（用于测试）
            
        Returns:
            过滤后的记忆列表，包含记忆对象和权重
        """
        is_new_session = self.is_new_session(user_input)
        
        # 更新最后交互时间
        self.last_interaction_time = datetime.datetime.now()
        
        if force_full:
            # 强制返回全部记忆
            memories = self.memory_manager.list_short_term_memories() + \
                       self.memory_manager.list_long_term_memories()
            return [(m, 1.0) for m in memories[:k]]
        
        # 获取所有记忆
        all_memories = self.memory_manager.list_short_term_memories() + \
                       self.memory_manager.list_long_term_memories()
        
        if not all_memories:
            return []
        
        # 判断用户是否主动提起之前的话题
        user_mentioned_topic = False
        for memory in all_memories:
            # 检查用户输入是否包含记忆中的关键词
            memory_keywords = set(memory.content.split())
            input_keywords = set(user_input.split())
            if memory_keywords.intersection(input_keywords):
                user_mentioned_topic = True
                break
        
        # 新会话过滤逻辑
        if is_new_session and not user_mentioned_topic:
            logger.debug("新会话且用户未提及旧话题，只返回长期偏好记忆")
            
            # 只保留长期偏好记忆
            filtered = [
                (memory, self.calculate_memory_weight(memory))
                for memory in all_memories
                if self.is_long_term_preference(memory.content)
            ]
            
            # 按权重排序
            filtered.sort(key=lambda x: x[1], reverse=True)
            
            # 如果没有长期偏好记忆，返回空列表（让对话自然开始）
            return filtered[:k]
        
        # 非新会话或用户主动提及旧话题，返回所有相关记忆（按权重排序）
        logger.debug("非新会话或用户提及旧话题，返回所有相关记忆")
        
        # 计算所有记忆的权重
        scored_memories = [
            (memory, self.calculate_memory_weight(memory))
            for memory in all_memories
        ]
        
        # 过滤掉权重过低的记忆
        scored_memories = [
            (m, w) for m, w in scored_memories
            if w > 0.01
        ]
        
        # 按权重排序
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        
        return scored_memories[:k]
    
    def get_filtered_memory_text(
        self,
        user_input: str,
        k: int = 5,
        force_full: bool = False
    ) -> str:
        """
        获取过滤后的记忆文本（用于构建提示词）
        
        Args:
            user_input: 用户输入
            k: 返回记忆数量
            force_full: 是否强制返回全部记忆
            
        Returns:
            格式化的记忆文本
        """
        filtered_memories = self.get_filtered_memories(user_input, k, force_full)
        
        if not filtered_memories:
            return ""
        
        memory_lines = []
        for memory, weight in filtered_memories:
            # 只保留内容，不显示权重
            memory_lines.append(f"- {memory.content}")
        
        return "\n".join(memory_lines)
    
    def reset(self) -> None:
        """
        重置过滤器状态
        
        用于测试或手动重置会话
        """
        self.last_interaction_time = None
        logger.debug("记忆过滤器已重置")


class MemoryFilterConfig:
    """
    记忆过滤器配置
    """
    
    def __init__(self):
        self.new_session_threshold_hours = 1
        self.min_memory_weight = 0.01
        # 不再使用关键词列表，使用泛化的启发式规则


# 全局记忆过滤器实例
_global_memory_filter = None


def get_memory_filter(memory_manager: Optional[MemoryManager] = None) -> MemoryFilter:
    """
    获取全局记忆过滤器实例
    
    Args:
        memory_manager: 记忆管理器实例（首次调用时必须提供）
        
    Returns:
        全局记忆过滤器实例
    """
    global _global_memory_filter
    
    if _global_memory_filter is None:
        if memory_manager is None:
            raise ValueError("首次调用时必须提供 memory_manager")
        _global_memory_filter = MemoryFilter(memory_manager)
    
    return _global_memory_filter


__all__ = [
    "MemoryFilter",
    "MemoryFilterConfig",
    "get_memory_filter"
]
