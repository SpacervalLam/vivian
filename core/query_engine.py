import asyncio
import json
import uuid
from typing import List, Dict, Any, Optional, AsyncGenerator, Callable
from datetime import datetime
from loguru import logger

from utils.config_manager import config_manager
from utils.i18n import translator

class MessageType:
    ASSISTANT = "assistant"
    USER = "user"
    SYSTEM = "system"
    PROGRESS = "progress"
    ATTACHMENT = "attachment"
    STREAM_EVENT = "stream_event"

class Message:
    def __init__(self, type: str, **kwargs):
        self.type = type
        self.uuid = kwargs.get('uuid', str(uuid.uuid4()))
        self.timestamp = kwargs.get('timestamp', datetime.now().isoformat())
        self.content = kwargs.get('content', '')
        self.message = kwargs.get('message', {})
        self.subtype = kwargs.get('subtype', None)
        self.compactMetadata = kwargs.get('compactMetadata', None)
        self.isMeta = kwargs.get('isMeta', False)
        self.isVisibleInTranscriptOnly = kwargs.get('isVisibleInTranscriptOnly', False)
        self.toolUseResult = kwargs.get('toolUseResult', None)
        self.isCompactSummary = kwargs.get('isCompactSummary', False)

class QueryEngineConfig:
    def __init__(self):
        self.cwd = config_manager.get("base.cwd", ".")
        self.tools = []
        self.commands = []
        self.mcp_clients = []
        self.agents = []
        self.can_use_tool = None
        self.get_app_state = None
        self.set_app_state = None
        self.initial_messages = []
        self.read_file_cache = {}
        self.custom_system_prompt = None
        self.append_system_prompt = None
        self.user_specified_model = None
        self.fallback_model = None
        self.max_turns = 10
        self.max_budget_usd = None
        self.json_schema = None
        self.verbose = False
        self.replay_user_messages = False
        self.include_partial_messages = False
        self.memory_manager = None
        self.dialogue_manager = None
        self.ai_manager = None

class QueryEngine:
    def __init__(self, config: QueryEngineConfig):
        self.config = config
        self.mutable_messages = config.initial_messages.copy()
        self.abort_controller = asyncio.Event()
        self.permission_denials = []
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self.has_handled_orphaned_permission = False
        self.read_file_state = config.read_file_cache.copy()
        self.discovered_skill_names = set()
        
    async def submit_message(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        options = options or {}
        verbose = self.config.verbose

        if verbose:
            logger.debug(f"[QueryEngine] Starting submit_message with prompt: {prompt[:50]}...")
        
        # 处理用户输入
        processed_input = await self._process_user_input(prompt)
        self.mutable_messages.extend(processed_input.get('messages', []))
        
        should_query = processed_input.get('should_query', True)
        if not should_query:
            yield self._build_result(
                success=True,
                result=processed_input.get('result_text', ''),
                num_turns=1
            )
            return
        
        # 构建提示词
        system_prompt = await self._build_system_prompt(prompt)

        if verbose:
            logger.debug(f"[QueryEngine] System prompt built, length: {len(system_prompt)}")
        
        # 执行查询循环
        async for message in self._execute_query_loop(system_prompt, prompt):
            yield message
            
        # 返回最终结果
        final_result = self._extract_final_result()
        yield final_result
        
    async def _process_user_input(self, prompt: str) -> Dict[str, Any]:
        """处理用户输入，包括命令解析"""
        result = {
            'messages': [
                Message(
                    type=MessageType.USER,
                    content=prompt,
                    message={'role': 'user', 'content': prompt}
                )
            ],
            'should_query': True,
            'allowed_tools': [],
            'model': None,
            'result_text': None
        }
        return result
    
    async def _build_system_prompt(self, user_input: str = "") -> str:
        """构建完整系统提示词，使用注入的组件"""
        from core.prompt_builder import PromptBuilder

        memory_manager = self.config.memory_manager
        dialogue_manager = self.config.dialogue_manager
        environment_manager = None

        prompt_builder = PromptBuilder(
            memory_manager=memory_manager,
            dialogue_manager=dialogue_manager,
            environment_manager=environment_manager,
            tool_call_manager=None
        )

        # 直接使用完整的 build_prompt 方法
        full_prompt = prompt_builder.build_prompt(user_input)
        
        return full_prompt
    
    async def _execute_query_loop(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行查询循环"""
        # 用户对话始终使用云端模型，ai.enable_local_proactive 只用于本地 LLM 主动交互服务
        use_local_model = False
        
        if use_local_model:
            async for message in self._execute_local_model(system_prompt, user_prompt):
                yield message
        else:
            async for message in self._execute_remote_model(system_prompt, user_prompt):
                yield message
    
    async def _execute_local_model(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行本地模型推理"""
        from core.local_model import LocalModel
        
        local_model = LocalModel()
        prompt = f"{system_prompt}\n\n## User Input\n{user_prompt}"
        
        try:
            response = await local_model.ainference(prompt)
            
            message = Message(
                type=MessageType.ASSISTANT,
                content=response,
                message={'role': 'assistant', 'content': response}
            )
            self.mutable_messages.append(message)
            
            yield {
                'type': 'assistant',
                'message': message.message,
                'uuid': message.uuid,
                'timestamp': message.timestamp
            }
        except Exception as e:
            logger.error(f"[QueryEngine] Local model error: {e}")
            yield {
                'type': 'system',
                'subtype': 'error',
                'error': str(e)
            }

    async def _execute_remote_model(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行远程模型推理"""
        ai_manager = self.config.ai_manager
        if not ai_manager:
            from core.ai_manager import AIManager
            ai_config = config_manager.get("ai", {})
            ai_manager = AIManager(ai_config)

        prompt = f"{system_prompt}\n\n## User Input\n{user_prompt}"

        try:
            # 使用流式异步接口逐块接收模型输出并实时 yield
            response_text = ""
            async for chunk in ai_manager.query_short_stream_async(prompt, use_history=False):
                # 每个 chunk 都作为流事件传出，UI 层可据此逐步渲染
                ts = datetime.now().isoformat()
                yield {
                    'type': MessageType.STREAM_EVENT,
                    'chunk': chunk,
                    'timestamp': ts,
                }
                response_text += chunk

                # 中断检测（如果外部设置了中断信号）
                if hasattr(self, 'abort_controller') and getattr(self, 'abort_controller'):
                    try:
                        if self.abort_controller.is_set():
                            # 发出中断提示并结束流
                            yield {'type': 'system', 'subtype': 'interrupted', 'timestamp': datetime.now().isoformat()}
                            return
                    except Exception:
                        pass

            # 流结束后，将完整回复写入消息历史并返回最终消息
            message = Message(
                type=MessageType.ASSISTANT,
                content=response_text,
                message={'role': 'assistant', 'content': response_text}
            )
            self.mutable_messages.append(message)

            yield {
                'type': 'assistant',
                'message': message.message,
                'uuid': message.uuid,
                'timestamp': message.timestamp
            }
        except Exception as e:
            logger.error(f"[QueryEngine] Remote model error: {e}")
            yield {
                'type': 'system',
                'subtype': 'error',
                'error': str(e)
            }

    def _extract_final_result(self) -> Dict[str, Any]:
        """提取最终结果"""
        last_message = None
        for msg in reversed(self.mutable_messages):
            if msg.type in [MessageType.ASSISTANT, MessageType.USER]:
                last_message = msg
                break
        
        result_text = ""
        if last_message and last_message.type == MessageType.ASSISTANT:
            result_text = last_message.content or ""
        
        return self._build_result(
            success=True,
            result=result_text,
            num_turns=len([m for m in self.mutable_messages if m.type == MessageType.USER])
        )
    
    def _build_result(
        self,
        success: bool,
        result: str = "",
        num_turns: int = 1,
        error: str = None
    ) -> Dict[str, Any]:
        """构建结果字典"""
        return {
            'type': 'result',
            'subtype': 'success' if success else 'error',
            'is_error': not success,
            'duration_ms': 0,
            'duration_api_ms': 0,
            'num_turns': num_turns,
            'result': result,
            'stop_reason': None,
            'session_id': str(uuid.uuid4()),
            'total_cost_usd': 0,
            'usage': self.total_usage,
            'modelUsage': {},
            'permission_denials': self.permission_denials,
            'uuid': str(uuid.uuid4()),
            'errors': [error] if error else []
        }
    
    def interrupt(self):
        """中断当前查询"""
        self.abort_controller.set()
    
    def get_messages(self) -> List[Message]:
        """获取所有消息"""
        return self.mutable_messages.copy()
    
    def get_read_file_state(self) -> Dict[str, Any]:
        """获取文件读取状态"""
        return self.read_file_state.copy()

async def ask(
    prompt: str,
    **kwargs
) -> AsyncGenerator[Dict[str, Any], None]:
    """便捷函数：发送单个提示并返回响应"""
    config = QueryEngineConfig()
    
    # 应用关键字参数
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    engine = QueryEngine(config)
    
    try:
        async for message in engine.submit_message(prompt):
            yield message
    finally:
        pass
