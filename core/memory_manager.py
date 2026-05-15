"""Memory Manager Module

记忆系统管理模块，负责短期记忆、长期记忆的存储和检索。
"""

from __future__ import annotations

import asyncio
import datetime
import os
import sys
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Union

from loguru import logger
from pydantic import BaseModel, Field

from core.memory.base import (LongTermMemory, Memory, MemoryNode,
                              ShortTermMemory)
from core.memory_types import MEMORY_TYPES
from core.memory_optimizations import (
    SmartRetrievalManager,
    RetrievalStrategy,
    MemoryExpirationManager,
    JsonMemoryStore,
    VectorStoreAdapter,
    StorageType,
)
from core.semantic_memory import (
    SemanticMemoryStore,
    HybridMemoryRetriever,
    get_semantic_store,
    get_hybrid_retriever,
)


class BaseRetriever(ABC):
    """检索器基类"""
    
    @abstractmethod
    def get_relevant_documents(self, query: str, **kwargs) -> List[Memory]:
        """获取相关文档"""
        pass
    
    async def aget_relevant_documents(self, query: str, **kwargs) -> List[Memory]:
        """异步获取相关文档"""
        return self.get_relevant_documents(query, **kwargs)


class VectorRetriever(BaseRetriever):
    """向量检索器"""
    
    def __init__(self, vector_store, embedding_model, k: int = 5):
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.k = k
    
    def get_relevant_documents(self, query: str, **kwargs) -> List[Memory]:
        """向量相似性检索"""
        k = kwargs.get('k', self.k)
        
        try:
            if hasattr(self.embedding_model, 'encode'):
                query_embedding = self.embedding_model.encode([query])[0]
            else:
                logger.warning("Embedding model has no encode method")
                return []
            
            if hasattr(self.vector_store, 'search'):
                results = self.vector_store.search(query_embedding, k=k)
            elif hasattr(self.vector_store, 'query'):
                results = self.vector_store.query(query_embeddings=[query_embedding.tolist()], n_results=k)
                if results and 'documents' in results:
                    results = [{'content': doc, **(results['metadatas'][0][i] if results.get('metadatas') else {})}
                               for i, doc in enumerate(results['documents'][0])]
            else:
                logger.warning("Vector store has no search method")
                return []
            
            memories = []
            for result in results:
                if isinstance(result, dict) and 'content' in result:
                    memory = Memory(
                        content=result['content'],
                        memory_type=MEMORY_TYPES.LONG_TERM,
                        importance=result.get('importance', 0.5),
                        timestamp=datetime.datetime.now()
                    )
                    memories.append(memory)
            
            return memories
        
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []


class HybridRetriever(BaseRetriever):
    """混合检索器"""
    
    def __init__(self, retrievers: List[BaseRetriever], weights: Optional[List[float]] = None):
        self.retrievers = retrievers
        self.weights = weights or [1.0] * len(retrievers)
    
    def get_relevant_documents(self, query: str, **kwargs) -> List[Memory]:
        """混合策略检索"""
        all_results = []
        
        for retriever, weight in zip(self.retrievers, self.weights):
            try:
                if hasattr(retriever, 'get_relevant_documents'):
                    results = retriever.get_relevant_documents(query, **kwargs)
                elif hasattr(retriever, 'search_similar'):
                    results = retriever.search_similar(query, k=kwargs.get('k', 5))
                    results = [Memory(content=r['content'],
                                     memory_type=MEMORY_TYPES.LONG_TERM,
                                     importance=r.get('importance', 0.5),
                                     timestamp=datetime.datetime.now())
                               for r in results if isinstance(r, dict) and 'content' in r]
                else:
                    logger.warning(f"Retriever {type(retriever).__name__} has no valid search method")
                    continue
                
                for memory in results:
                    memory.score = getattr(memory, 'score', 0) + weight
                all_results.extend(results)
            except Exception as e:
                logger.error(f"检索器失败: {e}")
        
        seen_contents = set()
        unique_results = []
        
        for memory in sorted(all_results, key=lambda x: getattr(x, 'score', 0), reverse=True):
            content = getattr(memory, 'content', str(memory))
            if content not in seen_contents:
                seen_contents.add(content)
                unique_results.append(memory)
        
        return unique_results[:kwargs.get('k', 5)]


class MemorySelector:
    """记忆选择器"""
    
    def __init__(self, memory_manager: 'MemoryManager', retriever: BaseRetriever, token_budget: int = 3000):
        self.memory_manager = memory_manager
        self.retriever = retriever
        self.token_budget = token_budget
        self._bm25_available: Optional[bool] = None
        self._BM25Okapi = None
        self._jieba = None
        
        self.semantic_store = get_semantic_store()
        self.hybrid_retriever = get_hybrid_retriever()
    
    def select_memories(self, query: str, k: int = 8, filters: Optional[Dict[str, Any]] = None,
                        include_short_term: bool = True, include_long_term: bool = True) -> List[Tuple[Memory, float]]:
        """选择相关记忆"""
        logger.debug(f"[select_memories] Query: '{query[:50]}...', k={k}")
        
        candidates: List[Memory] = []
        if include_short_term:
            short_term = self.memory_manager.list_short_term_memories(filters=filters)
            candidates.extend(short_term)
            logger.debug(f"[select_memories] Found {len(short_term)} short-term memories")
        if include_long_term:
            long_term = self.memory_manager.list_long_term_memories(filters=filters)
            candidates.extend(long_term)
            logger.debug(f"[select_memories] Found {len(long_term)} long-term memories")
        
        if not candidates:
            logger.debug("[select_memories] No candidate memories found")
            return []
        
        self._sync_semantic_store(candidates)
        
        semantic_results = self.hybrid_retriever.retrieve(query, k=k * 3)
        logger.debug(f"[select_memories] Semantic results: {len(semantic_results)}")
        
        bm25_results = self._get_bm25_results(query, candidates, k=k * 3)
        logger.debug(f"[select_memories] BM25 results: {len(bm25_results)}")
        
        scores: Dict[str, float] = {}
        
        for sem_mem, score in semantic_results:
            scores[sem_mem.id] = score * 0.6
        
        if bm25_results:
            max_bm25 = max(score for _, score in bm25_results) or 1.0
            for memory, score in bm25_results:
                normalized = score / max_bm25
                scores[memory.id] = scores.get(memory.id, 0.0) + normalized * 0.4
        
        ranked: List[Tuple[Memory, float]] = []
        now = datetime.datetime.now()
        for memory in candidates:
            base = scores.get(memory.id, 0.0)
            importance_factor = memory.importance * 0.2
            age_hours = (now - memory.created_at).total_seconds() / 3600.0
            recency_factor = 1.0 / (1.0 + age_hours / 24.0)
            final_score = base + importance_factor + recency_factor * 0.15
            ranked.append((memory, final_score))
        
        ranked.sort(key=lambda x: x[1], reverse=True)
        
        selected: List[Tuple[Memory, float]] = []
        seen_ids = set()
        token_count = 0
        for memory, score in ranked:
            if memory.id in seen_ids:
                continue
            seen_ids.add(memory.id)
            if memory.token_count is None:
                memory.token_count = self.memory_manager._calculate_tokens(memory.content)
            if token_count + (memory.token_count or 0) > self.token_budget:
                break
            selected.append((memory, score))
            token_count += memory.token_count or 0
            if len(selected) >= k:
                break
        
        logger.debug(f"[select_memories] Selected {len(selected)} memories")
        for mem, score in selected[:3]:
            logger.debug(f"  - {score:.4f}: {mem.content[:50]}...")
        
        return selected
    
    def _sync_semantic_store(self, memories: List[Memory]):
        """同步到语义存储"""
        try:
            for memory in memories:
                existing = self.semantic_store.get_memory(memory.id)
                if not existing:
                    self.semantic_store.add_memory(
                        content=memory.content,
                        id=memory.id,
                        importance=memory.importance,
                        created_at=memory.created_at,
                        metadata={'type': memory.memory_type}
                    )
        except Exception as e:
            logger.warning(f"Failed to sync memory to semantic store: {e}")
    
    def _get_vector_results(self, query: str, k: int, filters: Optional[Dict[str, Any]]) -> List[Memory]:
        try:
            if hasattr(self.retriever, 'get_relevant_documents'):
                return self.retriever.get_relevant_documents(query, k=k, filters=filters)
            elif hasattr(self.retriever, 'search_similar'):
                results = self.retriever.search_similar(query, k=k)
                return [Memory(content=r['content'],
                               memory_type=MEMORY_TYPES.LONG_TERM,
                               importance=r.get('importance', 0.5),
                               timestamp=datetime.datetime.now())
                        for r in results if isinstance(r, dict) and 'content' in r]
            else:
                logger.warning(f"Retriever {type(self.retriever).__name__} has no valid search method")
                return []
        except Exception as e:
            logger.warning(f"向量检索异常: {e}")
            return []
    
    def _load_bm25_dependencies(self) -> bool:
        if self._bm25_available is not None:
            return self._bm25_available
        try:
            import jieba
            from rank_bm25 import BM25Okapi
            
            self._BM25Okapi = BM25Okapi
            self._jieba = jieba
            self._bm25_available = True
        except ImportError:
            self._bm25_available = False
        return self._bm25_available
    
    def _get_bm25_results(
        self, query: str, candidates: List[Memory], k: int
    ) -> List[Tuple[Memory, float]]:
        if not self._load_bm25_dependencies():
            return []
        try:
            assert self._BM25Okapi is not None and self._jieba is not None
            documents = [mem.content for mem in candidates]
            tokenized_docs = [list(self._jieba.cut_for_search(doc)) for doc in documents]
            tokenized_query = list(self._jieba.cut_for_search(query))
            bm25 = self._BM25Okapi(tokenized_docs)
            scores = bm25.get_scores(tokenized_query)
            results = [
                (candidates[i], scores[i])
                for i in range(len(candidates))
                if scores[i] > 0
            ]
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]
        except Exception as e:
            logger.warning(f"BM25检索异常: {e}")
            return []


class MemoryBlock(BaseModel):
    """记忆块"""
    
    name: str
    priority: int = Field(default=0, description="优先级（0=最高）")
    accept_short_term_memory: bool = Field(default=True)
    token_limit: int = Field(default=1000, description="最大令牌数")
    content: List[Memory] = Field(default_factory=list)
    
    def add_memory(self, memory: Memory) -> bool:
        """添加记忆"""
        if not self.accept_short_term_memory and isinstance(memory, ShortTermMemory):
            return False
        
        current_tokens = sum(m.token_count or 0 for m in self.content)
        new_tokens = memory.token_count or 0
        
        if current_tokens + new_tokens > self.token_limit:
            self.content.sort(key=lambda x: x.importance, reverse=True)
            while current_tokens + new_tokens > self.token_limit and self.content:
                removed = self.content.pop()
                current_tokens -= removed.token_count or 0
        
        self.content.append(memory)
        return True
    
    def get_relevant_memories(self, query: str, k: int = 5) -> List[Memory]:
        """获取相关记忆"""
        return self.content[:k]
    
    def truncate(self, tokens_to_truncate: int) -> int:
        """截断记忆块"""
        if not self.content:
            return 0
        
        self.content.sort(key=lambda x: x.importance, reverse=True)
        
        truncated_tokens = 0
        while truncated_tokens < tokens_to_truncate and len(self.content) > 1:
            removed = self.content.pop()
            truncated_tokens += removed.token_count or 0
        
        return truncated_tokens


class MemoryManager:
    """记忆系统管理器（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[Dict[str, Any]] = None, ai_manager=None):
        """确保只创建一个实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, ai_manager=None):
        """初始化记忆管理器"""
        if ai_manager is not None:
            self.ai_manager = ai_manager
        
        if not hasattr(self, "_initialized"):
            with self._lock:
                if not hasattr(self, "_initialized"):
                    self._initialized = True
                    self.config = config or {}
                    if ai_manager is not None:
                        self.ai_manager = ai_manager
                    
                    if getattr(sys, "frozen", False):
                        self.base_path = os.path.dirname(sys.executable)
                    else:
                        self.base_path = os.path.dirname(
                            os.path.dirname(os.path.abspath(__file__))
                        )
                    
                    self.token_limit = self.config.get("token_limit", 30000)
                    self.token_flush_size = self.config.get(
                        "token_flush_size", int(self.token_limit * 0.1)
                    )
                    self.chat_history_token_ratio = self.config.get(
                        "chat_history_token_ratio", 0.7
                    )
                    self.decay_rate = self.config.get("decay_rate", 0.01)
                    self.decay_type = self.config.get(
                        "decay_type", "exponential"
                    )
                    self.dialogue_decay_rate = self.config.get("dialogue_decay_rate", 0.02)
                    self._dialogue_count_since_last_decay = 0
                    
                    user_data_dir = self._get_user_data_dir()
                    memory_dir = os.path.join(user_data_dir, "memory")
                    os.makedirs(memory_dir, exist_ok=True)
                    
                    from core.memory.sqlite_storage import SQLiteMemoryStore
                    
                    db_path = os.path.join(memory_dir, "memory.db")
                    self.sqlite_store = SQLiteMemoryStore(db_path=db_path)
                    
                    from core.memory.persistent_storage import (
                        PersistentLongTermMemoryStore,
                        PersistentShortTermMemoryStore)
                    
                    self.short_term_store = PersistentShortTermMemoryStore(
                        storage_path=os.path.join(memory_dir, "short_term_memory.json")
                    )
                    self.long_term_store = PersistentLongTermMemoryStore(
                        storage_path=os.path.join(memory_dir, "long_term_memory.json")
                    )
                    
                    from core.memory.embedding import SentenceTransformerEmbedding
                    
                    from utils.config_manager import config_manager
                    user_embedding_path = config_manager.get("memory.embedding_model_path", "")
                    
                    embedding_model_path = None
                    if user_embedding_path and os.path.exists(user_embedding_path):
                        embedding_model_path = user_embedding_path
                        logger.debug(f"使用用户配置的嵌入模型路径: {embedding_model_path}")
                    else:
                        default_path = os.path.join(self.base_path, "minilm")
                        if os.path.exists(default_path):
                            embedding_model_path = default_path
                            logger.debug(f"使用默认嵌入模型路径: {embedding_model_path}")
                    
                    if embedding_model_path:
                        self.embedding = SentenceTransformerEmbedding(
                            custom_model_path=embedding_model_path,
                            user_data_dir=user_data_dir,
                        )
                    else:
                        self.embedding = SentenceTransformerEmbedding(
                            user_data_dir=user_data_dir
                        )
                    
                    from core.memory.chroma_storage import ChromaMemoryStore
                    
                    chroma_db_path = os.path.join(user_data_dir, "chromadb")
                    self.chroma_store = ChromaMemoryStore(db_path=chroma_db_path)
                    
                    try:
                        from core.memory.faiss_store import FaissVectorStore, EnhancedFaissRetriever
                        
                        faiss_index_path = os.path.join(user_data_dir, "memory", "faiss_index")
                        self.faiss_store = FaissVectorStore(
                            index_path=faiss_index_path,
                            dim=384,
                            index_type="ivf_flat",
                            metric="IP",
                            nlist=100,
                            enable_gpu=True
                        )
                        self.faiss_store.load()
                        self.faiss_retriever = EnhancedFaissRetriever(self.faiss_store)
                        logger.debug("FAISS向量存储初始化完成")
                    except Exception as e:
                        logger.warning(f"FAISS向量存储初始化失败: {e}")
                        self.faiss_store = None
                        self.faiss_retriever = None
                    
                    try:
                        from core.proactive.topic_store import TopicStore
                        
                        topic_store_path = os.path.join(user_data_dir, "memory", "topic_store.json")
                        self.topic_store = TopicStore(topic_store_path)
                        logger.debug("话题存储初始化完成")
                    except Exception as e:
                        logger.warning(f"话题存储初始化失败: {e}")
                        self.topic_store = None
                    
                    self.vector_retriever = VectorRetriever(
                        vector_store=self.chroma_store,
                        embedding_model=self.embedding,
                        k=5
                    )
                    
                    retrievers = [self.vector_retriever]
                    if hasattr(self, 'faiss_retriever') and self.faiss_retriever:
                        retrievers.append(self.faiss_retriever)
                    
                    if len(retrievers) > 1:
                        self.retriever = HybridRetriever(retrievers)
                    else:
                        self.retriever = self.vector_retriever
                    
                    self.selector = MemorySelector(
                        memory_manager=self,
                        retriever=self.retriever,
                        token_budget=self.token_limit,
                    )
                    
                    logger.debug("检索器初始化完成")
                    
                    from core.memory.updater import AdaptiveMemoryUpdater
                    
                    self.updater = AdaptiveMemoryUpdater()
                    
                    from core.memory.forgetter import AdaptiveMemoryForgetter
                    
                    self.forgetter = AdaptiveMemoryForgetter(
                        self.short_term_store, self.long_term_store
                    )
                    
                    from core.memory.compressor import (
                        LangChainMemoryCompressor, SimpleMemoryCompressor)
                    
                    self.compressor = (
                        LangChainMemoryCompressor()
                        if LangChainMemoryCompressor().langchain_available
                        else SimpleMemoryCompressor()
                    )
                    
                    from core.memory.compressor import AutoGPTMemoryPrioritizer
                    
                    self.prioritizer = AutoGPTMemoryPrioritizer()
                    
                    from core.memory.optimizer import MemoryOptimizer
                    
                    self.optimizer = MemoryOptimizer()
                    
                    from core.memory.relationship_manager import MemoryRelationshipManager
                    
                    self.relationship_manager = MemoryRelationshipManager()
                    
                    from core.memory.visualization import MemoryVisualizer
                    
                    self.visualizer = MemoryVisualizer()
                    
                    self.use_chroma_for_long_term = True
                    
                    from core.memory_hybrid_retriever import HybridMemoryRetriever
                    self.hybrid_retriever = HybridMemoryRetriever(self, ai_manager)
                    logger.debug("混合记忆检索器初始化完成")
                    
                    from core.memory_auto_extractor import AutoMemoryExtractor
                    self.auto_extractor = AutoMemoryExtractor(self, ai_manager)
                    logger.debug("自动记忆提取器初始化完成")
                    
                    self.memory_blocks: List[MemoryBlock] = []
                    self._init_memory_blocks()
                    
                    self.tokenizer = self._get_tokenizer()
                    
                    self._init_smart_retrieval()
                    
                    self._init_memory_expiration()
    
    def _init_smart_retrieval(self) -> None:
        """初始化智能检索"""
        try:
            user_data_dir = self._get_user_data_dir()
            memory_dir = os.path.join(user_data_dir, "memory")
            os.makedirs(memory_dir, exist_ok=True)
            
            strategy_str = self.config.get("retrieval_strategy", "auto")
            try:
                strategy = RetrievalStrategy(strategy_str)
            except ValueError:
                strategy = RetrievalStrategy.AUTO
            
            vector_store_str = self.config.get("vector_store_type", "chroma")
            try:
                vector_store_type = StorageType(vector_store_str)
            except ValueError:
                vector_store_type = StorageType.CHROMA
            
            self.smart_retriever = SmartRetrievalManager(
                user_data_dir=memory_dir,
                strategy=strategy,
                primary_store=StorageType.JSON,
                vector_store_type=vector_store_type
            )
            
            logger.info(f"智能检索管理器初始化完成，策略: {strategy.value}")
        except Exception as e:
            logger.warning(f"智能检索管理器初始化失败: {e}")
            self.smart_retriever = None
    
    def _init_memory_expiration(self) -> None:
        """初始化记忆过期管理"""
        try:
            user_data_dir = self._get_user_data_dir()
            memory_dir = os.path.join(user_data_dir, "memory")
            storage_path = os.path.join(memory_dir, "memories.json")
            
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            
            self.expiration_store = JsonMemoryStore(storage_path)
            
            self.expiration_manager = MemoryExpirationManager(self.expiration_store)
            
            self.enable_auto_expiration = self.config.get("enable_expiration", True)
            
            self.expiration_interval = self.config.get("expiration_interval", 10)
            self._operation_count = 0
            
            logger.info("记忆过期管理器初始化完成")
        except Exception as e:
            logger.warning(f"记忆过期管理器初始化失败: {e}")
            self.expiration_manager = None
            self.enable_auto_expiration = False
    
    def _get_user_data_dir(self) -> str:
        """获取用户数据目录"""
        import os
        import platform
        
        app_name = "vivian"
        
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA")
            if not appdata:
                appdata = os.path.expanduser("~")
            user_data_dir = os.path.join(appdata, app_name)
        elif platform.system() == "Darwin":
            user_data_dir = os.path.join(
                os.path.expanduser("~"), "Library", "Application Support", app_name
            )
        else:
            user_data_dir = os.path.join(
                os.path.expanduser("~"), f".{app_name.lower()}"
            )
        
        os.makedirs(user_data_dir, exist_ok=True)
        return user_data_dir
    
    def _init_memory_blocks(self) -> None:
        """初始化记忆块"""
        self.memory_blocks = [
            MemoryBlock(name="important_events", priority=0, token_limit=5000),
            MemoryBlock(name="conversation_history", priority=1, token_limit=10000),
            MemoryBlock(name="knowledge_base", priority=2, token_limit=15000),
        ]
    
    def _get_tokenizer(self) -> Any:
        """获取令牌计算器"""
        try:
            local_path = os.path.join(self.base_path, "tokenizer")
            tokenizer_path = os.path.join(local_path, "tokenizer.json")
            
            try:
                from tokenizers import Tokenizer
                
                if os.path.exists(tokenizer_path):
                    tokenizer = Tokenizer.from_file(tokenizer_path)
                    return tokenizer
            except Exception:
                pass
            
            try:
                from tokenizers import GPT2TokenizerFast as RustGPT2TokenizerFast
                
                if os.path.exists(local_path):
                    tokenizer = RustGPT2TokenizerFast.from_file(tokenizer_path)
                    return tokenizer
            except Exception:
                pass
            
            class SimpleGPT2Tokenizer:
                """简单GPT2令牌器"""
                
                def __init__(self):
                    import re
                    
                    self.pattern = re.compile(
                        r"'s|'t|'re|'ve|'m|'ll|'d| ?[a-zA-Z\u00c0-\u017f\u4e00-\u9fa5]+| ?[0-9]+| ?[^\s\w\u4e00-\u9fa5]+|\s+(?!\S)|\s+"
                    )
                
                def encode(self, text):
                    import re
                    
                    tokens = self.pattern.findall(text)
                    return [
                        hash(token) % 50257 for token in tokens
                    ]
                
                def decode(self, token_ids):
                    return "".join([f"<token_{tid}>" for tid in token_ids])
            
            return SimpleGPT2Tokenizer()
        
        except Exception:
            return lambda text: len(text.split())
    
    def _calculate_tokens(self, text: str) -> int:
        """计算令牌数"""
        try:
            if hasattr(self.tokenizer, "encode"):
                result = self.tokenizer.encode(text)
                if isinstance(result, list):
                    return len(result)
                elif hasattr(result, "tokens"):
                    return len(result.tokens)
                elif hasattr(result, "ids"):
                    return len(result.ids)
                else:
                    return len(result)
            return self.tokenizer(text)
        except Exception:
            return len(text.split())
    
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
    
    def add_memory(
        self, content: str, memory_type: str = "short_term", **kwargs
    ) -> str:
        """添加记忆"""
        token_count = self._calculate_tokens(content)
        
        importance = kwargs.get("importance", 0.5)
        if self._detect_name_in_content(content):
            importance = min(0.95, importance + 0.4)
            logger.debug(f"检测到名字信息，提升重要性到 {importance}")
        
        if memory_type == "short_term":
            memory = ShortTermMemory(
                content=content,
                token_count=token_count,
                initial_importance=importance,
                **kwargs,
            )
            memory_id = self.short_term_store.save_memory(memory)
        elif memory_type == "long_term":
            embedding = kwargs.pop("embedding", None)
            if embedding is None:
                embedding = self.embedding.embed(content)
            importance = kwargs.pop("importance", 0.5)
            memory = LongTermMemory(
                content=content,
                embedding=embedding,
                token_count=token_count,
                importance=importance,
                initial_importance=importance,
                **kwargs,
            )
            
            if self.use_chroma_for_long_term:
                try:
                    memory_id = self.chroma_store.save_memory(memory)
                except Exception as e:
                    logger.warning(f"ChromaDB存储失败，回退到JSON存储: {e}")
                    memory_id = self.long_term_store.save_memory(memory)
            else:
                memory_id = self.long_term_store.save_memory(memory)
                try:
                    self.chroma_store.save_memory(memory)
                except Exception as e:
                    logger.warning(f"ChromaDB同步失败: {e}")
        else:
            raise ValueError(f"Unknown memory type: {memory_type}")
        
        self._check_memory_limits()
        
        self._dialogue_count_since_last_decay += 1
        
        if (self.enable_auto_expiration and 
            hasattr(self, 'expiration_manager') and 
            self.expiration_manager and
            self._operation_count % self.expiration_interval == 0):
            try:
                deleted_count = self.expiration_manager.cleanup_expired()
                if deleted_count > 0:
                    logger.info(f"自动过期清理完成，删除了 {deleted_count} 条过期记忆")
            except Exception as e:
                logger.warning(f"自动过期清理失败: {e}")
        
        self._operation_count += 1
        
        return memory_id
    
    def _check_memory_limits(self) -> None:
        """检查记忆限制"""
        short_term_memories = self.list_short_term_memories()
        total_short_term_tokens = sum(m.token_count or 0 for m in short_term_memories)
        
        if total_short_term_tokens > self.token_limit * self.chat_history_token_ratio:
            self.consolidate_sensory_to_semantic()
    
    def get_memory(
        self, memory_id: str, memory_type: str = "short_term"
    ) -> Optional[Memory]:
        """获取记忆"""
        if memory_type == "short_term":
            return self.short_term_store.get_memory(memory_id)
        elif memory_type == "long_term":
            return self.long_term_store.get_memory(memory_id)
        else:
            raise ValueError(f"Unknown memory type: {memory_type}")
    
    def update_memory(self, memory: Memory) -> None:
        """更新记忆"""
        updated_memory = self.updater.update(memory)
        updated_memory.token_count = self._calculate_tokens(updated_memory.content)
        
        if isinstance(updated_memory, ShortTermMemory):
            self.short_term_store.update_memory(updated_memory)
        elif isinstance(updated_memory, LongTermMemory):
            self.long_term_store.update_memory(updated_memory)
    
    def retrieve_memories(
        self, query: str, k: int = 5, filters: Optional[Dict[str, Any]] = None, **kwargs
    ) -> List[Tuple[Memory, float]]:
        """检索记忆"""
        import logging
        
        logger = logging.getLogger(__name__)
        logger.debug(f"开始检索记忆，查询: {query[:50]}..., k={k}")
        
        try:
            self.apply_time_decay_to_all_memories()
            logger.debug("已应用时间衰减到所有记忆")
            
            selected = self.selector.select_memories(
                query=query,
                k=k,
                filters=filters,
                include_short_term=kwargs.get("include_short_term", True),
                include_long_term=kwargs.get("include_long_term", True),
            )
            
            logger.debug(f"最终检索到 {len(selected)} 条相关记忆")
            return selected
        except Exception as e:
            logger.error(f"记忆检索失败: {e}", exc_info=True)
            return []
    
    def apply_time_decay_to_all_memories(self) -> None:
        """应用时间衰减"""
        dialogue_count = self._dialogue_count_since_last_decay
        
        short_term_memories = self.list_short_term_memories()
        updated_short_term = []
        for memory in short_term_memories:
            memory.update_importance_with_decay(
                self.decay_rate, 
                self.decay_type, 
                dialogue_count, 
                self.dialogue_decay_rate
            )
            updated_short_term.append(memory)
        
        if updated_short_term:
            with self.short_term_store._lock:
                for memory in updated_short_term:
                    self.short_term_store.memories[memory.id] = memory
                self.short_term_store._save_memories()
        
        long_term_memories = self.list_long_term_memories()
        updated_long_term = []
        for memory in long_term_memories:
            memory.update_importance_with_decay(
                self.decay_rate, 
                self.decay_type, 
                dialogue_count, 
                self.dialogue_decay_rate
            )
            updated_long_term.append(memory)
        
        if updated_long_term:
            with self.long_term_store._lock:
                for memory in updated_long_term:
                    self.long_term_store.memories[memory.id] = memory
                self.long_term_store._save_memories()
        
        self._dialogue_count_since_last_decay = 0
    
    def retrieve_memory(self, query: str, **kwargs) -> Dict[str, Any]:
        """检索记忆"""
        limit = kwargs.get("limit", 10)
        
        logger.debug(f"Retrieving memory for query: '{query[:50]}...', limit={limit}")
        
        result = {
            "profile": {
                "name": "主人",
                "preferences": [],
                "dislikes": [],
                "hobbies": [],
                "occupation": None,
                "location": None,
                "birthday": None,
                "conversation_style": "",
                "interests": [],
                "events": [],
                "last_interaction": time.time(),
            },
            "semantic_memory": [],
            "sensory_buffer": self.get_sensory_buffer(),
        }
        
        retrieved_memories = self.retrieve_memories(query, k=limit)
        result["semantic_memory"] = [mem for mem, score in retrieved_memories]
        
        logger.debug(f"[retrieve_memory] Retrieved {len(retrieved_memories)} memories for query: '{query[:50]}...'")
        for mem, score in retrieved_memories:
            logger.debug(f"[retrieve_memory]  - Memory: '{mem.content[:80]}...' (score: {score:.3f})")
        
        return result
    
    def _analyze_conversation_style(
        self, memories: List[Memory], profile: Dict[str, Any]
    ) -> None:
        """分析对话风格"""
        pass
    
    def forget_memories(
        self, filters: Optional[Dict[str, Any]] = None, **kwargs
    ) -> List[str]:
        """执行遗忘"""
        return self.forgetter.forget(filters=filters, **kwargs)
    
    def list_memories(self, memory_type: str = "short_term", **kwargs) -> List[Memory]:
        """列出记忆"""
        if memory_type == "short_term":
            return self.short_term_store.list_memories(**kwargs)
        elif memory_type == "long_term":
            return self.long_term_store.list_memories(**kwargs)
        else:
            raise ValueError(f"Unknown memory type: {memory_type}")
    
    def add_short_term_memory(self, content: str, **kwargs) -> str:
        """添加短期记忆"""
        return self.add_memory(content, memory_type="short_term", **kwargs)
    
    def add_long_term_memory(self, content: str, **kwargs) -> str:
        """添加长期记忆"""
        return self.add_memory(content, memory_type="long_term", **kwargs)
    
    def get_short_term_memory(self, memory_id: str) -> Optional[ShortTermMemory]:
        """获取短期记忆"""
        memory = self.get_memory(memory_id, memory_type="short_term")
        return memory if isinstance(memory, ShortTermMemory) else None
    
    def get_long_term_memory(self, memory_id: str) -> Optional[LongTermMemory]:
        """获取长期记忆"""
        memory = self.get_memory(memory_id, memory_type="long_term")
        return memory if isinstance(memory, LongTermMemory) else None
    
    def list_short_term_memories(self, **kwargs) -> List[ShortTermMemory]:
        """列出短期记忆"""
        memories = self.list_memories(memory_type="short_term", **kwargs)
        return [m for m in memories if isinstance(m, ShortTermMemory)]
    
    def list_long_term_memories(self, **kwargs) -> List[LongTermMemory]:
        """列出长期记忆"""
        memories = self.list_memories(memory_type="long_term", **kwargs)
        return [m for m in memories if isinstance(m, LongTermMemory)]
    
    def recall(
        self, query: str, k: int = 5, use_vector: bool = True
    ) -> List[Tuple[Memory, float]]:
        """回忆相关记忆"""
        return self.retrieve_memories(query, k=k)
    
    def learn(self, content: str, importance: float = 0.7, **kwargs) -> str:
        """学习新内容"""
        return self.add_long_term_memory(content, importance=importance, **kwargs)
    
    def forget(self, **kwargs) -> List[str]:
        """执行遗忘"""
        return self.forget_memories(**kwargs)
    
    def get_memory_stats(self) -> Dict[str, int]:
        """获取记忆统计"""
        short_term_count = len(self.list_short_term_memories())
        long_term_count = len(self.list_long_term_memories())
        
        return {
            "short_term": short_term_count,
            "long_term": long_term_count,
            "total": short_term_count + long_term_count,
        }
    
    def add_memory_node(self, memory_node: MemoryNode) -> str:
        """添加记忆节点"""
        memory = ShortTermMemory(
            content=memory_node.content,
            role=memory_node.role,
            importance=memory_node.importance,
            tags=[memory_node.source],
            metadata=memory_node.metadata,
        )
        return self.add_short_term_memory(
            memory.content,
            role=memory.role,
            importance=memory.importance,
            tags=memory.tags,
            metadata=memory.metadata,
        )
    
    def get_sensory_buffer(self) -> List[MemoryNode]:
        """获取感官缓冲区"""
        short_term_memories = self.list_short_term_memories()
        return [
            MemoryNode(
                id=mem.id,
                content=mem.content,
                role=mem.role,
                timestamp=mem.created_at.timestamp(),
                importance=mem.importance,
                source=mem.tags[0] if mem.tags else "short_term",
                metadata=mem.metadata,
            )
            for mem in short_term_memories
        ]
    
    def consolidate_sensory_to_semantic(self) -> None:
        """整合感官记忆到语义记忆"""
        short_term_memories = self.list_short_term_memories()
        
        if not short_term_memories:
            return
        
        optimized_memories = self.optimizer.optimize_memory_store(short_term_memories)
        
        prioritized_memories = self.prioritizer.prioritize(optimized_memories)
        
        categorized_memories = self._categorize_memories(prioritized_memories)
        
        all_long_term_memories = []
        
        for category, memories in categorized_memories.items():
            if memories:
                merged_memories = self.optimizer.merge_similar_memories(memories)
                
                summary_memory = self.compressor.compress(merged_memories)
                
                if summary_memory:
                    memory_id = self.add_long_term_memory(
                        content=summary_memory.content,
                        importance=summary_memory.importance,
                        tags=[category] + summary_memory.tags,
                        source=summary_memory.source,
                        summary=summary_memory.summary,
                    )
                    
                    saved_memory = self.get_memory(memory_id, memory_type="long_term")
                    if saved_memory:
                        all_long_term_memories.append(saved_memory)
        
        if all_long_term_memories:
            self.relationship_manager.analyze_memory_relationships(
                all_long_term_memories
            )
        
        try:
            all_memories = (
                self.list_short_term_memories() + self.list_long_term_memories()
            )
            relationships = self.relationship_manager.get_relationship_graph()
            
            report_path = self.visualizer.export_visualization_report(
                all_memories, relationships
            )
            logger.info(f"记忆可视化报告已生成: {report_path}")
        except Exception as e:
            logger.warning(f"生成可视化报告失败: {e}")
        
        for memory in short_term_memories:
            self.short_term_store.delete_memory(memory.id)
    
    def _categorize_memories(self, memories: List[Memory]) -> Dict[str, List[Memory]]:
        """分类记忆"""
        categories = {"conversation": [], "knowledge": [], "event": [], "other": []}
        
        for memory in memories:
            if "conversation" in memory.tags or "chat" in memory.tags:
                categories["conversation"].append(memory)
            elif "knowledge" in memory.tags or "fact" in memory.tags:
                categories["knowledge"].append(memory)
            elif "event" in memory.tags or "action" in memory.tags:
                categories["event"].append(memory)
            else:
                content_lower = memory.content.lower()
                if (
                    "i said" in content_lower
                    or "you said" in content_lower
                    or "they said" in content_lower
                ):
                    categories["conversation"].append(memory)
                elif (
                    "know" in content_lower
                    or "learn" in content_lower
                    or "fact" in content_lower
                ):
                    categories["knowledge"].append(memory)
                elif (
                    "did" in content_lower
                    or "happened" in content_lower
                    or "event" in content_lower
                ):
                    categories["event"].append(memory)
                else:
                    categories["other"].append(memory)
        
        return categories
    
    def refresh_memory_importance(
        self, memory_id: str, usage_score: float = 1.0
    ) -> None:
        """刷新记忆重要性"""
        memory = self.get_memory(
            memory_id, memory_type="short_term"
        ) or self.get_memory(memory_id, memory_type="long_term")
        
        if memory:
            new_importance = min(1.0, memory.importance + (usage_score * 0.1))
            memory.importance = new_importance
            memory.updated_at = datetime.datetime.now()
            
            memory.token_count = self._calculate_tokens(memory.content)
            
            if isinstance(memory, ShortTermMemory):
                self.short_term_store.update_memory(memory)
            elif isinstance(memory, LongTermMemory):
                self.long_term_store.update_memory(memory)
    
    def get_relevant_memories(
        self, query: str, k: int = 5
    ) -> List[Tuple[Memory, float]]:
        """获取相关记忆"""
        return self.retrieve_memories(query=query, k=k)
    
    def build_memory_context(
        self, query: str, max_tokens: int = 1500, k: int = 10
    ) -> str:
        """构建记忆上下文"""
        logger.debug(f"[build_memory_context] Start building memory context for query: '{query[:50]}...'")
        
        selected_memories = self.retrieve_memories(query=query, k=k)
        logger.debug(f"[build_memory_context] Retrieved {len(selected_memories)} memories from retrieve_memories")
        
        if not selected_memories:
            logger.debug("[build_memory_context] No memories found, trying to find user name memories")
            all_memories = self.list_short_term_memories() + self.list_long_term_memories()
            logger.debug(f"[build_memory_context] Total memories in storage: {len(all_memories)}")
            
            name_keywords = ["我是", "我的名字是", "叫我", "名字是", "称呼我"]
            for memory in all_memories:
                logger.debug(f"[build_memory_context] Checking memory: '{memory.content[:50]}...'")
                if any(keyword in memory.content for keyword in name_keywords):
                    selected_memories.append((memory, 1.0))
                    logger.debug(f"[build_memory_context] Found name memory: '{memory.content[:50]}...'")
                    break
        
        context_parts = []
        total_tokens = 0
        
        for memory, _ in selected_memories:
            if memory.token_count is None:
                memory.token_count = self._calculate_tokens(memory.content)
            memory_tokens = memory.token_count or 0
            if total_tokens + memory_tokens > max_tokens:
                break
            context_parts.append(memory.content)
            total_tokens += memory_tokens
        
        return "\n".join(context_parts)
    
    def clear_all_memories(self) -> None:
        """清除所有记忆"""
        short_term_memories = self.list_short_term_memories()
        for memory in short_term_memories:
            self.short_term_store.delete_memory(memory.id)
        
        long_term_memories = self.list_long_term_memories()
        for memory in long_term_memories:
            self.long_term_store.delete_memory(memory.id)
            if hasattr(self, "chroma_store"):
                try:
                    self.chroma_store.delete_memory(memory.id)
                except Exception:
                    pass
        
        if hasattr(self, "sqlite_store"):
            try:
                db_path = os.path.join(self.base_path, "memory", "memory.db")
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                
                from core.memory.sqlite_storage import SQLiteMemoryStore
                
                self.sqlite_store = SQLiteMemoryStore(db_path=db_path)
            except Exception:
                pass
        
        if hasattr(self, "chroma_store"):
            try:
                self.chroma_store.clear()
            except Exception:
                pass
        
        if hasattr(self, "relationship_manager"):
            self.relationship_manager.clear()
        
        logger.info("所有记忆已清除")
    
    async def aadd_memory(
        self, content: str, memory_type: str = "short_term", **kwargs
    ) -> str:
        """异步添加记忆"""
        return await asyncio.to_thread(self.add_memory, content, memory_type, **kwargs)
    
    async def aretrieve_memories(
        self, query: str, k: int = 5, **kwargs
    ) -> List[Tuple[Memory, float]]:
        """异步检索记忆"""
        return await asyncio.to_thread(self.retrieve_memories, query, k, **kwargs)
    
    async def aconsolidate_sensory_to_semantic(self) -> None:
        """异步整合记忆"""
        await asyncio.to_thread(self.consolidate_sensory_to_semantic)
    
    async def aget_relevant_memories(
        self, query: str, k: int = 5
    ) -> List[Tuple[Memory, float]]:
        """异步获取相关记忆"""
        return await asyncio.to_thread(self.get_relevant_memories, query, k)
    
    def consolidate_memory(self):
        """记忆整合"""
        return self.consolidate_sensory_to_semantic()
    
    def add_memory_with_type(
        self, content: str, memory_type: str = "user", importance: float = 0.5, **kwargs
    ) -> str:
        """添加带类型的记忆"""
        if memory_type not in MEMORY_TYPES:
            logger.warning(f"无效的记忆类型: {memory_type}，使用默认类型 user")
            memory_type = "user"
        
        return self.add_long_term_memory(
            content=content,
            importance=importance,
            tags=[memory_type],
            memory_type=memory_type,
            **kwargs
        )
    
    def get_memories_by_type(self, memory_type: str, k: int = 10) -> List[Memory]:
        """获取指定类型的记忆"""
        if memory_type == "short_term":
            return self.list_short_term_memories()[:k]
        elif memory_type == "long_term":
            return self.list_long_term_memories()[:k]
        else:
            all_memories = self.list_long_term_memories()
            return [m for m in all_memories if memory_type in m.tags][:k]
    
    def save_memory(self) -> None:
        """保存记忆"""
        try:
            self.short_term_store._save_memories()
            self.long_term_store._save_memories()
            logger.debug("记忆已保存")
        except Exception as e:
            logger.warning(f"保存记忆失败: {e}")
    
    def __del__(self):
        """析构时保存记忆"""
        try:
            if hasattr(self, 'short_term_store'):
                self.save_memory()
        except Exception:
            pass
