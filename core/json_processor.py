import json
import re
from typing import Any, Dict, List, Union

from loguru import logger


class JSONProcessor:
    """JSON处理器，负责JSON提取和解析"""

    def __init__(self, emotion_analyzer):
        """初始化JSON处理器"""
        self.emotion_analyzer = emotion_analyzer
        self.json_parsing_failures = 0  # 连续JSON解析失败计数器

    def extract_json(self, text: str) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """增强版JSON提取 - 支持同时提取工具调用和文本回复
        
        Args:
            text: 待提取JSON的文本
        
        Returns:
            提取并解析后的JSON（可能是字典或数组）
        """
        original_text = text
        text = text.strip()
        text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)

        is_json_valid = False
        data: Union[Dict[str, Any], List[Dict[str, Any]]] = {}
        
        json_objects = self._extract_all_json_objects(text)
        
        tool_call = None
        text_response = None
        text_before_tool = ""
        
        # 找出所有JSON的位置
        json_positions = []
        stack = []
        start_idx = -1
        
        for i, char in enumerate(text):
            if char == '{':
                if not stack:
                    start_idx = i
                stack.append(char)
            elif char == '}' and stack:
                stack.pop()
                if not stack:
                    json_positions.append((start_idx, i + 1))
        
        # 找出第一个工具调用JSON，然后提取它之前的文本
        if json_positions:
            first_json_start = json_positions[0][0]
            text_before_tool = text[:first_json_start].strip()
        
        for obj in json_objects:
            if "tool" in obj and "arguments" in obj:
                tool_call = obj
            if "text" in obj:
                text_response = obj
        
        # 如果有工具调用，并且有工具调用之前的纯文本，就用这个文本
        if tool_call and text_before_tool:
            logger.info("[JSONProcessor] 发现工具调用，使用工具前的文本")
            data = {"text": text_before_tool, "motion": "idle", "expression": "smile"}
            is_json_valid = True
        elif tool_call and text_response:
            logger.info("[JSONProcessor] 同时发现工具调用和文本回复，优先返回文本回复")
            data = text_response
            is_json_valid = True
        elif tool_call:
            logger.info("[JSONProcessor] 发现工具调用")
            data = tool_call
            is_json_valid = True
        elif text_response:
            logger.info("[JSONProcessor] 发现文本回复")
            data = text_response
            is_json_valid = True
        else:
            # 检查是否是纯文本回复（没有工具调用）
            has_brace = '{' in text or '}' in text
            has_bracket = '[' in text or ']' in text
            
            if not has_brace and not has_bracket:
                # 纯文本回复，直接包装
                logger.info("[JSONProcessor] 纯文本回复")
                data = {"text": text.strip(), "motion": "idle", "expression": "smile"}
                is_json_valid = True
            else:
                # 尝试解析JSON
                try:
                    data = json.loads(text)
                    is_json_valid = True
                except json.JSONDecodeError:
                    try:
                        pattern_array = r"\[[\s\S]*\]"
                        match = re.search(pattern_array, text)
                        if match:
                            json_str = match.group()
                            data = json.loads(json_str)
                            is_json_valid = True
                        else:
                            pattern = r"\{[\s\S]*\}"
                            match = re.search(pattern, text)

                            if match:
                                json_str = match.group()
                                data = json.loads(json_str)
                                is_json_valid = True
                            else:
                                # 没有找到有效的JSON，当作纯文本处理
                                logger.info("[JSONProcessor] 没有找到有效的JSON，当作纯文本处理")
                                data = {"text": text.strip(), "motion": "idle", "expression": "smile"}
                                is_json_valid = True
                    except Exception as e:
                        logger.error(f"JSON正则提取失败: {e}")
                        # 当作纯文本处理
                        data = {"text": text.strip(), "motion": "idle", "expression": "smile"}
                        is_json_valid = True

        if is_json_valid:
            self.json_parsing_failures = 0
        else:
            self.json_parsing_failures += 1
            logger.warning(f"JSON解析失败，连续失败次数: {self.json_parsing_failures}")

        if not is_json_valid:
            clean_text = text.strip()
            data = {"text": clean_text, "motion": "idle", "expression": "normal"}

        if isinstance(data, list):
            return data

        def clamp_score(score):
            try:
                return max(0.0, min(1.0, float(score)))
            except (ValueError, TypeError):
                return 0.3

        importance_user = clamp_score(data.get("importance_user", 0.3))
        importance_ai = clamp_score(data.get("importance_ai", 0.2))

        if self.json_parsing_failures >= 3:
            logger.warning("连续3次JSON解析失败，切换到EmotionAnalyzer评分")
            importance_user = self.emotion_analyzer.score_memory_importance(text, "")
            importance_ai = 0.2
            self.json_parsing_failures = 0

        result = {
            "text": data.get("text", data.get("content", "（薇薇安走神了...）")),
            "motion": data.get("motion", "idle"),
            "expression": data.get("expression", "smile"),
            "type": data.get("type", "chat"),
            "code": data.get("code", ""),
            "importance_user": importance_user,
            "importance_ai": importance_ai,
            "reason": data.get("reason", "normal chat"),
            "long_term_memory": data.get("long_term_memory", ""),
        }

        return result
    
    def _extract_all_json_objects(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取所有有效的JSON对象
        
        Args:
            text: 包含JSON的文本
        
        Returns:
            提取到的JSON对象列表
        """
        results = []
        
        stack = []
        start_idx = -1
        
        for i, char in enumerate(text):
            if char == '{':
                if not stack:
                    start_idx = i
                stack.append(char)
            elif char == '}' and stack:
                stack.pop()
                if not stack:
                    try:
                        json_str = text[start_idx:i+1]
                        obj = json.loads(json_str)
                        if isinstance(obj, dict):
                            results.append(obj)
                    except json.JSONDecodeError:
                        continue
        
        return results
