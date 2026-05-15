from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger


class EmotionAnalyzer:
    """情感分析器，分析文本的情感倾向"""

    # 情感到动作映射表
    EMOTION_MOTION_MAP = {
        "happy": ["wave", "nod", "idle"],
        "sad": ["idle", "nod"],
        "angry": ["idle"],
        "surprised": ["nod"],
        "neutral": ["idle"],
    }

    # 情感到表情映射表
    EMOTION_EXPRESSION_MAP = {
        "happy": ["shy"],
        "sad": ["cry"],
        "angry": ["angry", "eye_roll"],
        "surprised": ["eye_roll"],
        "neutral": [],
    }

    def __init__(self):
        """初始化情感分析器"""
        logger.debug("情感分析器初始化完成")

    def analyze_emotion(self, text: str) -> str:
        """分析文本情感
        
        Args:
            text: 要分析的文本
        
        Returns:
            情感类型，如happy, sad, angry, surprised, neutral
        """
        text_lower = text.lower()
        
        has_positive_punctuation = "!" in text or "！" in text
        has_smile = "😊" in text or "😄" in text or "🥳" in text or "❤️" in text
        has_sad_emoji = "😢" in text or "😭" in text or "😞" in text
        has_angry_emoji = "😠" in text or "😡" in text
        
        if has_positive_punctuation or has_smile:
            logger.debug(f"通过标点/表情符号分析出情感: happy")
            return "happy"
        elif has_sad_emoji:
            logger.debug(f"通过表情符号分析出情感: sad")
            return "sad"
        elif has_angry_emoji:
            logger.debug(f"通过表情符号分析出情感: angry")
            return "angry"
        
        is_question = "?" in text or "？" in text or "吗" in text or "呢" in text
        if is_question:
            logger.debug(f"检测到问题，返回neutral")
            return "neutral"
        
        if len(text) < 10:
            logger.debug(f"短文本，默认返回neutral")
            return "neutral"
        
        logger.debug(f"默认返回neutral")
        return "neutral"

    def map_emotion_to_action(self, emotion: str) -> tuple[str, str]:
        """将情感映射到动作和表情
        
        Args:
            emotion: 情感类型
        
        Returns:
            (动作, 表情)元组
        """
        import random

        motion = "Scene1"

        supported_expressions = [
            "umbrella_close",
            "cry",
            "shy",
            "panic",
            "eye_roll",
            "angry",
        ]

        expressions = self.EMOTION_EXPRESSION_MAP.get(emotion, [])
        valid_expressions = [exp for exp in expressions if exp in supported_expressions]

        expression = random.choice(valid_expressions) if valid_expressions else ""

        logger.debug(f"情感'{emotion}'映射到动作'{motion}'和表情'{expression}'")
        return motion, expression

    def extract_keywords(self, text: str) -> list[str]:
        """提取文本中的关键词
        
        Args:
            text: 要分析的文本
        
        Returns:
            关键词列表
        """
        keywords = []
        
        has_first_person = "我" in text or "俺" in text
        if has_first_person and len(text) >= 10:
            keywords.append("personal_statement")
        
        if len(text) > 30:
            keywords.append("long_content")
        
        logger.debug(f"从文本'{text[:20]}...'中提取特征: {keywords}")
        return keywords

    def score_memory_importance(self, user_input: str, ai_response: str) -> float:
        """评分记忆的重要性
        
        Args:
            user_input: 用户输入
            ai_response: AI响应
        
        Returns:
            重要性评分，0-1之间
        """
        importance = 0.0

        has_first_person = "我" in user_input or "俺" in user_input
        if has_first_person:
            importance += 0.4

        if len(user_input) > 20:
            importance += 0.4
        elif len(user_input) > 10:
            importance += 0.2
        
        has_emotion_symbol = "!" in user_input or "！" in user_input or "?" in user_input or "？" in user_input
        if has_emotion_symbol:
            importance += 0.2

        final_importance = min(1.0, max(0.0, importance))
        logger.debug(f"记忆重要性评分: {final_importance}")
        return final_importance
