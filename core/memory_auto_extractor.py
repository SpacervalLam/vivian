"""
智能记忆提取器

基于语义理解的记忆提取系统，完全使用 LLM 进行判断
"""

import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from core.memory.base import MemoryNode, LongTermMemory
from core.memory_types import MEMORY_TYPES


class SmartMemoryExtractor:
    """
    智能记忆提取器
    
    核心设计理念：
    - 使用 LLM 进行语义判断和操作
    - 支持记忆 CRUD 操作
    - 使用向量相似度去重和融合
    - 异步后台处理，不影响主对话
    """
    
    def __init__(self, memory_manager, ai_manager=None):
        self.memory_manager = memory_manager
        self.ai_manager = ai_manager
        self._in_progress = False
        self._pending_messages: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._enabled = True
        self._min_extract_interval = 3
        self._last_extract_time = 0
        
        # 批次配置
        self._batch_window_size = 10
        self._message_buffer: List[Dict[str, Any]] = []
        
        # 相似度阈值
        self._similarity_threshold = 0.85
    
    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        logger.info(f"智能记忆提取已{'启用' if enabled else '禁用'}")
    
    def extract_message(self, message: Dict[str, Any]) -> Optional[str]:
        if not self._enabled:
            return None
        
        with self._lock:
            self._message_buffer.append(message)
            if len(self._message_buffer) >= self._batch_window_size:
                messages_to_process = self._message_buffer.copy()
                self._message_buffer = []
                threading.Thread(
                    target=lambda: asyncio.run(self._process_batch_async(messages_to_process)),
                    daemon=True
                ).start()
        return None
    
    async def _process_batch_async(self, messages: List[Dict[str, Any]]):
        try:
            now = time.time()
            if now - self._last_extract_time < self._min_extract_interval:
                return
            
            self._last_extract_time = now
            await self.extract_and_update(messages)
        except Exception as e:
            logger.error(f"批处理记忆提取失败: {e}")
    
    async def extract_and_update(self, recent_messages: List[Dict[str, Any]]) -> List[str]:
        """
        核心提取逻辑：使用 LLM 分析对话并执行相应操作
        """
        if not self._enabled or not self.ai_manager:
            return []
        
        with self._lock:
            if self._in_progress:
                self._pending_messages.extend(recent_messages)
                return []
            self._in_progress = True
        
        try:
            dialog_text = "\n".join([
                f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
                for msg in recent_messages
            ])
            
            result = await self._analyze_with_llm_async(dialog_text)
            
            if not result or not result.get("has_valuable_memory"):
                return []
            
            saved_ids = []
            for op in result.get("operations", []):
                try:
                    memory_id = await self._execute_operation_async(op)
                    if memory_id:
                        saved_ids.append(memory_id)
                except Exception as e:
                    logger.error(f"执行记忆操作失败: {e}")
            
            with self._lock:
                if self._pending_messages:
                    pending = self._pending_messages.copy()
                    self._pending_messages = []
                    asyncio.create_task(self.extract_and_update(pending))
            
            return saved_ids
        finally:
            with self._lock:
                self._in_progress = False
    
    async def _analyze_with_llm_async(self, dialog_text: str) -> Optional[Dict[str, Any]]:
        system_prompt = """You are a memory management brain with sharp contextual insight.
Analyze the following conversation to determine if it contains facts, preferences, habits, or relationships about the user that are worth saving long-term. Evaluate how valuable this memory will be for future conversations, on a scale of 0-1.

Rules:
1. Ignore short-term task context in the current conversation (e.g., "help me write code", "open browser").
2. Capture deep-seated preferences (e.g., "user doesn't like being disturbed too much", "user frequently uses Python").
3. Important personal health information and allergies must be prioritized for saving.
4. Determine operation type:
   - ADD: Completely new fact
   - UPDATE: Corrects a previously known fact (e.g., user changed their mind)
   - DELETE: User explicitly asks to forget something

Memory Types:
- user_profile: User personal information (name, occupation, age, allergies, etc.)
- preference: User preferences, habits, interests, dislikes
- project_context: Project plans, goals, deadlines
- relationship: Relationship information
- health: Health-related information

Importance Scoring Criteria:
- 0.9-1: User's hard constraints, long-term preferences, core identity attributes, health information, compliance requirements ("I'm allergic to peanuts", "must use Python 3.11")
- 0.6-0.8: Project background, key decisions, clear goals ("Our project is mainly for elderly users"), long-term preferences (occupation, hobbies, values)
- 0.3-0.5: General facts, contextual explanations
- 0-0.2: Small talk, polite remarks, temporary questions ("Nice weather today")

Must output strictly in the following JSON format, without any additional text:
{
    "has_valuable_memory": true/false,
    "operations": [
        {
            "action": "ADD" | "UPDATE" | "DELETE",
            "type": "user_profile" | "preference" | "project_context" | "relationship" | "health",
            "content": "Extracted core memory point (first-person declarative sentence, e.g., 'I like drinking American coffee')",
            "importance": 0.1-1.0,
            "reason": "Brief explanation why this memory is extracted"
        }
    ]
}

If there is no content worth saving, set has_valuable_memory to false and operations to empty array."""

        full_prompt = f"""{system_prompt}

Analyze the following conversation:
{dialog_text}

Output the result in JSON format."""

        try:
            logger.info(f"[MemoryExtractor] 发送请求给 LLM，对话长度: {len(dialog_text)}")
            response = self.ai_manager.query_short(full_prompt, use_history=False)
            
            if not response:
                logger.warning(f"[MemoryExtractor] LLM 返回空响应")
                return None
            
            logger.info(f"[MemoryExtractor] 收到 LLM 响应，长度: {len(response)}")
            logger.debug(f"[MemoryExtractor] 响应内容: {response[:200]}...")
            
            result = self._parse_llm_response(response)
            logger.info(f"[MemoryExtractor] 解析结果: has_valuable_memory={result.get('has_valuable_memory') if result else 'None'}, operations_count={len(result.get('operations', [])) if result else 0}")
            return result
        except Exception as e:
            logger.error(f"[MemoryExtractor] LLM 分析异常: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug(f"[MemoryExtractor] 堆栈: {traceback.format_exc()}")
            return None
    
    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            try:
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    return json.loads(response[start:end+1])
            except Exception:
                pass
            
            try:
                from core.json_processor import JsonProcessor
                return JsonProcessor().process(response)
            except Exception as e:
                logger.warning(f"[MemoryExtractor] JSON 解析失败: {e}")
                return None
    
    async def _execute_operation_async(self, op: Dict[str, Any]) -> Optional[str]:
        action = op.get("action", "ADD")
        content = op.get("content", "")
        mem_type = op.get("type", "user_profile")
        importance = op.get("importance", 0.5)
        
        if not content:
            return None
        
        if mem_type not in MEMORY_TYPES:
            mem_type = "reference"
        
        if action == "ADD":
            return await self._add_memory_async(content, mem_type, importance)
        elif action == "UPDATE":
            return await self._update_memory_async(content, mem_type, importance)
        elif action == "DELETE":
            await self._delete_memory_async(content)
            return None
        else:
            logger.warning(f"未知的记忆操作: {action}")
            return None
    
    async def _add_memory_async(self, content: str, mem_type: str, importance: float) -> Optional[str]:
        similar_memories = await self._search_similar_async(content, top_k=1)
        
        if similar_memories:
            old_memory, similarity = similar_memories[0]
            
            if similarity > 0.95:
                return await self._update_memory_by_id_async(old_memory.id, content, importance)
            
            merged = await self._merge_memories_async(old_memory, content, importance)
            if merged:
                return merged
            else:
                return await self._update_memory_async(content, mem_type, importance)
        else:
            try:
                memory_id = self.memory_manager.add_memory(
                    content=content,
                    memory_type="long_term",
                    importance=importance,
                    tags=[mem_type],
                    memory_type_param=mem_type
                )
                logger.info(f"[MemoryExtractor][ADD] 保存记忆 [{mem_type}]: {content[:30]}... (重要性: {importance:.2f})")
                return memory_id
            except Exception as e:
                logger.error(f"[MemoryExtractor] 添加记忆失败: {e}")
                return None
    
    async def _search_similar_async(self, content: str, top_k: int = 5) -> List[tuple]:
        try:
            results = self.memory_manager.retrieve_memories(content, k=top_k)
            return [(m, s) for m, s in results if s >= self._similarity_threshold]
        except Exception as e:
            logger.error(f"[MemoryExtractor] 相似记忆检索失败: {e}")
            return []
    
    async def _merge_memories_async(self, old_memory: Any, new_content: str, new_importance: float) -> Optional[str]:
        merge_prompt = f"""请判断如何处理这两条相关记忆：
旧记忆: {old_memory.content}
新内容: {new_content}
请选择最合适的操作：
1. MERGE: 两条记忆互相补充，合并成一条更完整的记忆
2. REPLACE: 新记忆替换旧记忆（新信息更准确或更新）
3. IGNORE: 新记忆与旧记忆重复，不需要保存
4. KEEP_BOTH: 两条记忆虽然相关但侧重点不同，都需要保留

请严格以下面的 JSON 格式输出：
{{
    "decision": "MERGE" | "REPLACE" | "IGNORE" | "KEEP_BOTH",
    "merged_content": "如果选择MERGE，输出合并后的内容",
    "reason": "简要说明理由"
}}"""
        try:
            response = self.ai_manager.query_short(merge_prompt, use_history=False)
            result = self._parse_llm_response(response)
            
            if not result:
                return None
            
            decision = result.get("decision", "KEEP_BOTH")
            
            if decision == "IGNORE":
                return old_memory.id
            elif decision == "REPLACE":
                return await self._update_memory_by_id_async(old_memory.id, new_content, new_importance)
            elif decision == "MERGE":
                merged_content = result.get("merged_content", new_content)
                return await self._update_memory_by_id_async(old_memory.id, merged_content, max(old_memory.importance, new_importance))
            elif decision == "KEEP_BOTH":
                memory_id = self.memory_manager.add_memory(
                    content=new_content,
                    memory_type="long_term",
                    importance=new_importance,
                    tags=["related_to_" + old_memory.id]
                )
                return memory_id
        except Exception as e:
            logger.error(f"[MemoryExtractor] 记忆融合失败: {e}")
            return None
    
    async def _update_memory_async(self, content: str, mem_type: str, importance: float) -> Optional[str]:
        similar = await self._search_similar_async(content, top_k=1)
        if similar:
            old_memory, _ = similar[0]
            return await self._update_memory_by_id_async(old_memory.id, content, importance)
        else:
            return await self._add_memory_async(content, mem_type, importance)
    
    async def _update_memory_by_id_async(self, memory_id: str, content: str, importance: float) -> Optional[str]:
        try:
            old_memory = self.memory_manager.get_memory(memory_id, "long_term")
            if not old_memory:
                return None
            
            old_memory.content = content
            old_memory.importance = max(old_memory.importance, importance)
            old_memory.updated_at = time.time()
            
            if hasattr(self.memory_manager, 'embedding'):
                old_memory.embedding = self.memory_manager.embedding.embed(content)
            
            self.memory_manager.update_memory(old_memory)
            logger.info(f"[MemoryExtractor][UPDATE] 更新记忆: {content[:30]}...")
            return memory_id
        except Exception as e:
            logger.error(f"[MemoryExtractor] 更新记忆失败: {e}")
            return None
    
    async def _delete_memory_async(self, content: str):
        similar = await self._search_similar_async(content, top_k=1)
        if similar:
            memory, _ = similar[0]
            try:
                logger.info(f"[MemoryExtractor][DELETE] 删除记忆: {memory.content[:30]}...")
                if hasattr(self.memory_manager, 'long_term_store'):
                    try:
                        self.memory_manager.long_term_store.delete_memory(memory.id)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"[MemoryExtractor] 删除记忆失败: {e}")
    
    def extract(self, messages: List[Dict[str, Any]], use_llm: bool = True) -> List[str]:
        if not self._enabled:
            return []
        
        result_ids = []
        result_lock = threading.Lock()
        
        def _run_sync():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ids = loop.run_until_complete(self.extract_and_update(messages))
                with result_lock:
                    result_ids.extend(ids)
            except Exception as e:
                logger.error(f"[MemoryExtractor] 同步提取失败: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=_run_sync, daemon=True)
        thread.start()
        thread.join(timeout=5)
        
        return result_ids


# 保留旧类名作为别名
AutoMemoryExtractor = SmartMemoryExtractor
