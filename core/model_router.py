import httpx
import threading
from openai import AsyncOpenAI
from typing import Tuple, List, Dict, Any, Optional, Callable
from loguru import logger
from utils.config_manager import config_manager


class ModelRouter:
    def __init__(self, config_data: Optional[Dict[str, Any]] = None):
        if config_data is None:
            self.config = config_manager.get_all()
        else:
            self.config = config_data
        providers = self.config.get("providers", {})
        self.matrix = self._normalize_routing_matrix(self.config.get("routing_matrix", {}), providers)
        self.network = self.config.get("network", {})
        self.enable_fallback = self.config.get("enable_fallback", True)
        self.enable_routing_matrix = self.config.get("enable_routing_matrix", False)
        self._client_cache: Dict[str, AsyncOpenAI] = {}
        self._client_cache_lock = threading.Lock()

    def _normalize_routing_matrix(self, matrix: Dict[str, Any], providers: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
        """将路由矩阵标准化为完整配置格式，兼容旧格式"""
        providers = providers or {}
        normalized = {}
        legacy_fields = ['use_proxy', 'proxy_type', 'proxy_host', 'proxy_port', 'proxy_auth', 'proxy_username', 'proxy_password']
        
        for task_type, entries in matrix.items():
            normalized_entries = []
            for entry in entries:
                if isinstance(entry, str):
                    if entry in providers:
                        provider_config = providers[entry]
                        normalized_entry = {
                            'name': entry,
                            'base_url': provider_config.get('base_url', ''),
                            'api_key': provider_config.get('api_key', ''),
                            'model': provider_config.get('model', '')
                        }
                        for field in legacy_fields:
                            if field in provider_config:
                                normalized_entry[field] = provider_config[field]
                        normalized_entries.append(normalized_entry)
                elif isinstance(entry, dict):
                    normalized_entries.append(entry)
            
            normalized[task_type] = normalized_entries
        
        if not normalized and providers:
            default_provider = list(providers.keys())[0]
            default_config = providers[default_provider]
            default_entry = {
                'name': default_provider,
                'base_url': default_config.get('base_url', ''),
                'api_key': default_config.get('api_key', ''),
                'model': default_config.get('model', '')
            }
            for field in legacy_fields:
                if field in default_config:
                    default_entry[field] = default_config[field]
            normalized = {
                'chat': [default_entry],
                'reasoning': [default_entry],
                'diary': [default_entry]
            }
        
        return normalized

    def _get_basic_model_config(self) -> Tuple[str, Dict[str, Any]]:
        """获取基础模型配置"""
        ai_config = self.config.get("ai", {})
        provider_name = ai_config.get("provider", "")
        base_url = ai_config.get("endpoint", "")
        api_key = ai_config.get("api_key", "")
        model = ai_config.get("model", "")
        
        return (provider_name or "basic", {
            'base_url': base_url,
            'api_key': api_key,
            'model': model
        })

    def get_ordered_providers(self, task_type: str) -> List[Tuple[str, Dict[str, Any]]]:
        if not self.enable_routing_matrix:
            return [self._get_basic_model_config()]
        
        entries = self.matrix.get(task_type, [])
        if not entries:
            return [self._get_basic_model_config()]
            
        return [(entry.get('name', 'unnamed'), entry) for entry in entries]

    async def create_client_for_task(self, task_type: str, fallback_index: int = 0) -> Tuple[AsyncOpenAI, str, str]:
        candidates = self.get_ordered_providers(task_type)
        if fallback_index >= len(candidates):
            raise RuntimeError(f"任务 {task_type} 的所有配置模型均不可用（已尝试全部 Fallback）")
            
        provider_name, info = candidates[fallback_index]
        
        cache_key = f"{info.get('base_url', '')}|{info.get('api_key', '')}|{info.get('model', '')}"
        
        with self._client_cache_lock:
            if cache_key in self._client_cache:
                return self._client_cache[cache_key], info["model"], provider_name
        
        from core.ai_manager import get_proxy_mounts
        
        current_network = config_manager.get("network", {})
        mounts = get_proxy_mounts(current_network)
        timeout = current_network.get("timeout", 30.0)
        
        http_client = httpx.AsyncClient(
            mounts=mounts,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=3),
            http2=True,
            headers={'Accept-Encoding': 'gzip, deflate'},
            retries=httpx.Retry(
                total=3,
                backoff_factor=1,
                status_codes=[429, 500, 502, 503, 504]
            )
        )
        
        client = AsyncOpenAI(
            base_url=info["base_url"],
            api_key=info["api_key"],
            http_client=http_client
        )
        
        with self._client_cache_lock:
            self._client_cache[cache_key] = client
        
        logger.info(f"[ModelRouter] 为 Provider [{provider_name}] 创建独立 HTTP 客户端，代理: {mounts}")
        return client, info["model"], provider_name

    async def clear_client_cache(self):
        """清空客户端缓存，用于配置变更时重建客户端"""
        with self._client_cache_lock:
            for provider_name, client in self._client_cache.items():
                if hasattr(client, 'http_client') and client.http_client is not None:
                    try:
                        await client.http_client.aclose()
                        logger.info(f"[ModelRouter] 关闭 Provider [{provider_name}] 的 HTTP 客户端连接")
                    except Exception as e:
                        logger.warning(f"[ModelRouter] 关闭 Provider [{provider_name}] 的 HTTP 客户端连接失败: {e}")
            self._client_cache = {}

    async def query_with_fallback(self, task_type: str, messages: List[Dict[str, str]], 
                                  stream: bool = False, temperature: float = 0.7,
                                  max_tokens: int = 2000,
                                  stream_callback: Optional[Callable[[str], None]] = None) -> str:
        fallback_index = 0
        candidates = self.get_ordered_providers(task_type)
        
        max_attempts = len(candidates) if self.enable_fallback else 1
        
        while fallback_index < max_attempts:
            try:
                client, model_id, provider_name = await self.create_client_for_task(task_type, fallback_index)
                logger.info(f"[Router] 正在为任务类型 [{task_type}] 调度 [{provider_name}] -> {model_id}")
                
                if stream:
                    full_text = ""
                    response = await client.chat.completions.create(
                        model=model_id,
                        messages=messages,
                        stream=True,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    async for chunk in response:
                        content = chunk.choices[0].delta.content or ""
                        if content:
                            full_text += content
                            if stream_callback:
                                stream_callback(content)
                    return full_text
                else:
                    response = await client.chat.completions.create(
                        model=model_id,
                        messages=messages,
                        stream=False,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return response.choices[0].message.content or ""
                    
            except (httpx.ConnectError, httpx.TimeoutException, Exception) as e:
                current_provider = provider_name if 'provider_name' in locals() else (
                    candidates[fallback_index][0] if fallback_index < len(candidates) else "unknown"
                )
                if not self.enable_fallback:
                    logger.error(f"[Router] 通道 {current_provider} 异常: {e}，自动降级已禁用，直接抛出异常")
                    raise
                
                logger.warning(f"[Router Fallback] 通道 {current_provider} 异常: {e}，正在尝试自动熔断降级...")
                fallback_index += 1
        
        raise RuntimeError(f"任务 {task_type} 的所有配置模型均不可用")


_router_instance = None
_router_lock = threading.Lock()

def get_model_router() -> ModelRouter:
    global _router_instance
    with _router_lock:
        if _router_instance is None:
            _router_instance = ModelRouter()
        return _router_instance

async def reload_model_router():
    global _router_instance
    
    old_router = None
    
    with _router_lock:
        if _router_instance is not None:
            old_router = _router_instance
        
    if old_router is not None:
        await old_router.clear_client_cache()
        logger.info("[ModelRouter] 已清空旧实例的客户端缓存")
    
    with _router_lock:
        _router_instance = ModelRouter()
    
    from core.ai_manager import get_httpx_async_client
    await get_httpx_async_client(force_reload=True)
    
    logger.info("[ModelRouter] 模型路由已重新加载")
    return _router_instance