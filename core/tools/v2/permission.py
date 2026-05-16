"""
权限上下文系统 - 工具系统 V2

实现完整的权限管理系统，包括：
- 权限模式
- 权限规则
- 权限上下文
- 权限检查器
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field
from loguru import logger

from .types import PermissionBehavior, PermissionResult


class PermissionMode(Enum):
    """权限模式"""
    DEFAULT = "default"
    BYPASS = "bypass"
    AUTO = "auto"
    PLAN = "plan"


class RuleSource(Enum):
    """规则来源"""
    USER = "user"
    PROJECT = "project"
    SYSTEM = "system"
    MCP = "mcp"
    HOOK = "hook"


@dataclass
class PermissionRule:
    """
    权限规则

    定义单个权限规则的匹配条件和行为。
    """
    pattern: str
    behavior: PermissionBehavior
    source: RuleSource = RuleSource.USER
    message: str = ""
    rule_content: Optional[str] = None

    def matches(self, value: str) -> bool:
        """
        检查值是否匹配规则

        支持通配符和正则表达式匹配。
        """
        if self.pattern == "*":
            return True

        if self.pattern.startswith("regex:"):
            try:
                regex = self.pattern[6:]
                return bool(re.match(regex, value))
            except re.error:
                return False

        if "*" in self.pattern or "?" in self.pattern or "[" in self.pattern:
            return fnmatch.fnmatch(value, self.pattern)

        return value == self.pattern


@dataclass
class ToolPermissionRules:
    """
    工具权限规则集合

    按来源组织的权限规则。
    """
    allow: List[PermissionRule] = field(default_factory=list)
    deny: List[PermissionRule] = field(default_factory=list)
    ask: List[PermissionRule] = field(default_factory=list)

    def add_rule(self, rule: PermissionRule) -> None:
        """添加规则"""
        if rule.behavior == PermissionBehavior.ALLOW:
            self.allow.append(rule)
        elif rule.behavior == PermissionBehavior.DENY:
            self.deny.append(rule)
        elif rule.behavior == PermissionBehavior.ASK:
            self.ask.append(rule)

    def find_matching_rule(
        self,
        value: str,
        behavior: PermissionBehavior,
    ) -> Optional[PermissionRule]:
        """查找匹配的规则"""
        rules = {
            PermissionBehavior.ALLOW: self.allow,
            PermissionBehavior.DENY: self.deny,
            PermissionBehavior.ASK: self.ask,
        }.get(behavior, [])

        for rule in rules:
            if rule.matches(value):
                return rule
        return None


@dataclass
class AdditionalWorkingDirectory:
    """额外工作目录"""
    path: str
    permissions: Set[str] = field(default_factory=set)
    is_read_only: bool = False


@dataclass
class PermissionContext:
    """
    权限上下文

    包含所有权限检查所需的信息。
    参考 ClaudeCode 的 ToolPermissionContext 设计。
    """
    mode: PermissionMode = PermissionMode.DEFAULT
    additional_working_directories: Dict[str, AdditionalWorkingDirectory] = field(default_factory=dict)
    always_allow_rules: Dict[str, ToolPermissionRules] = field(default_factory=dict)
    always_deny_rules: Dict[str, ToolPermissionRules] = field(default_factory=dict)
    always_ask_rules: Dict[str, ToolPermissionRules] = field(default_factory=dict)
    is_bypass_permissions_mode_available: bool = False
    is_auto_mode_available: bool = False
    stripped_dangerous_rules: Optional[Dict[str, ToolPermissionRules]] = None
    should_avoid_permission_prompts: bool = False
    await_automated_checks_before_dialog: bool = False
    pre_plan_mode: Optional[PermissionMode] = None

    def is_bypass_mode(self) -> bool:
        """是否为绕过模式"""
        return self.mode == PermissionMode.BYPASS

    def is_auto_mode(self) -> bool:
        """是否为自动模式"""
        return self.mode == PermissionMode.AUTO

    def is_plan_mode(self) -> bool:
        """是否为计划模式"""
        return self.mode == PermissionMode.PLAN

    def is_default_mode(self) -> bool:
        """是否为默认模式"""
        return self.mode == PermissionMode.DEFAULT

    def get_working_directory_permissions(self, path: str) -> Set[str]:
        """获取工作目录的权限"""
        normalized = str(Path(path).resolve())
        for wd_path, wd in self.additional_working_directories.items():
            if normalized.startswith(wd_path):
                return wd.permissions
        return set()

    def is_path_in_working_directory(self, path: str) -> bool:
        """检查路径是否在工作目录中"""
        normalized = str(Path(path).resolve())
        return any(
            normalized.startswith(wd_path)
            for wd_path in self.additional_working_directories
        )


def get_empty_permission_context() -> PermissionContext:
    """创建空的权限上下文"""
    return PermissionContext()


class PermissionChecker:
    """
    权限检查器

    执行权限检查逻辑。
    """

    def __init__(self, context: PermissionContext):
        self.context = context

    async def check_tool_permission(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        tool_info: Optional[Dict[str, Any]] = None,
    ) -> PermissionResult:
        """
        检查工具权限

        Args:
            tool_name: 工具名称
            input_data: 输入数据
            tool_info: 工具信息（包含MCP信息等）

        Returns:
            权限检查结果
        """
        if self.context.is_bypass_mode():
            return PermissionResult.allow()

        if tool_info and tool_info.get("mcp_info"):
            return await self._check_mcp_tool_permission(
                tool_name,
                input_data,
                tool_info["mcp_info"],
            )

        deny_rule = self._find_deny_rule(tool_name)
        if deny_rule:
            return PermissionResult.deny(
                message=deny_rule.message or f"Tool '{tool_name}' is denied by rule"
            )

        ask_rule = self._find_ask_rule(tool_name)
        if ask_rule:
            return PermissionResult.ask(
                message=ask_rule.message or f"Tool '{tool_name}' requires confirmation"
            )

        allow_rule = self._find_allow_rule(tool_name)
        if allow_rule:
            return PermissionResult.allow()

        if self.context.is_auto_mode():
            return PermissionResult.allow()

        return PermissionResult.ask(
            message=f"Tool '{tool_name}' requires confirmation"
        )

    async def _check_mcp_tool_permission(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        mcp_info: Dict[str, Any],
    ) -> PermissionResult:
        """检查MCP工具权限"""
        server_name = mcp_info.get("server_name", "")

        server_deny = self._find_deny_rule(f"mcp__{server_name}")
        if server_deny:
            return PermissionResult.deny(
                message=server_deny.message or f"MCP server '{server_name}' is denied"
            )

        tool_deny = self._find_deny_rule(f"mcp__{server_name}__{tool_name}")
        if tool_deny:
            return PermissionResult.deny(
                message=tool_deny.message or f"MCP tool '{tool_name}' is denied"
            )

        server_ask = self._find_ask_rule(f"mcp__{server_name}")
        if server_ask:
            return PermissionResult.ask(
                message=server_ask.message or f"MCP server '{server_name}' requires confirmation"
            )

        tool_ask = self._find_ask_rule(f"mcp__{server_name}__{tool_name}")
        if tool_ask:
            return PermissionResult.ask(
                message=tool_ask.message or f"MCP tool '{tool_name}' requires confirmation"
            )

        return PermissionResult.passthrough(
            message=f"MCP tool '{tool_name}' from server '{server_name}' requires permission"
        )

    def _find_deny_rule(self, tool_name: str) -> Optional[PermissionRule]:
        """查找拒绝规则"""
        for source, rules in self.context.always_deny_rules.items():
            rule = rules.find_matching_rule(tool_name, PermissionBehavior.DENY)
            if rule:
                return rule
        return None

    def _find_ask_rule(self, tool_name: str) -> Optional[PermissionRule]:
        """查找询问规则"""
        for source, rules in self.context.always_ask_rules.items():
            rule = rules.find_matching_rule(tool_name, PermissionBehavior.ASK)
            if rule:
                return rule
        return None

    def _find_allow_rule(self, tool_name: str) -> Optional[PermissionRule]:
        """查找允许规则"""
        for source, rules in self.context.always_allow_rules.items():
            rule = rules.find_matching_rule(tool_name, PermissionBehavior.ALLOW)
            if rule:
                return rule
        return None

    async def check_file_permission(
        self,
        file_path: str,
        operation: str,
    ) -> PermissionResult:
        """
        检查文件权限

        Args:
            file_path: 文件路径
            operation: 操作类型（read/write/delete）

        Returns:
            权限检查结果
        """
        if self.context.is_bypass_mode():
            return PermissionResult.allow()

        normalized = str(Path(file_path).resolve())

        for wd_path, wd in self.context.additional_working_directories.items():
            if normalized.startswith(wd_path):
                if wd.is_read_only and operation in ("write", "delete"):
                    return PermissionResult.deny(
                        message=f"Directory '{wd_path}' is read-only"
                    )
                if operation not in wd.permissions and "*" not in wd.permissions:
                    return PermissionResult.ask(
                        message=f"Operation '{operation}' not allowed in '{wd_path}'"
                    )

        rule_pattern = f"{operation}({file_path})"
        deny_rule = self._find_deny_rule(rule_pattern)
        if deny_rule:
            return PermissionResult.deny(message=deny_rule.message)

        return PermissionResult.allow()


class PermissionManager:
    """
    权限管理器

    管理权限上下文和规则。
    """

    def __init__(self):
        self._contexts: Dict[str, PermissionContext] = {}
        self._default_context = get_empty_permission_context()

    def get_context(self, session_id: str = "default") -> PermissionContext:
        """获取权限上下文"""
        return self._contexts.get(session_id, self._default_context)

    def set_context(self, session_id: str, context: PermissionContext) -> None:
        """设置权限上下文"""
        self._contexts[session_id] = context

    def create_context(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        working_directories: Optional[List[str]] = None,
        allow_tools: Optional[List[str]] = None,
        deny_tools: Optional[List[str]] = None,
        ask_tools: Optional[List[str]] = None,
    ) -> PermissionContext:
        """
        创建权限上下文

        Args:
            mode: 权限模式
            working_directories: 工作目录列表
            allow_tools: 允许的工具列表
            deny_tools: 拒绝的工具列表
            ask_tools: 需要询问的工具列表

        Returns:
            新的权限上下文
        """
        context = PermissionContext(mode=mode)

        if working_directories:
            for wd in working_directories:
                context.additional_working_directories[wd] = AdditionalWorkingDirectory(
                    path=wd,
                    permissions={"read", "write", "delete"},
                )

        if allow_tools:
            rules = ToolPermissionRules()
            for tool in allow_tools:
                rules.add_rule(PermissionRule(
                    pattern=tool,
                    behavior=PermissionBehavior.ALLOW,
                    source=RuleSource.USER,
                ))
            context.always_allow_rules["user"] = rules

        if deny_tools:
            rules = ToolPermissionRules()
            for tool in deny_tools:
                rules.add_rule(PermissionRule(
                    pattern=tool,
                    behavior=PermissionBehavior.DENY,
                    source=RuleSource.USER,
                ))
            context.always_deny_rules["user"] = rules

        if ask_tools:
            rules = ToolPermissionRules()
            for tool in ask_tools:
                rules.add_rule(PermissionRule(
                    pattern=tool,
                    behavior=PermissionBehavior.ASK,
                    source=RuleSource.USER,
                ))
            context.always_ask_rules["user"] = rules

        return context

    def get_checker(self, session_id: str = "default") -> PermissionChecker:
        """获取权限检查器"""
        return PermissionChecker(self.get_context(session_id))


_permission_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    """获取权限管理器单例"""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager
