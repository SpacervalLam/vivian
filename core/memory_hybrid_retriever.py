"""
混合记忆检索器

结合向量检索和智能选择：
- 向量检索：快速找到候选记忆
- 支持向量和文本两种检索模式
- 更注重情感和上下文理解
- 考虑记忆的时效性和重要性
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from core.memory.base import LongTermMemory, Memory, ShortTermMemory
from core.memory_types import MEMORY_TYPES


class HybridMemoryRetriever:
    """
    混合记忆检索器
    
    支持两种检索模式：
    1. 向量模式：使用向量相似度匹配（适合本地模型）
    2. LLM模式：使用LLM智能选择（适合强大的云端模型）
    
    自动选择策略：
    - 根据记忆数量和模型能力自动选择最优方式
    """
    
    def __init__(self, memory_manager, ai_manager=None):
        self.memory_manager = memory_manager
        self.ai_manager = ai_manager
        self._retrieval_mode: str = "auto"  # auto, vector, llm
        self._cache = {}
        self._cache_lock = threading.Lock()
        
    def set_retrieval_mode(self, mode: str):
        """
        设置检索模式
        
        Args:
            mode: "auto" (自动), "vector" (向量检索), "llm" (LLM选择)
        """
        if mode in ["auto", "vector", "llm"]:
            self._retrieval_mode = mode
            logger.info(f"记忆检索模式已设置为: {mode}")
        else:
            logger.warning(f"无效的检索模式: {mode}")
    
    def _should_use_llm_selection(self) -> bool:
        """
        判断是否应该使用LLM选择模式
        
        决策依据：
        1. 是否有AI管理器
        2. 记忆数量（太少不需要LLM）
        3. 当前设置的模式
        """
        if self._retrieval_mode == "vector":
            return False
        if self._retrieval_mode == "llm":
            return True
        
        # 自动模式：根据条件判断
        if not self.ai_manager:
            return False
        
        # 获取记忆数量
        stats = self.memory_manager.get_memory_stats()
        total_memories = stats["short_term"] + stats["long_term"]
        
        # 如果记忆太少，直接使用向量检索
        if total_memories < 5:
            return False
        
        return True
    
    def _build_memory_manifest(self, memories: List[Memory]) -> str:
        """
        构建记忆清单供LLM选择
        
        Args:
            memories: 记忆列表
            
        Returns:
            格式化的记忆清单字符串
        """
        lines = []
        for i, mem in enumerate(memories):
            mem_type = getattr(mem, "memory_type", "unknown")
            importance = getattr(mem, "importance", 0.5)
            timestamp = getattr(mem, "created_at", None)
            
            if timestamp:
                age_days = (time.time() - timestamp.timestamp()) // (24 * 3600)
                age_str = f" (创建于{age_days}天前)" if age_days > 0 else " (最近)"
            else:
                age_str = ""
            
            lines.append(
                f"{i+1}. [{mem_type}] 重要性:{importance:.2f}{age_str}: {mem.content[:100]}..."
            )
        
        return "\n".join(lines)
    
    def _select_relevant_memories_with_llm(
        self, query: str, candidates: List[Memory], k: int = 5
    ) -> List[Memory]:
        """
        使用LLM从候选记忆中选择相关记忆
        
        Args:
            query: 用户查询
            candidates: 候选记忆列表
            k: 返回数量
            
        Returns:
            选中的记忆列表
        """
        if not self.ai_manager or not candidates:
            return candidates[:k]
        
        manifest = self._build_memory_manifest(candidates)
        
        system_prompt = """你是一个记忆选择专家。请根据用户的查询，从提供的记忆列表中选择最相关的记忆。

选择规则：
1. 只选择与查询直接相关的记忆
2. 如果不确定某个记忆是否相关，请不要选择
3. 最多选择5个记忆
4. 优先选择近期创建的记忆
5. 优先选择重要性高的记忆

输出格式：
只输出数字列表，用逗号分隔，例如：1,3,5

如果没有相关记忆，输出：none
"""

        user_prompt = f"""
查询: {query}

可用记忆:
{manifest}

请选择最相关的记忆编号：
"""

        try:
            response = self.ai_manager.query_short(user_prompt, use_history=False)
            if not response or response.lower() == "none":
                return []
            
            # 解析响应
            selected_indices = []
            for part in response.split(","):
                part = part.strip()
                if part.isdigit():
                    selected_indices.append(int(part) - 1)  # 转换为0-based索引
            
            # 根据索引获取记忆
            selected = []
            for idx in selected_indices:
                if 0 <= idx < len(candidates):
                    selected.append(candidates[idx])
            
            logger.debug(f"LLM选择了 {len(selected)} 条相关记忆")
            return selected[:k]
            
        except Exception as e:
            logger.error(f"LLM记忆选择失败: {e}")
            return candidates[:k]
    
    def _vector_retrieval(self, query: str, k: int = 10) -> List[Tuple[Memory, float]]:
        """
        执行向量检索
        
        Args:
            query: 用户查询
            k: 返回数量
            
        Returns:
            (记忆, 相似度分数) 列表
        """
        try:
            results = self.memory_manager.retrieve_memories(query, k=k * 2)
            logger.debug(f"向量检索获取到 {len(results)} 条候选记忆")
            return results
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
    
    def _keyword_retrieval(self, query: str, k: int = 10) -> List[Tuple[Memory, float]]:
        """
        执行关键词检索
        
        Args:
            query: 用户查询
            k: 返回数量
            
        Returns:
            (记忆, 分数) 列表
        """
        results = []
        query_lower = query.lower()
        
        # 获取所有记忆
        short_term = self.memory_manager.list_short_term_memories()
        long_term = self.memory_manager.list_long_term_memories()
        all_memories = short_term + long_term
        
        for mem in all_memories:
            content_lower = mem.content.lower() if mem.content else ""
            score = 0.0
            
            # 关键词匹配
            for word in query_lower.split():
                if word in content_lower:
                    score += 0.2
            
            # 时间衰减
            timestamp = getattr(mem, "created_at", None)
            if timestamp:
                time_diff = time.time() - timestamp.timestamp()
                time_score = max(0.1, 1.0 - time_diff / (7 * 24 * 3600))  # 7天内衰减到0.1
                score += time_score * 0.3
            
            # 重要性权重（只有长期记忆才加权重要性）
            if isinstance(mem, LongTermMemory):
                importance = getattr(mem, "importance", 0.5)
                score += importance * 0.5
            
            if score > 0.1:
                results.append((mem, score))
        
        # 排序
        results.sort(key=lambda x: x[1], reverse=True)
        logger.debug(f"关键词检索获取到 {len(results)} 条候选记忆")
        return results[:k]
    
    def retrieve(self, query: str, k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Memory]:
        """
        检索相关记忆
        
        Args:
            query: 用户查询
            k: 返回数量
            filters: 过滤条件
            
        Returns:
            相关记忆列表
        """
        # 检查缓存
        cache_key = (query, k, str(filters))
        with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if time.time() - cached["timestamp"] < 60:  # 缓存1分钟
                    logger.debug("使用缓存的记忆检索结果")
                    return cached["result"]
        
        # 获取候选记忆（混合向量和关键词检索）
        vector_results = self._vector_retrieval(query, k=k * 2)
        keyword_results = self._keyword_retrieval(query, k=k * 2)
        
        # 合并结果（去重）
        seen_ids = set()
        candidates = []
        
        def add_candidate(mem, score):
            if mem.id not in seen_ids:
                seen_ids.add(mem.id)
                candidates.append((mem, score))
        
        for mem, score in vector_results:
            add_candidate(mem, score * 0.6)  # 向量结果权重0.6
        
        for mem, score in keyword_results:
            if mem.id not in seen_ids:
                add_candidate(mem, score * 0.4)  # 关键词结果权重0.4
        
        # 排序候选
        candidates.sort(key=lambda x: x[1], reverse=True)
        candidate_memories = [mem for mem, score in candidates]
        
        # 根据模式选择最终结果
        if self._should_use_llm_selection():
            # 使用LLM智能选择
            final_results = self._select_relevant_memories_with_llm(
                query, candidate_memories, k=k
            )
        else:
            # 直接使用向量/关键词检索结果
            final_results = candidate_memories[:k]
        
        # 更新缓存
        with self._cache_lock:
            self._cache[cache_key] = {
                "result": final_results,
                "timestamp": time.time()
            }
        
        logger.debug(f"最终检索到 {len(final_results)} 条相关记忆")
        return final_results
    
    def retrieve_by_type(self, memory_type: str, k: int = 5) -> List[Memory]:
        """
        按记忆类型检索
        
        Args:
            memory_type: 记忆类型
            k: 返回数量
            
        Returns:
            该类型的记忆列表
        """
        if memory_type not in MEMORY_TYPES:
            logger.warning(f"无效的记忆类型: {memory_type}")
            return []
        
        short_term = self.memory_manager.list_short_term_memories()
        long_term = self.memory_manager.list_long_term_memories()
        all_memories = short_term + long_term
        
        # 过滤类型
        filtered = [
            mem for mem in all_memories 
            if getattr(mem, "memory_type", None) == memory_type
        ]
        
        # 按重要性排序
        filtered.sort(key=lambda x: getattr(x, "importance", 0.5), reverse=True)
        
        return filtered[:k]
    
    def clear_cache(self):
        """清除检索缓存"""
        with self._cache_lock:
            self._cache.clear()
        logger.debug("记忆检索缓存已清除")