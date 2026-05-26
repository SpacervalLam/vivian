"""
记忆系统优化模块
包含：
1. 简化存储架构 - 统一的存储接口
2. 记忆过期机制 - 自动清理过期记忆
3. 智能检索策略 - 支持向量检索和关键词检索的智能切换
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from dataclasses import dataclass
from loguru import logger


class StorageType(Enum):
    """存储类型枚举 - 支持多种存储后端"""
    JSON = "json"  # 简单JSON文件存储（默认）
    SQLITE = "sqlite"  # SQLite数据库
    CHROMA = "chroma"  # ChromaDB向量数据库
    FAISS = "faiss"  # FAISS向量索引


class RetrievalStrategy(Enum):
    """检索策略枚举"""
    KEYWORD = "keyword"  # 关键词匹配（快速）
    VECTOR = "vector"    # 向量相似度检索（精准）
    HYBRID = "hybrid"    # 混合策略（智能选择）
    AUTO = "auto"        # 自动选择最佳策略


@dataclass
class MemoryExpirationRule:
    """记忆过期规则"""
    memory_type: str  # 记忆类型
    max_age_hours: float  # 最大存活小时数
    max_count: Optional[int] = None  # 最大数量限制
    min_importance: float = 0.0  # 最低重要度（低于此可删除）


@dataclass
class MemoryRetentionPolicy:
    """记忆保留策略（参考ClaudeCode的设计）"""
    # 永不删除的内容
    KEEP_ALWAYS = {
        "user_preferences", "user_identity", "important_events"
    }
    
    # 可以删除的临时内容
    CAN_DELETE = {
        "casual_conversation", "temporary_context", "old_sessions"
    }
    
    @staticmethod
    def should_keep(memory_type: str, importance: float, age_hours: float) -> bool:
        """判断是否应该保留此记忆"""
        if memory_type in MemoryRetentionPolicy.KEEP_ALWAYS:
            return True
        if memory_type in MemoryRetentionPolicy.CAN_DELETE:
            if importance < 0.3 and age_hours > 24:
                return False
            if importance < 0.5 and age_hours > 72:
                return False
        return True


class SimplifiedMemoryStore(ABC):
    """简化的记忆存储接口"""
    
    @abstractmethod
    def save(self, memory_id: str, data: Dict[str, Any]) -> bool:
        """保存记忆"""
        pass
    
    @abstractmethod
    def load(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """加载记忆"""
        pass
    
    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        pass
    
    @abstractmethod
    def list_all(self) -> List[str]:
        """列出所有记忆ID"""
        pass
    
    @abstractmethod
    def clear_all(self) -> bool:
        """清空所有记忆"""
        pass


class JsonMemoryStore(SimplifiedMemoryStore):
    """简单的JSON文件存储实现"""
    
    def __init__(self, storage_path: str):
        import os
        self.storage_path = storage_path
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_all()
    
    def _load_all(self):
        """加载所有记忆"""
        import os
        import json
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load memory store: {e}")
                self._cache = {}
    
    def _save_all(self):
        """保存所有记忆"""
        import json
        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory store: {e}")
    
    def save(self, memory_id: str, data: Dict[str, Any]) -> bool:
        self._cache[memory_id] = {
            **data,
            "_saved_at": datetime.now().isoformat()
        }
        self._save_all()
        return True
    
    def load(self, memory_id: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(memory_id)
    
    def delete(self, memory_id: str) -> bool:
        if memory_id in self._cache:
            del self._cache[memory_id]
            self._save_all()
            return True
        return False
    
    def list_all(self) -> List[str]:
        return list(self._cache.keys())
    
    def clear_all(self) -> bool:
        self._cache = {}
        self._save_all()
        return True


class MemoryExpirationManager:
    """记忆过期管理器"""
    
    def __init__(self, store: SimplifiedMemoryStore):
        self.store = store
        self.rules: List[MemoryExpirationRule] = [
            MemoryExpirationRule("casual_conversation", max_age_hours=24, max_count=100),
            MemoryExpirationRule("temporary_context", max_age_hours=6, max_count=50),
            MemoryExpirationRule("long_term", max_age_hours=720, min_importance=0.3),
        ]
    
    def cleanup_expired(self) -> int:
        """清理过期记忆，返回删除数量"""
        deleted_count = 0
        now = datetime.now()
        
        for memory_id in list(self.store.list_all()):
            memory = self.store.load(memory_id)
            if not memory:
                continue
            
            if self._is_expired(memory, now):
                self.store.delete(memory_id)
                deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} expired memories")
        return deleted_count
    
    def _is_expired(self, memory: Dict[str, Any], now: datetime) -> bool:
        """判断记忆是否过期"""
        saved_at = memory.get("_saved_at")
        if not saved_at:
            return False
        
        try:
            saved_time = datetime.fromisoformat(saved_at)
            age_hours = (now - saved_time).total_seconds() / 3600
        except:
            return False
        
        memory_type = memory.get("type", "unknown")
        importance = memory.get("importance", 0.5)
        
        if not MemoryRetentionPolicy.should_keep(memory_type, importance, age_hours):
            return True
        
        for rule in self.rules:
            if rule.memory_type in [memory_type, "*"]:
                if age_hours > rule.max_age_hours:
                    if importance < rule.min_importance:
                        return True
        return False


class UnifiedMemoryManager:
    """统一的记忆管理器 - 简化存储架构"""
    
    def __init__(self, user_data_dir: str, storage_type: StorageType = StorageType.JSON):
        import os
        self.user_data_dir = user_data_dir
        
        if storage_type == StorageType.SQLITE:
            try:
                self.store = self._create_sqlite_store(user_data_dir)
            except Exception as e:
                logger.warning(f"Falling back to JSON store: {e}")
                storage_path = os.path.join(user_data_dir, "memory", "memories.json")
                self.store = JsonMemoryStore(storage_path)
        else:
            storage_path = os.path.join(user_data_dir, "memory", "memories.json")
            self.store = JsonMemoryStore(storage_path)
        
        self.expiration_manager = MemoryExpirationManager(self.store)
        
        logger.info("UnifiedMemoryManager initialized with simplified storage")
    
    def _create_sqlite_store(self, user_data_dir: str) -> SimplifiedMemoryStore:
        import os
        storage_path = os.path.join(user_data_dir, "memory", "memories.json")
        return JsonMemoryStore(storage_path)
    
    def add_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        importance: float = 0.5,
        **kwargs
    ) -> str:
        import uuid
        memory_id = str(uuid.uuid4())
        
        memory_data = {
            "id": memory_id,
            "content": content,
            "type": memory_type,
            "importance": importance,
            "created_at": datetime.now().isoformat(),
            **kwargs
        }
        
        self.store.save(memory_id, memory_data)
        
        if hash(memory_id) % 10 == 0:
            self.expiration_manager.cleanup_expired()
        
        return memory_id
    
    def retrieve_relevant(
        self,
        query: str,
        limit: int = 5,
        min_importance: float = 0.0
    ) -> List[Dict[str, Any]]:
        memories = []
        query_lower = query.lower()
        
        for memory_id in self.store.list_all():
            memory = self.store.load(memory_id)
            if not memory:
                continue
            
            if memory.get("importance", 0) < min_importance:
                continue
            
            content_lower = memory.get("content", "").lower()
            if query_lower in content_lower or any(keyword in content_lower for keyword in query_lower.split()):
                memories.append(memory)
        
        memories.sort(key=lambda x: x.get("importance", 0), reverse=True)
        return memories[:limit]
    
    def cleanup(self) -> int:
        return self.expiration_manager.cleanup_expired()


class VectorStoreAdapter(SimplifiedMemoryStore):
    """向量存储适配器 - 适配ChromaDB和FAISS"""
    
    def __init__(self, store_type: StorageType, data_dir: str):
        self.store_type = store_type
        self.data_dir = data_dir
        self._vector_store = None
        self._embedding_model = None
        self._initialized = False
        self._cache = {}
    
    def _initialize(self):
        """延迟初始化向量存储"""
        if self._initialized:
            return
        
        try:
            if self.store_type == StorageType.CHROMA:
                from chromadb import PersistentClient
                chromadb_path = os.path.join(self.data_dir, "chromadb")
                os.makedirs(chromadb_path, exist_ok=True)
                self._vector_store = PersistentClient(path=chromadb_path)
                self._collection = self._vector_store.get_or_create_collection("memories")
            elif self.store_type == StorageType.FAISS:
                import faiss
                self._vector_store = faiss.IndexFlatL2(384)
                self._index_path = os.path.join(self.data_dir, "faiss_index")
                if os.path.exists(self._index_path):
                    self._vector_store = faiss.read_index(self._index_path)
            
            # 初始化嵌入模型
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except:
                logger.warning("SentenceTransformer not available, using simple embedding")
                
            self._initialized = True
            logger.info(f"Vector store {self.store_type.value} initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize vector store: {e}")
            self._initialized = False
    
    def save(self, memory_id: str, data: Dict[str, Any]) -> bool:
        self._initialize()
        if not self._initialized:
            return False
        
        try:
            content = data.get("content", "")
            if self._embedding_model:
                embedding = self._embedding_model.encode([content])[0]
            else:
                embedding = self._simple_embed(content)
            
            if self.store_type == StorageType.CHROMA:
                self._collection.upsert(
                    ids=[memory_id],
                    embeddings=[embedding.tolist()],
                    documents=[content],
                    metadatas=[data]
                )
            elif self.store_type == StorageType.FAISS:
                import numpy as np
                self._vector_store.add(np.array([embedding]))
                faiss.write_index(self._vector_store, self._index_path)
            
            self._cache[memory_id] = data
            return True
        except Exception as e:
            logger.error(f"Vector store save failed: {e}")
            return False
    
    def load(self, memory_id: str) -> Optional[Dict[str, Any]]:
        if memory_id in self._cache:
            return self._cache[memory_id]
        
        self._initialize()
        if not self._initialized:
            return None
        
        try:
            if self.store_type == StorageType.CHROMA:
                result = self._collection.get(ids=[memory_id])
                if result and result['documents']:
                    metadata = result['metadatas'][0] if result['metadatas'] else {}
                    metadata['content'] = result['documents'][0]
                    self._cache[memory_id] = metadata
                    return metadata
        except Exception as e:
            logger.error(f"Vector store load failed: {e}")
        return None
    
    def delete(self, memory_id: str) -> bool:
        self._initialize()
        if not self._initialized:
            return False
        
        try:
            if self.store_type == StorageType.CHROMA:
                self._collection.delete(ids=[memory_id])
            if memory_id in self._cache:
                del self._cache[memory_id]
            return True
        except Exception as e:
            logger.error(f"Vector store delete failed: {e}")
            return False
    
    def list_all(self) -> List[str]:
        self._initialize()
        if not self._initialized:
            return list(self._cache.keys())
        
        try:
            if self.store_type == StorageType.CHROMA:
                result = self._collection.get()
                return result['ids'] if result else []
        except Exception as e:
            logger.error(f"Vector store list_all failed: {e}")
        return list(self._cache.keys())
    
    def clear_all(self) -> bool:
        self._initialize()
        if not self._initialized:
            self._cache = {}
            return True
        
        try:
            if self.store_type == StorageType.CHROMA:
                self._collection.delete(ids=self._collection.get()['ids'])
            elif self.store_type == StorageType.FAISS:
                import faiss
                self._vector_store = faiss.IndexFlatL2(384)
                faiss.write_index(self._vector_store, self._index_path)
            self._cache = {}
            return True
        except Exception as e:
            logger.error(f"Vector store clear_all failed: {e}")
            return False
    
    def _simple_embed(self, text: str) -> List[float]:
        """简单的字符级嵌入（备选方案）"""
        import hashlib
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        embedding = []
        for i in range(384):
            embedding.append(((hash_val >> (i * 8)) % 256) / 255.0)
        return embedding
    
    def search_similar(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """向量相似度检索"""
        self._initialize()
        if not self._initialized or not self._embedding_model:
            return []
        
        try:
            query_embedding = self._embedding_model.encode([query])[0]
            
            if self.store_type == StorageType.CHROMA:
                results = self._collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=k
                )
                if results and results['documents']:
                    memories = []
                    for i, doc in enumerate(results['documents'][0]):
                        metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                        memories.append({
                            "content": doc,
                            "score": results['distances'][0][i],
                            **metadata
                        })
                    return memories
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
        return []


class SmartRetrievalManager:
    """智能检索管理器 - 支持自动选择最佳检索策略"""
    
    def __init__(
        self,
        user_data_dir: str,
        strategy: RetrievalStrategy = RetrievalStrategy.AUTO,
        primary_store: StorageType = StorageType.JSON,
        vector_store_type: StorageType = StorageType.CHROMA
    ):
        import os
        self.user_data_dir = user_data_dir
        self.strategy = strategy
        self.primary_store_type = primary_store
        self.vector_store_type = vector_store_type
        
        # 初始化主存储（快速访问）
        storage_path = os.path.join(user_data_dir, "memory", "memories.json")
        self.primary_store = JsonMemoryStore(storage_path)
        
        # 初始化向量存储（精准检索）
        self.vector_store = VectorStoreAdapter(vector_store_type, user_data_dir)
        
        # 初始化过期管理器
        self.expiration_manager = MemoryExpirationManager(self.primary_store)
        
        # 统计信息（用于智能决策）
        self._memory_count = 0
        self._query_count = 0
        self._vector_success_rate = 0.0
        
        logger.info(f"SmartRetrievalManager initialized with strategy: {strategy.value}")
    
    def add_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        importance: float = 0.5,
        embedding_enabled: bool = True,
        **kwargs
    ) -> str:
        """添加记忆，智能决定是否创建向量索引"""
        import uuid
        memory_id = str(uuid.uuid4())
        
        memory_data = {
            "id": memory_id,
            "content": content,
            "type": memory_type,
            "importance": importance,
            "created_at": datetime.now().isoformat(),
            **kwargs
        }
        
        # 保存到主存储
        self.primary_store.save(memory_id, memory_data)
        
        # 根据策略决定是否保存到向量存储
        if embedding_enabled and self._should_use_vector(memory_type, importance):
            self.vector_store.save(memory_id, memory_data)
        
        # 更新统计
        self._memory_count += 1
        
        # 定期清理
        if self._memory_count % 10 == 0:
            self.expiration_manager.cleanup_expired()
        
        return memory_id
    
    def retrieve_relevant(
        self,
        query: str,
        limit: int = 5,
        min_importance: float = 0.0,
        strategy: Optional[RetrievalStrategy] = None
    ) -> List[Dict[str, Any]]:
        """智能检索相关记忆"""
        effective_strategy = strategy or self.strategy
        self._query_count += 1
        
        if effective_strategy == RetrievalStrategy.KEYWORD:
            return self._keyword_search(query, limit, min_importance)
        elif effective_strategy == RetrievalStrategy.VECTOR:
            return self._vector_search(query, limit, min_importance)
        elif effective_strategy == RetrievalStrategy.HYBRID:
            return self._hybrid_search(query, limit, min_importance)
        else:  # AUTO
            return self._auto_search(query, limit, min_importance)
    
    def _keyword_search(self, query: str, limit: int, min_importance: float) -> List[Dict[str, Any]]:
        """关键词匹配检索"""
        memories = []
        query_lower = query.lower()
        
        for memory_id in self.primary_store.list_all():
            memory = self.primary_store.load(memory_id)
            if not memory:
                continue
            
            if memory.get("importance", 0) < min_importance:
                continue
            
            content_lower = memory.get("content", "").lower()
            if query_lower in content_lower or any(keyword in content_lower for keyword in query_lower.split()):
                memory['retrieval_method'] = 'keyword'
                memories.append(memory)
        
        memories.sort(key=lambda x: x.get("importance", 0), reverse=True)
        return memories[:limit]
    
    def _vector_search(self, query: str, limit: int, min_importance: float) -> List[Dict[str, Any]]:
        """向量相似度检索"""
        results = self.vector_store.search_similar(query, k=limit * 2)
        
        # 过滤和排序
        filtered = []
        for result in results:
            if result.get("importance", 0) >= min_importance:
                result['retrieval_method'] = 'vector'
                filtered.append(result)
        
        # 按分数排序（向量检索的分数通常是距离，越小越好）
        filtered.sort(key=lambda x: x.get("score", float('inf')))
        return filtered[:limit]
    
    def _hybrid_search(self, query: str, limit: int, min_importance: float) -> List[Dict[str, Any]]:
        """混合检索策略"""
        keyword_results = self._keyword_search(query, limit * 2, min_importance)
        vector_results = self._vector_search(query, limit * 2, min_importance)
        
        # 合并结果（去重）
        seen_ids = set()
        merged = []
        
        # 优先添加向量检索结果（通常更精准）
        for result in vector_results:
            mem_id = result.get("id", result.get("content", str(id(result))))
            if mem_id not in seen_ids:
                seen_ids.add(mem_id)
                merged.append(result)
        
        # 补充关键词检索结果
        for result in keyword_results:
            mem_id = result.get("id", result.get("content", str(id(result))))
            if mem_id not in seen_ids:
                seen_ids.add(mem_id)
                merged.append(result)
        
        return merged[:limit]
    
    def _auto_search(self, query: str, limit: int, min_importance: float) -> List[Dict[str, Any]]:
        """自动选择最佳检索策略"""
        # 决策逻辑
        query_length = len(query)
        memory_count = self._memory_count
        
        # 策略选择规则
        if memory_count < 10 or query_length < 3:
            # 记忆少或查询短：使用关键词检索（更快）
            return self._keyword_search(query, limit, min_importance)
        elif query_length >= 10 and self.vector_store._initialized:
            # 查询较长且向量存储可用：使用混合策略
            return self._hybrid_search(query, limit, min_importance)
        else:
            # 默认使用关键词检索
            return self._keyword_search(query, limit, min_importance)
    
    def _should_use_vector(self, memory_type: str, importance: float) -> bool:
        """判断是否应该为该记忆创建向量索引"""
        # 只有高重要性的记忆才创建向量索引
        if importance >= 0.7:
            return True
        # 特定类型的记忆创建向量索引
        if memory_type in ["user_preferences", "important_events", "knowledge"]:
            return True
        return False
    
    def switch_strategy(self, new_strategy: RetrievalStrategy):
        """动态切换检索策略"""
        old_strategy = self.strategy
        self.strategy = new_strategy
        logger.info(f"Retrieval strategy switched from {old_strategy.value} to {new_strategy.value}")
    
    def cleanup(self) -> int:
        """清理过期记忆"""
        deleted = self.expiration_manager.cleanup_expired()
        
        # 同步清理向量存储中的过期记忆
        valid_ids = set(self.primary_store.list_all())
        vector_ids = set(self.vector_store.list_all())
        expired_vector_ids = vector_ids - valid_ids
        
        for mem_id in expired_vector_ids:
            self.vector_store.delete(mem_id)
        
        return deleted


def create_simplified_config():
    return {
        "storage_type": "json",
        "retrieval_strategy": "auto",
        "enable_expiration": True,
        "expiration_rules": [
            {"type": "temporary", "max_age": 6},
            {"type": "conversation", "max_age": 24},
            {"type": "long_term", "max_age": 720, "min_importance": 0.3},
        ]
    }


if __name__ == "__main__":
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 测试智能检索管理器
        manager = SmartRetrievalManager(
            tmpdir,
            strategy=RetrievalStrategy.AUTO
        )
        
        # 添加测试记忆
        manager.add_memory("用户喜欢喝珍珠奶茶", "user_preferences", 0.9)
        manager.add_memory("用户住在北京", "user_identity", 0.85)
        manager.add_memory("今天天气真好", "casual_conversation", 0.2)
        manager.add_memory("深度学习是机器学习的一个分支", "knowledge", 0.8)
        
        # 测试不同检索策略
        print("=== 关键词检索 ===")
        results = manager.retrieve_relevant("奶茶", strategy=RetrievalStrategy.KEYWORD)
        for r in results:
            print(f"- {r['content']} (method: {r.get('retrieval_method')})")
        
        print("\n=== 向量检索 ===")
        results = manager.retrieve_relevant("饮料", strategy=RetrievalStrategy.VECTOR)
        for r in results:
            print(f"- {r['content']} (method: {r.get('retrieval_method')})")
        
        print("\n=== 混合检索 ===")
        results = manager.retrieve_relevant("喜欢", strategy=RetrievalStrategy.HYBRID)
        for r in results:
            print(f"- {r['content']} (method: {r.get('retrieval_method')})")
        
        print("\n=== 自动策略 ===")
        results = manager.retrieve_relevant("机器学习")
        for r in results:
            print(f"- {r['content']} (method: {r.get('retrieval_method')})")
        
        # 动态切换策略
        print("\n=== 切换到向量策略 ===")
        manager.switch_strategy(RetrievalStrategy.VECTOR)
        results = manager.retrieve_relevant("人工智能")
        for r in results:
            print(f"- {r['content']}")
