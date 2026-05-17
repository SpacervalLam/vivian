from __future__ import annotations

import logging
import os
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


class BaseEmbeddingModel(ABC):
    
    @abstractmethod
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        pass


class OnnxEmbeddingModel(BaseEmbeddingModel):
    
    def __init__(self, model_path: Optional[str] = None):
        self._session = None
        self._tokenizer = None
        self._model_path = model_path
        self._dimension = 384
        self._initialized = False
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def _ensure_initialized(self):
        if self._initialized:
            return
        
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
            
            model_paths = [
                self._model_path,
                os.path.join(os.path.dirname(__file__), "models", "all-MiniLM-L6-v2.onnx"),
                os.path.expanduser("~/.cache/vivian/models/all-MiniLM-L6-v2.onnx"),
            ]
            
            tokenizer_paths = [
                os.path.join(os.path.dirname(path), "tokenizer") if path else None
                for path in model_paths
            ]
            
            found_model = None
            found_tokenizer = None
            
            for model_path, tokenizer_path in zip(model_paths, tokenizer_paths):
                if model_path and os.path.exists(model_path):
                    found_model = model_path
                    if tokenizer_path and os.path.exists(tokenizer_path):
                        found_tokenizer = tokenizer_path
                    break
            
            if not found_model:
                logger.warning("ONNX model not found, using fallback embedding")
                self._initialized = True
                return
            
            self._session = ort.InferenceSession(
                found_model,
                providers=["CPUExecutionProvider"]
            )
            
            if found_tokenizer:
                self._tokenizer = AutoTokenizer.from_pretrained(found_tokenizer)
            else:
                self._tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
            
            self._initialized = True
            logger.info(f"Loaded ONNX embedding model: {found_model}")
            
        except ImportError as e:
            logger.warning(f"ONNX Runtime or transformers not installed: {e}, using fallback embedding")
            self._initialized = True
        except Exception as e:
            logger.warning(f"Failed to load ONNX model: {e}, using fallback embedding")
            self._initialized = True
    
    def _simple_embed(self, text: str) -> np.ndarray:
        freq = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1
        
        embedding = np.zeros(384)
        for i, (char, count) in enumerate(sorted(freq.items())[:384]):
            embedding[i] = count / len(text) if len(text) > 0 else 0
        
        return embedding
    
    def embed(self, texts: List[str]) -> List[np.ndarray]:
        self._ensure_initialized()
        
        if not self._session or not self._tokenizer:
            return [self._simple_embed(text) for text in texts]
        
        try:
            inputs = self._tokenizer(
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np"
            )
            
            input_ids = inputs["input_ids"].astype(np.int64)
            attention_mask = inputs["attention_mask"].astype(np.int64)
            
            outputs = self._session.run(
                None,
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask
                }
            )
            
            embeddings = outputs[0]
            
            if len(embeddings.shape) == 3:
                embeddings = embeddings[:, 0, :]
            elif embeddings.shape[1] != self._dimension:
                embeddings = np.mean(embeddings, axis=1)
            
            return [np.array(emb) for emb in embeddings]
        
        except Exception as e:
            logger.warning(f"ONNX encoding failed: {e}, using fallback embedding")
            return [self._simple_embed(text) for text in texts]