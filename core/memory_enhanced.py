"""
改进的记忆系统 - 基于 memoryos-agent 的优秀实践

主要改进：
1. 并行检索：使用多线程并行执行记忆检索
2. 话题自动总结：使用 LLM 动态生成话题，替代预设话题
3. 改进记忆持久化：优化存储结构和去重逻辑
4. 混合检索：结合向量检索和关键词匹配
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from loguru import logger
from pydantic import BaseModel, Field

from core.memory.base import LongTermMemory, Memory, ShortTermMemory


class EnhancedMemoryRetriever:
    """增强版记忆检索器 - 支持并行检索和智能缓存"""

    def __init__(self, memory_manager):
        self.memory_manager = memory_manager
        self._turn_cache_future: Optional[Future] = None
        self._turn_cache_key: Optional[Tuple[Any, ...]] = None
        self._turn_cache_lock = threading.Lock()

    def _retrieve_short_term(self, user_query: str, top_k: int = 10):
        """检索短期记忆"""
        logger.debug("EnhancedRetriever: 检索短期记忆...")
        memories = self.memory_manager.list_short_term_memories()
        if not memories:
            return []

        # 简单的关键词匹配 + 时间衰减
        results = []
        query_lower = user_query.lower()
        
        for mem in memories:
            content_lower = mem.content.lower() if mem.content else ""
            score = 0.0
            
            # 关键词匹配
            if query_lower in content_lower:
                score += 0.7
            
            # 时间衰减 (最近的记忆权重更高)
            time_diff = time.time() - (mem.created_at.timestamp() if mem.created_at else time.time())
            time_score = max(0.1, 1.0 - time_diff / (24 * 3600))  # 24小时内衰减到0.1
            score += time_score * 0.3
            
            if score > 0.1:
                results.append((mem, score))
        
        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        logger.debug(f"EnhancedRetriever: 短期记忆检索完成，找到 {len(results)} 条匹配")
        return [mem for mem, score in results[:top_k]]

    def _retrieve_long_term(self, user_query: str, threshold: float = 0.3, top_k: int = 10):
        """检索长期记忆"""
        logger.debug("EnhancedRetriever: 检索长期记忆...")
        try:
            retrieved = self.memory_manager.retrieve_memories(user_query, k=top_k)
            # 过滤低于阈值的结果
            results = [(mem, score) for mem, score in retrieved if score >= threshold]
            results.sort(key=lambda x: x[1], reverse=True)
            logger.debug(f"EnhancedRetriever: 长期记忆检索完成，找到 {len(results)} 条匹配")
            return [mem for mem, score in results]
        except Exception as e:
            logger.error(f"EnhancedRetriever: 长期记忆检索失败: {e}")
            return []

    def _retrieve_user_profile(self, user_query: str):
        """检索用户资料"""
        logger.debug("EnhancedRetriever: 检索用户资料...")
        try:
            retrieved = self.memory_manager.retrieve_memory(user_query, limit=1)
            return retrieved.get("profile", {})
        except Exception as e:
            logger.error(f"EnhancedRetriever: 用户资料检索失败: {e}")
            return {}

    def retrieve_context(self, user_query: str, user_id: str = "default", 
                        threshold: float = 0.3, top_k: int = 10,
                        allow_cache: bool = True):
        """
        并行召回各类记忆
        
        同一轮的重复/并发调用会共用第一次的结果，避免重复计算
        """
        if not allow_cache:
            return self._do_retrieve(user_query, user_id, threshold, top_k)

        cache_key = (user_query, user_id, threshold, top_k)
        
        with self._turn_cache_lock:
            if self._turn_cache_key == cache_key and self._turn_cache_future is not None:
                future = self._turn_cache_future
                owns_compute = False
            else:
                future = Future()
                self._turn_cache_future = future
                self._turn_cache_key = cache_key
                owns_compute = True

        if not owns_compute:
            logger.debug(f"EnhancedRetriever: 缓存命中，复用检索结果")
            return future.result()

        try:
            result = self._do_retrieve(user_query, user_id, threshold, top_k)
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            with self._turn_cache_lock:
                if self._turn_cache_future is future:
                    self._turn_cache_future = None
                    self._turn_cache_key = None
            raise

    def _do_retrieve(self, user_query: str, user_id: str, 
                    threshold: float, top_k: int) -> Dict[str, Any]:
        """实际执行检索（无缓存层）"""
        logger.debug(f"EnhancedRetriever: 开始并行检索，查询: '{user_query[:50]}...'")
        
        tasks = [
            lambda: self._retrieve_short_term(user_query, top_k),
            lambda: self._retrieve_long_term(user_query, threshold, top_k),
            lambda: self._retrieve_user_profile(user_query),
        ]
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(task) for task in tasks]
            results = []
            for i, future in enumerate(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"EnhancedRetriever: 检索任务 {i} 失败: {e}")
                    results.append([] if i < 2 else {})
        
        short_term, long_term, profile = results
        
        return {
            "short_term_memories": short_term,
            "long_term_memories": long_term,
            "user_profile": profile,
            "retrieved_at": time.time()
        }


class TopicExtractor:
    """话题提取器 - 使用 LLM 动态总结话题"""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.topics: Dict[str, Topic] = {}
        self._lock = threading.Lock()

    def extract_topic(self, dialogs: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        从对话中提取话题信息
        
        Args:
            dialogs: 对话列表，格式: [{"user": "...", "assistant": "..."}, ...]
        
        Returns:
            话题信息字典，包含:
            - topic_summary: 话题总结
            - topic_keywords: 关键词列表
            - user_need: 用户需求
            - open_hooks: 未闭环的钩子
            - related_domains: 相关领域
            - emotional_state: 用户情绪状态
        """
        if not dialogs:
            return None

        dialog_text = "\n".join(
            [f"用户: {d.get('user', '')}\n助手: {d.get('assistant', '')}" for d in dialogs]
        )

        prompt = f"""
请分析以下对话，提取话题信息：

对话内容：
{dialog_text}

请输出 JSON 格式，包含以下字段：
1. topic_summary: 一句话总结这个对话的主题（不超过30字）
2. topic_keywords: 关键词列表（3-5个）
3. user_need: 用户的核心需求是什么？
4. open_hooks: 对话中未解决的问题或用户可能想要继续讨论的点
5. related_domains: 相关领域/话题标签（如：日常闲聊、工作学习、兴趣爱好等）
6. emotional_state: 用户的情绪状态（如：开心、疲惫、困惑、好奇等）

输出格式示例：
{{
    "topic_summary": "讨论周末旅行计划",
    "topic_keywords": ["旅行", "周末", "计划"],
    "user_need": "想了解适合周末旅行的目的地",
    "open_hooks": ["用户还没决定具体去哪里", "需要推荐景点"],
    "related_domains": ["旅行", "休闲"],
    "emotional_state": "期待"
}}
        """.strip()

        try:
            response = self.llm_client.generate(prompt)
            if response:
                import json
                return json.loads(response)
        except Exception as e:
            logger.error(f"TopicExtractor: LLM 调用失败: {e}")
        
        return None

    def update_or_create_topic(self, session_id: str, dialogs: List[Dict[str, str]]):
        """更新或创建话题"""
        topic_info = self.extract_topic(dialogs)
        if not topic_info:
            return None

        with self._lock:
            # 检查是否有相似话题
            existing_topic_id = self._find_similar_topic(topic_info)
            
            if existing_topic_id:
                # 更新现有话题
                self.topics[existing_topic_id].update(topic_info, session_id)
                return existing_topic_id
            else:
                # 创建新话题
                topic_id = str(uuid.uuid4())[:8]
                self.topics[topic_id] = Topic(
                    topic_id=topic_id,
                    **topic_info,
                    source_session_ids=[session_id]
                )
                logger.debug(f"TopicExtractor: 创建新话题 {topic_id}: {topic_info.get('topic_summary')}")
                return topic_id

    def _find_similar_topic(self, topic_info: Dict[str, Any], threshold: float = 0.7) -> Optional[str]:
        """查找相似话题"""
        new_summary = topic_info.get("topic_summary", "")
        if not new_summary:
            return None

        for tid, topic in self.topics.items():
            similarity = self._compute_similarity(new_summary, topic.topic_summary)
            if similarity >= threshold:
                return tid
        return None

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """简单的文本相似度计算"""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.lower())
        words2 = set(text2.lower())
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def list_topics(self) -> List[Dict[str, Any]]:
        """获取所有话题列表"""
        with self._lock:
            return [topic.to_dict() for topic in self.topics.values()]


class Topic(BaseModel):
    """话题模型"""
    
    topic_id: str
    topic_summary: str
    topic_keywords: List[str] = []
    user_need: str = ""
    open_hooks: List[str] = []
    related_domains: List[str] = []
    emotional_state: str = ""
    source_session_ids: List[str] = []
    created_at: float = Field(default_factory=lambda: time.time())
    updated_at: float = Field(default_factory=lambda: time.time())
    priority: float = 0.0

    def update(self, topic_info: Dict[str, Any], session_id: str):
        """更新话题信息"""
        if "topic_summary" in topic_info:
            self.topic_summary = topic_info["topic_summary"]
        if "topic_keywords" in topic_info:
            self.topic_keywords = list(set(self.topic_keywords + topic_info["topic_keywords"]))[:5]
        if "user_need" in topic_info:
            self.user_need = topic_info["user_need"]
        if "open_hooks" in topic_info:
            self.open_hooks = list(set(self.open_hooks + topic_info["open_hooks"]))[:5]
        if "related_domains" in topic_info:
            self.related_domains = list(set(self.related_domains + topic_info["related_domains"]))[:3]
        if "emotional_state" in topic_info:
            self.emotional_state = topic_info["emotional_state"]
        
        if session_id not in self.source_session_ids:
            self.source_session_ids.append(session_id)
        
        self.updated_at = time.time()
        # 更新优先级（基于活跃度）
        self.priority = min(1.0, self.priority + 0.1)

    def decay(self, decay_rate: float = 0.05):
        """话题优先级衰减"""
        self.priority = max(0.0, self.priority - decay_rate)
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "topic_id": self.topic_id,
            "topic_summary": self.topic_summary,
            "topic_keywords": self.topic_keywords,
            "user_need": self.user_need,
            "open_hooks": self.open_hooks,
            "related_domains": self.related_domains,
            "emotional_state": self.emotional_state,
            "source_session_ids": self.source_session_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "priority": self.priority
        }


class EnhancedMemoryPersistence:
    """增强版记忆持久化 - 支持智能合并和去重"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = threading.Lock()

    def save(self, data: Dict[str, Any]):
        """保存数据"""
        with self._lock:
            try:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.debug(f"EnhancedMemoryPersistence: 数据已保存到 {self.file_path}")
            except Exception as e:
                logger.error(f"EnhancedMemoryPersistence: 保存失败: {e}")

    def load(self) -> Dict[str, Any]:
        """加载数据"""
        with self._lock:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                logger.debug(f"EnhancedMemoryPersistence: 未找到文件 {self.file_path}")
                return {}
            except json.JSONDecodeError:
                logger.error(f"EnhancedMemoryPersistence: JSON 解析失败")
                return {}
            except Exception as e:
                logger.error(f"EnhancedMemoryPersistence: 加载失败: {e}")
                return {}

    def smart_merge_user_profile(self, existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """
        智能合并用户资料
        
        策略：
        1. 优先保留旧值（防止覆盖已有数据）
        2. 只填充空白字段
        3. 防止空值覆盖有效数据
        """
        merged = existing.copy()
        
        for key, new_value in new.items():
            old_value = existing.get(key)
            
            # 判断值是否有效
            new_is_valid = new_value and str(new_value).lower() not in ["null", "none", "未知", ""]
            old_is_valid = old_value and str(old_value).lower() not in ["null", "none", "未知", ""]
            
            if old_is_valid:
                # 旧值有效，保留旧值
                merged[key] = old_value
                if new_is_valid and new_value != old_value:
                    logger.debug(f"EnhancedMemoryPersistence: 保留字段 '{key}' 的旧值 '{old_value}'")
            elif new_is_valid:
                # 旧值无效但新值有效，填充新值
                merged[key] = new_value
                logger.debug(f"EnhancedMemoryPersistence: 填充字段 '{key}' 为 '{new_value}'")
        
        return merged
