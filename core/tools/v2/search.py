"""
工具搜索和延迟加载系统 - 工具系统 V2

实现工具的搜索和延迟加载功能。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type

from pydantic import BaseModel, Field
from loguru import logger

from .tool import Tool, build_tool, tool_matches_name
from .pool import ToolPool
from .types import ToolResult, ToolUseContext


class SearchMatchType(Enum):
    """搜索匹配类型"""
    EXACT = "exact"
    PREFIX = "prefix"
    CONTAINS = "contains"
    FUZZY = "fuzzy"
    SEMANTIC = "semantic"


@dataclass
class ToolSearchResult:
    """工具搜索结果"""
    tool: Tool
    score: float = 1.0
    match_type: SearchMatchType = SearchMatchType.EXACT
    matched_fields: List[str] = field(default_factory=list)

    def __lt__(self, other: "ToolSearchResult") -> bool:
        return self.score < other.score


class ToolSearchEngine:
    """
    工具搜索引擎

    支持多种搜索方式的工具搜索引擎。
    """

    def __init__(self, tools: Optional[List[Tool]] = None):
        self._tools: List[Tool] = tools or []
        self._name_index: Dict[str, Tool] = {}
        self._alias_index: Dict[str, str] = {}
        self._hint_index: Dict[str, List[Tool]] = {}
        self._rebuild_index()

    def set_tools(self, tools: List[Tool]) -> None:
        """设置工具列表"""
        self._tools = tools
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """重建索引"""
        self._name_index = {t.name.lower(): t for t in self._tools}
        self._alias_index = {}
        self._hint_index = {}

        for tool in self._tools:
            for alias in tool.aliases:
                self._alias_index[alias.lower()] = tool.name

            hint_words = tool.search_hint.lower().split()
            for word in hint_words:
                if word not in self._hint_index:
                    self._hint_index[word] = []
                self._hint_index[word].append(tool)

    def search(
        self,
        query: str,
        max_results: int = 10,
        match_types: Optional[Set[SearchMatchType]] = None,
    ) -> List[ToolSearchResult]:
        """
        搜索工具

        Args:
            query: 搜索查询
            max_results: 最大结果数
            match_types: 匹配类型集合

        Returns:
            搜索结果列表
        """
        if match_types is None:
            match_types = {
                SearchMatchType.EXACT,
                SearchMatchType.PREFIX,
                SearchMatchType.CONTAINS,
            }

        results: List[ToolSearchResult] = []
        query_lower = query.lower()
        seen: Set[str] = set()

        for tool in self._tools:
            if tool.name in seen:
                continue

            result = self._match_tool(tool, query_lower, match_types)
            if result:
                results.append(result)
                seen.add(tool.name)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def _match_tool(
        self,
        tool: Tool,
        query: str,
        match_types: Set[SearchMatchType],
    ) -> Optional[ToolSearchResult]:
        """匹配单个工具"""
        matched_fields = []

        if SearchMatchType.EXACT in match_types:
            if tool.name.lower() == query:
                return ToolSearchResult(
                    tool=tool,
                    score=1.0,
                    match_type=SearchMatchType.EXACT,
                    matched_fields=["name"],
                )
            if query in [a.lower() for a in tool.aliases]:
                return ToolSearchResult(
                    tool=tool,
                    score=0.95,
                    match_type=SearchMatchType.EXACT,
                    matched_fields=["alias"],
                )

        score = 0.0

        if SearchMatchType.PREFIX in match_types:
            if tool.name.lower().startswith(query):
                score = max(score, 0.8)
                matched_fields.append("name_prefix")
            for alias in tool.aliases:
                if alias.lower().startswith(query):
                    score = max(score, 0.75)
                    matched_fields.append("alias_prefix")

        if SearchMatchType.CONTAINS in match_types:
            if query in tool.name.lower():
                score = max(score, 0.6)
                matched_fields.append("name_contains")
            if query in tool.description.lower():
                score = max(score, 0.5)
                matched_fields.append("description")
            if query in tool.search_hint.lower():
                score = max(score, 0.55)
                matched_fields.append("hint")
            for alias in tool.aliases:
                if query in alias.lower():
                    score = max(score, 0.5)
                    matched_fields.append("alias_contains")

        if SearchMatchType.FUZZY in match_types:
            fuzzy_score = self._fuzzy_match(tool, query)
            if fuzzy_score > 0.3:
                score = max(score, fuzzy_score)
                matched_fields.append("fuzzy")

        if score > 0:
            match_type = SearchMatchType.CONTAINS
            if score >= 0.8:
                match_type = SearchMatchType.PREFIX

            return ToolSearchResult(
                tool=tool,
                score=score,
                match_type=match_type,
                matched_fields=matched_fields,
            )

        return None

    def _fuzzy_match(self, tool: Tool, query: str) -> float:
        """模糊匹配"""
        name = tool.name.lower()
        query_chars = list(query)
        name_chars = list(name)

        matched = 0
        name_idx = 0

        for q_char in query_chars:
            while name_idx < len(name_chars):
                if name_chars[name_idx] == q_char:
                    matched += 1
                    name_idx += 1
                    break
                name_idx += 1

        if matched == 0:
            return 0.0

        return matched / len(query_chars) * 0.4

    def search_by_keyword(self, keyword: str) -> List[Tool]:
        """按关键词搜索"""
        keyword_lower = keyword.lower()
        results = []

        if keyword_lower in self._hint_index:
            results.extend(self._hint_index[keyword_lower])

        for tool in self._tools:
            if keyword_lower in tool.search_hint.lower():
                if tool not in results:
                    results.append(tool)

        return results

    def get_by_name(self, name: str) -> Optional[Tool]:
        """按名称获取工具"""
        tool = self._name_index.get(name.lower())
        if tool:
            return tool

        alias_target = self._alias_index.get(name.lower())
        if alias_target:
            return self._name_index.get(alias_target.lower())

        return None

    def suggest(self, partial: str, max_suggestions: int = 5) -> List[str]:
        """
        建议补全

        Args:
            partial: 部分输入
            max_suggestions: 最大建议数

        Returns:
            建议的工具名称列表
        """
        partial_lower = partial.lower()
        suggestions = []

        for name in self._name_index:
            if name.startswith(partial_lower):
                suggestions.append(self._name_index[name].name)

        for alias in self._alias_index:
            if alias.startswith(partial_lower):
                tool_name = self._alias_index[alias]
                if tool_name not in suggestions:
                    suggestions.append(tool_name)

        return suggestions[:max_suggestions]


class DeferredToolLoader:
    """
    延迟工具加载器

    支持工具的延迟加载，减少初始加载时间。
    """

    def __init__(self):
        self._deferred: Dict[str, Callable[[], Tool]] = {}
        self._loaded: Dict[str, Tool] = {}
        self._loading: Set[str] = set()

    def register_deferred(
        self,
        name: str,
        loader: Callable[[], Tool],
    ) -> None:
        """
        注册延迟加载的工具

        Args:
            name: 工具名称
            loader: 加载函数
        """
        self._deferred[name] = loader

    def is_deferred(self, name: str) -> bool:
        """检查工具是否延迟加载"""
        return name in self._deferred and name not in self._loaded

    def is_loaded(self, name: str) -> bool:
        """检查工具是否已加载"""
        return name in self._loaded

    def load(self, name: str) -> Optional[Tool]:
        """
        加载工具

        Args:
            name: 工具名称

        Returns:
            加载的工具，如果不存在则返回None
        """
        if name in self._loaded:
            return self._loaded[name]

        if name not in self._deferred:
            return None

        if name in self._loading:
            logger.warning(f"Circular loading detected for tool '{name}'")
            return None

        self._loading.add(name)
        try:
            tool = self._deferred[name]()
            self._loaded[name] = tool
            del self._deferred[name]
            logger.debug(f"Deferred tool '{name}' loaded")
            return tool
        except Exception as e:
            logger.error(f"Failed to load deferred tool '{name}': {e}")
            return None
        finally:
            self._loading.discard(name)

    def load_all(self) -> List[Tool]:
        """加载所有延迟工具"""
        tools = []
        for name in list(self._deferred.keys()):
            tool = self.load(name)
            if tool:
                tools.append(tool)
        return tools

    def get_loaded_tools(self) -> List[Tool]:
        """获取所有已加载的工具"""
        return list(self._loaded.values())

    def get_deferred_names(self) -> List[str]:
        """获取所有延迟加载的工具名称"""
        return list(self._deferred.keys())

    def unload(self, name: str) -> bool:
        """卸载工具"""
        if name in self._loaded:
            del self._loaded[name]
            return True
        return False


def create_tool_search_tool() -> Tool:
    """
    创建工具搜索工具

    这是一个特殊的元工具，用于搜索其他工具。
    """

    class ToolSearchInput(BaseModel):
        query: str = Field(description="搜索查询")
        max_results: int = Field(default=10, description="最大结果数")

    async def search_tools(
        args: ToolSearchInput,
        context: ToolUseContext,
    ) -> ToolResult:
        from .pool import get_pool_manager

        pool = get_pool_manager().get_pool()
        engine = ToolSearchEngine(pool.tools)

        results = engine.search(args.query, args.max_results)

        output = []
        for result in results:
            tool = result.tool
            output.append({
                "name": tool.name,
                "description": tool.description,
                "score": result.score,
                "match_type": result.match_type.value,
            })

        return ToolResult(data=output)

    return build_tool(
        name="tool_search",
        description="搜索可用工具。当需要查找特定功能的工具时使用此工具。",
        input_schema=ToolSearchInput,
        call=search_tools,
        search_hint="find tools by keyword, search available tools",
        should_defer=False,
        always_load=True,
    )
