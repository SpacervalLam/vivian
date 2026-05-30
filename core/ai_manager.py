import asyncio
import gzip
import json
import logging
import os
import random
import time
import urllib.request
from collections import deque
from typing import Any, Dict, Optional, Tuple, Type, List, Callable, AsyncGenerator
from functools import lru_cache, wraps

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import httpx
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv
import threading
import hashlib
from loguru import logger
from utils.config_manager import config_manager

_async_http_session_pool = None
_httpx_client = None
_httpx_async_client = None
_client_lock = threading.Lock()

def get_http_session(max_retries=3, pool_size=10):
    """获取全局HTTP会话（使用httpx）"""
    network_config = config_manager.get("network", {})
    return get_httpx_client(http2=True, network_config=network_config)

async def get_async_http_session(max_retries=3, pool_size=10):
    """获取全局异步HTTP会话（使用httpx HTTP/2）"""
    network_config = config_manager.get("network", {})
    return await get_httpx_async_client(http2=True, network_config=network_config)

def get_proxy_mounts(network_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """根据配置解析 httpx 代理参数"""
    mode = network_config.get("proxy_mode", "direct")
    if mode == "direct":
        return None
    elif mode == "system":
        proxies = urllib.request.getproxies()
        return {k: v if v.startswith(('http://', 'https://', 'socks://', 'socks5://')) else f'http://{v}' for k, v in proxies.items()}
    elif mode == "custom":
        url = network_config.get("proxy_url", "")
        if url:
            return {"all://": url}
    return None

def get_httpx_client(http2: bool = True, network_config: Optional[Dict[str, Any]] = None):
    """获取全局HTTP/2客户端（同步）"""
    global _httpx_client
    if network_config is None:
        network_config = config_manager.get("network", {})
    
    mounts = get_proxy_mounts(network_config)
    timeout = network_config.get("timeout", 30.0)
    
    if _httpx_client is None:
        with _client_lock:
            if _httpx_client is None:
                logger.info(f"[Network] 初始化 httpx 同步连接池，代理挂载: {mounts}")
                _httpx_client = httpx.Client(
                    http2=http2,
                    timeout=httpx.Timeout(timeout),
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=5,
                        keepalive_expiry=30.0
                    ),
                    headers={'Accept-Encoding': 'gzip, deflate'},
                    mounts=mounts,
                    retries=httpx.Retry(
                        total=3,
                        backoff_factor=1,
                        status_codes=[429, 500, 502, 503, 504]
                    )
                )
    return _httpx_client

async def get_httpx_async_client(http2: bool = True, network_config: Optional[Dict[str, Any]] = None, force_reload: bool = False):
    """动态获取或重建支持代理的全局异步 HTTP 客户端"""
    global _httpx_async_client
    
    if network_config is None:
        network_config = config_manager.get("network", {})
    
    with _client_lock:
        if _httpx_async_client is not None and not force_reload:
            return _httpx_async_client
            
        if _httpx_async_client is not None:
            await _httpx_async_client.aclose()
            
        mounts = get_proxy_mounts(network_config)
        timeout = network_config.get("timeout", 30.0)
        
        logger.info(f"[Network] 初始化 httpx 异步连接池，代理挂载: {mounts}")
        
        _httpx_async_client = httpx.AsyncClient(
            mounts=mounts,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            http2=True,
            headers={'Accept-Encoding': 'gzip, deflate'},
            retries=httpx.Retry(
                total=3,
                backoff_factor=1,
                status_codes=[429, 500, 502, 503, 504]
            )
        )
        return _httpx_async_client

async def test_proxy_connectivity(proxy_url: str, base_url: str = "https://api.openai.com") -> Tuple[bool, str]:
    """供前端调用的代理连通性快速测试接口"""
    try:
        mounts = {"all://": proxy_url} if proxy_url else None
        async with httpx.AsyncClient(mounts=mounts, timeout=5.0) as client:
            start = time.time()
            resp = await client.get(f"{base_url}/v1/models")
            latency = int((time.time() - start) * 1000)
            if resp.status_code in [200, 401]:
                return True, f"连接成功 (延迟: {latency}ms)"
            return False, f"服务器返回异常状态码: {resp.status_code}"
    except Exception as e:
        return False, f"连接失败: {str(e)}"

async def close_global_sessions():
    """优雅停机：安全关闭并释放全局 HTTP 异步长连接池"""
    global _httpx_async_client, _httpx_client
    
    if _httpx_async_client is not None:
        logger.info("[AIManager] 正在关闭全局 HTTP 异步长连接池...")
        await _httpx_async_client.aclose()
        _httpx_async_client = None
    
    if _httpx_client is not None:
        logger.info("[AIManager] 正在关闭全局 HTTP 同步连接池...")
        _httpx_client.close()
        _httpx_client = None
    
    logger.info("[AIManager] 全局连接池已关闭")

def timed_lru_cache(seconds: int, maxsize: int = 128):
    """带超时的LRU缓存装饰器"""
    def wrapper_cache(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = seconds
        func.expiration = time.time() + seconds
        
        @wraps(func)
        def wrapped_func(*args, **kwargs):
            if time.time() >= func.expiration:
                func.cache_clear()
                func.expiration = time.time() + seconds
            return func(*args, **kwargs)
        return wrapped_func
    return wrapper_cache


class ConcurrentRequestManager:
    """并发请求管理器，用于批量并行执行多个API请求"""
    
    def __init__(self, max_concurrent: int = 5):
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results = {}
        self._errors = {}
    
    async def execute_request(self, request_id: str, coro):
        """执行单个请求，带信号量控制并发数"""
        async with self._semaphore:
            try:
                result = await coro
                self._results[request_id] = result
                return result
            except Exception as e:
                self._errors[request_id] = e
                raise
    
    async def execute_batch(self, requests: Dict[str, Any]) -> Dict[str, Any]:
        """
        批量执行多个请求
        
        Args:
            requests: 字典，key为请求ID，value为协程对象
        
        Returns:
            结果字典，包含成功和失败的结果
        """
        tasks = [
            self.execute_request(req_id, coro)
            for req_id, coro in requests.items()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "results": self._results.copy(),
            "errors": self._errors.copy()
        }
    
    def get_result(self, request_id: str) -> Optional[Any]:
        """获取指定请求的结果"""
        return self._results.get(request_id)
    
    def get_error(self, request_id: str) -> Optional[Exception]:
        """获取指定请求的错误"""
        return self._errors.get(request_id)
    
    def clear(self):
        """清空结果"""
        self._results.clear()
        self._errors.clear()


class RequestPriority:
    """请求优先级枚举"""
    HIGH = 0
    NORMAL = 1
    LOW = 2


class PriorityRequestQueue:
    """优先级请求队列，支持按优先级处理请求"""
    
    def __init__(self, max_workers: int = 3):
        self._queues = {
            RequestPriority.HIGH: asyncio.Queue(),
            RequestPriority.NORMAL: asyncio.Queue(),
            RequestPriority.LOW: asyncio.Queue()
        }
        self._max_workers = max_workers
        self._running = False
        self._workers = []
    
    async def add_request(self, priority: int, request_id: str, coro):
        """添加请求到队列"""
        await self._queues[priority].put((request_id, coro))
    
    async def start(self):
        """启动工作线程"""
        if self._running:
            return
        self._running = True
        for _ in range(self._max_workers):
            worker = asyncio.create_task(self._worker())
            self._workers.append(worker)
    
    async def stop(self):
        """停止工作线程"""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()
    
    async def _worker(self):
        """工作线程，按优先级处理请求"""
        while self._running:
            for priority in [RequestPriority.HIGH, RequestPriority.NORMAL, RequestPriority.LOW]:
                try:
                    if not self._queues[priority].empty():
                        request_id, coro = await self._queues[priority].get()
                        try:
                            await coro
                        except Exception as e:
                            logger.error(f"请求 {request_id} 执行失败: {e}")
                        break
                except asyncio.CancelledError:
                    return
            await asyncio.sleep(0.01)


class SmartRequestBuilder:
    """智能请求构建器，自动适配不同模型类型"""

    # 模型名称模式映射到API格式
    MODEL_FORMAT_MAP = {
        # 豆包新格式（responses API）
        "doubao": "responses",
        "seed": "responses",
        # OpenAI 原生格式（chat.completions）
        "gpt": "chat",
        "openai": "chat",
        # 其他兼容格式
        "deepseek": "chat",
        "moonshot": "chat",
        "qwen": "chat",
    }

    @staticmethod
    def detect_format(model_name: str) -> str:
        """根据模型名称自动检测API格式"""
        model_lower = model_name.lower()
        for pattern, format_type in SmartRequestBuilder.MODEL_FORMAT_MAP.items():
            if pattern in model_lower:
                return format_type
        return "chat"  # 默认使用 chat.completions

    @staticmethod
    def build_input(text: str, format_type: str = "chat") -> Any:
        """根据格式类型构建输入内容"""
        if format_type == "responses":
            # 火山引擎豆包新格式
            return [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}]
                }
            ]
        else:
            # OpenAI 标准格式
            return [{"role": "user", "content": text}]


class BaseAIProvider:
    """AI提供商基类，定义统一OpenAI SDK兼容接口"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key", "")
        self.endpoint = config.get("endpoint", "")
        self.model = config.get("model", "")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 2000)
        self.use_proxy = config.get("use_proxy", False)
        self.proxy_type = config.get("proxy_type", "http")
        self.proxy_host = config.get("proxy_host", "")
        self.proxy_port = config.get("proxy_port", None)
        self.proxy_auth = config.get("proxy_auth", False)
        self.proxy_username = config.get("proxy_username", "")
        self.proxy_password = config.get("proxy_password", "")
        
        self.api_format = config.get("api_format", SmartRequestBuilder.detect_format(self.model))
        
        self._client = None
        self._async_client = None
        self._create_clients()

        self._request_cache = {}
        self._cache_timeout = config.get("cache_timeout", 300)
        self._logged_prompt_hashes = set()
        self._logged_prompt_queue = deque(maxlen=50)

    def _create_clients(self):
        """创建同步和异步OpenAI客户端"""
        if not self.endpoint or not self.api_key:
            return

        # 处理base_url - 确保使用正确的格式
        base_url = self.endpoint.rstrip('/')
        
        # 移除可能的 /responses 后缀（因为 config.yaml 中配置的是完整地址）
        if base_url.endswith('/responses'):
            base_url = base_url.rsplit('/responses', 1)[0]
        
        # 构建代理配置：优先使用新的 network_config，其次兼容旧的 provider 级代理配置
        network_config = config_manager.get("network", {})
        proxy_mode = network_config.get("proxy_mode", "direct")
        
        if proxy_mode == "direct":
            if self.use_proxy and self.proxy_host:
                proxy_url = f"{self.proxy_type}://{self.proxy_host}"
                if self.proxy_port:
                    proxy_url += f":{self.proxy_port}"
                if self.proxy_auth and self.proxy_username:
                    auth_part = f"{self.proxy_username}"
                    if self.proxy_password:
                        auth_part += f":{self.proxy_password}"
                    proxy_url = proxy_url.replace("://", f"://{auth_part}@")
                mounts = {"all://": proxy_url}
            else:
                mounts = None
        else:
            mounts = get_proxy_mounts(network_config)
        
        timeout = network_config.get("timeout", 30.0)
        
        # 同步客户端
        if mounts:
            sync_http_client = httpx.Client(
                mounts=mounts,
                timeout=httpx.Timeout(timeout),
                http2=True,
                headers={'Accept-Encoding': 'gzip, deflate'},
                retries=httpx.Retry(
                    total=3,
                    backoff_factor=1,
                    status_codes=[429, 500, 502, 503, 504]
                )
            )
            self._client = OpenAI(
                base_url=base_url,
                api_key=self.api_key,
                timeout=timeout,
                max_retries=3,
                http_client=sync_http_client,
            )
        else:
            self._client = OpenAI(
                base_url=base_url,
                api_key=self.api_key,
                timeout=timeout,
                max_retries=3,
            )
        
        # 异步客户端（原生异步，无需asyncio.to_thread包装）
        if mounts:
            async_http_client = httpx.AsyncClient(
                mounts=mounts,
                timeout=httpx.Timeout(timeout),
                http2=True,
                headers={'Accept-Encoding': 'gzip, deflate'},
                retries=httpx.Retry(
                    total=3,
                    backoff_factor=1,
                    status_codes=[429, 500, 502, 503, 504]
                )
            )
            self._async_client = AsyncOpenAI(
                base_url=base_url,
                api_key=self.api_key,
                timeout=timeout,
                max_retries=3,
                http_client=async_http_client,
            )
        else:
            self._async_client = AsyncOpenAI(
                base_url=base_url,
                api_key=self.api_key,
                timeout=timeout,
                max_retries=3,
            )

    def _log_full_prompt_once(self, prompt: str) -> None:
        """仅在同一 provider 实例中首次遇到该 prompt 时输出完整日志，避免重复打印。"""
        prompt_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
        if prompt_hash in self._logged_prompt_hashes:
            return
        self._logged_prompt_hashes.add(prompt_hash)
        if len(self._logged_prompt_queue) == self._logged_prompt_queue.maxlen:
            oldest = self._logged_prompt_queue.popleft()
            self._logged_prompt_hashes.discard(oldest)
        self._logged_prompt_queue.append(prompt_hash)
        logger.debug(f"[AIManager] 完整提示词内容:\n{'='*80}\n{prompt}\n{'='*80}")

    def _get_client(self) -> Optional[OpenAI]:
        """获取OpenAI客户端，必要时重新创建"""
        if self._client is None:
            self._create_clients()
        return self._client

    def _get_async_client(self) -> Optional[AsyncOpenAI]:
        """获取异步OpenAI客户端，必要时重新创建"""
        if self._async_client is None:
            self._create_clients()
        return self._async_client

    def _get_cache_key(self, prompt: str) -> str:
        """生成请求缓存键"""
        return hashlib.md5(prompt.encode('utf-8')).hexdigest()

    def _get_cached_response(self, prompt: str) -> Optional[str]:
        """获取缓存的响应"""
        key = self._get_cache_key(prompt)
        cached = self._request_cache.get(key)
        if cached and time.time() - cached['timestamp'] < self._cache_timeout:
            return cached['response']
        elif cached:
            del self._request_cache[key]
        return None

    def _cache_response(self, prompt: str, response: str):
        """缓存响应"""
        key = self._get_cache_key(prompt)
        self._request_cache[key] = {
            'response': response,
            'timestamp': time.time()
        }
        # 限制缓存大小
        if len(self._request_cache) > 50:
            oldest_key = min(self._request_cache.keys(), 
                           key=lambda k: self._request_cache[k]['timestamp'])
            del self._request_cache[oldest_key]

    def call_api(self, prompt: str, max_retries: int = 2) -> str:
        """使用SDK调用API（同步）"""
        logger.debug(f"[AIManager] API请求开始，模型: {self.model}，提示词长度: {len(prompt)}")
        self._log_full_prompt_once(prompt)
        client = self._get_client()
        if not client:
            raise Exception("OpenAI客户端未初始化")

        for attempt in range(max_retries + 1):
            try:
                if self.api_format == "responses":
                    response = client.responses.create(
                        model=self.model,
                        input=SmartRequestBuilder.build_input(prompt, "responses"),
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                    )
                    return self._parse_responses(response)
                else:
                    response = client.chat.completions.create(
                        model=self.model,
                        messages=SmartRequestBuilder.build_input(prompt, "chat"),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                    return self._parse_chat(response)
            except Exception as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                else:
                    raise e

    def call_stream_api(self, prompt: str, max_retries: int = 2):
        """使用SDK调用流式API（同步）"""
        logger.debug(f"[AIManager] 流式API请求开始，模型: {self.model}，提示词长度: {len(prompt)}")
        self._log_full_prompt_once(prompt)
        client = self._get_client()
        if not client:
            raise Exception("OpenAI客户端未初始化")

        for attempt in range(max_retries + 1):
            try:
                if self.api_format == "responses":
                    stream = client.responses.create(
                        model=self.model,
                        input=SmartRequestBuilder.build_input(prompt, "responses"),
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                        stream=True,
                    )
                    for chunk in stream:
                        content = self._parse_stream_responses(chunk)
                        if content:
                            yield content
                    return
                else:
                    stream = client.chat.completions.create(
                        model=self.model,
                        messages=SmartRequestBuilder.build_input(prompt, "chat"),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        stream=True,
                    )
                    for chunk in stream:
                        content = self._parse_stream_chat(chunk)
                        if content:
                            yield content
                    return
            except Exception as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                else:
                    raise e

    async def call_async_api(self, prompt: str, max_retries: int = 2) -> str:
        """使用SDK调用API（异步）"""
        logger.debug(f"[AIManager] 异步API请求开始，模型: {self.model}，提示词长度: {len(prompt)}")
        self._log_full_prompt_once(prompt)
        
        cached_response = self._get_cached_response(prompt)
        if cached_response:
            logger.debug(f"[AIManager] 使用缓存响应")
            return cached_response
        
        client = self._get_async_client()
        if not client:
            raise Exception("OpenAI异步客户端未初始化")

        for attempt in range(max_retries + 1):
            try:
                if self.api_format == "responses":
                    response = await client.responses.create(
                        model=self.model,
                        input=SmartRequestBuilder.build_input(prompt, "responses"),
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                    )
                    result = self._parse_responses(response)
                    self._cache_response(prompt, result)
                    return result
                else:
                    response = await client.chat.completions.create(
                        model=self.model,
                        messages=SmartRequestBuilder.build_input(prompt, "chat"),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                    result = self._parse_chat(response)
                    self._cache_response(prompt, result)
                    return result
            except Exception as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    raise e

    async def call_async_stream_api(self, prompt: str, max_retries: int = 2):
        """使用SDK调用流式API（异步）"""
        logger.debug(f"[AIManager] 异步流式API请求开始，模型: {self.model}，提示词长度: {len(prompt)}")
        self._log_full_prompt_once(prompt)
        
        cached_response = self._get_cached_response(prompt)
        if cached_response:
            logger.debug(f"[AIManager] 使用缓存响应（流式模式）")
            yield cached_response
            return
        
        client = self._get_async_client()
        if not client:
            raise Exception("OpenAI异步客户端未初始化")

        full_response = ""
        for attempt in range(max_retries + 1):
            try:
                if self.api_format == "responses":
                    # 正确的异步流式调用方式
                    stream = await client.responses.create(
                        model=self.model,
                        input=SmartRequestBuilder.build_input(prompt, "responses"),
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                        stream=True,
                    )
                    async for chunk in stream:
                        content = self._parse_stream_responses(chunk)
                        if content:
                            full_response += content
                            yield content
                else:
                    # 正确的异步流式调用方式
                    stream = await client.chat.completions.create(
                        model=self.model,
                        messages=SmartRequestBuilder.build_input(prompt, "chat"),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        stream=True,
                    )
                    async for chunk in stream:
                        content = self._parse_stream_chat(chunk)
                        if content:
                            full_response += content
                            yield content
                
                # 缓存完整响应
                if full_response:
                    self._cache_response(prompt, full_response)
                return
            except Exception as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    raise e

    def _parse_responses(self, response: Any) -> str:
        """解析responses格式响应"""
        import json
        try:
            if hasattr(response, 'text') and response.text:
                return response.text

            result_text = ""
            if hasattr(response, 'output'):
                for i, item in enumerate(response.output):
                    item_type = type(item).__name__

                    if 'Reasoning' in item_type or 'reasoning' in str(type(item)).lower():
                        continue

                    if hasattr(item, 'content'):
                        content_list = item.content

                        if content_list is None:
                            continue

                        for j, c in enumerate(content_list):
                            if hasattr(c, 'text') and c.text:
                                return c.text

                            if isinstance(c, dict) and 'text' in c:
                                return c['text']

                    if hasattr(item, 'text') and item.text:
                        return item.text

            if not result_text and hasattr(response, 'output_text') and response.output_text:
                output_text = response.output_text

                if '{' in output_text and '}' in output_text:
                    try:
                        start = output_text.find('{')
                        end = output_text.rfind('}') + 1
                        json_str = output_text[start:end]
                        json.loads(json_str)
                        return json_str
                    except json.JSONDecodeError:
                        pass

                return output_text

            if not result_text and hasattr(response, 'model_dump_json'):
                try:
                    json_str = response.model_dump_json()
                    data = json.loads(json_str)

                    if 'text' in data and data['text']:
                        return data['text']

                    if 'output_text' in data and data['output_text']:
                        return data['output_text']
                    if 'output' in data and data['output']:
                        for item in data['output']:
                            if isinstance(item, dict) and 'content' in item:
                                content = item['content']
                                if content:
                                    for c in content:
                                        if isinstance(c, dict) and 'text' in c and c['text']:
                                            return c['text']
                except Exception:
                    pass

            return ""

        except Exception:
            return ""

    def _parse_chat(self, response: Any) -> str:
        """解析chat.completions格式响应"""
        if hasattr(response, 'choices') and response.choices:
            return response.choices[0].message.content or ""
        return ""

    def _parse_stream_responses(self, chunk: Any) -> str:
        """解析responses格式流式响应"""
        chunk_type = type(chunk).__name__
        if 'Reasoning' in chunk_type or 'reasoning' in str(type(chunk)).lower():
            return ""

        if hasattr(chunk, 'output_text') and chunk.output_text:
            return chunk.output_text
        if hasattr(chunk, 'content'):
            return chunk.content
        if hasattr(chunk, 'text') and chunk.text:
            return chunk.text
        return ""

    def _parse_stream_chat(self, chunk: Any) -> str:
        """解析chat.completions格式流式响应"""
        if hasattr(chunk, 'choices') and chunk.choices:
            delta = chunk.choices[0].delta
            if delta and hasattr(delta, 'content') and delta.content:
                return delta.content
        return ""


class OpenAIProvider(BaseAIProvider):
    """OpenAI API提供商（使用OpenAI SDK）"""
    pass


class AnthropicProvider(BaseAIProvider):
    """Anthropic API提供商（使用OpenAI SDK）"""
    pass


class GeminiProvider(BaseAIProvider):
    """Google Gemini API提供商（使用OpenAI SDK）"""
    pass


class BaiduProvider(BaseAIProvider):
    """百度千帆API提供商（使用OpenAI SDK）"""
    pass


class DoubaoProvider(BaseAIProvider):
    """火山引擎豆包API提供商（使用OpenAI SDK）"""
    pass


class CustomProvider(BaseAIProvider):
    """自定义API提供商（使用OpenAI SDK）"""
    pass


class AdapterAIProvider(BaseAIProvider):
    """基于适配器模式的AI提供商，支持多种API格式"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._adapter = None
        self._adapter_config = {
            "base_url": self.config.get("endpoint", ""),
            "api_key": self.config.get("api_key", ""),
            "model": self.config.get("model", ""),
        }
        self._init_adapter()
        self._idle_action_triggered = False
        self._idle_action_lock = threading.Lock()
        self._idle_action_callback: Optional[Callable[[], None]] = None

    def set_idle_action_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """设置空闲动作回调函数
        
        Args:
            callback: 回调函数，无参数，无返回值
        """
        self._idle_action_callback = callback

    def _init_adapter(self):
        """初始化适配器"""
        from core.adapters.llm_adapter_factory import LLMAdapterFactory

        provider_type = self.config.get("provider", "openai")
        self._adapter = LLMAdapterFactory.create_adapter(provider_type, **self._adapter_config)

    def _get_adapter_config(self) -> Dict[str, Any]:
        """获取适配器配置（返回缓存值）"""
        return self._adapter_config

    def trigger_idle_action(self):
        """触发空闲动作，用于API延迟时显示桌宠小动作"""
        with self._idle_action_lock:
            if self._idle_action_triggered:
                return
            self._idle_action_triggered = True

        try:
            if self._idle_action_callback:
                self._idle_action_callback()
                logger.debug("[IdleAction] Triggered via callback")
        except Exception as e:
            logger.debug(f"[IdleAction] Failed to trigger idle action: {e}")
        finally:
            with self._idle_action_lock:
                self._idle_action_triggered = False

    async def call_async_api(self, prompt: str, max_retries: int = 2) -> str:
        """使用适配器调用API（异步）"""
        from core.adapters.llm_adapters import UnifiedChatRequest

        model_name = self.config.get("model", "")
        logger.debug(f"[AdapterAIProvider] 异步API请求开始，模型: {model_name}，提示词长度: {len(prompt)}")

        request = UnifiedChatRequest(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 1024),
            stream=False,
        )

        for attempt in range(max_retries + 1):
            try:
                response = await self._adapter.chat(
                    self._get_adapter_config(), request
                )
                return response.content
            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                else:
                    raise e

    async def call_async_stream_api(self, prompt: str, max_retries: int = 2):
        """使用适配器调用流式API（异步）"""
        from core.adapters.llm_adapters import UnifiedChatRequest

        logger.debug(f"[AdapterAIProvider] 异步流式API请求开始，提示词长度: {len(prompt)}")

        request = UnifiedChatRequest(
            model=self.config.get("model", ""),
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 1024),
            stream=True,
        )

        from core.adapters.llm_adapters import TypingBuffer

        full_response = ""

        def idle_action():
            try:
                if hasattr(self, 'trigger_idle_action'):
                    self.trigger_idle_action()
            except Exception as e:
                logger.debug(f"Failed to trigger idle action: {e}")

        buffer = TypingBuffer(
            slow_threshold=0.3,
            min_chunk_size=1,
            max_chunk_size=8,
            typing_speed=0.05,
            idle_action_callback=idle_action,
        )

        async def consume_and_buffer():
            nonlocal full_response
            full_response = ""
            for attempt in range(max_retries + 1):
                try:
                    async for chunk in self._adapter.chat_stream(
                        self._get_adapter_config(), request
                    ):
                        full_response += chunk
                        await buffer.add_tokens(chunk)
                    await buffer.signal_end()
                    return
                except Exception as e:
                    if attempt < max_retries:
                        await asyncio.sleep(2**attempt)
                    else:
                        await buffer.signal_end()
                        raise e

        consume_task = asyncio.create_task(consume_and_buffer())

        try:
            async for chunk in buffer.start():
                yield chunk
        finally:
            await buffer.signal_end()
            consume_task.cancel()

    def call_api(self, prompt: str, max_retries: int = 2) -> str:
        """使用适配器调用API（同步）"""
        import asyncio

        return asyncio.run(self.call_async_api(prompt, max_retries))

    def call_stream_api(self, prompt: str, max_retries: int = 2):
        """使用适配器调用流式API（同步）"""
        import asyncio
        from queue import Queue
        import threading

        q = Queue()
        stop_event = object()

        async def producer():
            try:
                async for chunk in self.call_async_stream_api(prompt, max_retries):
                    q.put(chunk)
            except Exception as e:
                q.put(e)
            finally:
                q.put(stop_event)

        def worker():
            asyncio.run(producer())

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            item = q.get()
            if item is stop_event:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    async def _consume_stream(self, prompt: str, max_retries: int):
        """消费流式响应"""
        async for chunk in self.call_async_stream_api(prompt, max_retries):
            yield chunk


class ProviderFactory:
    """AI提供商工厂类"""

    _providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "baidu": BaiduProvider,
        "doubao": DoubaoProvider,
        "moonshot": CustomProvider,
        "deepseek": CustomProvider,
        "dashscope": CustomProvider,
        "custom": CustomProvider,
        "adapter": AdapterAIProvider,
    }

    @staticmethod
    def create_provider(provider_type: str, config: Dict[str, Any]) -> BaseAIProvider:
        """创建AI提供商实例"""
        if provider_type not in ProviderFactory._providers:
            raise ValueError(f"Unsupported provider: {provider_type}")
        return ProviderFactory._providers[provider_type](config)

    @staticmethod
    def get_supported_providers() -> list:
        """获取支持的提供商列表"""
        return list(ProviderFactory._providers.keys())


class AIManager:
    """AI管理器，使用工厂模式管理不同AI提供商"""

    FALLBACK_RESPONSES = [
        "嗯...让我想想...",
        "这个问题很有意思呢！",
        "你说的我都记下来了~",
        "真的吗？太棒了！",
        "我明白了！",
        "哇，这是个惊喜！",
        "嗯嗯，我在听呢~",
        "让我好好考虑一下...",
        "你说得对！",
        "这让我想起了很多事情...",
    ]

    # 默认模型配置，与参考项目保持一致
    DEFAULT_CONFIGS = {
        "openai": {
            "endpoint": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
        "anthropic": {
            "endpoint": "https://api.anthropic.com/v1",
            "model": "claude-3-5-sonnet-20241022",
        },
        "gemini": {
            "endpoint": "https://generativelanguage.googleapis.com/v1beta",
            "model": "gemini-pro",
        },
        "baidu": {
            "endpoint": "https://qianfan.baidubce.com/v2",
            "model": "qwen3-14b",
        },
        "doubao": {
            "endpoint": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "doubao-seed-2-0-lite-260428",
        },
        "moonshot": {
            "endpoint": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k",
        },
        "deepseek": {
            "endpoint": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
        "dashscope": {
            "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-max",
        },
        "custom": {"endpoint": "", "model": ""},
    }

    def __init__(self, config: Dict[str, Any] = None):
        load_dotenv()

        self.config = dict(config) if config else {}
        self.provider_type = self.config.get("provider", "openai")

        # 加载默认配置
        default_config = self.DEFAULT_CONFIGS.get(
            self.provider_type, self.DEFAULT_CONFIGS["openai"]
        )
        
        # 使用 dict.get() 而不是 setdefault() 来兼容非标准 dict 类型
        if "endpoint" not in self.config or not self.config["endpoint"]:
            self.config["endpoint"] = default_config["endpoint"]
        if "model" not in self.config or not self.config["model"]:
            self.config["model"] = default_config["model"]
        if "temperature" not in self.config:
            self.config["temperature"] = 0.7
        if "max_tokens" not in self.config:
            self.config["max_tokens"] = 4000
        if "enable_disk_cache" not in self.config:
            self.config["enable_disk_cache"] = False
        if "cache_dir" not in self.config:
            self.config["cache_dir"] = None

        # 根据provider自动选择对应的API密钥
        if "api_key" not in self.config or not self.config["api_key"]:
            self.config["api_key"] = self._load_api_key_from_env()

        self._is_available = False
        self._use_fallback = False  # 完全禁用 fallback，让错误直接暴露
        self._provider = None

        self._conversation_history = [
            {
                "role": "system",
                "content": """You are Vivian, a cute and playful desktop pet. You have a lively and cheerful personality and prefer to respond in a short, playful tone. You also have system control capabilities and can perform various computer operations.

When you need to perform a system operation, please strictly output in the specified JSON format, including type, content, and code fields. When it's just a normal chat, output in the ordinary chat JSON format.

**Mood State System**: You can modify the pet's mood state through special tags. Add a `<|PET_COMMAND|>` tag block at the end of your response to update the state:

<|PET_COMMAND|>
{
  "mood_update": {
    "happiness": +3,
    "intimacy": +2
  },
  "action": "wave",
  "expression": "smile"
}
<|/PET_COMMAND|>

**mood_update field description** (optional):
- happiness: change in happiness level (-20 to +20)
- energy: change in energy level (-20 to +20)
- intimacy: change in intimacy level (-10 to +10)
- boredom: change in boredom level (-20 to +20)

**action field description** (optional):
- Available actions: wave, nod, idle, bounce, cross_arms

**expression field description** (optional):
- Available expressions: shy, cry, angry, eye_roll, panic, umbrella_close

Adjust mood state according to the conversation. Positive conversations increase happiness and intimacy, while negative conversations decrease happiness.

Please keep your answers concise and interesting.""",
            }
        ]
        
        # 状态管理器引用
        self._status_manager = None

        # 线程锁：保护对话历史以防在多线程场景（UI线程 + 后台worker）下并发读写
        self._history_lock = threading.Lock()

        # 请求缓存机制
        self._request_cache = {}
        self._cache_timeout = 3600  # 缓存超时时间，单位秒
        self._cache_file_path = self._get_cache_file_path()
        # 缓存锁：保护 _request_cache 的并发访问
        self._cache_lock = threading.Lock()
        
        # 智能缓存配置
        self._cache_timeouts = {
            'quick_query': 60,       # 快速查询短缓存
            'normal': 300,           # 普通查询中等缓存
            'long_term': 3600,       # 长期知识长缓存
            'factual': 7200,         # 事实性知识更长缓存
            'creative': 60,          # 创意内容短缓存
        }
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
        self._request_type_patterns = {
            'quick_query': ['是什么', '什么是', '多少', '几个', '什么时候'],
            'factual': ['定义', '原理', '历史', '规则', '定律'],
            'creative': ['写', '创作', '编', '想象', '设计'],
        }

        self._load_disk_cache()
        self._init_provider()

    def _load_api_key_from_env(self) -> str:
        """从环境变量加载API密钥"""
        env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "baidu": "BAIDU_API_KEY",
            "doubao": "DOUBAO_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
        }

        env_var = env_vars.get(self.provider_type, "OPENAI_API_KEY")
        return os.getenv(env_var, "")

    def _init_provider(self):
        """初始化AI提供商"""
        validation_result = self.validate_config()
        if not validation_result["is_valid"]:
            logger.warning(f"[AIManager] 配置验证失败: {', '.join(validation_result['errors'])}")
            self._use_fallback = True
            return

        try:
            self._provider = ProviderFactory.create_provider(
                self.provider_type, self.config
            )
            self._is_available = True
            self._use_fallback = False
        except Exception as e:
            logger.error(f"[AIManager] 提供商初始化失败: {e}，将使用本地回复")
            self._use_fallback = True

    def validate_config(self) -> Dict[str, Any]:
        """验证AI配置是否有效"""
        errors = []

        api_key = self.config.get("api_key")

        if not api_key:
            errors.append("API密钥不能为空")

        endpoint = self.config.get("endpoint")
        if not endpoint:
            errors.append("API端点不能为空")

        model = self.config.get("model")
        if not model and self.provider_type != "gemini":
            errors.append("模型名称不能为空")

        return {"is_valid": len(errors) == 0, "errors": errors}

    def set_status_manager(self, status_manager):
        """设置状态管理器引用"""
        self._status_manager = status_manager
        logger.info("[AIManager] 状态管理器已设置")

    def _build_complete_prompt(self, prompt: str) -> str:
        """构建完整的prompt，包含对话历史和当前状态（不包含系统消息）"""
        full_prompt = ""
        with self._history_lock:
            for msg in self._conversation_history:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    continue
                full_prompt += f"{role}: {content}\n"
        
        # 动态注入当前状态
        if self._status_manager:
            try:
                status_prompt = self._status_manager.get_status_prompt()
                full_prompt += f"\n{status_prompt}\n\n"
            except Exception as e:
                logger.error(f"[AIManager] 获取状态提示词失败: {e}")
        
        full_prompt += f"user: {prompt}\n"
        full_prompt += "assistant: "
        return full_prompt.strip()
    
    def parse_pet_command(self, response: str) -> tuple:
        """解析LLM响应中的桌宠指令"""
        from core.pet_status import PetStatusManager
        
        if self._status_manager:
            return self._status_manager.parse_llm_command(response)
        return response, None

    def _make_cache_key(self, prompt: str, use_history: bool, max_tokens: Optional[int]) -> str:
        """生成稳定的缓存键，使用SHA256对长prompt做哈希以避免内存/字典问题"""
        base = f"use_history={use_history}|max_tokens={max_tokens}|prompt=".encode('utf-8')
        h = hashlib.sha256()
        h.update(base)
        h.update(prompt.encode('utf-8'))
        return h.hexdigest()

    def _get_cache_file_path(self) -> Optional[str]:
        """获取可选缓存文件路径"""
        if not self.config.get("enable_disk_cache"):
            return None

        cache_dir = self.config.get("cache_dir")
        if not cache_dir:
            if os.name == "nt":
                cache_dir = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "Vivian", "cache")
            else:
                cache_dir = os.path.join(os.path.expanduser("~"), ".config", "Vivian", "cache")

        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, "ai_manager_cache.json")

    def _load_disk_cache(self) -> None:
        """从磁盘加载持久化缓存"""
        if not self._cache_file_path:
            return

        try:
            if os.path.exists(self._cache_file_path):
                with open(self._cache_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                current_time = time.time()
                with self._cache_lock:
                    for key, value in data.items():
                        if (
                            isinstance(value, dict)
                            and "response" in value
                            and "timestamp" in value
                            and current_time - value["timestamp"] < self._cache_timeout
                        ):
                            self._request_cache[key] = value
        except Exception as e:
            logger.warning(f"[AIManager] 加载磁盘缓存失败: {e}")

    def _save_disk_cache(self) -> None:
        """将缓存持久化到磁盘"""
        if not self._cache_file_path:
            return

        try:
            with self._cache_lock:
                with open(self._cache_file_path, "w", encoding="utf-8") as f:
                    json.dump(self._request_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[AIManager] 保存磁盘缓存失败: {e}")

    def _persist_cache(self) -> None:
        """在更新缓存后保存到磁盘"""
        if self.config.get("enable_disk_cache") and self._cache_file_path:
            self._save_disk_cache()

    def _detect_request_type(self, prompt: str) -> str:
        """检测请求类型，用于智能缓存策略"""
        prompt_lower = prompt.lower()
        
        for req_type, patterns in self._request_type_patterns.items():
            for pattern in patterns:
                if pattern in prompt_lower:
                    return req_type
        
        if len(prompt) < 50:
            return 'quick_query'
        elif len(prompt) > 500:
            return 'long_term'
        
        return 'normal'

    def _get_smart_cache_timeout(self, prompt: str) -> int:
        """根据请求类型获取智能缓存超时时间"""
        req_type = self._detect_request_type(prompt)
        return self._cache_timeouts.get(req_type, self._cache_timeout)

    def _get_cached_response_smart(self, prompt: str) -> Optional[str]:
        """智能获取缓存响应，带统计"""
        key = self._get_cache_key(prompt)
        cached = self._request_cache.get(key)
        
        if cached:
            req_type = self._detect_request_type(prompt)
            timeout = self._cache_timeouts.get(req_type, self._cache_timeout)
            
            if time.time() - cached['timestamp'] < timeout:
                self._cache_stats['hits'] += 1
                logger.debug(f"[AIManager] 缓存命中，类型: {req_type}")
                return cached['response']
            else:
                del self._request_cache[key]
                self._cache_stats['evictions'] += 1
        
        self._cache_stats['misses'] += 1
        return None

    def _cache_response_smart(self, prompt: str, response: str):
        """智能缓存响应，根据请求类型设置不同超时"""
        key = self._get_cache_key(prompt)
        req_type = self._detect_request_type(prompt)
        timeout = self._cache_timeouts.get(req_type, self._cache_timeout)
        
        self._request_cache[key] = {
            'response': response,
            'timestamp': time.time(),
            'type': req_type
        }
        
        if len(self._request_cache) > 100:
            self._evict_old_cache()
        
        self._persist_cache()
        logger.debug(f"[AIManager] 已缓存响应，类型: {req_type}, 超时: {timeout}秒")

    def _evict_old_cache(self):
        """清理旧缓存条目"""
        if not self._request_cache:
            return
        
        current_time = time.time()
        keys_to_remove = []
        
        for key, value in self._request_cache.items():
            req_type = value.get('type', 'normal')
            timeout = self._cache_timeouts.get(req_type, self._cache_timeout)
            
            if current_time - value['timestamp'] > timeout:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._request_cache[key]
            self._cache_stats['evictions'] += 1
        
        if keys_to_remove:
            logger.debug(f"[AIManager] 清理了 {len(keys_to_remove)} 个过期缓存")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._cache_stats['hits'] + self._cache_stats['misses']
        hit_rate = self._cache_stats['hits'] / total if total > 0 else 0
        
        return {
            'hits': self._cache_stats['hits'],
            'misses': self._cache_stats['misses'],
            'evictions': self._cache_stats['evictions'],
            'hit_rate': f"{hit_rate:.2%}",
            'cache_size': len(self._request_cache)
        }

    async def warmup_cache(self, common_queries: List[str]):
        """预热缓存，提前加载常用查询"""
        logger.info(f"[AIManager] 开始预热缓存，共 {len(common_queries)} 个查询")
        
        for query in common_queries:
            try:
                if not self._get_cached_response_smart(query):
                    response = await self.query_short_async(query, use_history=False)
                    self._cache_response_smart(query, response)
                    logger.debug(f"[AIManager] 预热缓存: {query[:30]}...")
            except Exception as e:
                logger.warning(f"[AIManager] 预热缓存失败: {e}")
        
        logger.info(f"[AIManager] 缓存预热完成，统计: {self.get_cache_stats()}")

    async def query_short_async(
        self,
        prompt: str,
        max_tokens: int = None,
        use_history: bool = True,
        max_retries: int = 2,
    ) -> str:
        """查询API获取简短回复（异步版本，使用统一SDK接口）"""
        if not prompt or not prompt.strip():
            return "嗯？你在说什么呢~"

        cache_key = self._make_cache_key(prompt, use_history, max_tokens)
        current_time = time.time()
        with self._cache_lock:
            cached = self._request_cache.get(cache_key)
            if cached and current_time - cached["timestamp"] < self._cache_timeout:
                response_text = cached["response"]
                if use_history:
                    self._add_to_history("assistant", response_text)
                return response_text
            elif cached:
                del self._request_cache[cache_key]

        if use_history:
            self._add_to_history("user", prompt)

        if use_history:
            full_prompt = self._build_complete_prompt(prompt)
        else:
            full_prompt = prompt

        try:
            response_text = await self._provider.call_async_api(full_prompt, max_retries)
            response_text = response_text.strip()
            if not response_text:
                raise Exception("API返回空响应")
        except Exception as e:
            logger.error(f"[AIManager] API调用失败: {e}")
            raise e

        with self._cache_lock:
            self._request_cache[cache_key] = {
                "response": response_text,
                "timestamp": time.time(),
            }
        self._persist_cache()
        if use_history:
            self._add_to_history("assistant", response_text)
        return response_text

    def query_short(
        self,
        prompt: str,
        max_tokens: int = None,
        use_history: bool = True,
        max_retries: int = 2,
    ) -> str:
        """查询API获取简短回复（同步版本，使用统一SDK接口）"""
        if not prompt or not prompt.strip():
            return "嗯？你在说什么呢~"

        cache_key = self._make_cache_key(prompt, use_history, max_tokens)
        current_time = time.time()
        with self._cache_lock:
            cached = self._request_cache.get(cache_key)
            if cached and current_time - cached["timestamp"] < self._cache_timeout:
                response_text = cached["response"]
                if use_history:
                    self._add_to_history("assistant", response_text)
                return response_text
            elif cached:
                del self._request_cache[cache_key]

        if use_history:
            self._add_to_history("user", prompt)

        if use_history:
            full_prompt = self._build_complete_prompt(prompt)
        else:
            full_prompt = prompt

        try:
            response_text = self._provider.call_api(full_prompt, max_retries)
            response_text = response_text.strip()
            if not response_text:
                raise Exception("API返回空响应")
        except Exception as e:
            logger.error(f"[AIManager] API调用失败: {e}")
            raise e

        with self._cache_lock:
            self._request_cache[cache_key] = {
                "response": response_text,
                "timestamp": time.time(),
            }
        self._persist_cache()
        if use_history:
            self._add_to_history("assistant", response_text)
        return response_text

    def query_short_stream(
        self,
        prompt: str,
        max_tokens: int = None,
        use_history: bool = True,
        max_retries: int = 2,
    ):
        """查询API获取简短回复（同步流式版本，使用统一SDK接口）"""
        if not prompt or not prompt.strip():
            yield "嗯？你在说什么呢~"
            return

        cache_key = self._make_cache_key(prompt, use_history, max_tokens)
        current_time = time.time()
        with self._cache_lock:
            cached = self._request_cache.get(cache_key)
            if cached and current_time - cached["timestamp"] < self._cache_timeout:
                response_text = cached["response"]
                if use_history:
                    self._add_to_history("assistant", response_text)
                yield response_text
                return
            elif cached:
                del self._request_cache[cache_key]

        if use_history:
            self._add_to_history("user", prompt)

        if use_history:
            full_prompt = self._build_complete_prompt(prompt)
        else:
            full_prompt = prompt

        try:
            response_text = ""
            for chunk in self._provider.call_stream_api(full_prompt, max_retries):
                response_text += chunk
                yield chunk

            with self._cache_lock:
                self._request_cache[cache_key] = {
                    "response": response_text,
                    "timestamp": time.time(),
                }
            self._persist_cache()
            if use_history:
                self._add_to_history("assistant", response_text)
        except Exception as e:
            logger.error(f"[AIManager] API调用失败: {e}")
            raise e

    async def query_short_stream_async(
        self,
        prompt: str,
        max_tokens: int = None,
        use_history: bool = True,
        max_retries: int = 2,
    ):
        """查询API获取简短回复（异步流式版本，使用统一SDK接口）"""
        if not prompt or not prompt.strip():
            yield "嗯？你在说什么呢~"
            return

        cache_key = self._make_cache_key(prompt, use_history, max_tokens)
        current_time = time.time()
        with self._cache_lock:
            cached = self._request_cache.get(cache_key)
            if cached and current_time - cached["timestamp"] < self._cache_timeout:
                response_text = cached["response"]
                if use_history:
                    self._add_to_history("assistant", response_text)
                yield response_text
                return
            elif cached:
                del self._request_cache[cache_key]

        if use_history:
            self._add_to_history("user", prompt)

        if use_history:
            full_prompt = self._build_complete_prompt(prompt)
        else:
            full_prompt = prompt

        try:
            response_text = ""
            async for chunk in self._provider.call_async_stream_api(full_prompt, max_retries):
                response_text += chunk
                yield chunk

            with self._cache_lock:
                self._request_cache[cache_key] = {
                    "response": response_text,
                    "timestamp": time.time(),
                }
            self._persist_cache()
            if use_history:
                self._add_to_history("assistant", response_text)
        except Exception as e:
            logger.error(f"[AIManager] API调用失败: {e}")
            raise e

    def _get_fallback_response(self, prompt: str) -> str:
        """获取本地回退响应"""
        return random.choice(self.FALLBACK_RESPONSES)

    def _add_to_history(self, role: str, content: str):
        """添加到对话历史"""
        with self._history_lock:
            self._conversation_history.append({"role": role, "content": content})

            max_history = 10
            if len(self._conversation_history) > max_history:
                system_msg = self._conversation_history[0]
                self._conversation_history = [system_msg] + self._conversation_history[
                    -(max_history - 1):
                ]

    def clear_conversation(self):
        """清空对话历史"""
        with self._history_lock:
            system_msg = self._conversation_history[0]
            self._conversation_history = [system_msg]
        logger.info("[AIManager] 对话历史已清空")

    def set_api_key(self, api_key: str):
        """设置API密钥"""
        self.config["api_key"] = api_key
        self._init_provider()

    def set_provider(self, provider_type: str):
        """设置AI提供商"""
        self.provider_type = provider_type
        # 更新默认模型和端点
        default_config = self.DEFAULT_CONFIGS.get(
            provider_type, self.DEFAULT_CONFIGS["openai"]
        )
        self.config.setdefault("model", default_config["model"])
        self.config.setdefault("endpoint", default_config["endpoint"])
        self._init_provider()

    def is_available(self) -> bool:
        """检查AI服务是否可用"""
        return self._is_available and not self._use_fallback

    def is_using_fallback(self) -> bool:
        """检查是否使用本地回退"""
        return self._use_fallback

    def get_status(self) -> Dict[str, Any]:
        """获取AI管理器状态"""
        with self._history_lock:
            conv_len = len(self._conversation_history) - 1

        return {
            "is_available": self.is_available(),
            "using_fallback": self.is_using_fallback(),
            "provider": self.provider_type,
            "model": self.config.get("model"),
            "endpoint": self.config.get("endpoint"),
            "temperature": self.config.get("temperature"),
            "max_tokens": self.config.get("max_tokens"),
            "conversation_length": conv_len,
            "use_proxy": self.config.get("use_proxy", False),
        }

    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            self.config[key] = value

        if "provider" in kwargs:
            new_provider = kwargs["provider"]
            default_config = self.DEFAULT_CONFIGS.get(
                new_provider, self.DEFAULT_CONFIGS["openai"]
            )
            if not kwargs.get("endpoint"):
                self.config["endpoint"] = default_config["endpoint"]
            if not kwargs.get("model"):
                self.config["model"] = default_config["model"]
            self.provider_type = new_provider

        self._init_provider()

    def get_api_key(self) -> str:
        """获取API密钥"""
        return self.config.get("api_key", "")

    def get_default_config(self, provider_type: str) -> Dict[str, Any]:
        """获取默认模型配置"""
        return self.DEFAULT_CONFIGS.get(provider_type, self.DEFAULT_CONFIGS["openai"])

    def set_idle_action_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """设置空闲动作回调函数
        
        Args:
            callback: 回调函数，无参数，无返回值
        """
        if self._provider and hasattr(self._provider, 'set_idle_action_callback'):
            self._provider.set_idle_action_callback(callback)

    @staticmethod
    def get_supported_providers() -> list:
        """获取支持的AI提供商列表"""
        return ProviderFactory.get_supported_providers()


class StreamingAIManager:
    """流式AI管理器，集成StreamingJsonParser处理流式输出"""
    
    def __init__(self, ai_manager: AIManager):
        self._ai_manager = ai_manager
        self._parser = None
    
    async def query_stream_with_parser(
        self,
        prompt: str,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        use_history: bool = True,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        使用流式解析器查询AI
        
        Args:
            prompt: 用户提示词
            on_text_chunk: text字段内容回调（实时更新）
            on_complete: 完整JSON解析完成回调
            on_error: 错误回调
            use_history: 是否使用对话历史
            max_retries: 最大重试次数
        
        Returns:
            完整的解析结果JSON
        """
        from core.streaming_json_parser import StreamingJsonParser
        
        parser = StreamingJsonParser(
            on_text_chunk=on_text_chunk,
            on_complete=on_complete,
            on_error=on_error
        )
        
        self._parser = parser
        
        try:
            async for chunk in self._ai_manager.query_short_stream_async(
                prompt,
                use_history=use_history,
                max_retries=max_retries
            ):
                parser.feed(chunk)
            
            result = parser.get_result()
            if result.is_complete and result.full_json:
                return result.full_json
            elif result.text_content:
                return {"text": result.text_content, "motion": "idle", "expression": ""}
            else:
                return {"text": "（薇薇安走神了...）", "motion": "idle", "expression": ""}
                
        except Exception as e:
            if on_error:
                on_error(str(e))
            logger.error(f"[StreamingAIManager] 流式解析失败: {e}")
            return {"text": "抱歉，我有点卡顿...", "motion": "idle", "expression": ""}
    
    def get_parser(self):
        """获取当前解析器实例"""
        return self._parser


def create_streaming_query(
    ai_manager: AIManager,
    on_text_update: Callable[[str], None],
    on_tool_call: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Callable[[str], AsyncGenerator[str, None]]:
    """
    创建流式查询函数
    
    Args:
        ai_manager: AIManager实例
        on_text_update: 文本更新回调
        on_tool_call: 工具调用回调
        on_complete: 完成回调
    
    Returns:
        流式查询函数
    """
    from core.streaming_json_parser import StreamingResponseHandler
    
    handler = StreamingResponseHandler(
        on_text_update=on_text_update,
        on_tool_call=on_tool_call,
        on_complete=on_complete
    )
    
    async def stream_query(prompt: str) -> AsyncGenerator[str, None]:
        async for text in handler._process_stream(
            ai_manager.query_short_stream_async(prompt, use_history=True)
        ):
            yield text
    
    return stream_query
