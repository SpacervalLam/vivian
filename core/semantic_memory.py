"""语义记忆检索系统

基于向量相似度的记忆检索。
"""

from __future__ import annotations

import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SemanticMemoryItem:
    """语义记忆项"""
    id: str
    content: str
    embedding: np.ndarray
    created_at: datetime
    importance: float = 0.5
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseEmbeddingModel(ABC):
    """嵌入模型抽象接口"""
    
    @abstractmethod
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        """将文本转换为向量嵌入"""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """嵌入向量的维度"""
        pass


class SentenceTransformerEmbedding(BaseEmbeddingModel):
    """SentenceTransformer嵌入模型"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = None
        self._model_name = model_name
        self._dimension = 384  # all-MiniLM-L6-v2 的维度
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                logger.info(f"Loaded SentenceTransformer model: {self._model_name}")
            except ImportError:
                logger.warning("sentence_transformers not installed, falling back to simple embedding")
                self._model = "fallback"
    
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        self._ensure_model()
        
        if self._model == "fallback":
            # 简单的字符频率嵌入作为备用方案
            return [self._simple_embed(text) for text in texts]
        
        try:
            embeddings = self._model.encode(texts)
            return [np.array(emb) for emb in embeddings]
        except Exception as e:
            logger.warning(f"SentenceTransformer encoding failed: {e}")
            return [self._simple_embed(text) for text in texts]
    
    def _simple_embed(self, text: str) -> np.ndarray:
        """简单字符频率嵌入"""
        freq = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1
        
        embedding = np.zeros(384)
        for i, (char, count) in enumerate(sorted(freq.items())[:384]):
            embedding[i] = count / len(text)
        
        return embedding


class SemanticMemoryStore:
    """语义记忆存储 - 基于向量相似度检索"""
    
    def __init__(self, embedding_model: Optional[BaseEmbeddingModel] = None):
        self.embedding_model = embedding_model or SentenceTransformerEmbedding()
        self.memories: Dict[str, SemanticMemoryItem] = {}
        self.embeddings: List[Tuple[str, np.ndarray]] = []  # (id, embedding)
    
    def add_memory(self, content: str, id: Optional[str] = None, 
                   importance: float = 0.5, metadata: Optional[Dict[str, Any]] = None,
                   created_at: Optional[datetime] = None):
        """添加记忆"""
        memory_id = id or f"mem_{len(self.memories)}_{int(datetime.now().timestamp())}"
        
        # 获取嵌入
        embedding = self.embedding_model.embed([content])[0]
        
        # 使用指定时间戳或当前时间
        memory_created_at = created_at or datetime.now()
        
        memory = SemanticMemoryItem(
            id=memory_id,
            content=content,
            embedding=embedding,
            created_at=memory_created_at,
            importance=importance,
            metadata=metadata
        )
        
        self.memories[memory_id] = memory
        self.embeddings.append((memory_id, embedding))
        
        logger.debug(f"Added semantic memory: {memory_id[:20]}...")
        return memory_id
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0.0
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    
    def search(self, query: str, k: int = 5, 
               importance_weight: float = 0.3) -> List[Tuple[SemanticMemoryItem, float]]:
        """语义搜索"""
        if not self.embeddings:
            return []
        
        query_embedding = self.embedding_model.embed([query])[0]
        
        results = []
        for memory_id, embedding in self.embeddings:
            similarity = self._cosine_similarity(query_embedding, embedding)
            memory = self.memories[memory_id]
            
            combined_score = (1 - importance_weight) * similarity + importance_weight * memory.importance
            results.append((memory, combined_score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        logger.debug(f"Semantic search found {len(results)} results for query: '{query[:30]}...'")
        for mem, score in results[:k]:
            logger.debug(f"  - {score:.4f}: {mem.content[:50]}...")
        
        return results[:k]
    
    def get_memory(self, memory_id: str) -> Optional[SemanticMemoryItem]:
        """获取单个记忆"""
        return self.memories.get(memory_id)
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if memory_id in self.memories:
            del self.memories[memory_id]
            self.embeddings = [(id_, emb) for id_, emb in self.embeddings if id_ != memory_id]
            return True
        return False
    
    def clear(self):
        """清空所有记忆"""
        self.memories.clear()
        self.embeddings.clear()
    
    @property
    def count(self) -> int:
        """记忆数量"""
        return len(self.memories)


class HybridMemoryRetriever:
    """混合记忆检索器 - 结合语义检索和关键词检索"""
    
    def __init__(self, semantic_store: SemanticMemoryStore):
        self.semantic_store = semantic_store
        self._bm25_available = False
        self._BM25Okapi = None
        self._jieba = None
    
    def _load_bm25(self):
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
    
    def _bm25_search(self, query: str, k: int = 5) -> List[Tuple[SemanticMemoryItem, float]]:
        """BM25关键词搜索"""
        if not self._load_bm25():
            return []
        
        memories = list(self.semantic_store.memories.values())
        if not memories:
            return []
        
        documents = [mem.content for mem in memories]
        tokenized_docs = [list(self._jieba.cut_for_search(doc)) for doc in documents]
        tokenized_query = list(self._jieba.cut_for_search(query))
        
        bm25 = self._BM25Okapi(tokenized_docs)
        scores = bm25.get_scores(tokenized_query)
        
        results = [(memories[i], scores[i]) for i in range(len(memories)) if scores[i] > 0]
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:k]
    
    def retrieve(self, query: str, k: int = 5, 
                 semantic_weight: float = 0.6, bm25_weight: float = 0.4) -> List[Tuple[SemanticMemoryItem, float]]:
        """混合检索"""
        semantic_results = self.semantic_store.search(query, k=k * 2)
        bm25_results = self._bm25_search(query, k=k * 2)
        
        scores: Dict[str, float] = {}
        seen_ids = set()
        
        for mem, score in semantic_results:
            scores[mem.id] = score * semantic_weight
            seen_ids.add(mem.id)
        
        for mem, score in bm25_results:
            if mem.id in scores:
                scores[mem.id] += score * bm25_weight
            else:
                scores[mem.id] = score * bm25_weight
        
        results = []
        for mem_id, score in scores.items():
            mem = self.semantic_store.get_memory(mem_id)
            if mem:
                results.append((mem, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        logger.debug(f"Hybrid retrieval found {len(results)} results for query: '{query[:30]}...'")
        return results[:k]


# 全局单例
_semantic_store = None

def get_semantic_store() -> SemanticMemoryStore:
    """获取全局语义记忆存储实例"""
    global _semantic_store
    if _semantic_store is None:
        _semantic_store = SemanticMemoryStore()
    return _semantic_store


def get_hybrid_retriever() -> HybridMemoryRetriever:
    """获取全局混合检索器实例"""
    return HybridMemoryRetriever(get_semantic_store())
