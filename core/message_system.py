import asyncio
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator, Union, Callable
from enum import Enum
from loguru import logger

class MessageType(Enum):
    ASSISTANT = "assistant"
    USER = "user"
    SYSTEM = "system"
    PROGRESS = "progress"
    ATTACHMENT = "attachment"
    STREAM_EVENT = "stream_event"
    TOOL_USE_SUMMARY = "tool_use_summary"

class StreamEventType(Enum):
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_STOP = "message_stop"

class Message:
    def __init__(self, message_type: MessageType, **kwargs):
        self.type = message_type.value
        self.uuid = kwargs.get('uuid', str(uuid.uuid4()))
        self.timestamp = kwargs.get('timestamp', datetime.now().isoformat())
        self.content = kwargs.get('content', '')
        self.message = kwargs.get('message', {})
        self.subtype = kwargs.get('subtype', None)
        self.compact_metadata = kwargs.get('compact_metadata', None)
        self.is_meta = kwargs.get('is_meta', False)
        self.is_visible_in_transcript_only = kwargs.get('is_visible_in_transcript_only', False)
        self.tool_use_result = kwargs.get('tool_use_result', None)
        self.is_compact_summary = kwargs.get('is_compact_summary', False)
        self.session_id = kwargs.get('session_id', None)
        self.parent_tool_use_id = kwargs.get('parent_tool_use_id', None)
        self.is_replay = kwargs.get('is_replay', False)
        self.is_synthetic = kwargs.get('is_synthetic', False)
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'type': self.type,
            'uuid': self.uuid,
            'timestamp': self.timestamp,
            'content': self.content,
            'message': self.message,
            'subtype': self.subtype,
            'compact_metadata': self.compact_metadata,
            'is_meta': self.is_meta,
            'is_visible_in_transcript_only': self.is_visible_in_transcript_only,
            'tool_use_result': self.tool_use_result,
            'is_compact_summary': self.is_compact_summary,
            'session_id': self.session_id,
            'parent_tool_use_id': self.parent_tool_use_id,
            'is_replay': self.is_replay,
            'is_synthetic': self.is_synthetic
        }

class StreamEvent:
    def __init__(self, event_type: StreamEventType, **kwargs):
        self.type = event_type.value
        self.message = kwargs.get('message', {})
        self.delta = kwargs.get('delta', {})
        self.usage = kwargs.get('usage', {})
        self.stop_reason = kwargs.get('stop_reason', None)

class Attachment:
    def __init__(self, attachment_type: str, **kwargs):
        self.type = attachment_type
        self.data = kwargs.get('data', {})
        self.turn_count = kwargs.get('turn_count', 0)
        self.max_turns = kwargs.get('max_turns', 0)
        self.prompt = kwargs.get('prompt', '')
        self.source_uuid = kwargs.get('source_uuid', None)

class ProgressMessage(Message):
    def __init__(self, tool_use_id: str, data: Dict[str, Any]):
        super().__init__(
            MessageType.PROGRESS,
            content=str(data),
            message={'tool_use_id': tool_use_id, 'data': data}
        )
        self.tool_use_id = tool_use_id
        self.progress_data = data

class MessageStore:
    def __init__(self, max_size: int = 100):
        self._messages: List[Message] = []
        self._max_size = max_size
        self._lock = asyncio.Lock()
    
    async def add_message(self, message: Message) -> None:
        """添加消息"""
        async with self._lock:
            self._messages.append(message)
            # 保持消息数量在限制范围内
            while len(self._messages) > self._max_size:
                self._messages.pop(0)
    
    async def add_messages(self, messages: List[Message]) -> None:
        """批量添加消息"""
        async with self._lock:
            self._messages.extend(messages)
            while len(self._messages) > self._max_size:
                self._messages.pop(0)
    
    async def get_messages(self) -> List[Message]:
        """获取所有消息"""
        async with self._lock:
            return list(self._messages)
    
    async def get_messages_by_type(self, message_type: MessageType) -> List[Message]:
        """按类型获取消息"""
        async with self._lock:
            return [m for m in self._messages if m.type == message_type.value]
    
    async def get_last_message(self) -> Optional[Message]:
        """获取最后一条消息"""
        async with self._lock:
            return self._messages[-1] if self._messages else None
    
    async def get_messages_since(self, timestamp: str) -> List[Message]:
        """获取指定时间戳之后的消息"""
        async with self._lock:
            return [m for m in self._messages if m.timestamp >= timestamp]
    
    async def clear(self) -> None:
        """清空所有消息"""
        async with self._lock:
            self._messages.clear()
    
    def __len__(self) -> int:
        return len(self._messages)

class MessageNormalizer:
    """消息标准化器"""
    
    @staticmethod
    def normalize(message: Message) -> Dict[str, Any]:
        """标准化消息格式"""
        base = message.to_dict()
        
        if message.type == MessageType.ASSISTANT.value:
            return MessageNormalizer._normalize_assistant(message, base)
        elif message.type == MessageType.USER.value:
            return MessageNormalizer._normalize_user(message, base)
        elif message.type == MessageType.SYSTEM.value:
            return MessageNormalizer._normalize_system(message, base)
        elif message.type == MessageType.PROGRESS.value:
            return MessageNormalizer._normalize_progress(message, base)
        elif message.type == MessageType.ATTACHMENT.value:
            return MessageNormalizer._normalize_attachment(message, base)
        else:
            return base
    
    @staticmethod
    def _normalize_assistant(message: Message, base: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **base,
            'type': 'assistant',
            'message': {
                'role': 'assistant',
                'content': message.content,
                'stop_reason': message.message.get('stop_reason'),
                'usage': message.message.get('usage', {})
            }
        }
    
    @staticmethod
    def _normalize_user(message: Message, base: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **base,
            'type': 'user',
            'message': {
                'role': 'user',
                'content': message.content
            }
        }
    
    @staticmethod
    def _normalize_system(message: Message, base: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **base,
            'type': 'system',
            'subtype': message.subtype,
            'compact_metadata': message.compact_metadata
        }
    
    @staticmethod
    def _normalize_progress(message: Message, base: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **base,
            'type': 'progress',
            'tool_use_id': message.message.get('tool_use_id'),
            'data': message.message.get('data', {})
        }
    
    @staticmethod
    def _normalize_attachment(message: Message, base: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **base,
            'type': 'attachment',
            'attachment': message.message.get('attachment', {})
        }

class MessageStreamer:
    """消息流式处理器 - 优化版：零拷贝流式传输"""
    
    def __init__(self, message_store: MessageStore):
        self._message_store = message_store
        self._listeners = []
        self._streaming_tasks = {}
        self._stream_buffer = {}  # 流式缓冲区，用于累积数据
        self._buffer_threshold = 10  # 缓冲区阈值，超过此值触发刷新
    
    def add_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """添加消息监听器"""
        self._listeners.append(callback)
    
    def remove_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """移除消息监听器"""
        self._listeners.remove(callback)
    
    async def _notify_listeners(self, message: Dict[str, Any]) -> None:
        """通知所有监听器 - 使用并行通知优化"""
        tasks = []
        for callback in self._listeners:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(asyncio.create_task(callback(message)))
                else:
                    callback(message)
            except Exception as e:
                logger.warning(f"[MessageStreamer] Listener error: {e}")
        
        # 并行等待所有异步回调完成
        if tasks:
            await asyncio.gather(*tasks)
    
    async def stream_message(self, message: Message) -> AsyncGenerator[Dict[str, Any], None]:
        """流式输出消息 - 零拷贝优化"""
        normalized = MessageNormalizer.normalize(message)
        # 使用 asyncio.create_task 异步添加到存储，不阻塞流式传输
        asyncio.create_task(self._message_store.add_message(message))
        await self._notify_listeners(normalized)
        yield normalized
    
    async def stream_messages(self, messages: List[Message]) -> AsyncGenerator[Dict[str, Any], None]:
        """流式输出多条消息 - 批量优化"""
        # 批量添加消息到存储
        if messages:
            asyncio.create_task(self._message_store.add_messages(messages))
        
        # 逐个通知监听器
        for message in messages:
            normalized = MessageNormalizer.normalize(message)
            await self._notify_listeners(normalized)
            yield normalized
    
    async def start_streaming(self, source: AsyncGenerator[Message, None]) -> str:
        """开始从源流式接收消息 - 高性能版本"""
        stream_id = str(uuid.uuid4())
        
        async def stream_worker():
            buffer = []
            async for message in source:
                normalized = MessageNormalizer.normalize(message)
                buffer.append(normalized)
                
                # 批量处理：每N条或达到阈值时批量通知
                if len(buffer) >= self._buffer_threshold:
                    # 批量通知（异步并行）
                    notify_tasks = []
                    for msg in buffer:
                        notify_tasks.append(self._notify_listeners(msg))
                    if notify_tasks:
                        await asyncio.gather(*notify_tasks)
                    buffer.clear()
            
            # 处理剩余消息
            if buffer:
                notify_tasks = [self._notify_listeners(msg) for msg in buffer]
                await asyncio.gather(*notify_tasks)
        
        self._streaming_tasks[stream_id] = asyncio.create_task(stream_worker())
        return stream_id
    
    async def stop_streaming(self, stream_id: str) -> None:
        """停止指定的流"""
        task = self._streaming_tasks.get(stream_id)
        if task:
            task.cancel()
            del self._streaming_tasks[stream_id]
    
    def stream_chunk_direct(self, stream_id: str, chunk: str) -> None:
        """
        直接流式传输文本块，跳过Message对象创建（零拷贝优化）
        
        Args:
            stream_id: 流标识符
            chunk: 文本块
        """
        if stream_id not in self._stream_buffer:
            self._stream_buffer[stream_id] = {"content": "", "count": 0}
        
        self._stream_buffer[stream_id]["content"] += chunk
        self._stream_buffer[stream_id]["count"] += 1
        
        # 实时通知监听器（每次收到块都通知）
        message = {
            "type": "stream_event",
            "chunk": chunk,
            "is_complete": False
        }
        
        # 同步通知（最快路径）
        for callback in self._listeners:
            try:
                callback(message)
            except Exception as e:
                logger.warning(f"[MessageStreamer] Listener error: {e}")
    
    def finalize_stream(self, stream_id: str) -> str:
        """
        完成流式传输，返回完整内容
        
        Args:
            stream_id: 流标识符
        
        Returns:
            完整的累积内容
        """
        buffer = self._stream_buffer.get(stream_id)
        if buffer:
            content = buffer["content"]
            # 发送完成消息
            message = {
                "type": "stream_event",
                "chunk": "",
                "is_complete": True,
                "content": content
            }
            for callback in self._listeners:
                try:
                    callback(message)
                except Exception as e:
                    logger.warning(f"[MessageStreamer] Listener error: {e}")
            del self._stream_buffer[stream_id]
            return content
        return ""

class MessageFactory:
    """消息工厂"""
    
    @staticmethod
    def create_user_message(content: str, **kwargs) -> Message:
        """创建用户消息"""
        return Message(
            MessageType.USER,
            content=content,
            message={'role': 'user', 'content': content},
            **kwargs
        )
    
    @staticmethod
    def create_assistant_message(content: str, **kwargs) -> Message:
        """创建助手消息"""
        return Message(
            MessageType.ASSISTANT,
            content=content,
            message={'role': 'assistant', 'content': content},
            **kwargs
        )
    
    @staticmethod
    def create_system_message(subtype: str, content: str = '', **kwargs) -> Message:
        """创建系统消息"""
        return Message(
            MessageType.SYSTEM,
            subtype=subtype,
            content=content,
            **kwargs
        )
    
    @staticmethod
    def create_progress_message(tool_use_id: str, data: Dict[str, Any]) -> ProgressMessage:
        """创建进度消息"""
        return ProgressMessage(tool_use_id, data)
    
    @staticmethod
    def create_attachment_message(attachment_type: str, data: Any, **kwargs) -> Message:
        """创建附件消息"""
        return Message(
            MessageType.ATTACHMENT,
            content=str(data),
            message={'attachment': {'type': attachment_type, 'data': data}},
            **kwargs
        )
    
    @staticmethod
    def create_stream_event(event_type: StreamEventType, **kwargs) -> Message:
        """创建流式事件消息"""
        return Message(
            MessageType.STREAM_EVENT,
            content=str(kwargs),
            message={'event': {'type': event_type.value, **kwargs}}
        )
    
    @staticmethod
    def create_tool_use_summary(summary: str, preceding_tool_use_ids: List[str]) -> Message:
        """创建工具使用摘要消息"""
        return Message(
            MessageType.TOOL_USE_SUMMARY,
            content=summary,
            message={'summary': summary, 'preceding_tool_use_ids': preceding_tool_use_ids}
        )

# 创建全局消息存储和流处理器
message_store = MessageStore()
message_streamer = MessageStreamer(message_store)
message_factory = MessageFactory()
