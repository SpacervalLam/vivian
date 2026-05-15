"""
本地LLM主动交互服务 (LocalProactiveService)

核心功能：
1. 基于本地小型LLM生成主动交互内容
2. 整点问候、调戏嗔怪、长时间未交互问候
3. 结合记忆库生成相关性和连贯性内容
4. 交互场景判断和状态检测
5. 费用控制：主动交互必须使用本地LLM

设计原则：
- 所有本地LLM调用生成可解析的JSON格式输出
- 提示词简洁明了，适应本地模型较弱的处理能力
- 严格区分本地LLM与云端LLM的使用场景
"""

import asyncio
import json
import random
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QTimer, QThread, pyqtSignal

from loguru import logger

from core.interruption_controller import (
    UserActivityLevel,
    get_interruption_controller
)
from utils.config_manager import config_manager


class ProactiveTriggerType(Enum):
    """主动交互触发类型"""
    HOURLY_GREETING = "hourly_greeting"      # 整点问候
    TEASING_RESPONSE = "teasing_response"    # 调戏嗔怪
    IDLE_GREETING = "idle_greeting"          # 长时间未交互问候


class InteractionContext:
    """交互上下文"""
    
    def __init__(self):
        self.is_user_interacting = False
        self.is_dragging = False
        self.drag_start_time = 0
        self.drag_distance = 0
        self.last_user_input_time = time.time()
        self.last_ai_response_time = 0
        self.pending_output = None
        self.output_ready_time = 0


class ProactiveWorker(QThread):
    """后台工作线程，用于处理本地LLM调用"""
    
    result_ready = pyqtSignal(dict, dict)  # (trigger_info, result)
    
    def __init__(self, local_model, memory_manager, trigger_type, context):
        super().__init__()
        self.local_model = local_model
        self.memory_manager = memory_manager
        self.trigger_type = trigger_type
        self.context = context
        self._cancelled = False
        
    def cancel(self):
        self._cancelled = True
        
    def run(self):
        """在后台线程中运行"""
        try:
            if self._cancelled:
                return
                
            result = self._generate_proactive_content_sync()
            
            if result and not self._cancelled:
                self.result_ready.emit(
                    {"type": self.trigger_type.value, "context": self.context},
                    result
                )
                
        except Exception as e:
            logger.error(f"[ProactiveWorker] 后台任务失败: {e}")
            
    def _generate_proactive_content_sync(self):
        """同步版本的内容生成"""
        if not self.local_model:
            return self._fallback_response()
            
        try:
            prompt = self._build_prompt()
            
            # 直接调用同步推理
            response = self.local_model.inference(
                prompt=prompt,
                max_tokens=100,
                temperature=0.8,
                stop=["\n\n", "user:", "assistant:", "##"]
            )
            
            if not response:
                return self._fallback_response()
                
            result = self._parse_response(response)
            
            if not result or not result.get("text"):
                return self._fallback_response()
                
            return result
            
        except Exception as e:
            logger.error(f"[ProactiveWorker] 本地LLM推理失败: {e}")
            return self._fallback_response()
            
    def _fallback_response(self):
        """回退响应"""
        if self.trigger_type == ProactiveTriggerType.HOURLY_GREETING:
            hour = self.context.get("hour", datetime.now().hour)
            greetings = self._get_hourly_greetings(hour)
            return {"text": random.choice(greetings), "expression": "shy"}
            
        elif self.trigger_type == ProactiveTriggerType.TEASING_RESPONSE:
            responses = [
                "喂喂喂，别晃我啦~",
                "晕了晕了，快停下！",
                "你再晃我就生气了哦！",
                "好晕好晕，让我歇会儿~",
                "主人好坏，总欺负我~",
            ]
            return {"text": random.choice(responses), "expression": "angry"}
            
        elif self.trigger_type == ProactiveTriggerType.IDLE_GREETING:
            idle_minutes = self.context.get("idle_seconds", 0) // 60
            responses = [
                f"主人，你都{idle_minutes}分钟没理我了...",
                "在忙什么呢？好无聊呀~",
                "主人还在吗？想你了~",
                "有人吗？没人我就自己玩了哦~",
            ]
            return {"text": random.choice(responses), "expression": ""}
            
        return {"text": "嗯~", "expression": ""}
        
    def _build_prompt(self):
        """构建提示词"""
        memory_hints = self._get_memory_hints()
        time_context = self._get_time_context()
        
        base_prompt = """你是薇薇安，一个可爱的桌面宠物。
性格：活泼、傲娇、温暖
说话风格：简短自然，像朋友聊天

输出JSON格式：{"text": "回复内容", "expression": "表情"}
expression可选：shy, angry, cry, panic, eye_roll, umbrella_close
回复控制在30字以内。"""

        if self.trigger_type == ProactiveTriggerType.HOURLY_GREETING:
            hour = self.context.get("hour", datetime.now().hour)
            return f"""{base_prompt}

场景：整点问候
时间：{hour}点
记忆：{memory_hints[:100] if memory_hints else '无'}

生成一句自然的问候，可以关心用户状态或聊聊时间。
JSON输出："""

        elif self.trigger_type == ProactiveTriggerType.TEASING_RESPONSE:
            distance = self.context.get("drag_distance", 0)
            duration = self.context.get("drag_duration", 0)
            return f"""{base_prompt}

场景：用户在拖动你玩（调戏）
拖动距离：{distance}像素
持续时间：{duration}秒
记忆：{memory_hints[:100] if memory_hints else '无'}

生成一句嗔怪的话，可以撒娇或假装生气。
JSON输出："""

        elif self.trigger_type == ProactiveTriggerType.IDLE_GREETING:
            idle_seconds = self.context.get("idle_seconds", 0)
            idle_minutes = idle_seconds // 60
            return f"""{base_prompt}

场景：用户{idle_minutes}分钟没理你了
时间：{time_context}
记忆：{memory_hints[:100] if memory_hints else '无'}

生成一句主动问候，可以表达想念或好奇。
JSON输出："""

        else:
            return f"""{base_prompt}

场景：主动问候
时间：{time_context}
记忆：{memory_hints[:100] if memory_hints else '无'}

生成一句自然的问候。
JSON输出："""
            
    def _get_memory_hints(self):
        """获取记忆提示"""
        if not self.memory_manager:
            return ""
            
        try:
            memories = self.memory_manager.list_short_term_memories(limit=3)
            if memories:
                hints = []
                for m in memories[:3]:
                    content = m.content if hasattr(m, 'content') else str(m)
                    hints.append(content[:50])
                return " | ".join(hints)
        except Exception as e:
            logger.debug(f"[ProactiveWorker] 获取记忆失败: {e}")
            
        return ""
        
    def _get_time_context(self):
        """获取时间上下文"""
        now = datetime.now()
        hour = now.hour
        
        if 5 <= hour < 9:
            return "早上"
        elif 9 <= hour < 12:
            return "上午"
        elif 12 <= hour < 14:
            return "中午"
        elif 14 <= hour < 18:
            return "下午"
        elif 18 <= hour < 22:
            return "晚上"
        else:
            return "深夜"
            
    def _parse_response(self, response):
        """解析LLM响应"""
        try:
            response = response.strip()
            
            if response.startswith("{"):
                pass
            elif "{" in response:
                start = response.index("{")
                end = response.rindex("}") + 1 if "}" in response else len(response)
                response = response[start:end]
            else:
                return {"text": response[:50], "expression": ""}
                
            try:
                data = json.loads(response)
                logger.debug(f"[ProactiveWorker] 解析到JSON数据: {data}")
                
                if "text" in data:
                    text = str(data["text"])
                    # 检查text是否本身是JSON格式
                    if text.strip().startswith("{"):
                        logger.debug(f"[ProactiveWorker] text字段本身是JSON格式: {text[:100]}")
                        # 尝试再次解析
                        try:
                            inner_data = json.loads(text)
                            if "text" in inner_data:
                                text = str(inner_data["text"])
                        except json.JSONDecodeError:
                            pass
                    
                    # 验证表情值
                    expression = data.get("expression", "")
                    valid_expressions = ["shy", "angry", "cry", "panic", "eye_roll", "umbrella_close"]
                    if expression and expression not in valid_expressions:
                        logger.debug(f"[ProactiveWorker] 无效的表情值: {expression}，已忽略")
                        expression = ""
                    
                    return {
                        "text": text[:50],
                        "expression": expression
                    }
                else:
                    logger.debug(f"[ProactiveWorker] JSON缺少text字段: {response[:100]}")
                    return None
            except json.JSONDecodeError:
                logger.debug(f"[ProactiveWorker] JSON解析失败: {response[:100]}")
                return None
                
        except Exception as e:
            logger.debug(f"[ProactiveWorker] 解析响应失败: {e}")
            
        return None
        
    def _get_hourly_greetings(self, hour):
        """获取整点问候语"""
        if 5 <= hour < 9:
            return [
                "早上好呀~今天也要元气满满哦！",
                "早安~睡得好吗？",
                "新的一天开始啦，加油哦~",
            ]
        elif 9 <= hour < 12:
            return [
                "上午好~工作顺利吗？",
                "记得休息一下眼睛哦~",
                "要不要喝杯水？",
            ]
        elif 12 <= hour < 14:
            return [
                "中午啦~吃午饭了吗？",
                "午休时间到~要不要小憩一下？",
                "记得按时吃饭哦~",
            ]
        elif 14 <= hour < 18:
            return [
                "下午好~下午茶时间到！",
                "加油，快下班啦~",
                "今天过得怎么样？",
            ]
        elif 18 <= hour < 22:
            return [
                "晚上好~今天累不累？",
                "晚饭吃了吗？",
                "晚上有什么安排吗？",
            ]
        else:
            return [
                "这么晚还不睡呀~早点休息哦",
                "夜深了，注意身体~",
                "熬夜对身体不好哦~",
            ]


class LocalProactiveService(QObject):
    """
    本地LLM主动交互服务
    
    使用本地小型LLM生成主动交互内容，确保费用控制
    """
    
    TRIGGER_CONFIG = {
        ProactiveTriggerType.HOURLY_GREETING: {
            "min_idle_seconds": 60,
            "probability": 0.1,
            "cooldown_seconds": 600,
        },
        ProactiveTriggerType.TEASING_RESPONSE: {
            "min_drag_distance": 200,
            "min_drag_duration": 1.0,
            "probability": 0.2,
            "cooldown_seconds": 60,
        },
        ProactiveTriggerType.IDLE_GREETING: {
            "min_idle_seconds": 600,
            "probability": 0.1,
            "cooldown_seconds": 1200,
        },
    }
    
    def __init__(self, local_model, memory_manager=None, brain=None):
        super().__init__()
        self.local_model = local_model
        self.memory_manager = memory_manager
        self.brain = brain
        
        self._context = InteractionContext()
        self._last_trigger_time: Dict[ProactiveTriggerType, float] = {}
        self._callback_on_proactive: Optional[Callable] = None
        self._is_active = False
        self._output_cancelled = False
        self._current_worker: Optional[ProactiveWorker] = None
        
        self._init_config()
        
    def _init_config(self):
        """初始化配置"""
        self.enabled = config_manager.get("ai.enable_local_proactive", True)
    
    def reload_config(self):
        """重新加载配置"""
        self.enabled = config_manager.get("ai.enable_local_proactive", True)
        
    def set_callback(self, callback: Callable):
        """设置主动交互回调"""
        self._callback_on_proactive = callback
        
    def set_memory_manager(self, memory_manager):
        """设置记忆管理器"""
        self.memory_manager = memory_manager
        
    def start(self):
        """启动服务"""
        if self._is_active:
            return
            
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._periodic_check)
        self._check_timer.start(5000)
        
        self._is_active = True
        logger.info("[LocalProactiveService] 本地LLM主动交互服务已启动")
        
    def stop(self):
        """停止服务"""
        if hasattr(self, '_check_timer'):
            self._check_timer.stop()
            
        self._cancel_current_worker()
        self._is_active = False
        logger.info("[LocalProactiveService] 本地LLM主动交互服务已停止")
        
    def _periodic_check(self):
        """定期检查触发条件"""
        if not self.enabled or not self.local_model:
            return
            
        self._check_hourly_greeting()
        self._check_idle_greeting()
        
    def _can_trigger(self, trigger_type: ProactiveTriggerType) -> Tuple[bool, str]:
        """
        检查是否可以触发指定类型的主动交互
        
        Returns:
            (是否可以触发, 原因)
        """
        if not self.enabled:
            return False, "主动交互功能未启用"
            
        if not self.local_model:
            return False, "本地模型不可用"
            
        if self._context.is_user_interacting:
            return False, "用户正在交互中"
            
        readiness = get_interruption_controller().get_interruption_readiness()
        if not readiness["can_interrupt"]:
            return False, f"打扰控制器阻止: {readiness['suggested_action']}"
            
        config = self.TRIGGER_CONFIG.get(trigger_type, {})
        cooldown = config.get("cooldown_seconds", 60)
        last_time = self._last_trigger_time.get(trigger_type, 0)
        
        if time.time() - last_time < cooldown:
            return False, "触发冷却中"
            
        return True, "可以触发"
        
    def _check_hourly_greeting(self):
        """检查整点问候触发条件"""
        now = datetime.now()
        
        if now.minute != 0 or now.second > 10:
            return
            
        can_trigger, reason = self._can_trigger(ProactiveTriggerType.HOURLY_GREETING)
        if not can_trigger:
            logger.debug(f"[LocalProactiveService] 整点问候跳过: {reason}")
            return
            
        idle_time = time.time() - self._context.last_user_input_time
        config = self.TRIGGER_CONFIG[ProactiveTriggerType.HOURLY_GREETING]
        
        if idle_time < config["min_idle_seconds"]:
            logger.debug(f"[LocalProactiveService] 整点问候跳过: 用户刚交互过 ({idle_time:.0f}s)")
            return
            
        if random.random() > config["probability"]:
            logger.debug("[LocalProactiveService] 整点问候跳过: 概率筛选")
            return
            
        self._start_worker(ProactiveTriggerType.HOURLY_GREETING, {"hour": now.hour})
        
    def _check_idle_greeting(self):
        """检查长时间未交互问候触发条件"""
        can_trigger, reason = self._can_trigger(ProactiveTriggerType.IDLE_GREETING)
        if not can_trigger:
            return
            
        idle_time = time.time() - self._context.last_user_input_time
        config = self.TRIGGER_CONFIG[ProactiveTriggerType.IDLE_GREETING]
        
        if idle_time < config["min_idle_seconds"]:
            return
            
        if random.random() > config["probability"]:
            return
            
        self._start_worker(ProactiveTriggerType.IDLE_GREETING, {"idle_seconds": int(idle_time)})
        
    def on_drag_start(self):
        """拖动开始回调"""
        self._context.is_dragging = True
        self._context.drag_start_time = time.time()
        self._context.drag_distance = 0
        
    def on_drag_move(self, distance: float):
        """拖动移动回调"""
        if not self._context.is_dragging:
            return
            
        self._context.drag_distance += distance
        
        config = self.TRIGGER_CONFIG[ProactiveTriggerType.TEASING_RESPONSE]
        
        if self._context.drag_distance >= config["min_drag_distance"]:
            drag_duration = time.time() - self._context.drag_start_time
            
            if drag_duration >= config["min_drag_duration"]:
                can_trigger, reason = self._can_trigger(ProactiveTriggerType.TEASING_RESPONSE)
                
                if can_trigger and random.random() < config["probability"]:
                    self._start_worker(
                        ProactiveTriggerType.TEASING_RESPONSE,
                        {
                            "drag_distance": int(self._context.drag_distance),
                            "drag_duration": round(drag_duration, 1)
                        }
                    )
                    self._context.drag_distance = 0
                    self._context.drag_start_time = time.time()
                    
    def on_drag_end(self):
        """拖动结束回调"""
        self._context.is_dragging = False
        self._output_cancelled = True
        self._context.drag_distance = 0
        self._cancel_current_worker()
        
    def on_user_input(self):
        """用户输入回调"""
        self._context.last_user_input_time = time.time()
        self._context.is_user_interacting = True
        self._output_cancelled = True
        self._cancel_current_worker()
        
    def on_user_input_complete(self):
        """用户输入完成回调"""
        self._context.is_user_interacting = False
        
    def on_ai_response(self):
        """AI响应回调"""
        self._context.last_ai_response_time = time.time()
        
    def _start_worker(self, trigger_type, context):
        """启动后台工作线程"""
        self._cancel_current_worker()
        
        self._last_trigger_time[trigger_type] = time.time()
        self._output_cancelled = False
        
        self._current_worker = ProactiveWorker(
            self.local_model,
            self.memory_manager,
            trigger_type,
            context
        )
        self._current_worker.result_ready.connect(self._on_worker_result)
        self._current_worker.start()
        
    def _cancel_current_worker(self):
        """取消当前工作线程"""
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
            self._current_worker.wait(1000)  # 等待最多1秒
        self._current_worker = None
        
    def _on_worker_result(self, trigger_info, result):
        """处理工作线程结果"""
        if self._output_cancelled:
            logger.debug("[LocalProactiveService] 输出已取消")
            return
            
        if self._context.is_user_interacting:
            logger.debug("[LocalProactiveService] 用户正在交互，取消输出")
            return
            
        try:
            # 注意：不再保存到memory_manager，因为brain会处理对话记忆
            # 保存记忆会导致重复，因为brain._memorize_async已经会保存
            
            # 触发回调
            if self._callback_on_proactive:
                self._callback_on_proactive({
                    "type": "local_proactive",
                    "trigger": trigger_info.get("type"),
                    "message": result.get("text", ""),
                    "expression": result.get("expression", ""),
                    "context": trigger_info.get("context")
                })
                
            logger.info(f"[LocalProactiveService] 主动交互触发 [{trigger_info.get('type')}]: {result.get('text', '')[:30]}...")
            
        except Exception as e:
            logger.error(f"[LocalProactiveService] 处理结果失败: {e}")
            
    def _save_to_memory_sync(self, trigger_info, result):
        """同步保存到记忆库"""
        if not self.memory_manager:
            return
            
        try:
            content = f"[主动交互-{trigger_info.get('type')}] {result.get('text', '')}"
            
            self.memory_manager.add_short_term_memory(
                content,
                importance=0.3,
                tags=["proactive", trigger_info.get("type")]
            )
            
            logger.debug(f"[LocalProactiveService] 已保存到记忆库: {content[:30]}...")
            
        except Exception as e:
            logger.warning(f"[LocalProactiveService] 保存记忆失败: {e}")
            
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "enabled": self.enabled,
            "is_active": self._is_active,
            "local_model_available": self.local_model is not None,
            "last_user_input": int(time.time() - self._context.last_user_input_time),
            "is_user_interacting": self._context.is_user_interacting,
            "is_dragging": self._context.is_dragging,
            "last_triggers": {
                t.value: int(time.time() - ts) if ts else -1
                for t, ts in self._last_trigger_time.items()
            }
        }


_local_proactive_service: Optional[LocalProactiveService] = None


def get_local_proactive_service() -> Optional[LocalProactiveService]:
    """获取本地LLM主动交互服务单例"""
    return _local_proactive_service


def init_local_proactive_service(local_model, memory_manager=None, brain=None) -> LocalProactiveService:
    """初始化本地LLM主动交互服务"""
    global _local_proactive_service
    _local_proactive_service = LocalProactiveService(local_model, memory_manager, brain)
    return _local_proactive_service
