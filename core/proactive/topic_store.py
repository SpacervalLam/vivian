"""
话题存储系统

核心功能：
- 话题的持久化存储和管理
- 激活度管理和冷却机制
- 支持session和topic两种存储模式
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


class TopicStore:
    """话题存储系统"""

    def __init__(self, store_path: str):
        """
        初始化话题存储

        Args:
            store_path: 存储文件路径
        """
        self.store_path = store_path
        self._topics: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._current_turn = 0
        self._dirty = False
        self._last_save_time = 0

        # 配置常量
        self.COOLING_TURNS = 10  # 触发后冷却轮数
        self.SAVE_INTERVAL = 5.0  # 自动保存间隔(秒)

        # 确保目录存在
        os.makedirs(os.path.dirname(store_path), exist_ok=True)

        # 加载存储
        self.load()

    def _generate_topic_id(self) -> str:
        """生成唯一话题ID"""
        return f"topic_{int(time.time() * 1000)}_{id(self) % 10000}"

    def get_topic(self, topic_id: str) -> Optional[dict]:
        """获取话题"""
        with self._lock:
            return self._topics.get(topic_id)

    def list_topics(self) -> List[dict]:
        """列出所有话题"""
        with self._lock:
            return list(self._topics.values())

    def create_topic(self, summary: str, source_session_ids: List[str] = None) -> str:
        """
        创建新话题

        Args:
            summary: 话题摘要
            source_session_ids: 来源会话ID列表

        Returns:
            新创建的话题ID
        """
        topic_id = self._generate_topic_id()
        
        topic = {
            "topic_id": topic_id,
            "summary": summary,
            "source_session_ids": source_session_ids or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "should_proactive": True,
            "proactive_activation": 0.0,
            "callback_count": 0,
            "last_callback_turn": -1,
            "open_hooks": [],
            "user_need": "",
            "related_domains": [],
            "hook_embeddings": [],
            "user_need_embedding": None,
            "summary_embedding": None,
            "task_status": None,
            "task_description": "",
            "metadata": {}
        }

        with self._lock:
            self._topics[topic_id] = topic
            self._dirty = True

        logger.debug(f"[TopicStore] 创建话题: {topic_id}")
        return topic_id

    def update_topic(self, topic_id: str, **kwargs):
        """更新话题属性"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                logger.warning(f"[TopicStore] 话题不存在: {topic_id}")
                return

            for key, value in kwargs.items():
                if key in topic:
                    topic[key] = value

            topic["updated_at"] = datetime.now().isoformat()
            self._dirty = True

        logger.debug(f"[TopicStore] 更新话题: {topic_id}")

    def delete_topic(self, topic_id: str):
        """删除话题"""
        with self._lock:
            if topic_id in self._topics:
                del self._topics[topic_id]
                self._dirty = True
                logger.debug(f"[TopicStore] 删除话题: {topic_id}")

    def set_activation(self, topic_id: str, activation: float):
        """设置激活度"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if topic:
                topic["proactive_activation"] = activation
                topic["updated_at"] = datetime.now().isoformat()
                self._dirty = True

    def get_activation(self, topic_id: str) -> float:
        """获取激活度"""
        with self._lock:
            topic = self._topics.get(topic_id)
            return topic["proactive_activation"] if topic else 0.0

    def mark_callback_used(self, topic_id: str):
        """标记callback已使用"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if topic:
                topic["callback_count"] += 1
                topic["updated_at"] = datetime.now().isoformat()
                self._dirty = True

    def set_last_callback_turn(self, topic_id: str, turn: int):
        """设置上次callback的轮数"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if topic:
                topic["last_callback_turn"] = turn
                topic["updated_at"] = datetime.now().isoformat()
                self._dirty = True

    def current_turn(self) -> int:
        """获取当前轮数"""
        return self._current_turn

    def advance_turn(self):
        """推进轮数"""
        with self._lock:
            self._current_turn += 1
            self._dirty = True

    def is_cooling(self, topic_id: str) -> bool:
        """检查话题是否在冷却中"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                return False

            last_turn = topic.get("last_callback_turn", -1)
            if last_turn < 0:
                return False

            return (self._current_turn - last_turn) < self.COOLING_TURNS

    def update_annotation(self, topic_id: str, annotation: dict):
        """更新话题标注"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                logger.warning(f"[TopicStore] 更新标注失败，话题不存在: {topic_id}")
                return

            # 更新标注字段
            if "open_hooks" in annotation:
                topic["open_hooks"] = annotation["open_hooks"]
            if "user_need" in annotation:
                topic["user_need"] = annotation["user_need"]
            if "related_domains" in annotation:
                topic["related_domains"] = annotation["related_domains"]
            if "hook_embeddings" in annotation:
                topic["hook_embeddings"] = annotation["hook_embeddings"]
            if "user_need_embedding" in annotation:
                topic["user_need_embedding"] = annotation["user_need_embedding"]
            if "summary_embedding" in annotation:
                topic["summary_embedding"] = annotation["summary_embedding"]

            topic["updated_at"] = datetime.now().isoformat()
            self._dirty = True

        logger.debug(f"[TopicStore] 更新标注: {topic_id}")

    def add_sessions_to_topic(self, topic_id: str, session_ids: List[str]):
        """添加会话到话题"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                logger.warning(f"[TopicStore] 添加会话失败，话题不存在: {topic_id}")
                return

            existing_ids = set(topic["source_session_ids"])
            new_ids = [sid for sid in session_ids if sid not in existing_ids]
            topic["source_session_ids"].extend(new_ids)
            topic["updated_at"] = datetime.now().isoformat()
            self._dirty = True

        logger.debug(f"[TopicStore] 添加会话到话题 {topic_id}: {len(new_ids)} 个")

    def close_hook(self, topic_id: str, hook: str):
        """关闭指定的hook"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                return

            if hook in topic["open_hooks"]:
                topic["open_hooks"].remove(hook)
                topic["updated_at"] = datetime.now().isoformat()
                self._dirty = True
                logger.debug(f"[TopicStore] 关闭hook: {topic_id} -> {hook}")

    def add_hook(self, topic_id: str, hook: str):
        """添加一个hook到话题"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                logger.warning(f"[TopicStore] 添加hook失败，话题不存在: {topic_id}")
                return

            if hook not in topic["open_hooks"]:
                topic["open_hooks"].append(hook)
                topic["updated_at"] = datetime.now().isoformat()
                self._dirty = True
                logger.debug(f"[TopicStore] 添加hook: {topic_id} -> {hook}")

    def clear_hooks(self, topic_id: str):
        """清空话题的所有hooks"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if not topic:
                return

            topic["open_hooks"] = []
            topic["updated_at"] = datetime.now().isoformat()
            self._dirty = True
            logger.debug(f"[TopicStore] 清空hooks: {topic_id}")

    def archive_topic(self, topic_id: str):
        """归档话题（停止主动触发）"""
        with self._lock:
            topic = self._topics.get(topic_id)
            if topic:
                topic["should_proactive"] = False
                topic["updated_at"] = datetime.now().isoformat()
                self._dirty = True
                logger.debug(f"[TopicStore] 归档话题: {topic_id}")

    def get_active_topics(self) -> List[dict]:
        """获取所有活跃话题"""
        with self._lock:
            return [
                topic for topic in self._topics.values()
                if topic.get("should_proactive", True) and not self.is_cooling(topic["topic_id"])
            ]

    def save(self, force: bool = False):
        """保存到磁盘"""
        if not self._dirty and not force:
            return

        current_time = time.time()
        if not force and (current_time - self._last_save_time) < self.SAVE_INTERVAL:
            return

        with self._lock:
            data = {
                "topics": self._topics,
                "current_turn": self._current_turn,
                "saved_at": datetime.now().isoformat()
            }

            try:
                with open(self.store_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                self._dirty = False
                self._last_save_time = current_time
                logger.debug(f"[TopicStore] 已保存到: {self.store_path}")
            except Exception as e:
                logger.error(f"[TopicStore] 保存失败: {e}")

    def load(self):
        """从磁盘加载"""
        if not os.path.exists(self.store_path):
            logger.debug(f"[TopicStore] 存储文件不存在，创建新存储: {self.store_path}")
            return

        try:
            with open(self.store_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._topics = data.get("topics", {})
            self._current_turn = data.get("current_turn", 0)

            logger.info(f"[TopicStore] 加载完成，话题数: {len(self._topics)}")
        except Exception as e:
            logger.error(f"[TopicStore] 加载失败: {e}")
            self._topics = {}

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            active_count = len(self.get_active_topics())
            total_count = len(self._topics)
            cooling_count = sum(1 for tid in self._topics if self.is_cooling(tid))

            return {
                "total_topics": total_count,
                "active_topics": active_count,
                "cooling_topics": cooling_count,
                "current_turn": self._current_turn,
                "store_path": self.store_path
            }

    def clear(self):
        """清空所有话题"""
        with self._lock:
            self._topics = {}
            self._current_turn = 0
            self._dirty = True
            logger.info("[TopicStore] 已清空所有话题")


# 全局单例
_topic_store: Optional[TopicStore] = None


def get_topic_store(store_path: str = None) -> TopicStore:
    """获取话题存储单例"""
    global _topic_store
    if _topic_store is None:
        if store_path is None:
            from core.memory_manager import MemoryManager
            mm = MemoryManager()
            store_path = os.path.join(mm._get_user_data_dir(), "memory", "topic_store.json")

        _topic_store = TopicStore(store_path)

    return _topic_store


def init_topic_store(store_path: str) -> TopicStore:
    """初始化话题存储"""
    global _topic_store
    _topic_store = TopicStore(store_path)
    return _topic_store