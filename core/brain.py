"""
Vivian AI Brain Module - Based on Runnable Architecture

This module provides the main AI brain functionality, completely refactored
to use the Runnable architecture for better modularity and maintainability.
"""

import asyncio
import json
import os
import random
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger

from core.behavior_decider import BehaviorDecider
from core.command_handler import CommandHandler
from core.computer_control import ComputerController
from core.dialogue_manager import DialogueManager, History
from core.emotion_analyzer import EmotionAnalyzer
from core.json_processor import JSONProcessor
from core.local_model import LocalModel
from core.prompt_builder import PromptBuilder

from core.types import AIResponse, AITaskType
from core.tools.v2 import (
    ToolSystem,
    PermissionContext,
    PermissionMode,
    register_builtin_tools,
    get_tool_system,
)
from utils.config_manager import config_manager
from utils.environment_manager import EnvironmentManager

from core.memory.activation_gate import ActivationGate, TopicActivation, get_activation_gate
from core.memory.heat_aware_memory import HeatAwareMemoryManager, compute_segment_heat, get_heat_aware_memory_manager
from core.memory.parallel_retriever import ParallelRetriever, RetrievalTask, get_parallel_retriever
from core.memory.smart_updater import SmartMerger, VectorDeduplicator, get_smart_updater
from core.memory.smart_topic_detector import SmartTopicDetector, get_smart_topic_detector
from core.voice_manager import VoiceManager, get_voice_manager

from core.brain_runnables import BrainChatChain

from core.callbacks import get_vivian_callback_manager

try:
    from core.memory_filter import MemoryFilter
    MEMORY_FILTER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Memory filter unavailable: {e}")
    MEMORY_FILTER_AVAILABLE = False


class Brain:
    """AI大脑类"""

    def __init__(self, ai_manager, main_window=None):
        """初始化AI大脑
        
        Args:
            ai_manager: AI管理器
            main_window: 主窗口实例
        """
        self.ai_manager = ai_manager
        self.main_window = main_window
        self.is_thinking = False
        self.memory_dir = self._get_memory_dir()
        self.memory_consolidator = None
        self._background_tasks = []
        
        self.use_new_architecture = False
        self.query_engine = None
        self.message_system = None
        self.permission_manager = None
        self.task_manager = None

        self._init_environment_manager()
        self._init_local_model()
        self._init_dialogue_manager()
        self._init_emotion_analyzer()
        self._init_tool_manager()
        self._init_memory_manager()
        self._init_computer_controller()

        self._init_command_handler()
        self._init_prompt_builder()
        self._init_memory_consolidator()
        self._init_json_processor()
        self._init_behavior_decider()
        self._init_proactive_features()
        self._init_voice_manager()
        
        self.callback_manager = get_vivian_callback_manager()
        
        self._init_memory_filter()
        
        self._init_runnable_chain()

        logger.info("AI Brain initialized with Runnable architecture")

    def _get_memory_dir(self) -> str:
        """Get memory storage directory"""
        if sys.platform == "win32":
            app_data = os.getenv("APPDATA")
            memory_dir = os.path.join(app_data, "VivianDeskpet", "memory")
        else:
            memory_dir = os.path.join(
                os.path.expanduser("~"), ".vivian_deskpet", "memory"
            )

        os.makedirs(memory_dir, exist_ok=True)
        return memory_dir

    def _init_environment_manager(self):
        """Initialize environment manager"""
        monitor_interval = config_manager.get("environment.monitor_interval", 5)
        self.environment_manager = EnvironmentManager(monitor_interval)

    def _init_local_model(self):
        """Initialize local model"""
        self.local_model_instance = LocalModel()
        self.local_model = self.local_model_instance.local_model

    def _init_dialogue_manager(self):
        """Initialize dialogue manager"""
        max_history_len = config_manager.get("dialogue.max_history_len", 10)
        self.dialogue_manager = DialogueManager(max_history_len=max_history_len)
        logger.debug(f"Dialogue manager initialized, max history: {max_history_len}")
        
        # 加载之前保存的对话历史
        try:
            self.dialogue_manager.load_history()
        except Exception as e:
            logger.error(f"加载对话历史失败: {e}")

    def _init_emotion_analyzer(self):
        """Initialize emotion analyzer"""
        self.emotion_analyzer = EmotionAnalyzer()
        logger.debug("Emotion analyzer initialized")

    def _init_tool_manager(self):
        """Initialize tool manager using V2 tool system"""
        try:
            self.tool_system = get_tool_system()
            register_builtin_tools()
            logger.debug("V2 Tool system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize V2 tool system: {e}", exc_info=True)
            self.tool_system = ToolSystem()
            register_builtin_tools()

        self._init_permission_context()

        if self.main_window:
            try:
                from core.window_control_tools import WindowControlTools
                window_tools = WindowControlTools(self.main_window)
                for tool in window_tools.get_all_tools():
                    self.tool_system.register_tool(tool)
                logger.debug("Window control tools registered")
            except Exception as e:
                logger.error(f"Failed to register window control tools: {e}")

        self._init_tool_call_manager_v2()
        logger.debug("Tool system V2 initialized")

    def _init_tool_call_manager_v2(self):
        """Initialize V2 tool call manager with permission context"""
        try:
            from core.tools.tool_call_manager_v2 import init_tool_call_manager_v2
            self.tool_call_manager = init_tool_call_manager_v2(
                tool_system=self.tool_system,
                permission_context=self.permission_context,
            )
            self.tool_call_manager.set_max_iterations(10)
            logger.debug("V2 Tool call manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize V2 tool call manager: {e}")
            from core.tools.tool_call_manager import get_tool_call_manager
            self.tool_call_manager = get_tool_call_manager()

    def _init_permission_context(self):
        """Initialize permission context for V2 tool system"""
        try:
            self.permission_context = PermissionContext(
                mode=PermissionMode.DEFAULT,
                is_bypass_permissions_mode_available=True,
                is_auto_mode_available=True,
            )
            
            from utils.config_manager import config_manager
            working_dirs = config_manager.get("security.working_directories", [])
            if working_dirs:
                for wd in working_dirs:
                    from core.tools.v2.permission import AdditionalWorkingDirectory
                    self.permission_context.additional_working_directories[wd] = AdditionalWorkingDirectory(
                        path=wd,
                        permissions={"read", "write", "delete"},
                        is_read_only=False,
                    )
            logger.debug("Permission context initialized")
        except Exception as e:
            logger.error(f"Failed to initialize permission context: {e}")
            self.permission_context = PermissionContext(mode=PermissionMode.BYPASS)

    def _init_memory_manager(self):
        """Initialize memory manager"""
        from core.memory_manager import MemoryManager
        memory_config = {
            "memory_dir": self.memory_dir,
            "token_limit": 30000,
            "token_flush_size": 3000,
            "chat_history_token_ratio": 0.7,
        }
        self.memory_manager = MemoryManager(memory_config, ai_manager=self.ai_manager)
        logger.debug("Memory manager initialized")

    def _init_computer_controller(self):
        """Initialize computer controller"""
        self.computer_controller = ComputerController()
        logger.debug("Computer controller initialized")

    def _init_behavior_decider(self):
        """Initialize behavior decider"""
        self.behavior_decider = BehaviorDecider(
            environment_manager=self.environment_manager,
            local_model=self.local_model_instance,
            json_processor=self.json_processor
        )
        logger.debug("Behavior decider initialized")

    def _init_command_handler(self):
        """Initialize command handler"""
        self.command_handler = CommandHandler(self.memory_manager)
        logger.debug("Command handler initialized")

    def _init_prompt_builder(self):
        """Initialize prompt builder"""
        self.prompt_builder = PromptBuilder(
            memory_manager=self.memory_manager,
            dialogue_manager=self.dialogue_manager,
            environment_manager=self.environment_manager,
            tool_call_manager=self.tool_call_manager,
            tool_system=self.tool_system,
        )
        logger.debug("Prompt builder initialized")
    
    def _init_memory_consolidator(self):
        """Initialize memory consolidator"""
        self.memory_consolidator = None
        logger.debug("MemoryConsolidator disabled temporarily")

    def _init_json_processor(self):
        """Initialize JSON processor"""
        self.json_processor = JSONProcessor(self.emotion_analyzer)
        logger.debug("JSON processor initialized")

    def _init_proactive_features(self):
        """Initialize proactive features"""
        self.activation_gate = get_activation_gate()
        self.activation_gate.start_decay_thread(interval=60.0)
        logger.debug("Activation gate manager initialized")

        self.heat_manager = get_heat_aware_memory_manager()
        logger.debug("Heat-aware memory manager initialized")

        self.retriever = get_parallel_retriever()
        logger.debug("Parallel retriever initialized")

        self.smart_updater = get_smart_updater()
        logger.debug("Smart updater initialized")

        from core.interruption_controller import get_interruption_controller
        self.interruption_controller = get_interruption_controller()
        logger.debug("Interruption controller initialized")

        from core.proactive_manager import init_proactive_manager
        self.proactive_manager = init_proactive_manager(self, self.main_window)
        self.proactive_manager.set_proactive_callback(self._on_proactive_manager_callback)
        logger.debug("Proactive manager initialized")

        try:
            from core.proactive import init_proactive_process
            self.proactive_process = init_proactive_process(
                memory_manager=self.memory_manager,
                ai_manager=self.ai_manager
            )
            self.proactive_process.set_callback_handler(self._on_proactive_callback)
            logger.debug("Proactive process initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize proactive process: {e}")
            self.proactive_process = None

        self.smart_topic_detector = get_smart_topic_detector(self.ai_manager)
        logger.debug("Smart topic detector initialized")

        self._register_default_topics()
        logger.debug("Proactive topics registered")

        try:
            from core.local_proactive_service import init_local_proactive_service
            self.local_proactive_service = init_local_proactive_service(
                local_model=self.local_model_instance,
                memory_manager=self.memory_manager,
                brain=self
            )
            self.local_proactive_service.set_callback(self._on_local_proactive_callback)
            self.local_proactive_service.start()
            logger.debug("Local proactive service initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize local proactive service: {e}")
            self.local_proactive_service = None

    def _on_local_proactive_callback(self, action: dict):
        """Handle local proactive callback"""
        message = action.get("message", "")
        expression = action.get("expression", "")
        if message:
            logger.info(f"[LocalProactive] Message: {message}")
            if self.main_window and hasattr(self.main_window, 'show_message_bubble'):
                self.main_window.show_message_bubble(message, duration_ms=5000)
            if expression and hasattr(self, 'expression_manager') and self.expression_manager:
                self.expression_manager.set_expression(expression, duration_ms=3000)

    def _on_proactive_callback(self, message: str, topic: dict):
        """Handle proactive callback"""
        logger.debug(f"[Proactive] Triggered: {message}")
        if self.main_window and hasattr(self.main_window, 'show_message_bubble'):
            self.main_window.show_message_bubble(message, duration_ms=5000)

    def _on_proactive_manager_callback(self, action: dict):
        """Handle proactive manager callback"""
        message = action.get("message", "")
        if message:
            logger.debug(f"[ProactiveManager] Triggered: {message}")
            if self.main_window and hasattr(self.main_window, 'show_message_bubble'):
                self.main_window.show_message_bubble(message, duration_ms=5000)
    
    def reload_proactive_config(self):
        """Reload proactive config"""
        if hasattr(self, 'local_proactive_service') and self.local_proactive_service:
            self.local_proactive_service.reload_config()
            logger.debug("[Brain] Local proactive service config reloaded")

    def _init_voice_manager(self):
        """Initialize voice manager"""
        self.voice_manager = get_voice_manager()
        logger.debug(f"Voice manager initialized (ASR={self.voice_manager.is_asr_available()}, TTS={self.voice_manager.is_tts_available()})")

    def _init_memory_filter(self):
        """初始化记忆过滤器"""
        if not MEMORY_FILTER_AVAILABLE:
            self.memory_filter = None
            return
            
        try:
            self.memory_filter = MemoryFilter(self.memory_manager)
            logger.info("Memory filter initialized")
        except Exception as e:
            logger.error(f"Failed to initialize memory filter: {e}")
            self.memory_filter = None

    def _init_runnable_chain(self):
        """初始化Runnable链架构"""
        try:
            self.chat_chain = BrainChatChain(
                dialogue_manager=self.dialogue_manager,
                memory_manager=self.memory_manager,
                prompt_builder=self.prompt_builder,
                ai_manager=self.ai_manager,
                emotion_analyzer=self.emotion_analyzer,
                command_handler=self.command_handler,
                tool_call_manager=self.tool_call_manager,
                json_processor=self.json_processor,
                environment_manager=self.environment_manager,
                memory_filter=self.memory_filter,
                use_time_stamped_memory=True
            )
            logger.info("Runnable chat chain initialized")
        except Exception as e:
            logger.exception("Failed to initialize Runnable chat chain")
            self.chat_chain = None

    def _register_default_topics(self):
        """Register default proactive topics"""
        default_topics = [
            {
                "topic_id": "emotional_support",
                "keywords": ["累", "忙", "压力", "烦恼", "难过", "开心", "高兴", "累死了"],
                "threshold": 1.0,
            }
        ]

        for topic in default_topics:
            self.activation_gate.register_topic(
                topic_id=topic["topic_id"],
                threshold=topic["threshold"],
                callback=self._on_topic_activated,
                context={"keywords": topic["keywords"]},
            )

    def _on_topic_activated(self, topic_id: str, context: Dict[str, Any]):
        """Handle topic activation callback"""
        logger.debug(f"Topic '{topic_id}' activated")
        if self.main_window and hasattr(self.main_window, 'live2d_widget'):
            live2d_widget = self.main_window.live2d_widget
            if topic_id == "emotional_support":
                live2d_widget.set_expression("sad")
                live2d_widget.idle()
            elif topic_id == "travel_plan":
                live2d_widget.set_expression("curious")
                live2d_widget.idle()
            else:
                live2d_widget.set_expression("curious")

    def _update_topic_activation(self, user_input: str) -> Optional[str]:
        """Update topic activation and return gradual prompt"""
        keywords = []
        for activation in self.activation_gate.get_all_activations():
            if activation and not activation["callback_triggered"]:
                topic_keywords = activation.get("context", {}).get("keywords", [])
                keywords.extend(topic_keywords)
                if any(kw in user_input for kw in topic_keywords):
                    status = self.activation_gate.bump_topic(activation["topic_id"])
                    if status > 0:
                        new_status = self.activation_gate.get_activation_status(activation["topic_id"])
                        if new_status and new_status["progress"] > 0.2:
                            return new_status["gradual_prompt"]
        return None

    async def athink(
        self,
        user_input: str,
        stream: bool = False,
        stream_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Async thinking main method - uses Runnable architecture by default
        
        Args:
            user_input: User input text
            stream: Whether to use streaming output
            stream_callback: Streaming callback function
        
        Returns:
            Response dictionary with text, motion, expression, etc.
        """
        if hasattr(self, 'chat_chain') and self.chat_chain:
            try:
                return await self.chat_chain.ainvoke(
                    user_input,
                    stream=stream,
                    stream_callback=stream_callback
                )
            except Exception as e:
                logger.error(f"Runnable chain failed, falling back to legacy: {e}", exc_info=True)
                return await self._athink_legacy(user_input, stream, stream_callback)
        
        return await self._athink_legacy(user_input, stream, stream_callback)

    async def _athink_legacy(
        self,
        user_input: str,
        stream: bool = False,
        stream_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """遗留athink实现"""
        self.is_thinking = True
        try:
            should_respond = True
            full_response = True
            
            topic_decision = self.dialogue_manager.should_generate_full_response(user_input)
            if topic_decision is None:
                logger.info("Topic ended, skipping response")
                self.is_thinking = False
                return {"text": "", "motion": "idle", "expression": "", "importance_user": 0.1, "importance_ai": 0.1}
            should_respond = topic_decision is not None
            full_response = bool(topic_decision)
            self.dialogue_manager.update_topic_activeness(user_input)
            logger.debug(f"Topic activeness: {self.dialogue_manager.get_topic_activeness()}")

            gradual_prompt_task = asyncio.create_task(self._async_update_topic_activation(user_input))
            cmd_parse_task = asyncio.create_task(self._async_parse_command(user_input))
            prompt_parts_task = asyncio.create_task(self._async_build_prompt_parts(user_input))

            cmd, args = await cmd_parse_task
            if cmd:
                response_data = self.command_handler.handle_command(cmd, args)
                self.dialogue_manager.add_message("user", user_input)
                self.dialogue_manager.add_message("assistant", response_data["text"])
                return response_data

            gradual_prompt = await gradual_prompt_task
            prompt_parts = await prompt_parts_task

            logger.debug("Using cloud model prompt")
            system_prompt = self.prompt_builder.build_prompt_from_parts(user_input, prompt_parts)
            
            if self.dialogue_manager.is_in_cooldown():
                user_name = self.dialogue_manager.user_name
                system_prompt += f"\n\n⚠️ CURRENTLY IN NAME CALL COOLDOWN - DO NOT USE '{user_name}' IN YOUR RESPONSE!"
            if not full_response:
                system_prompt += "\n\n⚠️ TOPIC ENDED - RESPOND WITH ONLY 1-3 WORDS + 1 EMOJI MAX! DO NOT ASK QUESTIONS OR CONTINUE THE TOPIC!"

            async def ai_generate_func(prompt: str) -> str:
                if hasattr(self.ai_manager, "aquery_short"):
                    return await self.ai_manager.aquery_short(prompt, use_history=False)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, self.ai_manager.query_short, prompt, False)

            response_text = ""
            tool_calls_performed = []
            tool_call_executed = False

            try:
                if self.tool_call_manager:
                    final_response, tool_calls = await self.tool_call_manager.execute_multi_step(
                        ai_generate_func, system_prompt
                    )
                    response_text = final_response
                    tool_calls_performed = tool_calls
                    tool_call_executed = True
                    
                    if stream and stream_callback and response_text:
                        self._has_streamed_content = True
                        stream_callback(response_text)
                        logger.info(f"Quick streaming response: {len(response_text)} chars")
                else:
                    raise Exception("Tool call manager not initialized")
            except Exception as e:
                logger.warning(f"Tool calls failed, direct inference: {e}")
                if stream:
                    if hasattr(self.ai_manager, "query_short_stream_async"):
                        async for chunk in self.ai_manager.query_short_stream_async(system_prompt, use_history=False):
                            response_text += chunk
                            if stream_callback:
                                stream_callback(chunk)
                    else:
                        for chunk in self.ai_manager.query_short_stream(system_prompt, use_history=False):
                            response_text += chunk
                            if stream_callback:
                                stream_callback(chunk)
                else:
                    if hasattr(self.ai_manager, "aquery_short"):
                        response_text = await self.ai_manager.aquery_short(system_prompt, use_history=False)
                    else:
                        loop = asyncio.get_event_loop()
                        response_text = await loop.run_in_executor(
                            None, self.ai_manager.query_short, system_prompt, False
                        )

            response_json = self.json_processor.extract_json(response_text)

            text = ""
            motion = "idle"
            expression = ""
            importance_user = 0.3
            importance_ai = 0.3
            
            if isinstance(response_json, list) and len(response_json) > 0:
                first_item = response_json[0]
                if isinstance(first_item, dict) and "text" in first_item:
                    text = first_item.get("text", "")
                    motion = first_item.get("motion", "idle")
                    expression = first_item.get("expression", "")
                    importance_user = first_item.get("importance_user", 0.3)
                    importance_ai = first_item.get("importance_ai", 0.3)
            elif isinstance(response_json, dict) and "text" in response_json:
                text = response_json.get("text", "")
                motion = response_json.get("motion", "idle")
                expression = response_json.get("expression", "")
                importance_user = response_json.get("importance_user", 0.3)
                importance_ai = response_json.get("importance_ai", 0.3)

            if not text:
                text = response_text.strip() or "嗯...让我想想..."

            if gradual_prompt and not text.startswith(gradual_prompt):
                text = f"{gradual_prompt} {text}"

            if not motion or not expression:
                emotion = self.emotion_analyzer.analyze_emotion(text)
                if not motion:
                    motion, _ = self.emotion_analyzer.map_emotion_to_action(emotion)
                if not expression:
                    _, expression = self.emotion_analyzer.map_emotion_to_action(emotion)

            await self._memorize_async(user_input, text, "chat", importance_user, importance_ai)
            self.dialogue_manager.add_message("user", user_input)
            self.dialogue_manager.add_message("assistant", text)

            self.dialogue_manager.check_and_update_cooldown(text)

            return {
                "text": text,
                "motion": motion,
                "expression": expression,
                "importance_user": importance_user,
                "importance_ai": importance_ai,
            }
        except Exception as e:
            logger.error(f"Thinking failed: {e}", exc_info=True)
            return {"text": "我掉线了...", "motion": "idle", "expression": "angry", "importance_user": 0.1, "importance_ai": 0.1}
        finally:
            self.is_thinking = False

    async def _async_update_topic_activation(self, user_input: str) -> Optional[str]:
        """Async update topic activation"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._update_topic_activation, user_input)

    async def _async_parse_command(self, user_input: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Async command parsing"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.command_handler.parse, user_input)

    async def _async_build_prompt_parts(self, user_input: str) -> Dict[str, Any]:
        """Async build prompt parts"""
        memory_task = asyncio.create_task(self._async_retrieve_memory(user_input))
        history_task = asyncio.create_task(self._async_get_history())
        context_task = asyncio.create_task(self._async_get_context())
        tools_task = asyncio.create_task(self._async_get_tools_text())

        memory_text = await memory_task
        history_text = await history_task
        context_text = await context_task
        tools_text = await tools_task

        return {
            "memory_text": memory_text,
            "history_text": history_text,
            "context_text": context_text,
            "tools_text": tools_text,
        }

    async def _async_retrieve_memory(self, user_input: str) -> str:
        """Async retrieve memory"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.memory_manager.retrieve_memory(user_input, limit=3, skip_profile_extraction=True))

    async def _async_get_history(self) -> str:
        """Async get history"""
        if not self.dialogue_manager:
            return ""
        loop = asyncio.get_event_loop()
        history_msgs = await loop.run_in_executor(None, lambda: self.dialogue_manager.get_history_as_messages(10))
        if history_msgs:
            return "\n".join([f"{msg['role']}: {msg['content']}" for msg in history_msgs])
        return ""

    async def _async_get_context(self) -> Dict[str, str]:
        """Async get context"""
        from datetime import datetime
        
        if not self.environment_manager:
            return {"time": "", "active_app": "", "season": ""}
        
        loop = asyncio.get_event_loop()
        env_info = await loop.run_in_executor(None, lambda: self.environment_manager.get_environment_info())
        
        month = datetime.now().month
        if month in [3, 4, 5]:
            season = "Spring"
        elif month in [6, 7, 8]:
            season = "Summer"
        elif month in [9, 10, 11]:
            season = "Autumn"
        else:
            season = "Winter"
        
        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"),
            "active_app": env_info.get("current_window", "Unknown"),
            "season": season,
        }

    async def _async_get_tools_text(self) -> str:
        """Async get tools text"""
        if not self.tool_call_manager:
            return ""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.tool_call_manager.get_system_prompt())

    async def _memorize_async(self, user_input: str, ai_response: str, source: str, importance_user: float = 0.3, importance_ai: float = 0.1):
        """Async memorize conversation"""
        try:
            loop = asyncio.get_event_loop()
            from core.memory_schema import MemoryNode

            user_emotion = self.emotion_analyzer.analyze_emotion(user_input)
            user_keywords = self.emotion_analyzer.extract_keywords(user_input)
            user_node = MemoryNode(
                content=user_input,
                role="user",
                importance=importance_user,
                emotion=user_emotion,
                keywords=user_keywords,
                source=source,
            )
            await loop.run_in_executor(None, self.memory_manager.add_memory_node, user_node)

            if ai_response.strip():
                ai_emotion = self.emotion_analyzer.analyze_emotion(ai_response)
                ai_keywords = self.emotion_analyzer.extract_keywords(ai_response)
                assistant_node = MemoryNode(
                    content=ai_response,
                    role="assistant",
                    importance=min(importance_ai, 0.3),
                    emotion=ai_emotion,
                    keywords=ai_keywords,
                    source=source,
                )
                await loop.run_in_executor(None, self.memory_manager.add_memory_node, assistant_node)

        except Exception as e:
            logger.warning(f"Memory saving failed: {e}")

    async def _background_extract_user_profile(self):
        """Background extract user profile"""
        try:
            await asyncio.sleep(2)
            all_memories = self.memory_manager.list_short_term_memories() + self.memory_manager.list_long_term_memories()
            if len(all_memories) >= 5:
                retrieved = self.memory_manager.retrieve_memory("", limit=0)
                profile = retrieved.get("profile", {})
                if profile and profile.get("name") and profile.get("name") != "主人":
                    logger.debug(f"Background extracted user name: {profile.get('name')}")
        except Exception as e:
            logger.warning(f"Background profile extraction failed: {e}")

    def _register_default_tools(self):
        """Register default tools"""
        pass

    def make_decision(self) -> Dict[str, Any]:
        """Make behavior decision"""
        return self.behavior_decider.make_decision()

    def get_memory_summary(self) -> str:
        """Get memory summary"""
        return self.memory_manager.get_memory_summary()

    def clear_memory(self):
        """Clear memory"""
        self.memory_manager.clear_all_memories()

    def save_memory(self):
        """Save memory"""
        self.memory_manager.save_memory()

    def load_memory(self):
        """Load memory"""
        self.memory_manager.load_memory()


__all__ = ["Brain"]