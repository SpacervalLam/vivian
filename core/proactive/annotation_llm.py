"""
LLM标注服务 - AnnotationLLM

核心功能：
1. 自动标注话题的open_hooks、user_need、related_domains
2. 支持异步调用
3. 与memoryos-agent架构兼容

灵感来源：memoryos-agent/core/proactive/proactive_process/services/annotation_llm.py
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger


class AnnotationLLM:
    """LLM标注服务"""

    def __init__(self, ai_manager=None):
        """
        初始化标注服务

        Args:
            ai_manager: AI管理器实例
        """
        self._ai_manager = ai_manager

    async def annotate(self, summary: str) -> Optional[Dict[str, Any]]:
        """
        标注话题摘要

        Args:
            summary: 话题摘要

        Returns:
            标注结果字典，包含open_hooks、user_need、related_domains
        """
        if not summary:
            return None

        try:
            # 构建标注提示词
            prompt = self._build_annotation_prompt(summary)

            # 调用LLM
            if self._ai_manager:
                response = await self._ai_manager.generate_async(prompt)
            else:
                # 回退到规则引擎
                response = self._fallback_annotation(summary)

            # 解析结果
            return self._parse_annotation_response(response)

        except Exception as e:
            logger.error(f"[AnnotationLLM] 标注失败: {e}")
            # 回退到规则引擎
            return self._fallback_annotation(summary)

    def _build_annotation_prompt(self, summary: str) -> str:
        """
        构建标注提示词

        Args:
            summary: 话题摘要

        Returns:
            完整的提示词
        """
        prompt = f"""
请分析以下对话摘要，并提取关键信息：

对话摘要：{summary}

请输出JSON格式，包含以下字段：
1. "open_hooks": 列表，包含对话中提到的需要跟进的事项或关注点（最多3个）
2. "user_need": 字符串，用户的核心需求或关注点
3. "related_domains": 列表，相关的领域标签（最多5个）

示例输出：
{{
  "open_hooks": ["复诊时间", "报告结果"],
  "user_need": "用户需要了解体检报告结果并安排复诊",
  "related_domains": ["健康", "医疗", "预约"]
}}

请确保输出是有效的JSON格式。
        """
        return prompt.strip()

    def _fallback_annotation(self, summary: str) -> Dict[str, Any]:
        """
        规则引擎回退标注

        Args:
            summary: 话题摘要

        Returns:
            标注结果
        """
        summary_lower = summary.lower()

        # 关键词匹配生成hooks
        hooks = []
        
        # 健康相关
        health_keywords = ["病", "痛", "检查", "体检", "医院", "医生", "药", "治疗", "康复"]
        if any(kw in summary_lower for kw in health_keywords):
            hooks.append("健康状况跟进")

        # 工作学习相关
        work_keywords = ["工作", "学习", "项目", "任务", "报告", "作业", "考试"]
        if any(kw in summary_lower for kw in work_keywords):
            hooks.append("工作学习进度")

        # 旅行相关
        travel_keywords = ["旅行", "旅游", "度假", "机票", "酒店", "行程"]
        if any(kw in summary_lower for kw in travel_keywords):
            hooks.append("旅行计划")

        # 情感相关
        emotion_keywords = ["难过", "开心", "压力", "累", "焦虑", "抑郁"]
        if any(kw in summary_lower for kw in emotion_keywords):
            hooks.append("情感支持")

        # 确定用户需求
        user_need = self._extract_user_need(summary_lower, hooks)

        # 确定领域
        domains = self._extract_domains(summary_lower)

        return {
            "open_hooks": hooks[:3],
            "user_need": user_need,
            "related_domains": domains[:5]
        }

    def _extract_user_need(self, summary_lower: str, hooks: List[str]) -> str:
        """
        提取用户需求

        Args:
            summary_lower: 小写摘要
            hooks: 已识别的hooks

        Returns:
            用户需求描述
        """
        if "健康状况跟进" in hooks:
            return "用户关注健康相关问题"
        if "工作学习进度" in hooks:
            return "用户关注工作或学习进度"
        if "旅行计划" in hooks:
            return "用户计划旅行或关注旅行相关"
        if "情感支持" in hooks:
            return "用户需要情感支持"

        # 默认
        return "用户讨论了某个话题"

    def _extract_domains(self, summary_lower: str) -> List[str]:
        """
        提取领域标签

        Args:
            summary_lower: 小写摘要

        Returns:
            领域标签列表
        """
        domains = []

        domain_keywords = {
            "健康": ["病", "痛", "检查", "体检", "医院", "医生", "药"],
            "工作": ["工作", "项目", "任务", "报告", "会议"],
            "学习": ["学习", "考试", "作业", "课程", "学校"],
            "旅行": ["旅行", "旅游", "度假", "机票", "酒店"],
            "情感": ["难过", "开心", "压力", "累", "焦虑"],
            "技术": ["代码", "编程", "开发", "软件", "电脑"],
            "娱乐": ["游戏", "电影", "音乐", "视频", "玩"],
            "生活": ["吃饭", "睡觉", "购物", "做饭", "家务"],
        }

        for domain, keywords in domain_keywords.items():
            if any(kw in summary_lower for kw in keywords):
                domains.append(domain)

        return domains

    def _parse_annotation_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        解析LLM响应

        Args:
            response: LLM响应文本

        Returns:
            解析后的标注结果
        """
        try:
            # 尝试提取JSON部分
            if "{" in response:
                start = response.index("{")
                end = response.rindex("}") + 1
                json_str = response[start:end]
                data = json.loads(json_str)

                # 验证必要字段
                if "open_hooks" in data and "user_need" in data:
                    return data
        except json.JSONDecodeError as e:
            logger.warning(f"[AnnotationLLM] JSON解析失败: {e}")
        except Exception as e:
            logger.warning(f"[AnnotationLLM] 解析失败: {e}")

        return None

    def set_ai_manager(self, ai_manager):
        """设置AI管理器"""
        self._ai_manager = ai_manager
        logger.info("[AnnotationLLM] AI管理器已设置")


# 全局单例
_annotation_llm: Optional[AnnotationLLM] = None


def get_annotation_llm(ai_manager=None) -> AnnotationLLM:
    """获取标注LLM单例"""
    global _annotation_llm
    if _annotation_llm is None:
        _annotation_llm = AnnotationLLM(ai_manager)
    return _annotation_llm