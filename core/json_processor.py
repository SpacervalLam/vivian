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
        """增强版JSON提取
        
        Args:
            text: 待提取JSON的文本
        
        Returns:
            提取并解析后的JSON（可能是字典或数组）
        """
        text = text.strip()
        text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)

        is_json_valid = False
        data: Union[Dict[str, Any], List[Dict[str, Any]]] = {}

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
                        is_json_valid = False
            except Exception as e:
                logger.error(f"JSON正则提取失败: {e}")
                is_json_valid = False

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
        }

        return result
