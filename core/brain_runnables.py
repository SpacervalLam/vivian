"""
Vivian Brain Runnable 架构

可组合的对话处理管道，采用 Runnable 模式。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from core.dialogue_manager import DialogueManager, History
from core.memory_manager import MemoryManager
from core.emotion_analyzer import EmotionAnalyzer
from core.prompt_builder import PromptBuilder
from core.command_handler import CommandHandler
from core.tools.tool_call_manager import ToolCallManager
from core.json_processor import JSONProcessor
from utils.environment_manager import EnvironmentManager
from core.time_stamped_memory import TimeStampedMemory, build_time_aware_system_prompt


Input = TypeVar("Input")
Output = TypeVar("Output")


class RunnableConfig:
    """Runnable 配置"""
    
    def __init__(
        self,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        callbacks: Optional[List[Any]] = None,
        max_retries: int = 3,
        timeout: float = 30.0,
        **kwargs: Any,
    ):
        self.tags = tags
        self.metadata = metadata
        self.callbacks = callbacks
        self.max_retries = max_retries
        self.timeout = timeout
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def get(self, key: str, default: Any = None) -> Any:
        if "." in key:
            parts = key.split(".")
            value = self
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                elif hasattr(value, part):
                    value = getattr(value, part)
                elif hasattr(value, "metadata") and isinstance(value.metadata, dict):
                    value = value.metadata.get(part)
                else:
                    return default
                if value is None:
                    return default
            return value if value is not None else default
        
        if hasattr(self, key):
            return getattr(self, key)
        
        if self.metadata and key in self.metadata:
            return self.metadata[key]
        
        return default


class RunnableSerializable(ABC, Generic[Input, Output]):
    """可序列化的 Runnable 基类"""
    
    @abstractmethod
    def invoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        pass
    
    @abstractmethod
    async def ainvoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        pass
    
    def stream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Iterator[Output]:
        yield self.invoke(input, config, **kwargs)
    
    async def astream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Output]:
        yield await self.ainvoke(input, config, **kwargs)
    
    def batch(
        self,
        inputs: List[Input],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> List[Output]:
        return [self.invoke(input, config, **kwargs) for input in inputs]
    
    async def abatch(
        self,
        inputs: List[Input],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> List[Output]:
        tasks = [self.ainvoke(input, config, **kwargs) for input in inputs]
        return await asyncio.gather(*tasks)


class RunnableLambda(RunnableSerializable[Input, Output]):
    """Lambda 表达式包装的 Runnable"""
    
    def __init__(self, func: Callable, afunc: Optional[Callable] = None):
        self.func = func
        self.afunc = afunc
    
    def invoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        return self.func(input)
    
    async def ainvoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        if self.afunc:
            return await self.afunc(input)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.func, input)


class RunnableSequence(RunnableSerializable[Input, Output]):
    """Runnable 序列组合"""
    
    def __init__(self, *steps: RunnableSerializable):
        self.steps = steps
    
    def invoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        result = input
        for step in self.steps:
            result = step.invoke(result, config, **kwargs)
        return result
    
    async def ainvoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        result = input
        for step in self.steps:
            result = await step.ainvoke(result, config, **kwargs)
        return result
    
    def stream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Iterator[Output]:
        result = input
        for i, step in enumerate(self.steps):
            for chunk in step.stream(result, config, **kwargs):
                result = chunk
                if i == len(self.steps) - 1:
                    yield chunk
    
    async def astream(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Output]:
        result = input
        for i, step in enumerate(self.steps):
            async for chunk in step.astream(result, config, **kwargs):
                result = chunk
                if i == len(self.steps) - 1:
                    yield chunk


class RunnableParallel(RunnableSerializable[Dict[str, Input], Dict[str, Output]]):
    """并行执行的 Runnable"""
    
    def __init__(self, steps: Dict[str, RunnableSerializable]):
        self.steps = steps
    
    def invoke(
        self,
        input: Dict[str, Input],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Dict[str, Output]:
        result = {}
        for key, step in self.steps.items():
            result[key] = step.invoke(input.get(key), config, **kwargs)
        return result
    
    async def ainvoke(
        self,
        input: Dict[str, Input],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Dict[str, Output]:
        tasks = []
        keys = []
        for key, step in self.steps.items():
            keys.append(key)
            tasks.append(step.ainvoke(input.get(key), config, **kwargs))
        
        results = await asyncio.gather(*tasks)
        return dict(zip(keys, results))


class RunnableBinding(RunnableSerializable[Input, Output]):
    """绑定配置的 Runnable"""
    
    def __init__(
        self,
        bound: RunnableSerializable,
        kwargs: Dict[str, Any],
        config: RunnableConfig,
    ):
        self.bound = bound
        self.kwargs = kwargs
        self.config = config
    
    def invoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        merged_kwargs = {**self.kwargs, **kwargs}
        merged_config = self._merge_configs(self.config, config)
        return self.bound.invoke(input, merged_config, **merged_kwargs)
    
    async def ainvoke(
        self,
        input: Input,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Output:
        merged_kwargs = {**self.kwargs, **kwargs}
        merged_config = self._merge_configs(self.config, config)
        return await self.bound.ainvoke(input, merged_config, **merged_kwargs)
    
    def _merge_configs(
        self,
        config1: RunnableConfig,
        config2: Optional[RunnableConfig],
    ) -> RunnableConfig:
        if not config2:
            return config1
        merged = RunnableConfig()
        merged.tags = config1.tags or config2.tags
        merged.metadata = config1.metadata or config2.metadata
        merged.callbacks = config1.callbacks or config2.callbacks
        merged.max_retries = config2.max_retries
        merged.timeout = config2.timeout
        return merged


def ensure_config(config: Optional[RunnableConfig] = None) -> RunnableConfig:
    """确保配置存在"""
    if config is None:
        return RunnableConfig()
    return config


def Runnable(*args, **kwargs):
    """Runnable 工厂函数"""
    if len(args) == 1 and callable(args[0]):
        return RunnableLambda(func=args[0])
    raise ValueError("Invalid arguments for Runnable")


def handle_runnable_error(func_name: str, error: Exception, state: BrainState) -> BrainState:
    """处理 Runnable 执行错误"""
    logger.error(f"[{func_name}] 执行失败: {error}", exc_info=True)
    state.error = str(error)
    state.generation_status = f"{func_name}_failed"
    return state


class BrainState(BaseModel):
    """对话处理状态"""
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    user_input: str = Field(..., description="用户输入")
    
    should_respond: bool = Field(default=True, description="是否应该响应")
    full_response: bool = Field(default=True, description="是否允许完整响应")
    topic_activeness: int = Field(default=10, description="话题活跃度")
    
    command: Optional[str] = Field(default=None, description="命令类型")
    command_args: Dict[str, Any] = Field(default_factory=dict, description="命令参数")
    is_command: bool = Field(default=False, description="是否是命令")
    command_response: Optional[Dict[str, Any]] = Field(default=None, description="命令响应")
    
    system_prompt: str = Field(default="", description="系统提示词")
    memory_text: str = Field(default="", description="记忆文本")
    history_text: str = Field(default="", description="历史文本")
    context_text: str = Field(default="", description="上下文文本")
    tools_text: str = Field(default="", description="工具文本")
    
    response_text: str = Field(default="", description="AI 响应文本")
    response_json: Optional[Dict] = Field(default=None, description="解析后的 JSON")
    tool_calls: List[Dict] = Field(default_factory=list, description="工具调用列表")
    tool_call_executed: bool = Field(default=False, description="工具调用是否已执行")
    
    text: str = Field(default="", description="最终响应文本")
    motion: str = Field(default="idle", description="动作")
    expression: str = Field(default="", description="表情")
    importance_user: float = Field(default=0.3, description="用户侧重要性")
    importance_ai: float = Field(default=0.3, description="AI 侧重要性")
    
    memory_saved: bool = Field(default=False, description="记忆是否已保存")
    
    time_stamped_memory: Optional[TimeStampedMemory] = Field(default=None, description="时间戳记忆系统实例")
    memory_vars: Dict[str, Any] = Field(default_factory=dict, description="记忆变量")
    memory_profile: Dict[str, Any] = Field(default_factory=dict, description="记忆资料")
    
    in_cooldown: bool = Field(default=False, description="是否在称呼冷却期")
    user_name: str = Field(default="Master", description="用户名")
    generation_status: str = Field(default="pending", description="生成状态")
    emotion: Optional[str] = Field(default=None, description="情感")
    duration_ms: float = Field(default=0.0, description="处理耗时（毫秒）")
    error: Optional[str] = Field(default=None, description="错误信息")


class VivianRunnable(RunnableSerializable[Input, Output], ABC):
    """Vivian 增强版 Runnable 基类"""
    
    def __init__(self, **kwargs):
        self.max_retries = kwargs.get('max_retries', 3)
        self.retry_delay = kwargs.get('retry_delay', 1.0)
        self.timeout = kwargs.get('timeout', 30.0)
        self.enable_streaming = kwargs.get('enable_streaming', True)

    @abstractmethod
    def invoke(
        self,
        input: Input,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Output:
        pass

    @abstractmethod
    async def ainvoke(
        self,
        input: Input,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Output:
        pass

    def stream(
        self,
        input: Input,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Iterator[Output]:
        if not self.enable_streaming:
            yield self.invoke(input, config, **kwargs)
            return
        yield self.invoke(input, config, **kwargs)

    async def astream(
        self,
        input: Input,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Output]:
        if not self.enable_streaming:
            yield await self.ainvoke(input, config, **kwargs)
            return
        yield await self.ainvoke(input, config, **kwargs)

    def _execute_with_retry(
        self,
        func: Callable[[], Output],
        operation_name: str,
        config: RunnableConfig | None = None
    ) -> Output:
        """带重试的执行"""
        config = ensure_config(config)
        max_retries = self.max_retries
        retry_delay = self.retry_delay

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = func()
                logger.debug(f"[{operation_name}] 执行成功")
                return result

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"[{operation_name}] 第{attempt + 1}次尝试失败: {e}，{retry_delay}s后重试")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(f"[{operation_name}] 所有重试都失败: {e}")

        raise last_error

    async def _aexecute_with_retry(
        self,
        func: Callable[[], Any],
        operation_name: str,
        config: RunnableConfig | None = None
    ) -> Output:
        """异步带重试的执行"""
        config = ensure_config(config)
        max_retries = self.max_retries
        retry_delay = self.retry_delay

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = await func()
                logger.debug(f"[{operation_name}] 异步执行成功")
                return result

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"[{operation_name}] 第{attempt + 1}次异步尝试失败: {e}，{retry_delay}s后重试")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    logger.error(f"[{operation_name}] 所有异步重试都失败: {e}")

        raise last_error


class TopicDetectionRunnable(VivianRunnable[Union[str, Dict], BrainState]):
    """话题终结检测"""
    
    def __init__(self, dialogue_manager, **kwargs):
        super().__init__(**kwargs)
        self.dialogue_manager = dialogue_manager
    
    def invoke(
        self,
        input: Union[str, Dict],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return self._execute_with_retry(
            lambda: self._invoke_impl(input, config, **kwargs),
            "TopicDetection",
            config
        )
    
    def _invoke_impl(
        self,
        input: Union[str, Dict],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)

        user_input = input["user_input"] if isinstance(input, dict) else input

        state = BrainState(
            user_input=user_input,
            user_name=self.dialogue_manager.user_name
        )

        try:
            state.generation_status = "topic_detection_start"

            topic_decision = self.dialogue_manager.should_generate_full_response(user_input)

            if topic_decision is None:
                state.should_respond = False
                state.generation_status = "skipped_topic_ended"
                logger.info(f"[TopicDetection] 用户连续发送简短消息，跳过回复")
                return state

            state.should_respond = topic_decision is not None
            state.full_response = bool(topic_decision)

            self.dialogue_manager.update_topic_activeness(user_input)
            state.topic_activeness = self.dialogue_manager.get_topic_activeness()

            state.in_cooldown = self.dialogue_manager.is_in_cooldown()

            logger.debug(f"[TopicDetection] 话题活跃度: {state.topic_activeness}, 完整响应: {state.full_response}")

            state.generation_status = "topic_detection_complete"
            return state

        except Exception as e:
            return handle_runnable_error("TopicDetection", e, state)
    
    async def ainvoke(
        self,
        input: Union[str, Dict],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return await self._aexecute_with_retry(
            lambda: self._ainvoke_impl(input, config),
            "TopicDetection",
            config
        )
    
    async def _ainvoke_impl(
        self,
        input: Union[str, Dict],
        config: RunnableConfig | None = None,
    ) -> BrainState:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._invoke_impl, input, config
        )


class CommandParsingRunnable(VivianRunnable[BrainState, BrainState]):
    """命令解析"""
    
    def __init__(self, command_handler, dialogue_manager, **kwargs):
        super().__init__(**kwargs)
        self.command_handler = command_handler
        self.dialogue_manager = dialogue_manager
    
    def invoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return self._execute_with_retry(
            lambda: self._invoke_impl(input, config, **kwargs),
            "CommandParsing",
            config
        )
    
    def _invoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)
        
        if not input.should_respond:
            return input
        
        try:
            cmd, args = self.command_handler.parse(input.user_input)
            input.command = cmd
            input.command_args = args or {}
            input.is_command = cmd is not None
            
            if input.is_command:
                input.command_response = self.command_handler.handle_command(cmd, args)
                
                self.dialogue_manager.add_message("user", input.user_input)
                self.dialogue_manager.add_message("assistant", input.command_response["text"])
                
                input.generation_status = "command_executed"
                logger.debug(f"[CommandParsing] 执行命令: {cmd}")
            
        except Exception as e:
            logger.error(f"[CommandParsing] 命令解析失败: {e}")
            input.is_command = False
        
        return input
    
    async def ainvoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return await self._aexecute_with_retry(
            lambda: self._ainvoke_impl(input, config),
            "CommandParsing",
            config
        )
    
    async def _ainvoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
    ) -> BrainState:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._invoke_impl, input, config
        )


class PromptBuildingRunnable(VivianRunnable[BrainState, BrainState]):
    """提示词构建"""
    
    def __init__(self, prompt_builder, memory_manager=None, dialogue_manager=None, 
                 environment_manager=None, tool_call_manager=None, 
                 memory_filter=None, ai_manager=None, 
                 use_time_stamped_memory=True, **kwargs):
        super().__init__(**kwargs)
        self.prompt_builder = prompt_builder
        self.memory_manager = memory_manager
        self.dialogue_manager = dialogue_manager
        self.environment_manager = environment_manager
        self.tool_call_manager = tool_call_manager
        self.memory_filter = memory_filter
        self.ai_manager = ai_manager
        self.use_time_stamped_memory = use_time_stamped_memory
        self.time_stamped_memory = None
    
    def invoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return self._execute_with_retry(
            lambda: self._invoke_impl(input, config, **kwargs),
            "PromptBuilding",
            config
        )
    
    def _invoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)
        
        if not input.should_respond or input.is_command:
            return input
        
        try:
            if self.use_time_stamped_memory and not self.time_stamped_memory:
                self.time_stamped_memory = TimeStampedMemory(llm=self.ai_manager)
                logger.info("[PromptBuilding] 时间戳记忆系统已初始化")
            
            if self.use_time_stamped_memory and self.time_stamped_memory:
                input.time_stamped_memory = self.time_stamped_memory
            
            if self.use_time_stamped_memory and self.time_stamped_memory:
                input.memory_vars = self.time_stamped_memory.load_memory_variables(input.user_input)
                time_stamped_history = input.memory_vars.get("history", "")
                
                semantic_memories = []
                if self.memory_manager:
                    retrieved = self.memory_manager.retrieve_memory(input.user_input, limit=8, skip_profile_extraction=False)
                    input.memory_profile = retrieved.get("profile", {})
                    semantic_memories = retrieved.get("semantic_memory", [])
                
                memory_parts = []
                if time_stamped_history:
                    memory_parts.append(time_stamped_history)
                for mem in semantic_memories:
                    if hasattr(mem, 'content'):
                        time_str = ""
                        if hasattr(mem, 'created_at'):
                            try:
                                time_str = mem.created_at.strftime("%Y-%m-%d %H:%M") + " "
                            except:
                                pass
                        memory_parts.append(f"[记忆] {time_str}{mem.content}")
                
                input.memory_text = "\n".join(memory_parts)
            elif self.memory_filter:
                input.memory_text = self.memory_filter.get_filtered_memory_text(
                    input.user_input, k=3
                )
            elif self.memory_manager:
                retrieved = self.memory_manager.retrieve_memory(
                    input.user_input, limit=3, skip_profile_extraction=False
                )
                input.memory_text = retrieved
                input.memory_profile = retrieved.get("profile", {})
            else:
                input.memory_text = ""
            
            if self.dialogue_manager and not (self.use_time_stamped_memory and self.time_stamped_memory):
                history_msgs = self.dialogue_manager.get_history_as_messages(10)
                if history_msgs:
                    input.history_text = "\n".join([
                        f"{msg['role']}: {msg['content']}"
                        for msg in history_msgs
                    ])
                else:
                    input.history_text = ""
            
            if self.environment_manager:
                env_info = self.environment_manager.get_environment_info()
                input.context_text = str(env_info)
            else:
                input.context_text = ""
            
            if self.tool_call_manager:
                input.tools_text = self.tool_call_manager.get_system_prompt()
            else:
                input.tools_text = ""
            
            prompt_parts = {
                "memory_text": input.memory_text,
                "history_text": input.history_text,
                "context_text": input.context_text,
                "tools_text": input.tools_text,
            }
            
            input.system_prompt = self.prompt_builder.build_prompt_from_parts(
                input.user_input, prompt_parts
            )
            
            if self.use_time_stamped_memory and input.memory_vars:
                input.system_prompt = build_time_aware_system_prompt(
                    input.system_prompt, input.memory_vars
                )
            
            if input.in_cooldown:
                input.system_prompt += f"\n\n⚠️ CURRENTLY IN NAME CALL COOLDOWN - DO NOT USE '{input.user_name}' IN YOUR RESPONSE!"
            
            if not input.full_response:
                input.system_prompt += "\n\n⚠️ TOPIC ENDED - RESPOND WITH ONLY 1-3 WORDS + 1 EMOJI MAX! DO NOT ASK QUESTIONS OR CONTINUE THE TOPIC!"
            
            input.generation_status = "prompt_building_complete"
            logger.debug(f"[PromptBuilding] 提示词构建完成，长度: {len(input.system_prompt)}")
            
        except Exception as e:
            logger.error(f"[PromptBuilding] 提示词构建失败: {e}")
            input.system_prompt = self.prompt_builder.build_system_prompt()
        
        return input
    
    async def ainvoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return await self._aexecute_with_retry(
            lambda: self._ainvoke_impl(input, config),
            "PromptBuilding",
            config
        )
    
    async def _ainvoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
    ) -> BrainState:
        if not input.should_respond or input.is_command:
            return input
        
        try:
            if self.use_time_stamped_memory and not self.time_stamped_memory:
                self.time_stamped_memory = TimeStampedMemory(llm=self.ai_manager)
                logger.info("[PromptBuilding] 时间戳记忆系统已初始化")
            
            if self.use_time_stamped_memory and self.time_stamped_memory:
                input.time_stamped_memory = self.time_stamped_memory
            
            async def build_memory():
                if self.use_time_stamped_memory and self.time_stamped_memory:
                    loop = asyncio.get_event_loop()
                    
                    tasks = []
                    
                    task_memory = loop.run_in_executor(
                        None, lambda: self.time_stamped_memory.load_memory_variables(input.user_input)
                    )
                    tasks.append(task_memory)
                    
                    if self.memory_manager:
                        task_profile = loop.run_in_executor(
                            None, lambda: self.memory_manager.retrieve_memory(input.user_input, limit=8, skip_profile_extraction=False)
                        )
                        tasks.append(task_profile)
                    
                    results = await asyncio.gather(*tasks)
                    
                    input.memory_vars = results[0]
                    time_stamped_history = input.memory_vars.get("history", "")
                    
                    semantic_memories = []
                    if self.memory_manager and len(results) > 1:
                        input.memory_profile = results[1].get("profile", {})
                        semantic_memories = results[1].get("semantic_memory", [])
                    
                    memory_parts = []
                    if time_stamped_history:
                        memory_parts.append(time_stamped_history)
                    for mem in semantic_memories:
                        if hasattr(mem, 'content'):
                            time_str = ""
                            if hasattr(mem, 'created_at'):
                                try:
                                    time_str = mem.created_at.strftime("%Y-%m-%d %H:%M") + " "
                                except:
                                    pass
                            memory_parts.append(f"[记忆] {time_str}{mem.content}")
                    
                    return "\n".join(memory_parts)
                elif self.memory_filter:
                    return self.memory_filter.get_filtered_memory_text(input.user_input, k=3)
                elif self.memory_manager:
                    loop = asyncio.get_event_loop()
                    retrieved = await loop.run_in_executor(
                        None, lambda: self.memory_manager.retrieve_memory(input.user_input, limit=3, skip_profile_extraction=False)
                    )
                    input.memory_profile = retrieved.get("profile", {})
                    return retrieved
                return ""
            
            async def build_history():
                if self.dialogue_manager and not (self.use_time_stamped_memory and self.time_stamped_memory):
                    loop = asyncio.get_event_loop()
                    history_msgs = await loop.run_in_executor(
                        None, lambda: self.dialogue_manager.get_history_as_messages(5)
                    )
                    if history_msgs:
                        return "\n".join([f"{msg['role']}: {msg['content']}" for msg in history_msgs])
                return ""
            
            async def build_context():
                if self.environment_manager:
                    loop = asyncio.get_event_loop()
                    try:
                        info = await loop.run_in_executor(
                            None, lambda: self.environment_manager.get_environment_info()
                        )
                        if isinstance(info, dict):
                            return info
                        return {"text": str(info)}
                    except:
                        pass
                return {}
            
            async def build_tools():
                if self.tool_call_manager:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None, lambda: self.tool_call_manager.get_system_prompt()
                    )
                return ""
            
            tasks = [build_memory(), build_history(), build_context(), build_tools()]
            results = await asyncio.gather(*tasks)
            
            input.memory_text = results[0]
            if isinstance(input.memory_text, str):
                input.memory_text = input.memory_text[:1000]
            
            input.history_text = results[1]
            input.context_text = results[2]
            input.tools_text = results[3]
            
            prompt_parts = {
                "memory_text": input.memory_text,
                "history_text": input.history_text,
                "context_text": input.context_text,
                "tools_text": input.tools_text,
            }
            
            input.system_prompt = self.prompt_builder.build_prompt_from_parts(
                input.user_input, prompt_parts
            )
            
            if self.use_time_stamped_memory and input.memory_vars:
                input.system_prompt = build_time_aware_system_prompt(
                    input.system_prompt, input.memory_vars
                )
            
            if input.in_cooldown:
                input.system_prompt += f"\n\n⚠️ CURRENTLY IN NAME CALL COOLDOWN - DO NOT USE '{input.user_name}' IN YOUR RESPONSE!"
            
            if not input.full_response:
                input.system_prompt += "\n\n⚠️ TOPIC ENDED - RESPOND WITH ONLY 1-3 WORDS + 1 EMOJI MAX! DO NOT ASK QUESTIONS OR CONTINUE THE TOPIC!"
            
            input.generation_status = "prompt_building_complete"
            
        except Exception as e:
            logger.error(f"[PromptBuilding] 异步提示词构建失败: {e}")
            input.system_prompt = self.prompt_builder.build_system_prompt()
        
        return input


class AIResponseGenerationRunnable(VivianRunnable[BrainState, BrainState]):
    """AI 响应生成"""
    
    def __init__(self, ai_manager, tool_call_manager=None, json_processor=None, 
                 emotion_analyzer=None, **kwargs):
        super().__init__(**kwargs)
        self.ai_manager = ai_manager
        self.tool_call_manager = tool_call_manager
        self.json_processor = json_processor
        self.emotion_analyzer = emotion_analyzer
    
    async def ainvoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return await self._aexecute_with_retry(
            lambda: self._ainvoke_impl(input, config, **kwargs),
            "AIResponseGeneration",
            config
        )
    
    async def _ainvoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)
        
        if not input.should_respond or input.is_command:
            return input
        
        stream_callback = config.get("stream_callback")
        stream = config.get("stream", False)
        
        async def ai_generate_func(prompt: str) -> str:
            if hasattr(self.ai_manager, "aquery_short"):
                return await self.ai_manager.aquery_short(prompt, use_history=False)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self.ai_manager.query_short, prompt, False
                )
        
        try:
            if self.tool_call_manager:
                final_response, tool_calls = await self.tool_call_manager.execute_multi_step(
                    ai_generate_func, input.system_prompt
                )
                input.response_text = final_response
                input.tool_calls = tool_calls
                input.tool_call_executed = True
                
                if stream and stream_callback and input.response_text:
                    stream_callback(input.response_text)
                
                logger.debug(f"[AIResponse] 工具调用完成，响应长度: {len(input.response_text)}")
            else:
                raise Exception("Tool call manager not available")
            
            if self.json_processor:
                input.response_json = self.json_processor.extract_json(input.response_text)
            
            input.generation_status = "ai_generation_complete"
            
        except Exception as e:
            logger.warning(f"[AIResponse] 工具调用失败，直接推理: {e}")
            try:
                if stream and hasattr(self.ai_manager, "query_short_stream_async"):
                    async for chunk in self.ai_manager.query_short_stream_async(
                        input.system_prompt, use_history=False
                    ):
                        input.response_text += chunk
                        if stream_callback:
                            stream_callback(chunk)
                else:
                    input.response_text = await ai_generate_func(input.system_prompt)
                
                if self.json_processor:
                    input.response_json = self.json_processor.extract_json(input.response_text)
                
                input.generation_status = "ai_generation_fallback"
                
            except Exception as fallback_e:
                input.generation_status = f"error: {str(fallback_e)}"
                input.response_text = "嗯...让我想想..."
        
        return input
    
    def invoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return self._execute_with_retry(
            lambda: self._invoke_impl(input, config, **kwargs),
            "AIResponseGeneration",
            config
        )
    
    def _invoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.ainvoke(input, config, **kwargs))


class ResponseParsingRunnable(VivianRunnable[BrainState, BrainState]):
    """响应解析"""
    
    def __init__(self, emotion_analyzer=None, dialogue_manager=None, **kwargs):
        super().__init__(**kwargs)
        self.emotion_analyzer = emotion_analyzer
        self.dialogue_manager = dialogue_manager
    
    def invoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return self._execute_with_retry(
            lambda: self._invoke_impl(input, config, **kwargs),
            "ResponseParsing",
            config
        )
    
    def _invoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)
        
        if not input.should_respond or input.is_command:
            return input
        
        try:
            response_json = input.response_json
            response_text = input.response_text
            
            if isinstance(response_json, list) and len(response_json) > 0:
                first_item = response_json[0]
                if isinstance(first_item, dict) and "text" in first_item:
                    input.text = first_item.get("text", "")
                    input.motion = first_item.get("motion", "idle")
                    input.expression = first_item.get("expression", "")
                    input.importance_user = first_item.get("importance_user", 0.3)
                    input.importance_ai = first_item.get("importance_ai", 0.3)
            elif isinstance(response_json, dict) and "text" in response_json:
                input.text = response_json.get("text", "")
                input.motion = response_json.get("motion", "idle")
                input.expression = response_json.get("expression", "")
                input.importance_user = response_json.get("importance_user", 0.3)
                input.importance_ai = response_json.get("importance_ai", 0.3)
            
            if not input.tool_call_executed:
                if isinstance(response_json, list):
                    for item in response_json:
                        if isinstance(item, dict) and item.get("tool") and item.get("arguments"):
                            input.tool_calls.append(item)
                elif isinstance(response_json, dict) and response_json.get("tool") and response_json.get("arguments"):
                    input.tool_calls = [response_json]
            
            if not input.text:
                input.text = response_text.strip() or "嗯...让我想想..."
            
            if input.in_cooldown and self.dialogue_manager:
                input.text = self._remove_name(input.text, input.user_name)
            
            if not input.motion or not input.expression:
                if self.emotion_analyzer:
                    input.emotion = self.emotion_analyzer.analyze_emotion(input.text)
                    if not input.motion:
                        input.motion, _ = self.emotion_analyzer.map_emotion_to_action(input.emotion)
                    if not input.expression:
                        _, input.expression = self.emotion_analyzer.map_emotion_to_action(input.emotion)
            
            if not input.motion:
                input.motion = "idle"
            
            input.generation_status = "response_parsing_complete"
            
        except Exception as e:
            logger.error(f"[ResponseParsing] 解析失败: {e}")
            input.text = input.response_text.strip() or "嗯...让我想想..."
            input.motion = "idle"
            input.expression = ""
        
        return input
    
    async def ainvoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        return await self._aexecute_with_retry(
            lambda: self._ainvoke_impl(input, config),
            "ResponseParsing",
            config
        )
    
    async def _ainvoke_impl(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
    ) -> BrainState:
        return self._invoke_impl(input, config)
    
    def _remove_name(self, text: str, name: str) -> str:
        """移除称呼冷却期间的称呼"""
        if not name or not text:
            return text
        return text.replace(name, "").replace(",", ",").strip()


class UserMemorySavingRunnable(VivianRunnable[BrainState, BrainState]):
    """用户消息早期保存"""
    
    def __init__(self, memory_manager=None, emotion_analyzer=None, 
                 use_time_stamped_memory=True, **kwargs):
        super().__init__(**kwargs)
        self.memory_manager = memory_manager
        self.emotion_analyzer = emotion_analyzer
        self.use_time_stamped_memory = use_time_stamped_memory
    
    async def ainvoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)
        
        if not input.should_respond:
            return input
        
        try:
            if self.memory_manager:
                user_emotion = self.emotion_analyzer.analyze_emotion(input.user_input) if self.emotion_analyzer else "neutral"
                
                from core.memory_schema import MemoryNode
                
                import threading
                thread = threading.Thread(
                    target=self._save_user_memory_sync,
                    args=(input.user_input, input.importance_user, user_emotion),
                    daemon=True
                )
                thread.start()
                logger.debug("[UserMemorySaving] 用户消息已提交到后台保存")
            
        except Exception as e:
            logger.warning(f"[UserMemorySaving] 用户消息保存失败: {e}")
        
        return input
    
    def _save_user_memory_sync(self, content: str, importance: float, emotion: str):
        """后台线程同步保存"""
        try:
            memory_node = MemoryNode(
                content=content,
                role="user",
                importance=importance,
                emotion=emotion,
                source="chat"
            )
            self.memory_manager.add_memory_node(memory_node)
            logger.debug("[UserMemorySaving] 用户消息已保存到记忆系统")
        except Exception as e:
            logger.warning(f"[UserMemorySaving] 后台保存失败: {e}")
    
    def invoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.ainvoke(input, config, **kwargs))


class MemorySavingRunnable(VivianRunnable[BrainState, BrainState]):
    """记忆保存"""
    
    def __init__(self, dialogue_manager=None, memory_manager=None, 
                 emotion_analyzer=None, use_time_stamped_memory=True, **kwargs):
        super().__init__(**kwargs)
        self.dialogue_manager = dialogue_manager
        self.memory_manager = memory_manager
        self.emotion_analyzer = emotion_analyzer
        self.use_time_stamped_memory = use_time_stamped_memory
    
    async def ainvoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        config = ensure_config(config)
        
        if not input.should_respond or input.is_command:
            return input
        
        try:
            if self.use_time_stamped_memory:
                if hasattr(input, 'time_stamped_memory') and input.time_stamped_memory:
                    input.time_stamped_memory.add_message(input.user_input, "human", input.importance_user)
                    input.time_stamped_memory.add_message(input.text, "ai", input.importance_ai)
                    logger.debug("[MemorySaving] 已保存到时间戳记忆系统")
            
            if self.dialogue_manager:
                self.dialogue_manager.add_message("user", input.user_input)
                self.dialogue_manager.add_message("assistant", input.text)
                self.dialogue_manager.check_and_update_cooldown(input.text)
            
            if self.memory_manager:
                try:
                    loop = asyncio.get_event_loop()
                    
                    from core.memory_schema import MemoryNode
                    
                    if input.text.strip():
                        ai_emotion = self.emotion_analyzer.analyze_emotion(input.text) if self.emotion_analyzer else "neutral"
                        await loop.run_in_executor(
                            None,
                            lambda: self.memory_manager.add_memory_node(
                                MemoryNode(
                                    content=input.text,
                                    role="assistant",
                                    importance=min(input.importance_ai, 0.3),
                                    emotion=ai_emotion,
                                    source="chat"
                                )
                            )
                        )
                    
                except Exception as e:
                    logger.warning(f"[MemorySaving] 记忆保存失败: {e}")
            
            input.memory_saved = True
            input.generation_status = "memory_saving_complete"
            
        except Exception as e:
            logger.error(f"[MemorySaving] 保存失败: {e}")
        
        return input
    
    def invoke(
        self,
        input: BrainState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> BrainState:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.ainvoke(input, config, **kwargs))


class BrainChatChain:
    """完整对话链"""
    
    def __init__(
        self,
        dialogue_manager: DialogueManager,
        memory_manager: MemoryManager,
        prompt_builder: PromptBuilder,
        ai_manager: Any,
        emotion_analyzer: EmotionAnalyzer,
        command_handler: CommandHandler,
        tool_call_manager: Optional[ToolCallManager] = None,
        json_processor: Optional[JSONProcessor] = None,
        environment_manager: Optional[EnvironmentManager] = None,
        memory_filter: Optional[Any] = None,
        use_time_stamped_memory: bool = True,
    ):
        self.dialogue_manager = dialogue_manager
        self.memory_manager = memory_manager
        self.prompt_builder = prompt_builder
        self.ai_manager = ai_manager
        self.emotion_analyzer = emotion_analyzer
        self.command_handler = command_handler
        self.tool_call_manager = tool_call_manager
        self.json_processor = json_processor
        self.environment_manager = environment_manager
        self.memory_filter = memory_filter
        self.use_time_stamped_memory = use_time_stamped_memory
        
        self.time_stamped_memory = None
        if self.use_time_stamped_memory:
            self.time_stamped_memory = TimeStampedMemory(
                llm=self.ai_manager,
                memory_manager=self.memory_manager
            )
            logger.info("[BrainChatChain] 时间戳记忆系统已初始化（已加载已有记忆）")
        
        self._build_chain()
        
        logger.info("[BrainChatChain] 初始化完成")
    
    def _build_chain(self):
        """构建处理链"""
        topic_detection = TopicDetectionRunnable(
            dialogue_manager=self.dialogue_manager
        )
        
        command_parsing = CommandParsingRunnable(
            command_handler=self.command_handler,
            dialogue_manager=self.dialogue_manager
        )
        
        user_memory_saving = UserMemorySavingRunnable(
            memory_manager=self.memory_manager,
            emotion_analyzer=self.emotion_analyzer,
            use_time_stamped_memory=self.use_time_stamped_memory
        )
        
        prompt_building = PromptBuildingRunnable(
            prompt_builder=self.prompt_builder,
            memory_manager=self.memory_manager,
            dialogue_manager=self.dialogue_manager,
            environment_manager=self.environment_manager,
            tool_call_manager=self.tool_call_manager,
            memory_filter=self.memory_filter,
            time_stamped_memory=self.time_stamped_memory,
            ai_manager=self.ai_manager,
            use_time_stamped_memory=self.use_time_stamped_memory
        )
        
        ai_generation = AIResponseGenerationRunnable(
            ai_manager=self.ai_manager,
            tool_call_manager=self.tool_call_manager,
            json_processor=self.json_processor,
            emotion_analyzer=self.emotion_analyzer
        )
        
        response_parsing = ResponseParsingRunnable(
            emotion_analyzer=self.emotion_analyzer,
            dialogue_manager=self.dialogue_manager
        )
        
        memory_saving = MemorySavingRunnable(
            dialogue_manager=self.dialogue_manager,
            memory_manager=self.memory_manager,
            emotion_analyzer=self.emotion_analyzer,
            use_time_stamped_memory=self.use_time_stamped_memory
        )
        
        self.chain = RunnableSequence(
            topic_detection,
            command_parsing,
            user_memory_saving,
            prompt_building,
            ai_generation,
            response_parsing,
            memory_saving
        )
    
    async def ainvoke(self, user_input: str, stream: bool = False, stream_callback=None, **kwargs) -> Dict[str, Any]:
        """异步调用对话链"""
        config = RunnableConfig()
        config.metadata = {
            "stream": stream,
            "stream_callback": stream_callback
        }
        
        brain_state = await self.chain.ainvoke(user_input, config, **kwargs)
        
        return {
            "text": brain_state.text,
            "motion": brain_state.motion,
            "expression": brain_state.expression,
            "importance_user": brain_state.importance_user,
            "importance_ai": brain_state.importance_ai
        }
    
    def invoke(self, user_input: str, stream: bool = False, stream_callback=None, **kwargs) -> Dict[str, Any]:
        """同步调用对话链"""
        config = RunnableConfig()
        config.metadata = {
            "stream": stream,
            "stream_callback": stream_callback
        }
        
        brain_state = self.chain.invoke(user_input, config, **kwargs)
        
        return {
            "text": brain_state.text,
            "motion": brain_state.motion,
            "expression": brain_state.expression,
            "importance_user": brain_state.importance_user,
            "importance_ai": brain_state.importance_ai
        }


__all__ = [
    "Runnable",
    "RunnableConfig",
    "RunnableSerializable",
    "RunnableLambda",
    "RunnableSequence",
    "RunnableParallel",
    "RunnableBinding",
    "ensure_config",
    "VivianRunnable",
    "BrainState",
    "TopicDetectionRunnable",
    "CommandParsingRunnable",
    "UserMemorySavingRunnable",
    "PromptBuildingRunnable",
    "AIResponseGenerationRunnable",
    "ResponseParsingRunnable",
    "MemorySavingRunnable",
    "BrainChatChain",
]
