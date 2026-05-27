import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union
from abc import ABC, abstractmethod
from loguru import logger


class UnifiedMessage:
    """统一消息格式"""
    def __init__(
        self,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_result: Optional[Dict[str, Any]] = None,
    ):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls or []
        self.tool_result = tool_result

    def to_dict(self) -> Dict[str, Any]:
        result = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_result:
            result["tool_result"] = self.tool_result
        return result


class UnifiedTool:
    """统一工具定义"""
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        required: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.required = required or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "required": self.required,
        }


class UnifiedRequest:
    """统一请求格式"""
    def __init__(
        self,
        model: str,
        messages: List[UnifiedMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = False,
        tools: Optional[List[UnifiedTool]] = None,
        response_format: Optional[str] = None,
        **kwargs,
    ):
        self.model = model
        self.messages = messages
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.tools = tools or []
        self.response_format = response_format
        self.kwargs = kwargs


class UnifiedResponse:
    """统一响应格式"""
    def __init__(
        self,
        content: Optional[str] = None,
        finish_reason: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        usage: Optional[Dict[str, int]] = None,
    ):
        self.content = content
        self.finish_reason = finish_reason
        self.tool_calls = tool_calls
        self.model = model
        self.usage = usage


class ProviderConfig:
    """供应商配置结构"""
    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        stream: bool = True,
        **extra,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.extra = extra

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            **self.extra,
        }


class ProviderAdapter(ABC):
    """供应商适配器基类"""

    @abstractmethod
    async def chat(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> UnifiedResponse:
        pass

    @abstractmethod
    async def chat_stream(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> AsyncGenerator[str, None]:
        pass

    @abstractmethod
    async def list_models(self, config: ProviderConfig) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        pass

    @abstractmethod
    def supports_streaming(self) -> bool:
        pass


class OpenAIAdapter(ProviderAdapter):
    """OpenAI 原生适配器"""

    async def chat(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> UnifiedResponse:
        import httpx

        messages = [m.to_dict() for m in request.messages]
        
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": min(request.temperature, 2),
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        if request.tools:
            payload["tools"] = [t.to_dict() for t in request.tools]
        
        if request.response_format:
            payload["response_format"] = {"type": request.response_format}

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        
        return UnifiedResponse(
            content=message.get("content"),
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls"),
            model=data.get("model"),
            usage=data.get("usage"),
        )

    async def chat_stream(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> AsyncGenerator[str, None]:
        import httpx

        messages = [m.to_dict() for m in request.messages]
        
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": min(request.temperature, 2),
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if request.tools:
            payload["tools"] = [t.to_dict() for t in request.tools]
        
        if request.response_format:
            payload["response_format"] = {"type": request.response_format}

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{config.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
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
                            delta = parsed["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

    async def list_models(self, config: ProviderConfig) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{config.base_url}/models",
                headers={"Authorization": f"Bearer {config.api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            return []

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True


class AnthropicAdapter(ProviderAdapter):
    """Anthropic Claude 适配器"""

    async def chat(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> UnifiedResponse:
        import httpx

        system_messages = [m for m in request.messages if m.role == "system"]
        other_messages = [m for m in request.messages if m.role != "system"]
        
        system_content = "\n".join(m.content for m in system_messages)
        
        messages = []
        for m in other_messages:
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            if m.tool_result:
                msg["tool_result"] = m.tool_result
            messages.append(msg)

        payload = {
            "model": request.model,
            "system": system_content,
            "messages": messages,
            "temperature": min(request.temperature, 1),
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": config.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return UnifiedResponse(
            content=data["content"][0]["text"],
            finish_reason=data.get("stop_reason"),
            model=data.get("model"),
            usage=data.get("usage"),
        )

    async def chat_stream(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> AsyncGenerator[str, None]:
        import httpx

        system_messages = [m for m in request.messages if m.role == "system"]
        other_messages = [m for m in request.messages if m.role != "system"]
        
        system_content = "\n".join(m.content for m in system_messages)
        
        messages = []
        for m in other_messages:
            msg = {"role": m.role, "content": m.content}
            messages.append(msg)

        payload = {
            "model": request.model,
            "system": system_content,
            "messages": messages,
            "temperature": min(request.temperature, 1),
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{config.base_url}/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": config.api_key,
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
                                text = data.get("delta", {}).get("text", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue

    async def list_models(self, config: ProviderConfig) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{config.base_url}/models",
                headers={
                    "x-api-key": config.api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            return []

    def supports_tools(self) -> bool:
        return False

    def supports_streaming(self) -> bool:
        return True


class GeminiAdapter(ProviderAdapter):
    """Google Gemini 适配器"""

    async def chat(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> UnifiedResponse:
        import httpx

        contents = []
        for m in request.messages:
            role = "model" if m.role == "assistant" else "user"
            parts = [{"text": m.content}]
            contents.append({"role": role, "parts": parts})

        generation_config = {
            "temperature": min(request.temperature, 1),
            "maxOutputTokens": request.max_tokens,
        }

        if request.response_format == "json_object":
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.base_url}/models/{request.model}:generateContent?key={config.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        candidate = data["candidates"][0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        
        return UnifiedResponse(
            content=parts[0]["text"] if parts else None,
            finish_reason=candidate.get("finishReason"),
            model=data.get("model"),
        )

    async def chat_stream(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> AsyncGenerator[str, None]:
        import httpx

        contents = []
        for m in request.messages:
            role = "model" if m.role == "assistant" else "user"
            parts = [{"text": m.content}]
            contents.append({"role": role, "parts": parts})

        generation_config = {
            "temperature": min(request.temperature, 1),
            "maxOutputTokens": request.max_tokens,
        }

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
            "stream": True,
        }

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{config.base_url}/models/{request.model}:generateContent?key={config.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            candidates = data.get("candidates", [])
                            if candidates:
                                content = candidates[0].get("content", {})
                                parts = content.get("parts", [])
                                if parts:
                                    text = parts[0].get("text", "")
                                    if text:
                                        yield text
                        except json.JSONDecodeError:
                            continue

    async def list_models(self, config: ProviderConfig) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{config.base_url}/models?key={config.api_key}",
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
            return []

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True


class MistralAdapter(ProviderAdapter):
    """Mistral AI 适配器（OpenAI-compatible）"""

    async def chat(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> UnifiedResponse:
        import httpx

        messages = [m.to_dict() for m in request.messages]
        
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": min(request.temperature, 2),
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        if request.tools:
            payload["tools"] = [t.to_dict() for t in request.tools]

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        
        return UnifiedResponse(
            content=message.get("content"),
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls"),
            model=data.get("model"),
            usage=data.get("usage"),
        )

    async def chat_stream(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> AsyncGenerator[str, None]:
        import httpx

        messages = [m.to_dict() for m in request.messages]
        
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": min(request.temperature, 2),
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if request.tools:
            payload["tools"] = [t.to_dict() for t in request.tools]

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{config.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
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
                            delta = parsed["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

    async def list_models(self, config: ProviderConfig) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{config.base_url}/models",
                headers={"Authorization": f"Bearer {config.api_key}"},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            return []

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True


class OpenAICompatibleAdapter(ProviderAdapter):
    """通用 OpenAI 兼容适配器"""

    async def chat(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> UnifiedResponse:
        import httpx

        messages = [m.to_dict() for m in request.messages]
        
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": min(request.temperature, 2),
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        if request.tools:
            payload["tools"] = [t.to_dict() for t in request.tools]
        
        if request.response_format:
            payload["response_format"] = {"type": request.response_format}

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        
        return UnifiedResponse(
            content=message.get("content"),
            finish_reason=choice.get("finish_reason"),
            tool_calls=message.get("tool_calls"),
            model=data.get("model"),
            usage=data.get("usage"),
        )

    async def chat_stream(
        self,
        config: ProviderConfig,
        request: UnifiedRequest,
    ) -> AsyncGenerator[str, None]:
        import httpx

        messages = [m.to_dict() for m in request.messages]
        
        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": min(request.temperature, 2),
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if request.tools:
            payload["tools"] = [t.to_dict() for t in request.tools]
        
        if request.response_format:
            payload["response_format"] = {"type": request.response_format}

        payload.update(request.kwargs)

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{config.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.api_key}",
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
                            delta = parsed["choices"][0]["delta"]
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

    async def list_models(self, config: ProviderConfig) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{config.base_url}/models",
                    headers={"Authorization": f"Bearer {config.api_key}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", [])
            except Exception:
                pass
            return []

    def supports_tools(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True


class LLMGateway:
    """多供应商 LLM 网关"""

    _adapter_map: Dict[str, Type[ProviderAdapter]] = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "gemini": GeminiAdapter,
        "mistral": MistralAdapter,
        "openai_compatible": OpenAICompatibleAdapter,
        "deepseek": OpenAICompatibleAdapter,
        "qwen": OpenAICompatibleAdapter,
        "kimi": OpenAICompatibleAdapter,
        "moonshot": OpenAICompatibleAdapter,
        "baidu": OpenAICompatibleAdapter,
        "doubao": OpenAICompatibleAdapter,
        "dashscope": OpenAICompatibleAdapter,
        "together": OpenAICompatibleAdapter,
        "ollama": OpenAICompatibleAdapter,
        "vllm": OpenAICompatibleAdapter,
        "custom": OpenAICompatibleAdapter,
    }

    def __init__(self, config: Optional[ProviderConfig] = None):
        self._config = config
        self._adapter = None
        if config:
            self._adapter = self._create_adapter(config.provider)

    def _create_adapter(self, provider: str) -> ProviderAdapter:
        adapter_class = self._adapter_map.get(provider.lower())
        if not adapter_class:
            adapter_class = OpenAICompatibleAdapter
            logger.warning(f"Unknown provider '{provider}', falling back to OpenAI-compatible adapter")
        return adapter_class()

    async def configure(self, config: ProviderConfig):
        """配置网关"""
        self._config = config
        self._adapter = self._create_adapter(config.provider)
        await self._validate_config()

    async def _validate_config(self):
        """验证配置"""
        if not self._config:
            raise ValueError("Gateway not configured")
        
        if not self._config.api_key:
            raise ValueError("API key is required")
        
        if not self._config.base_url:
            raise ValueError("Base URL is required")
        
        if not self._config.model:
            raise ValueError("Model is required")

    async def chat(
        self,
        messages: List[Union[UnifiedMessage, Dict[str, Any]]],
        **kwargs,
    ) -> UnifiedResponse:
        """执行非流式对话"""
        if not self._adapter:
            raise ValueError("Gateway not configured")

        unified_messages = []
        for msg in messages:
            if isinstance(msg, UnifiedMessage):
                unified_messages.append(msg)
            else:
                unified_messages.append(UnifiedMessage(**msg))

        request = UnifiedRequest(
            model=self._config.model,
            messages=unified_messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            stream=False,
            **kwargs,
        )

        return await self._adapter.chat(self._config, request)

    async def chat_stream(
        self,
        messages: List[Union[UnifiedMessage, Dict[str, Any]]],
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """执行流式对话"""
        if not self._adapter:
            raise ValueError("Gateway not configured")

        unified_messages = []
        for msg in messages:
            if isinstance(msg, UnifiedMessage):
                unified_messages.append(msg)
            else:
                unified_messages.append(UnifiedMessage(**msg))

        request = UnifiedRequest(
            model=self._config.model,
            messages=unified_messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            stream=True,
            **kwargs,
        )

        async for chunk in self._adapter.chat_stream(self._config, request):
            yield chunk

    async def list_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        if not self._adapter:
            raise ValueError("Gateway not configured")
        return await self._adapter.list_models(self._config)

    async def validate_model(self, model_name: str) -> bool:
        """验证模型是否存在"""
        models = await self.list_models()
        model_names = [m.get("id") or m.get("name") for m in models if isinstance(m, dict)]
        return model_name in model_names

    def get_adapter_info(self) -> Dict[str, Any]:
        """获取适配器信息"""
        if not self._adapter:
            return {}
        return {
            "provider": self._config.provider if self._config else None,
            "supports_tools": self._adapter.supports_tools(),
            "supports_streaming": self._adapter.supports_streaming(),
        }

    @classmethod
    def get_supported_providers(cls) -> List[str]:
        """获取支持的供应商列表"""
        return list(cls._adapter_map.keys())

    @classmethod
    def register_adapter(cls, provider: str, adapter_class: Type[ProviderAdapter]):
        """注册自定义适配器"""
        cls._adapter_map[provider.lower()] = adapter_class