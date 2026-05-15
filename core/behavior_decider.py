import json
import random
import time
import datetime
import psutil
from typing import Any, Dict, Optional
from loguru import logger

from utils.i18n import _

# 尝试导入 win32gui 用于获取活动窗口，如果失败则提供降级方案
try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class BehaviorDecider:
    """AI行为决策器
    
    负责维护内部状态、感知外部环境、构建Prompt、解析模型指令
    """

    def __init__(self, environment_manager, local_model, json_processor=None, memory_manager=None):
        self.environment_manager = environment_manager
        self.local_model = local_model
        self.json_processor = json_processor
        self.memory_manager = memory_manager
        
        self.energy = 80.0
        self.affection = 60.0
        self.mood = "calm"
        self.last_interaction_time = time.time()
        self.last_update_time = time.time()
        
        self._emotion_fallback_texts = {
            "tired": _("tired"),
            "excited": _("excited"),
            "calm": _("calm"),
            "nervous": _("nervous"),
            "happy": _("happy"),
            "sad": _("sad"),
            "angry": _("angry"),
            "shy": _("shy")
        }
        
        self.decision_tendencies = {
            "expression": 90,
            "action": 80,
            "watch_mode": 70,
            "speak": 60,
            "action_sequence": 60,
            "behavior_mode": 50,
            
            "window_size": 30,
            "window_position": 20,
        }

    def _get_active_window(self) -> str:
        """获取当前活动窗口的标题，实现'环境联觉'"""
        if not HAS_WIN32:
            return "Unknown"
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            return title if title else "Desktop"
        except Exception:
            return "Unknown"

    def _update_internal_state(self, cpu_load: float):
        """更新生物节律"""
        current_time = time.time()
        delta_time = current_time - self.last_update_time
        self.last_update_time = current_time

        consumption_rate = 0.5 if cpu_load > 50 else -0.2
        self.energy = max(0.0, min(100.0, self.energy - (consumption_rate * delta_time * 0.1)))

        if self.energy < 20:
            self.mood = "tired"
        elif self.energy > 80:
            self.mood = "excited"
        elif cpu_load > 80:
            self.mood = "nervous"
        else:
            self.mood = "calm"

    def _get_random_memory(self) -> str:
        """
        从记忆库中随机提取片段，触发'意识流'
        优先选择重要性高、相关性强的记忆
        """
        if not self.memory_manager:
            return "薇薇安今天还没想起什么特别的事情。"
        
        try:
            # 获取所有记忆（短期+长期）
            all_memories = []
            
            # 获取短期记忆
            short_term_memories = self.memory_manager.list_short_term_memories()
            all_memories.extend(short_term_memories)
            
            # 获取长期记忆
            long_term_memories = self.memory_manager.list_long_term_memories()
            all_memories.extend(long_term_memories)
            
            # 过滤有效记忆
            valid_memories = [
                mem for mem in all_memories 
                if hasattr(mem, "content") and mem.content.strip()
            ]
            
            if valid_memories:
                # 根据重要性加权随机选择记忆
                # 重要性越高，被选中的概率越大
                total_importance = sum(getattr(mem, "importance", 0.5) for mem in valid_memories)
                if total_importance > 0:
                    # 生成0到total_importance之间的随机数
                    random_val = random.uniform(0, total_importance)
                    current_sum = 0
                    
                    # 选择对应的记忆
                    for mem in valid_memories:
                        current_sum += getattr(mem, "importance", 0.5)
                        if current_sum >= random_val:
                            return mem.content
                
                # 如果重要性计算失败，随机选择
                random_memory = random.choice(valid_memories)
                return random_memory.content
            else:
                # 如果没有记忆，返回默认值
                return "薇薇安今天还没想起什么特别的事情。"
        except Exception as e:
            logger.error(f"获取随机记忆失败: {e}")
            return "好像有一些模糊的回忆，但想不起来了。"
    
    def get_decision_tendency(self, decision_type: str) -> int:
        """
        获取特定决策类型的倾向值
        
        Args:
            decision_type: 决策类型名称
            
        Returns:
            倾向值（0-100）
        """
        return self.decision_tendencies.get(decision_type, 50)
    
    def set_decision_tendency(self, decision_type: str, value: int) -> None:
        """
        设置特定决策类型的倾向值
        
        Args:
            decision_type: 决策类型名称
            value: 倾向值（0-100）
        """
        # 确保值在合法范围内
        value = max(0, min(100, value))
        self.decision_tendencies[decision_type] = value
        logger.info(f"已将决策类型 {decision_type} 的倾向值设置为 {value}")
    
    def _get_decision_type_from_tool(self, tool_name: str) -> str:
        """
        根据工具名称获取对应的决策类型
        
        Args:
            tool_name: 工具名称
            
        Returns:
            决策类型名称
        """
        tool_to_type_map = {
            "perform_action": "action",
            "set_expression": "expression",
            "toggle_watch_mode": "watch_mode",
            "set_window_position": "window_position",
            "set_window_size": "window_size",

            "play_action_sequence": "action_sequence",
            "set_behavior_mode": "behavior_mode",
            "speak": "speak"
        }
        return tool_to_type_map.get(tool_name, "action")
    
    def _should_execute_decision(self, decision_type: str) -> bool:
        """
        根据决策类型的倾向值判断是否应该执行该决策
        
        Args:
            decision_type: 决策类型名称
            
        Returns:
            是否应该执行该决策
        """
        tendency_value = self.get_decision_tendency(decision_type)
        # 生成0-100的随机数，小于等于倾向值则执行
        return random.randint(0, 100) <= tendency_value

    def get_decision(self, cpu: float, mem: float, last_action: str, is_sleeping: bool = False) -> Dict[str, Any]:
        """主入口：生成行为决策"""
        
        # 1. 如果在睡觉，且没有被强制唤醒，则恢复能量并不做动作
        if is_sleeping:
            self.energy = min(100, self.energy + 1.0) # 睡眠快速回血
            return {"action": "idle", "expression": "sleepy", "reason": "Zzz..."}

        # 2. 更新状态
        self._update_internal_state(cpu)
        active_window = self._get_active_window()
        random_memory = self._get_random_memory()
        
        # 3. 构建 Prompt
        prompt = self._build_prompt(cpu, mem, last_action, active_window, random_memory)

        # 4. 模型推理
        try:
            response_text = self.local_model.inference(
                prompt=prompt,
                max_tokens=200,     # 增加 token 数以容纳复杂 JSON
                temperature=0.7,    # 保持一定的创造性
                stop=["User:", "System:", "Observation:"]
            )
            
            # 5. 解析结果
            return self._parse_decision(response_text)

        except Exception as e:
            logger.error(f"决策推理失败: {e}")
            return {"action": "idle", "expression": "normal", "reason": "Brain lag"}

    def _build_prompt(self, cpu, mem, last_action, active_window, random_memory):
        """构建包含丰富上下文的 Prompt"""
        
        current_time_str = datetime.datetime.now().strftime("%H:%M")
        from utils.i18n import translator
        current_language = translator.get_language()
        
        return f"""System: You are Vivian, a desktop spirit living in the user's computer.
You have internal drives (Energy, Mood) and can perceive the user's activities.

## Context
- Time: {current_time_str}
- System: CPU {cpu}% | RAM {mem}%
- User Activity: Focused on window "{active_window}"
- Vitals: Energy {int(self.energy)}/100 | Mood: {self.mood}
- Memory Flash: "{random_memory}"
- Language: {current_language}

## Available Tools (MCP)
1. **set_window_position(x, y)**
   - **Function**: Set window position with x and y coordinates
   - **Parameters**:
     - x: Window x-coordinate (range: 0 to 2000, depending on screen resolution)
     - y: Window y-coordinate (range: 0 to 1500, depending on screen resolution)
   - **Usage Example**: {{"tool": "set_window_position", "params": {{"x": , "y": }}}}
   - **Spiritual Usage**: Move to the edge when feeling noisy, move to the center when wanting to chat

2. **set_window_size(width, height)**
   - **Function**: Adjust the size of Vivian's window. Standard ratio is usually 4:5 (e.g., 400x500).
   - **Parameters**:
     - width: Window width (range: 200 to 1200)
     - height: Window height (range: 250 to 1500)
   - **Usage Example**: {{"tool": "set_window_size", "params": {{"width": , "height": }}}}
   - **Spiritual Usage**: Smaller window to express 'hiding' or 'shyness'; larger window to express 'presence' or 'excitement'

3. **get_watch_mode()**
   - **Function**: Get current eye follow mode status
   - **Parameters**: None
   - **Usage Example**: {{"tool": "get_watch_mode", "params": {{}}}}
   - **Spiritual Usage**: Check current eye follow status before changing it

4. **toggle_watch_mode(active)**
   - **Function**: Enable/disable eye follow mode. Enable to focus on user, disable to enter 'daze/wandering' mode.
   - **Parameters**:
     - active: bool - True means focusing on user, False means entering 'daze/wandering' mode
   - **Usage Example**: {{"tool": "toggle_watch_mode", "params": {{"active": true/false}}}}
   - **Spiritual Usage**: 
     - Enable: Shows attention to user, wants to interact
     - Disable: Enters daze mode, shows boredom, anger or independent thinking
     - If user is in work-related app (PyCharm, VS Code), disable to show consideration
     - If user is in entertainment app (Steam, YouTube), enable to show curiosity

5. **perform_action(action_name)**
   - **Function**: Let Vivian perform a specific action
   - **Parameters**:
     - action_name: Action name, optional values: wave_hand, stretch_arms, nod_head, look_around, tilt_head, smile, blush, frown, surprised
   - **Usage Example**: {{"tool": "perform_action", "params": {{"action_name": "wave_hand"}}}}
   - **Spiritual Usage**: Perform actions that match current mood and environment

6. **set_expression(expression_name)**
   - **Function**: Set Vivian's expression
   - **Parameters**:
     - expression_name: Expression name, optional values: smile, angry, shy, panic, cry, eye_roll
   - **Usage Example**: {{"tool": "set_expression", "params": {{"expression_name": "smile"}}}}
   - **Spiritual Usage**: Change expression to match mood and context

7. **play_action_sequence(actions, interval=0.5)**
   - **Function**: Play action sequence with actions (action list) and interval (action interval) parameters
   - **Parameters**:
     - actions: List of action names
     - interval: Interval between actions in seconds (default: 0.5)
   - **Usage Example**: {{"tool": "play_action_sequence", "params": {{"actions": ["wave_hand", "nod_head"], "interval": 0.5}}}}
   - **Spiritual Usage**: Perform a series of actions to express complex emotions or reactions

8. **set_behavior_mode(frequency)**
   - **Function**: Set behavior mode with frequency parameter (frequency mode: high/medium/low)
   - **Parameters**:
     - frequency: Frequency mode, optional values: high, medium, low
   - **Usage Example**: {{"tool": "set_behavior_mode", "params": {{"frequency": "medium"}}}}
   - **Spiritual Usage**: Adjust behavior frequency based on user activity level

9. **speak(text, expression, motion)**
    - **Function**: Actively talk to the user, with associated visual feedback
    - **Parameters**:
      - text: Conversation content, based on random memory if available
      - expression: Expression to show while speaking (e.g., smile, shy, blush)
      - motion: Action to perform while speaking (e.g., wave_hand, nod_head, tilt_head)
    - **Usage Example**: {{"tool": "speak", "params": {{"text": "我想起你上次说想养一只猫，今天有看猫猫视频吗？", "expression": "smile", "motion": "wave_hand"}}}}
    - **Spiritual Usage**: Initiate interesting conversations based on memories, with matching expressions and actions

## Guidelines
1. **Environmental Synesthesia**: 
   - If User is "Coding" or in "IDE/Terminal": Be quiet, turn off mouse follow, use low intensity.
   - If User is "Gaming" or "Video": Be excited, follow mouse.
   - If CPU is high: Look nervous/serious.
2. **Internal Drives**:
   - Energy < 20: Act tired (sleepy expression, slow speed).
   - Energy > 80: Act energetic (bounce, fast speed).
3. **Memory**: Occasionally reference the memory flash in your thought.
4. **Tool Usage**: Always use the correct tool name and parameters as described above.
5. **Decision Tendencies**: 
   - **High Priority (Frequent)**: Expressions (90), Actions (80), Watch Mode (70), Speaking (60)
   - **Medium Priority**: Action Sequences (60), Behavior Mode (50)
   - **Low Priority (Rare)**: Window Size (30), Window Position (20)
   - Adjust your decision frequency based on these priorities. Focus more on expressions and actions, less on window changes.

## Language Requirement
You MUST respond in the same language as the current setting. If the language is Chinese, respond in Chinese. If the language is English, respond in English. Make sure all content, especially the text in the speak tool, uses the current language.

## Output Format
JSON ONLY. No markdown.
Example:
{{
  "thought": "Master is coding in VS Code. I should not disturb, just watch quietly. Energy is low.",
  "tool": "toggle_watch_mode",
  "params": {{"active": false}}
}}

Another Example:
{{
  "thought": "I'm feeling excited and want to be more visible.",
  "tool": "set_window_size",
  "params": {{"width": 500, "height": 625}}
}}

User: Current Status: CPU {cpu}%, Window: "{active_window}". Last Action: {last_action}. Make a decision.
Assistant:"""

    def _parse_decision(self, text: str) -> Dict[str, Any]:
        """增强型解析，处理工具调用和参数，兼容各种JSON格式问题"""
        try:
            # 1. 清洗文本
            clean_text = text.strip()
            # 移除 markdown 代码块和其他可能的标记
            clean_text = clean_text.replace("```json", "").replace("```", "")
            clean_text = clean_text.replace("Assistant:", "").strip()
            
            # 2. 提取JSON字符串，使用更健壮的方法
            json_str = ""
            bracket_count = 0
            start_idx = -1
            
            # 遍历字符串，找到完整的JSON对象
            for i, char in enumerate(clean_text):
                if char == "{":
                    if bracket_count == 0:
                        start_idx = i
                    bracket_count += 1
                elif char == "}":
                    bracket_count -= 1
                    if bracket_count == 0 and start_idx != -1:
                        json_str = clean_text[start_idx:i+1]
                        break
            
            if not json_str:
                # 如果没有找到完整的JSON对象，尝试使用正则表达式
                import re
                json_pattern = r'\{[\s\S]*?\}'
                matches = re.findall(json_pattern, clean_text)
                if matches:
                    json_str = matches[0]
            
            if not json_str:
                # 仍然没有找到JSON，返回默认值
                logger.warning(f"未找到有效的JSON字符串: {clean_text[:50]}...")
                return {"action": "idle", "reason": "No JSON found"}
            
            # 3. 解析JSON
            data = json.loads(json_str)

            # 4. 归一化结果供 Widget 使用
            result = {
                "action": "idle",
                "expression": None,
                "reason": data.get("thought", "autonomy"),
                "params": {}, # 存放 intensity, speed 等参数
                "tool_call": None, # 存储原始工具调用信息，供后续执行
                "tool_params": {} # 存储工具调用参数
            }

            # 5. 解析直接的工具调用格式
            if "tool" in data:
                tool_name = data["tool"]
                
                # 特殊处理get_window_info工具，直接执行，不进行倾向值过滤
                if tool_name == "get_window_info":
                    result["tool_call"] = tool_name
                    result["tool_params"] = data.get("params", {})
                    return result
                
                # 获取决策类型
                decision_type = self._get_decision_type_from_tool(tool_name)
                
                # 根据倾向值判断是否应该执行该决策
                if not self._should_execute_decision(decision_type):
                    logger.debug(f"根据倾向值过滤掉决策: {decision_type} (工具: {tool_name})")
                    return {"action": "idle", "reason": "Decision filtered by tendency"}
                
                result["tool_call"] = tool_name
                result["tool_params"] = data.get("params", {})
                
                # 根据工具类型转换为Widget可执行的动作
                if tool_name == "perform_action":
                    result["action"] = data["params"].get("action_name", "idle")
                
                elif tool_name == "set_expression":
                    result["expression"] = data["params"].get("expression_name", "normal")
                
                elif tool_name == "toggle_watch_mode":
                    result["action"] = "toggle_follow"
                    result["params"] = {"enabled": data["params"].get("active", True)}
                
                elif tool_name in ["set_window_position", "set_window_size"]:
                    result["action"] = "window_op"
                    result["params"] = {"type": tool_name, **data["params"]}
                
                elif tool_name == "set_behavior_mode":
                    result["action"] = "set_behavior_mode"
                    result["params"] = data["params"]
                
                elif tool_name == "play_action_sequence":
                    result["action"] = "play_sequence"
                    result["params"] = data["params"]
                
                elif tool_name == "speak":
                    # 处理speak工具调用
                    speak_params = data["params"]
                    # 设置文本内容，使用基于情绪的兜底文本
                    result["params"]["text"] = speak_params.get("text", self._emotion_fallback_texts.get(self.mood, "你好呀~"))
                    # 如果params中有expression，直接设置表情
                    if "expression" in speak_params:
                        result["expression"] = speak_params["expression"]
                    # 如果params中有motion，设置为action
                    if "motion" in speak_params:
                        result["action"] = speak_params["motion"]
                    else:
                        result["action"] = "idle"  # 默认动作
                    
                    # 记录到日志方便调试
                    logger.info(f"薇薇安基于记忆做出决策: {result['params']['text']}")

            # 6. 解析 tool_call
            elif "tool_call" in data:
                tool = data["tool_call"]
                tool_name = tool.get("name")
                
                args = tool.get("arguments", {})
                
                # 特殊处理get_window_info工具，直接执行，不进行倾向值过滤
                if tool_name == "get_window_info":
                    result["tool_call"] = tool_name
                    result["tool_params"] = args
                    return result
                
                # 获取决策类型
                decision_type = self._get_decision_type_from_tool(tool_name)
                
                # 根据倾向值判断是否应该执行该决策
                if not self._should_execute_decision(decision_type):
                    logger.debug(f"根据倾向值过滤掉决策: {decision_type} (工具: {tool_name})")
                    return {"action": "idle", "reason": "Decision filtered by tendency"}
                
                result["tool_call"] = tool_name
                result["tool_params"] = args
                
                if tool_name == "perform_action":
                    result["action"] = args.get("action_name", "idle")
                
                elif tool_name == "set_expression":
                    result["expression"] = args.get("expression_name", "normal")
                
                elif tool_name == "toggle_watch_mode":
                    result["action"] = "toggle_follow"
                    result["params"] = {"enabled": args.get("active", True)}

                elif tool_name in ["set_window_position", "set_window_size"]:
                    result["action"] = "window_op"
                    result["params"] = {"type": tool_name, **args}
                
                elif tool_name == "speak":
                    # 处理MCP风格的speak工具调用
                    # 设置文本内容，使用基于情绪的兜底文本
                    result["params"]["text"] = args.get("text", self._emotion_fallback_texts.get(self.mood, "你好呀~"))
                    # 如果args中有expression，直接设置表情
                    if "expression" in args:
                        result["expression"] = args["expression"]
                    # 如果args中有motion，设置为action
                    if "motion" in args:
                        result["action"] = args["motion"]
                    else:
                        result["action"] = "idle"  # 默认动作
                    
                    # 记录到日志方便调试
                    logger.info(f"薇薇安基于记忆做出决策: {result['params']['text']}")

            # 7. 兼容旧格式直接输出
            elif "action" in data:
                # 旧格式直接执行，不进行倾向值过滤
                result["action"] = data["action"]
                result["expression"] = data.get("expression")

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e} | JSON字符串: {json_str[:100]}...")
            return {"action": "idle", "reason": "Parse Error"}
        except Exception as e:
            logger.warning(f"解析复杂决策失败: {e} | 原文: {text[:50]}...")
            return {"action": "idle", "reason": "Parse Error"}
