from typing import Any, Dict, List, Optional, Set, Union
from abc import ABC, abstractmethod
from loguru import logger


class ModelCapability:
    """模型能力定义"""
    
    def __init__(
        self,
        supports_stream: bool = False,
        input_modalities: Optional[Set[str]] = None,
        output_modalities: Optional[Set[str]] = None,
        supports_tools: bool = False,
        supports_json_schema: bool = False,
        max_context_tokens: int = 4096,
        max_output_tokens: int = 1024,
        temperature_range: tuple = (0, 2),
        supported_languages: Optional[List[str]] = None,
    ):
        self.supports_stream = supports_stream
        self.input_modalities = input_modalities or {"text"}
        self.output_modalities = output_modalities or {"text"}
        self.supports_tools = supports_tools
        self.supports_json_schema = supports_json_schema
        self.max_context_tokens = max_context_tokens
        self.max_output_tokens = max_output_tokens
        self.temperature_range = temperature_range
        self.supported_languages = supported_languages or ["en", "zh"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supports_stream": self.supports_stream,
            "input_modalities": list(self.input_modalities),
            "output_modalities": list(self.output_modalities),
            "supports_tools": self.supports_tools,
            "supports_json_schema": self.supports_json_schema,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "temperature_range": self.temperature_range,
            "supported_languages": self.supported_languages,
        }


class ProviderCapabilityStore:
    """供应商能力存储"""
    
    _capabilities: Dict[str, Dict[str, ModelCapability]] = {
        "openai": {
            "gpt-4o": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh", "ja", "ko", "fr", "de"],
            ),
            "gpt-4o-mini": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=16384,
                temperature_range=(0, 2),
                supported_languages=["en", "zh", "ja", "ko", "fr", "de"],
            ),
            "gpt-4-turbo": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh", "ja", "ko", "fr", "de"],
            ),
            "gpt-3.5-turbo": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=16384,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh", "ja", "ko", "fr", "de"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=8192,
                max_output_tokens=2048,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
        "anthropic": {
            "claude-3-5-sonnet": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=False,
                supports_json_schema=False,
                max_context_tokens=200000,
                max_output_tokens=8191,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "fr", "de"],
            ),
            "claude-3-opus": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=False,
                supports_json_schema=False,
                max_context_tokens=200000,
                max_output_tokens=8191,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "fr", "de"],
            ),
            "claude-3-sonnet": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=False,
                supports_json_schema=False,
                max_context_tokens=200000,
                max_output_tokens=8191,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "fr", "de"],
            ),
            "claude-3-haiku": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=False,
                supports_json_schema=False,
                max_context_tokens=200000,
                max_output_tokens=8191,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "fr", "de"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=False,
                supports_json_schema=False,
                max_context_tokens=100000,
                max_output_tokens=4096,
                temperature_range=(0, 1),
                supported_languages=["en", "zh"],
            ),
        },
        "gemini": {
            "gemini-1.5-pro": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image", "audio", "video"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=1048576,
                max_output_tokens=8192,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "ko", "fr", "de", "es"],
            ),
            "gemini-1.5-flash": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image", "audio", "video"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=1048576,
                max_output_tokens=8192,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "ko", "fr", "de", "es"],
            ),
            "gemini-1.0-pro": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=2048,
                temperature_range=(0, 1),
                supported_languages=["en", "zh", "ja", "fr", "de"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=2048,
                temperature_range=(0, 1),
                supported_languages=["en", "zh"],
            ),
        },
        "mistral": {
            "mistral-large": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "zh", "fr", "de", "es"],
            ),
            "mistral-medium": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "fr", "de", "es"],
            ),
            "mistral-small": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "fr", "de", "es"],
            ),
            "mixtral-8x7b": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=65536,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "fr", "de", "es"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en"],
            ),
        },
        "deepseek": {
            "deepseek-chat": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "deepseek-r1": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=65536,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
        "qwen": {
            "qwen-max": ModelCapability(
                supports_stream=True,
                input_modalities={"text", "image"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "qwen2-72b": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=65536,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
        "kimi": {
            "kimi-8k": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=8192,
                max_output_tokens=2048,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "kimi-32k": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "kimi-128k": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=128000,
                max_output_tokens=8192,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=65536,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
        "moonshot": {
            "moonshot-v1-8k": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=8192,
                max_output_tokens=2048,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "moonshot-v1-32k": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
        "ollama": {
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=False,
                supports_json_schema=False,
                max_context_tokens=8192,
                max_output_tokens=2048,
                temperature_range=(0, 2),
                supported_languages=["en"],
            ),
        },
        "vllm": {
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=32768,
                max_output_tokens=4096,
                temperature_range=(0, 2),
                supported_languages=["en"],
            ),
        },
        "openai_compatible": {
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=8192,
                max_output_tokens=2048,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
        "custom": {
            "*": ModelCapability(
                supports_stream=True,
                input_modalities={"text"},
                output_modalities={"text"},
                supports_tools=True,
                supports_json_schema=True,
                max_context_tokens=8192,
                max_output_tokens=2048,
                temperature_range=(0, 2),
                supported_languages=["en", "zh"],
            ),
        },
    }

    @classmethod
    def get_capability(cls, provider: str, model: str) -> ModelCapability:
        """获取模型能力"""
        provider_lower = provider.lower()
        model_lower = model.lower()
        
        if provider_lower not in cls._capabilities:
            logger.warning(f"Unknown provider '{provider}', falling back to openai_compatible")
            provider_lower = "openai_compatible"
        
        provider_caps = cls._capabilities[provider_lower]
        
        if model_lower in provider_caps:
            return provider_caps[model_lower]
        
        for pattern in provider_caps:
            if pattern != "*" and pattern.lower() in model_lower:
                return provider_caps[pattern]
        
        return provider_caps["*"]

    @classmethod
    def register_capability(cls, provider: str, model: str, capability: ModelCapability):
        """注册自定义模型能力"""
        provider_lower = provider.lower()
        model_lower = model.lower()
        
        if provider_lower not in cls._capabilities:
            cls._capabilities[provider_lower] = {}
        
        cls._capabilities[provider_lower][model_lower] = capability

    @classmethod
    def get_provider_models(cls, provider: str) -> List[str]:
        """获取供应商支持的模型列表"""
        provider_lower = provider.lower()
        if provider_lower not in cls._capabilities:
            return []
        return [k for k in cls._capabilities[provider_lower].keys() if k != "*"]


class CapabilityNegotiator:
    """能力协商器"""
    
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        self.capability = ProviderCapabilityStore.get_capability(provider, model)

    def can_stream(self) -> bool:
        """检查是否支持流式输出"""
        return self.capability.supports_stream

    def supports_input_modality(self, modality: str) -> bool:
        """检查是否支持输入模态"""
        return modality.lower() in self.capability.input_modalities

    def supports_output_modality(self, modality: str) -> bool:
        """检查是否支持输出模态"""
        return modality.lower() in self.capability.output_modalities

    def can_use_tools(self) -> bool:
        """检查是否支持工具调用"""
        return self.capability.supports_tools

    def can_use_json_schema(self) -> bool:
        """检查是否支持JSON Schema"""
        return self.capability.supports_json_schema

    def validate_temperature(self, temperature: float) -> float:
        """验证并修正温度参数"""
        min_temp, max_temp = self.capability.temperature_range
        return max(min(temperature, max_temp), min_temp)

    def validate_max_tokens(self, max_tokens: int) -> int:
        """验证并修正最大token数"""
        return min(max_tokens, self.capability.max_output_tokens)

    def get_degradation_strategy(
        self,
        required_stream: bool = False,
        required_modalities: Optional[List[str]] = None,
        required_tools: bool = False,
    ) -> Dict[str, Any]:
        """获取降级策略"""
        required_modalities = required_modalities or []
        
        issues = []
        recommendations = []
        
        if required_stream and not self.can_stream():
            issues.append("streaming_not_supported")
            recommendations.append({
                "strategy": "fallback_to_non_streaming",
                "action": "使用非流式请求，前端做伪流式渲染",
            })
        
        for modality in required_modalities:
            if not self.supports_input_modality(modality):
                issues.append(f"input_modality_{modality}_not_supported")
                recommendations.append({
                    "strategy": f"convert_{modality}_to_text",
                    "action": f"先将{modality}转换为文本再处理",
                })
        
        if required_tools and not self.can_use_tools():
            issues.append("tools_not_supported")
            recommendations.append({
                "strategy": "fallback_without_tools",
                "action": "禁用工具调用，仅使用基础对话",
            })
        
        return {
            "capability": self.capability.to_dict(),
            "issues": issues,
            "recommendations": recommendations,
            "can_proceed": len(issues) == 0,
        }

    def get_capability_summary(self) -> Dict[str, Any]:
        """获取能力摘要"""
        return {
            "provider": self.provider,
            "model": self.model,
            **self.capability.to_dict(),
        }


class ModalityConverter(ABC):
    """模态转换器基类"""
    
    @abstractmethod
    async def convert(self, data: Any, **kwargs) -> str:
        """将非文本模态转换为文本描述"""
        pass


class ImageToTextConverter(ModalityConverter):
    """图片转文本转换器"""
    
    async def convert(self, image_data: Union[str, bytes], **kwargs) -> str:
        """将图片转换为文本描述"""
        logger.info("Converting image to text description")
        return f"[图片内容描述：使用OCR识别或图像描述模型处理]"


class AudioToTextConverter(ModalityConverter):
    """音频转文本转换器"""
    
    async def convert(self, audio_data: Union[str, bytes], **kwargs) -> str:
        """将音频转换为文本"""
        logger.info("Converting audio to text")
        return f"[音频转写内容：使用ASR模型处理]"


class VideoToTextConverter(ModalityConverter):
    """视频转文本转换器"""
    
    async def convert(self, video_data: Union[str, bytes], **kwargs) -> str:
        """将视频转换为文本摘要"""
        logger.info("Converting video to text summary")
        return f"[视频内容摘要：抽帧+ASR+关键片段分析]"


class ModalityConverterFactory:
    """模态转换器工厂"""
    
    _converters: Dict[str, ModalityConverter] = {
        "image": ImageToTextConverter(),
        "audio": AudioToTextConverter(),
        "video": VideoToTextConverter(),
    }

    @classmethod
    def get_converter(cls, modality: str) -> Optional[ModalityConverter]:
        """获取模态转换器"""
        return cls._converters.get(modality.lower())

    @classmethod
    def register_converter(cls, modality: str, converter: ModalityConverter):
        """注册自定义转换器"""
        cls._converters[modality.lower()] = converter

    @classmethod
    async def convert_if_needed(
        cls,
        modality: str,
        data: Any,
        capability: ModelCapability,
    ) -> Any:
        """根据能力决定是否转换模态"""
        if modality.lower() in capability.input_modalities:
            return data
        
        converter = cls.get_converter(modality)
        if converter:
            return await converter.convert(data)
        
        logger.warning(f"No converter available for modality '{modality}'")
        return str(data)


class RequestValidator:
    """请求验证器"""
    
    def __init__(self, negotiator: CapabilityNegotiator):
        self.negotiator = negotiator

    def validate(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证请求并返回修正后的参数"""
        errors = []
        warnings = []
        validated = request_data.copy()
        
        if "temperature" in request_data:
            validated["temperature"] = self.negotiator.validate_temperature(
                request_data["temperature"]
            )
            if validated["temperature"] != request_data["temperature"]:
                warnings.append({
                    "field": "temperature",
                    "original": request_data["temperature"],
                    "corrected": validated["temperature"],
                    "reason": f"超出模型支持范围 {self.negotiator.capability.temperature_range}",
                })
        
        if "max_tokens" in request_data:
            validated["max_tokens"] = self.negotiator.validate_max_tokens(
                request_data["max_tokens"]
            )
            if validated["max_tokens"] != request_data["max_tokens"]:
                warnings.append({
                    "field": "max_tokens",
                    "original": request_data["max_tokens"],
                    "corrected": validated["max_tokens"],
                    "reason": f"超出模型最大输出 {self.negotiator.capability.max_output_tokens}",
                })
        
        if "stream" in request_data and request_data["stream"]:
            if not self.negotiator.can_stream():
                validated["stream"] = False
                warnings.append({
                    "field": "stream",
                    "original": True,
                    "corrected": False,
                    "reason": "模型不支持流式输出，已自动降级",
                })
        
        if "tools" in request_data and request_data["tools"]:
            if not self.negotiator.can_use_tools():
                validated["tools"] = []
                warnings.append({
                    "field": "tools",
                    "original": len(request_data["tools"]),
                    "corrected": 0,
                    "reason": "模型不支持工具调用，已移除工具列表",
                })
        
        return {
            "validated": validated,
            "errors": errors,
            "warnings": warnings,
            "is_valid": len(errors) == 0,
        }