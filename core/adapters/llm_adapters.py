import asyncio
import json
import threading
import time
import httpx
from abc import ABC, abstractmethod
from loguru import logger
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional, Union

class UnifiedChatRequest:
    def __init__(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = 1024,
        stream: bool = False,
        **kwargs
    ):
        self.model = model
        self.messages = messages
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.kwargs = kwargs

class UnifiedChatResponse:
    def __init__(self, content: str, finish_reason: Optional[str] = None):
        self.content = content
        self.finish_reason = finish_reason

class TypingBuffer:
    def __init__(
        self,
        slow_threshold: float = 0.3,  
        min_chunk_size: int = 1,
        max_chunk_size: int = 8,
        typing_speed: float = 0.05,  
        idle_action_callback: Optional[Callable[[], None]] = None,
    ):
        self.slow_threshold = slow_threshold  
        self.min_chunk_size = min_chunk_size  
        self.max_chunk_size = max_chunk_size  
        self.typing_speed = typing_speed  
        self.idle_action_callback = idle_action_callback  

        self.buffer = []
        self.last_receive_time = time.time()
        self.is_streaming = False
        self.lock = asyncio.Lock()
        self._task = None

    async def add_tokens(self, tokens: str) -> None:
        async with self.lock:
            self.buffer.extend(list(tokens))
            self.last_receive_time = time.time()

    async def signal_end(self) -> None:
        self.is_streaming = False

    def _calculate_chunk_size(self) -> int:
        now = time.time()
        time_since_last = now - self.last_receive_time

        if time_since_last < 0.1:
            return min(self.max_chunk_size, len(self.buffer))
        elif time_since_last < 0.2:
            return min(max(4, len(self.buffer)), self.max_chunk_size)
        elif time_since_last < self.slow_threshold:
            return min(2, len(self.buffer))
        else:
            return self.min_chunk_size

    def _should_trigger_action(self) -> bool:
        now = time.time()
        return now - self.last_receive_time > self.slow_threshold

    async def _idle_action_loop(self):
        while self.is_streaming:
            await asyncio.sleep(self.slow_threshold)
            if self._should_trigger_action() and self.idle_action_callback:
                try:
                    self.idle_action_callback()
                except Exception as e:
                    logger.error(f"Idle action callback failed: {e}")

    async def start(self) -> AsyncGenerator[str, None]:
        self.is_streaming = True
        self.last_receive_time = time.time()
        self._task = asyncio.create_task(self._idle_action_loop())

        try:
            while self.is_streaming or self.buffer:
                async with self.lock:
                    chunk_size = self._calculate_chunk_size()
                    
                    if chunk_size > 0 and len(self.buffer) >= chunk_size:
                        chunk = ''.join(self.buffer[:chunk_size])
                        self.buffer = self.buffer[chunk_size:]
                        self.last_receive_time = time.time()
                    elif len(self.buffer) > 0:
                        chunk = ''.join(self.buffer[:1])
                        self.buffer = self.buffer[1:]
                    else:
                        chunk = None

                if chunk:
                    yield chunk
                    await asyncio.sleep(self.typing_speed)
                else:
                    await asyncio.sleep(0.01)
        finally:
            self.is_streaming = False
            if self._task:
                self._task.cancel()

class BaseLLMAdapter(ABC):
    def __init__(self, **kwargs):
        pass

    @abstractmethod
    async def chat(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> UnifiedChatResponse:
        pass

    @abstractmethod
    async def chat_stream(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> AsyncGenerator[str, None]:
        pass

class OpenAICompatibleAdapter(BaseLLMAdapter):
    async def chat(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> UnifiedChatResponse:
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", request.model)

        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": min(request.temperature or 0.7, 2),
            "max_tokens": request.max_tokens or 1024,
            "stream": False,
            **request.kwargs,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if "choices" not in data or not data["choices"]:
            raise ValueError(f"Unexpected API response: {data}")
        return UnifiedChatResponse(
            content=data["choices"][0]["message"]["content"],
            finish_reason=data["choices"][0]["finish_reason"],
        )

    async def chat_stream(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> AsyncGenerator[str, None]:
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", request.model)

        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": min(request.temperature or 0.7, 2),
            "max_tokens": request.max_tokens or 1024,
            "stream": True,
            **request.kwargs,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            parsed = json.loads(data)
                            content = parsed["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

class AnthropicAdapter(BaseLLMAdapter):
    async def chat(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> UnifiedChatResponse:
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", request.model)

        system_message = next(
            (m for m in request.messages if m.get("role") == "system"), None
        )
        other_messages = [m for m in request.messages if m.get("role") != "system"]

        payload = {
            "model": model,
            "system": system_message.get("content", "") if system_message else "",
            "messages": other_messages,
            "temperature": min(request.temperature or 0.7, 1),
            "max_tokens": request.max_tokens or 1024,
            "stream": False,
            **request.kwargs,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return UnifiedChatResponse(
            content=data["content"][0]["text"],
            finish_reason=data.get("stop_reason"),
        )

    async def chat_stream(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> AsyncGenerator[str, None]:
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", request.model)

        system_message = next(
            (m for m in request.messages if m.get("role") == "system"), None
        )
        other_messages = [m for m in request.messages if m.get("role") != "system"]

        payload = {
            "model": model,
            "system": system_message.get("content", "") if system_message else "",
            "messages": other_messages,
            "temperature": min(request.temperature or 0.7, 1),
            "max_tokens": request.max_tokens or 1024,
            "stream": True,
            **request.kwargs,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:]
                        if event_type == "message_stop":
                            return
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") == "content_block_delta":
                                content = data.get("delta", {}).get("text", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

class GeminiAdapter(BaseLLMAdapter):
    async def chat(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> UnifiedChatResponse:
        import httpx

        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", request.model)

        contents = []
        for msg in request.messages:
            role = msg["role"]
            if role == "system":
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": msg["content"]}],
                    }
                )
            else:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [{"text": msg["content"]}],
                    }
                )

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/models/{model}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": contents,
                    "generationConfig": {
                        "temperature": min(request.temperature or 0.7, 1),
                        "maxOutputTokens": request.max_tokens or 1024,
                    },
                    **request.kwargs,
                },
            )
            response.raise_for_status()
            data = response.json()

        candidate = data["candidates"][0]
        return UnifiedChatResponse(
            content=candidate["content"]["parts"][0]["text"],
            finish_reason=candidate.get("finishReason"),
        )

    async def chat_stream(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> AsyncGenerator[str, None]:
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", request.model)

        contents = []
        for msg in request.messages:
            role = msg["role"]
            if role == "system":
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": msg["content"]}],
                    }
                )
            else:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [{"text": msg["content"]}],
                    }
                )

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{base_url}/models/{model}:generateContent?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": contents,
                    "generationConfig": {
                        "temperature": min(request.temperature or 0.7, 1),
                        "maxOutputTokens": request.max_tokens or 1024,
                    },
                    "stream": True,
                    **request.kwargs,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    content = parts[0].get("text", "")
                                    if content:
                                        yield content
                        except json.JSONDecodeError:
                            continue


class LocalAdapter(BaseLLMAdapter):
    """本地模型适配器"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.local_model = None
        self._init_local_model()

    def _init_local_model(self):
        """初始化本地模型"""
        try:
            from ..local_model import LocalModel
            self.local_model = LocalModel()
        except Exception as e:
            logger.warning(f"Failed to initialize local model: {e}")
            self.local_model = None

    async def chat(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> UnifiedChatResponse:
        if not self.local_model:
            return UnifiedChatResponse(content="", finish_reason="error")

        prompt = self._build_prompt(request.messages)
        response = await self.local_model.ainference(
            prompt,
            max_tokens=request.max_tokens or 1024,
            temperature=request.temperature or 0.7,
        )
        return UnifiedChatResponse(content=response, finish_reason="stop")

    async def chat_stream(
        self,
        config: Dict[str, Any],
        request: UnifiedChatRequest,
    ) -> AsyncGenerator[str, None]:
        if not self.local_model:
            yield ""
            return

        prompt = self._build_prompt(request.messages)
        async for chunk in self.local_model.ainference_stream(
            prompt,
            max_tokens=request.max_tokens or 1024,
            temperature=request.temperature or 0.7,
        ):
            if chunk:
                yield chunk

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """构建本地模型的提示词格式"""
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            else:
                prompt_parts.append(f"User: {content}")
        
        prompt_parts.append("Assistant:")
        return "\n".join(prompt_parts)