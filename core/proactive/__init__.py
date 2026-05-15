"""
主动交互主模块 - ProactiveProcess

核心功能：
1. 整合所有主动交互组件
2. 实现完整的主动交互流程
3. 与memoryos-agent架构兼容

灵感来源：memoryos-agent/core/proactive/proactive_process
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from loguru import logger

from .activation_gate import get_activation_gate
from .annotation_llm import get_annotation_llm
from .hook_judge import get_hook_judge
from .topic_extractor import get_topic_extractor
from .topic_store import get_topic_store


class ProactiveProcess:
    """主动交互流程管理器"""

    def __init__(self, memory_manager=None):
        """
        初始化主动交互流程

        Args:
            memory_manager: 记忆管理器实例
        """
        self.memory_manager = memory_manager

        # 初始化组件
        self.topic_store = get_topic_store()
        self.topic_extractor = get_topic_extractor()
        self.topic_extractor.set_memory_manager(memory_manager)
        self.activation_gate = get_activation_gate()
        self.hook_judge = get_hook_judge()
        self.annotation_llm = get_annotation_llm()

        # 配置状态
        self._configured = False

        logger.debug("[ProactiveProcess] 主动交互流程模块初始化完成")

    def configure(self, memory_manager, ai_manager=None):
        """
        配置主动交互流程

        Args:
            memory_manager: 记忆管理器
            ai_manager: AI管理器（用于LLM标注）
        """
        self.memory_manager = memory_manager

        # 设置AI管理器到标注服务
        if ai_manager:
            self.annotation_llm.set_ai_manager(ai_manager)

        # 配置HookJudge的回调
        self._configure_hook_judge()

        self._configured = True
        logger.info("[ProactiveProcess] 主动交互流程已配置完成")

    def _configure_hook_judge(self):
        """配置HookJudge的Host回调"""
        def session_getter(sid: str) -> Optional[dict]:
            if self.memory_manager and hasattr(self.memory_manager, 'mid_term_memory'):
                return self.memory_manager.mid_term_memory.sessions.get(sid)
            return None

        def lock_getter(sid: str) -> object:
            # 返回一个简单的锁对象
            return getattr(self.memory_manager, '_lock', None) or object()

        def save_session_meta(sid: str):
            if self.memory_manager and hasattr(self.memory_manager, 'mid_term_memory'):
                try:
                    self.memory_manager.mid_term_memory._mark_dirty()
                    self.memory_manager.mid_term_memory._save_if_needed(force=True)
                except Exception as e:
                    logger.error(f"[ProactiveProcess] 保存session meta失败: {e}")

        self.hook_judge.configure(
            session_getter=session_getter,
            lock_getter=lock_getter,
            save_session_meta=save_session_meta
        )

    async def process_new_sessions(self, new_session_ids: List[str]):
        """
        处理新会话，归入话题或创建新话题

        Args:
            new_session_ids: 新会话ID列表
        """
        if not self.memory_manager:
            logger.warning("[ProactiveProcess] 内存管理器未配置")
            return

        mid_term = getattr(self.memory_manager, 'mid_term_memory', None)
        if mid_term is None:
            logger.warning("[ProactiveProcess] 中期记忆未初始化")
            return

        # 归并会话到话题
        self.topic_extractor.consolidate_new_sessions_into_topics(
            new_session_ids,
            mid_term.sessions,
            self.topic_store
        )

        # 异步标注需要标注的话题
        await self.topic_extractor.annotate_topics_if_needed(
            self.topic_store,
            self.annotation_llm
        )

        # 推进轮数
        self.topic_store.advance_turn()

        # 保存
        self.topic_store.save()

    async def process_query(self, query: str, query_emb: Optional[List[float]] = None) -> Optional[dict]:
        """
        处理用户查询，执行主动交互决策

        Args:
            query: 用户查询文本
            query_emb: 查询向量（可选）

        Returns:
            主动交互决策结果
        """
        if not self._configured:
            logger.warning("[ProactiveProcess] 未配置，跳过主动交互")
            return None

        # 1. 获取候选话题
        candidates = self._retrieve_candidates(query, query_emb)
        if not candidates:
            return None

        # 2. 调用LLM决策是否主动
        decision = await self._llm_decide(query, candidates)
        if not decision.get("should_callback"):
            return None

        # 3. 应用激活门控
        final_decision = self.activation_gate.apply_activation_gate(
            self.memory_manager,
            decision,
            candidates
        )

        # 4. 如果触发，执行回调
        if final_decision.get("activation_fired"):
            await self._execute_callback(final_decision, candidates)

        return final_decision

    def _retrieve_candidates(self, query: str, query_emb: Optional[List[float]] = None) -> List[dict]:
        """
        获取候选话题

        Args:
            query: 查询文本
            query_emb: 查询向量

        Returns:
            候选话题列表
        """
        candidates = []

        # 获取所有活跃话题
        active_topics = self.topic_store.get_active_topics()
        if not active_topics:
            return candidates

        # 如果有查询向量，计算关联评分
        if query_emb is not None:
            query_emb_np = __import__('numpy').array(query_emb, dtype='float32')

            for topic in active_topics:
                score_breakdown = self.topic_extractor.compute_association_score(
                    query_emb_np,
                    topic,
                    query
                )
                candidates.append({
                    "topic_id": topic["topic_id"],
                    "summary": topic["summary"],
                    "proactive_meta": topic,
                    "_association_score": score_breakdown["total"],
                    "_score_breakdown": score_breakdown
                })

            # 按关联评分排序
            candidates.sort(key=lambda x: x["_association_score"], reverse=True)
        else:
            # 没有向量，直接返回活跃话题
            for topic in active_topics:
                candidates.append({
                    "topic_id": topic["topic_id"],
                    "summary": topic["summary"],
                    "proactive_meta": topic,
                    "_association_score": 0.5  # 默认评分
                })

        return candidates[:10]  # 最多返回10个候选

    async def _llm_decide(self, query: str, candidates: List[dict]) -> dict:
        """
        调用LLM决策是否应该主动交互

        Args:
            query: 用户查询
            candidates: 候选话题

        Returns:
            决策结果
        """
        # 简单规则版本（实际应调用LLM）
        if not candidates:
            return {"should_callback": False}

        # 检查最高评分是否超过阈值
        top_score = candidates[0].get("_association_score", 0)
        if top_score >= 0.6:  # 阈值可以调整
            return {
                "should_callback": True,
                "target_memory_index": 0,
                "match_strength": "strong" if top_score >= 0.8 else "medium",
                "thoughts": f"检测到相关话题: {candidates[0]['summary'][:30]}",
                "topic_id": candidates[0]["topic_id"]
            }

        return {"should_callback": False}

    async def _execute_callback(self, decision: dict, candidates: List[dict]):
        """
        执行主动交互回调

        Args:
            decision: 决策结果
            candidates: 候选话题
        """
        topic_id = decision.get("topic_id")
        if not topic_id:
            return

        topic = self.topic_store.get_topic(topic_id)
        if not topic:
            return

        # 生成主动消息
        message = self._generate_proactive_message(topic)
        if message:
            logger.info(f"[ProactiveProcess] 主动消息: {message}")
            # 触发UI显示消息
            if hasattr(self, 'callback_handler'):
                await self.callback_handler(message, topic)

    def _generate_proactive_message(self, topic: dict) -> Optional[str]:
        """
        生成主动消息

        Args:
            topic: 话题对象

        Returns:
            主动消息文本
        """
        import random

        open_hooks = topic.get("open_hooks", [])
        user_need = topic.get("user_need", "")
        summary = topic.get("summary", "")
        callback_count = topic.get("callback_count", 0)

        # 根据callback_count调整消息风格
        if callback_count >= 3:
            # 多次回调后，换更自然的表达
            messages = [
                f"我们之前聊到的{summary[:15] if summary else '那个话题'}，你有什么新想法吗？",
                f"想起你之前提到的{open_hooks[0] if open_hooks else summary[:10]}，想继续聊聊~",
                f"关于{user_need[:10] if user_need else '这事'}~你后来怎么样了？"
            ]
            return random.choice(messages)

        if open_hooks:
            hook_messages = [
                f"我记得你之前提到过{open_hooks[0]}，现在怎么样了？",
                f"你之前说的{open_hooks[0]}，有进展吗？",
                f"说起来，{open_hooks[0]}后来怎么样了？",
                f"你提到过的{open_hooks[0]}，我一直记着呢~",
            ]
            return random.choice(hook_messages)
        elif user_need:
            need_messages = [
                f"关于{user_need[:10]}，有什么新进展吗？",
                f"你需要的{user_need[:10]}，搞定了没？",
                f"上次聊到{user_need[:8]}，想听听你的想法~",
            ]
            return random.choice(need_messages)
        elif summary:
            summary_messages = [
                f"想到我们之前聊的{summary[:10]}，想继续聊聊吗？",
                f"还记得我们之前讨论的{summary[:8]}吗？",
                f"突然又想到{summary[:10]}，你怎么看？",
            ]
            return random.choice(summary_messages)

        return None

    async def process_closure(self, user_message: str, recent_dialogs: List[dict] = None):
        """
        处理Hook闭环判定

        Args:
            user_message: 用户消息
            recent_dialogs: 最近对话
        """
        if not self.memory_manager:
            return

        await self.hook_judge.judge_closures(
            self.memory_manager,
            user_message,
            recent_dialogs
        )

    def set_callback_handler(self, handler):
        """设置回调处理器"""
        self.callback_handler = handler

    def get_stats(self) -> dict:
        """获取统计信息"""
        topic_stats = self.topic_store.get_stats()
        return {
            "topic_store": topic_stats,
            "configured": self._configured,
            "components": {
                "topic_store": True,
                "topic_extractor": True,
                "activation_gate": True,
                "hook_judge": True,
                "annotation_llm": True
            }
        }

    def save(self):
        """保存所有状态"""
        self.topic_store.save(force=True)

    def shutdown(self):
        """关闭所有组件"""
        self.save()
        self.hook_judge.shutdown()
        logger.info("[ProactiveProcess] 主动交互流程已关闭")


# 全局单例
_proactive_process: Optional[ProactiveProcess] = None


def get_proactive_process(memory_manager=None) -> ProactiveProcess:
    """获取主动交互流程单例"""
    global _proactive_process
    if _proactive_process is None:
        _proactive_process = ProactiveProcess(memory_manager)
    return _proactive_process


def init_proactive_process(memory_manager, ai_manager=None) -> ProactiveProcess:
    """初始化主动交互流程"""
    global _proactive_process
    _proactive_process = ProactiveProcess(memory_manager)
    _proactive_process.configure(memory_manager, ai_manager)
    return _proactive_process