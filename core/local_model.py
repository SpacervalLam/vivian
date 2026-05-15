import asyncio
import os
import sys
import threading
from queue import Queue
from typing import Generator, Optional

from loguru import logger

# 本地模型支持（llama-cpp-python）
try:
    from llama_cpp import Llama

    LLAMA_AVAILABLE = True
    logger.debug("llama-cpp-python 库已安装，支持本地模型")
except ImportError:
    LLAMA_AVAILABLE = False
    logger.debug("llama-cpp-python 库未安装，将仅使用云端模型")

from utils.config_manager import config_manager


class LocalModel:
    """本地模型管理类"""

    DEFAULT_CONFIG = {
        "model_path": "G:\\vivian\\model\\qwen2.5-1.5b-instruct-q8_0.gguf",
        "n_ctx": 2048,
        "n_threads": 4,
        "n_gpu_layers": 0,
    }

    def __init__(self):
        """初始化本地模型"""
        self.local_model = None
        self._init_local_model()

    def _init_local_model(self):
        """初始化本地模型"""
        logger.debug("开始初始化本地模型")
        if not LLAMA_AVAILABLE:
            logger.info("llama-cpp-python库未安装，跳过本地模型初始化")
            return

        try:
            model_path = config_manager.get(
                "ai.local_model_path", self.DEFAULT_CONFIG["model_path"]
            )
            if not model_path:
                logger.warning("本地模型路径未配置，跳过本地模型初始化")
                return

            logger.debug(f"本地模型路径: {model_path}")
            if os.path.exists(model_path):
                try:
                    logger.debug("开始加载本地模型")
                    n_ctx = config_manager.get(
                        "ai.local_model_n_ctx", self.DEFAULT_CONFIG["n_ctx"]
                    )
                    n_threads = config_manager.get(
                        "ai.local_model_n_threads", self.DEFAULT_CONFIG["n_threads"]
                    )
                    n_gpu_layers = config_manager.get(
                        "ai.local_model_n_gpu_layers",
                        self.DEFAULT_CONFIG["n_gpu_layers"],
                    )

                    self.local_model = Llama(
                        model_path=model_path,
                        n_ctx=n_ctx,
                        n_threads=n_threads,
                        n_gpu_layers=n_gpu_layers,
                        verbose=False,
                    )
                    logger.info(f"本地模型已成功加载: {model_path}")
                except Exception as e:
                    logger.error(f"加载本地模型失败: {e}", exc_info=True)
                    self.local_model = None
                    logger.info("本地模型加载失败，将使用云端模型或回退响应")
            else:
                logger.warning(f"本地模型文件不存在: {model_path}")
                logger.info(
                    f"请确保模型文件存在，或在配置中修改ai.local_model_path指向正确的模型文件"
                )
        except Exception as e:
            logger.error(f"初始化本地模型失败: {e}", exc_info=True)
            self.local_model = None
            logger.debug("本地模型初始化失败，将使用云端模型或回退响应")

    def inference(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7, stop: list = None) -> str:
        """本地模型推理"""
        if not self.local_model:
            return ""

        if stop is None:
            # 移除 "\n" 以允许模型生成多行输出
            # 对于本地小模型，需要更宽松的stop条件
            stop = ["user:", "assistant:", "##", "###"]

        try:
            response = self.local_model(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                echo=False,
            )
            return response["choices"][0]["text"].strip()
        except Exception as e:
            logger.error(f"本地模型推理失败: {e}")
            return ""

    def inference_stream(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7, stop: list = None) -> Generator[str, None, None]:
        """本地模型流式推理"""
        if not self.local_model:
            yield ""
            return

        if stop is None:
            stop = ["\n", "user:", "assistant:"]

        try:
            # 流式调用本地模型
            response = self.local_model(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                echo=False,
                stream=True,  # 启用流式输出
            )

            # 处理流式响应
            for chunk in response:
                if "choices" in chunk:
                    text_chunk = chunk["choices"][0]["text"]
                    if text_chunk:
                        yield text_chunk
        except Exception as e:
            logger.error(f"本地模型流式推理失败: {e}")
            yield ""

    async def ainference(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7, stop: list = None) -> str:
        """异步本地模型推理"""
        logger.debug(f"[LocalModel] 发送给AI的完整Prompt:\n{prompt}")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.inference, prompt, max_tokens, temperature, stop)

    async def ainference_stream(self, prompt: str, max_tokens: int = 128, temperature: float = 0.7, stop: list = None) -> Generator[str, None, None]:
        """异步本地模型流式推理"""
        logger.debug(f"[LocalModel] 发送给AI的完整Prompt:\n{prompt}")
        loop = asyncio.get_event_loop()
        # 创建一个队列来存储流式输出
        q = Queue()

        def stream_worker():
            try:
                for chunk in self.inference_stream(prompt, max_tokens, temperature, stop):
                    q.put(chunk)
            except Exception as e:
                logger.error(f"本地模型流式推理工作线程失败: {e}")
            finally:
                q.put(None)  # 结束标志

        # 启动工作线程
        loop.run_in_executor(None, stream_worker)

        # 从队列中获取结果
        while True:
            chunk = await loop.run_in_executor(None, q.get)
            if chunk is None:
                break
            yield chunk
