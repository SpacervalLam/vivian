"""
话题提取器 - TopicExtractor

核心功能：
1. 四信号关联评分 (semantic + hook_max + domain_overlap + need_sim)
2. 话题归并算法
3. LLM标注服务集成
4. 向量缓存管理

灵感来源：memoryos-agent/core/proactive/proactive_process/topic/topic_extractor.py
"""

import asyncio
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    logger.warning("[TopicExtractor] sentence-transformers 未安装")


class TopicExtractor:
    """话题提取器"""

    def __init__(self, embedding_model: Optional[str] = None, memory_manager=None):
        """
        初始化话题提取器

        Args:
            embedding_model: 嵌入模型名称或路径
            memory_manager: 记忆管理器实例
        """
        self._embedding_model = None
        self._embedding_dim = 384
        self._memory_manager = memory_manager

        if EMBEDDING_AVAILABLE:
            try:
                self._embedding_model = SentenceTransformer(
                    embedding_model or "all-MiniLM-L6-v2"
                )
                self._embedding_dim = self._embedding_model.get_sentence_embedding_dimension()
                logger.info(f"[TopicExtractor] 嵌入模型加载完成，维度: {self._embedding_dim}")
            except Exception as e:
                logger.warning(f"[TopicExtractor] 加载嵌入模型失败: {e}")

        # 评分权重配置 (与memoryos-agent一致)
        self.WEIGHTS = {
            "semantic": 1.0,
            "hook_max": 0.6,
            "domain_overlap": 0.3,
            "need_sim": 0.4
        }

        # 归并阈值
        self.MERGE_THRESHOLD = 0.75

    @property
    def memory_manager(self):
        """获取记忆管理器"""
        return self._memory_manager

    def set_memory_manager(self, memory_manager):
        """设置记忆管理器"""
        self._memory_manager = memory_manager

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """生成文本嵌入向量"""
        if not self._embedding_model or not text:
            return None

        try:
            embedding = self._embedding_model.encode(text)
            return embedding.astype(np.float32)
        except Exception as e:
            logger.warning(f"[TopicExtractor] 嵌入失败: {e}")
            return None

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        """归一化向量"""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if vec1 is None or vec2 is None:
            return 0.0
        try:
            return float(np.dot(vec1, vec2))
        except Exception:
            return 0.0

    def compute_association_score(
        self,
        query_emb: np.ndarray,
        topic: dict,
        query_text: str = ""
    ) -> Dict[str, float]:
        """
        计算四信号关联评分

        Args:
            query_emb: 查询向量
            topic: 话题对象
            query_text: 查询文本（用于domain_overlap计算）

        Returns:
            各信号评分和总分
        """
        query_emb_norm = self._normalize(query_emb)

        # 1. semantic: 语义相似度
        summary_emb = topic.get("summary_embedding")
        if summary_emb is not None:
            summary_emb = np.array(summary_emb, dtype=np.float32)
            summary_emb_norm = self._normalize(summary_emb)
            semantic = self._cosine_similarity(query_emb_norm, summary_emb_norm)
        else:
            # 回退到文本相似度
            summary = topic.get("summary", "")
            if summary:
                summary_emb = self._embed(summary)
                if summary_emb is not None:
                    summary_emb_norm = self._normalize(summary_emb)
                    semantic = self._cosine_similarity(query_emb_norm, summary_emb_norm)
                else:
                    semantic = 0.0
            else:
                semantic = 0.0

        # 2. hook_max: Hook匹配度最大值
        hook_embs = topic.get("hook_embeddings", [])
        hook_max = 0.0
        for hook_emb in hook_embs:
            if hook_emb is not None:
                hook_emb_norm = self._normalize(np.array(hook_emb, dtype=np.float32))
                sim = self._cosine_similarity(query_emb_norm, hook_emb_norm)
                hook_max = max(hook_max, sim)

        # 3. domain_overlap: 领域重叠
        related_domains = topic.get("related_domains", [])
        domain_overlap = 0.0
        if related_domains and query_text:
            query_lower = query_text.lower()
            hits = sum(1 for domain in related_domains if domain.lower() in query_lower)
            domain_overlap = hits / len(related_domains) if related_domains else 0.0

        # 4. need_sim: 用户需求相似度
        need_emb = topic.get("user_need_embedding")
        if need_emb is not None:
            need_emb_norm = self._normalize(np.array(need_emb, dtype=np.float32))
            need_sim = self._cosine_similarity(query_emb_norm, need_emb_norm)
        else:
            user_need = topic.get("user_need", "")
            if user_need:
                need_emb = self._embed(user_need)
                if need_emb is not None:
                    need_emb_norm = self._normalize(need_emb)
                    need_sim = self._cosine_similarity(query_emb_norm, need_emb_norm)
                else:
                    need_sim = 0.0
            else:
                need_sim = 0.0

        # 计算总分
        total = (
            self.WEIGHTS["semantic"] * semantic
            + self.WEIGHTS["hook_max"] * hook_max
            + self.WEIGHTS["domain_overlap"] * domain_overlap
            + self.WEIGHTS["need_sim"] * need_sim
        )

        return {
            "semantic": semantic,
            "hook_max": hook_max,
            "domain_overlap": domain_overlap,
            "need_sim": need_sim,
            "total": total
        }

    def _topic_representative_embedding(self, topic: dict) -> Optional[np.ndarray]:
        """获取话题的代表嵌入向量"""
        # 优先使用summary_embedding
        summary_emb = topic.get("summary_embedding")
        if summary_emb is not None:
            return np.array(summary_emb, dtype=np.float32)

        # 回退到生成
        summary = topic.get("summary", "")
        return self._embed(summary)

    def consolidate_new_sessions_into_topics(
        self,
        new_session_ids: List[str],
        sessions: Dict[str, dict],
        topic_store
    ) -> List[str]:
        """
        将新会话归并到已有话题

        Args:
            new_session_ids: 新会话ID列表
            sessions: 所有会话字典
            topic_store: 话题存储

        Returns:
            未匹配的会话ID列表（将创建新话题）
        """
        unmatched_ids = []

        for sid in new_session_ids:
            session = sessions.get(sid)
            if not session:
                continue

            session_summary = session.get("summary", "")
            if not session_summary:
                unmatched_ids.append(sid)
                continue

            # 获取会话向量
            session_emb = self._embed(session_summary)
            if session_emb is None:
                unmatched_ids.append(sid)
                continue

            session_emb_norm = self._normalize(session_emb)

            # 找到最佳匹配话题
            best_topic_id = None
            best_score = 0.0

            for topic in topic_store.list_topics():
                if not topic.get("should_proactive", True):
                    continue

                topic_emb = self._topic_representative_embedding(topic)
                if topic_emb is None:
                    continue

                topic_emb_norm = self._normalize(topic_emb)
                score = self._cosine_similarity(session_emb_norm, topic_emb_norm)

                if score > best_score:
                    best_score = score
                    best_topic_id = topic["topic_id"]

            # 判断是否合并
            if best_topic_id and best_score >= self.MERGE_THRESHOLD:
                # 合并到已有话题
                topic_store.add_sessions_to_topic(best_topic_id, [sid])

                # 如果话题已标注，立即同步到session
                topic = topic_store.get_topic(best_topic_id)
                if topic and topic.get("open_hooks"):
                    self._mirror_topic_to_session(session, topic)

                logger.debug(f"[TopicExtractor] 会话 {sid} 归入话题 {best_topic_id} (评分: {best_score:.2f})")
            else:
                unmatched_ids.append(sid)

        # 未匹配的会话合成一个新话题
        if unmatched_ids:
            # 生成组合摘要
            combined_summary = "; ".join([
                sessions.get(sid, {}).get("summary", "")[:50]
                for sid in unmatched_ids if sessions.get(sid)
            ])
            if combined_summary:
                new_topic_id = topic_store.create_topic(
                    summary=combined_summary[:200],
                    source_session_ids=unmatched_ids
                )
                logger.debug(f"[TopicExtractor] 创建新话题 {new_topic_id}，包含 {len(unmatched_ids)} 个会话")
                # 创建新话题后，这些session不再属于"未匹配"
                # 返回空列表表示所有session都已处理（归并或创建新话题）
                return []

        return unmatched_ids

    def _mirror_topic_to_session(self, session: dict, topic: dict):
        """将话题标注镜像到会话"""
        if "proactive_meta" not in session:
            session["proactive_meta"] = {}

        session["proactive_meta"]["topic_id"] = topic["topic_id"]
        session["proactive_meta"]["should_proactive"] = topic["should_proactive"]
        session["proactive_meta"]["open_hooks"] = topic["open_hooks"].copy()
        session["proactive_meta"]["user_need"] = topic["user_need"]
        session["proactive_meta"]["related_domains"] = topic["related_domains"].copy()

    async def annotate_topics_if_needed(
        self,
        topic_store,
        annotation_llm,
        max_batch_size: int = 8
    ):
        """
        异步标注需要标注的话题

        Args:
            topic_store: 话题存储
            annotation_llm: 标注LLM服务
            max_batch_size: 批处理大小
        """
        # 找到未标注的话题
        unannotated_topics = [
            topic for topic in topic_store.list_topics()
            if not topic.get("open_hooks") and topic.get("should_proactive")
        ]

        if not unannotated_topics:
            logger.debug("[TopicExtractor] 没有需要标注的话题")
            return

        logger.info(f"[TopicExtractor] 发现 {len(unannotated_topics)} 个未标注话题")

        # 分批处理
        for i in range(0, len(unannotated_topics), max_batch_size):
            batch = unannotated_topics[i:i + max_batch_size]
            await self._run_topic_annotation_batch(batch, topic_store, annotation_llm)

    async def _run_topic_annotation_batch(
        self,
        topics: List[dict],
        topic_store,
        annotation_llm
    ):
        """
        批量标注话题

        Args:
            topics: 话题列表
            topic_store: 话题存储
            annotation_llm: 标注LLM服务
        """
        for topic in topics:
            topic_id = topic["topic_id"]
            summary = topic["summary"]

            try:
                # 调用LLM标注
                annotation = await annotation_llm.annotate(summary)

                if annotation:
                    # 生成嵌入向量
                    hook_embeddings = []
                    for hook in annotation.get("open_hooks", []):
                        emb = self._embed(hook)
                        if emb is not None:
                            hook_embeddings.append(emb.tolist())

                    user_need_embedding = None
                    user_need = annotation.get("user_need", "")
                    if user_need:
                        emb = self._embed(user_need)
                        if emb is not None:
                            user_need_embedding = emb.tolist()

                    summary_embedding = None
                    if summary:
                        emb = self._embed(summary)
                        if emb is not None:
                            summary_embedding = emb.tolist()

                    # 更新标注
                    topic_store.update_annotation(topic_id, {
                        "open_hooks": annotation.get("open_hooks", []),
                        "user_need": user_need,
                        "related_domains": annotation.get("related_domains", []),
                        "hook_embeddings": hook_embeddings,
                        "user_need_embedding": user_need_embedding,
                        "summary_embedding": summary_embedding
                    })

                    # 镜像到所有source sessions
                    await self._mirror_annotation_to_sessions(topic_id, topic_store)

                    logger.debug(f"[TopicExtractor] 标注完成: {topic_id}")

            except Exception as e:
                logger.error(f"[TopicExtractor] 标注话题 {topic_id} 失败: {e}")

    async def _mirror_annotation_to_sessions(self, topic_id: str, topic_store):
        """将标注镜像到所有关联会话"""
        topic = topic_store.get_topic(topic_id)
        if not topic:
            return

        source_session_ids = topic.get("source_session_ids", [])
        if not source_session_ids:
            return

        annotation_data = {
            "topic_id": topic_id,
            "should_proactive": topic.get("should_proactive", True),
            "open_hooks": topic.get("open_hooks", []).copy(),
            "user_need": topic.get("user_need", ""),
            "related_domains": topic.get("related_domains", []).copy(),
        }

        memory = getattr(self, 'memory_manager', None)
        if memory is None:
            return

        mid_term = getattr(memory, 'mid_term_memory', None)
        if mid_term is None:
            return

        for sid in source_session_ids:
            session = mid_term.sessions.get(sid)
            if session:
                session["proactive_meta"] = annotation_data.copy()
                logger.debug(f"[TopicExtractor] 标注已镜像到会话: {sid}")

        try:
            mid_term._mark_dirty()
            mid_term._save_if_needed(force=True)
        except Exception as e:
            logger.error(f"[TopicExtractor] 保存会话标注失败: {e}")

    async def extract_topic_from_dialog(self, dialogs: List[Dict[str, str]], llm_client) -> Optional[Dict[str, Any]]:
        """
        使用LLM从对话中动态提取话题信息（替代预设话题）

        Args:
            dialogs: 对话列表，格式: [{"user": "...", "assistant": "..."}, ...]
            llm_client: LLM客户端

        Returns:
            话题信息字典
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
            response = await llm_client.generate(prompt)
            if response:
                import json
                return json.loads(response)
        except Exception as e:
            logger.error(f"[TopicExtractor] LLM调用失败: {e}")

        return None

    async def create_topic_from_dialog(self, dialogs: List[Dict[str, str]], llm_client, session_id: str = "") -> Optional[str]:
        """
        从对话创建话题（使用LLM动态生成，不使用预设话题）

        Args:
            dialogs: 对话列表
            llm_client: LLM客户端
            session_id: 会话ID

        Returns:
            新创建的话题ID
        """
        import time
        import uuid

        topic_info = await self.extract_topic_from_dialog(dialogs, llm_client)
        if not topic_info:
            return None

        topic_id = str(uuid.uuid4())[:8]
        topic_data = {
            "topic_id": topic_id,
            "summary": topic_info.get("topic_summary", ""),
            "topic_keywords": topic_info.get("topic_keywords", []),
            "user_need": topic_info.get("user_need", ""),
            "open_hooks": topic_info.get("open_hooks", []),
            "related_domains": topic_info.get("related_domains", []),
            "emotional_state": topic_info.get("emotional_state", ""),
            "source_session_ids": [session_id] if session_id else [],
            "should_proactive": True,
            "created_at": time.time(),
            "updated_at": time.time(),
            "priority": 0.0
        }

        # 生成嵌入向量
        if topic_data["summary"]:
            emb = self._embed(topic_data["summary"])
            if emb is not None:
                topic_data["summary_embedding"] = emb.tolist()

        if topic_data["user_need"]:
            emb = self._embed(topic_data["user_need"])
            if emb is not None:
                topic_data["user_need_embedding"] = emb.tolist()

        hook_embeddings = []
        for hook in topic_data["open_hooks"]:
            emb = self._embed(hook)
            if emb is not None:
                hook_embeddings.append(emb.tolist())
        topic_data["hook_embeddings"] = hook_embeddings

        # 更新到本地缓存
        if not hasattr(self, '_local_topics'):
            self._local_topics = {}
        self._local_topics[topic_id] = topic_data
        logger.debug(f"[TopicExtractor] 创建动态话题 {topic_id}: {topic_info.get('topic_summary')}")
        return topic_id

    def list_local_topics(self) -> List[Dict[str, Any]]:
        """获取本地话题列表"""
        return list(getattr(self, '_local_topics', {}).values())

    def get_local_topic(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """获取本地话题"""
        return getattr(self, '_local_topics', {}).get(topic_id)


# 全局单例
_topic_extractor: Optional[TopicExtractor] = None


def get_topic_extractor(embedding_model: str = None) -> TopicExtractor:
    """获取话题提取器单例"""
    global _topic_extractor
    if _topic_extractor is None:
        _topic_extractor = TopicExtractor(embedding_model)
    return _topic_extractor