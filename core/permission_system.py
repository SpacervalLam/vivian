import asyncio
from typing import Any, Dict, List, Optional, Callable, Set
from enum import Enum
import uuid

class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    AUTO = "auto"
    BYPASS = "bypass"

class PermissionScope(Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    EXECUTE_COMMAND = "execute_command"
    NETWORK_ACCESS = "network_access"
    SYSTEM_ACCESS = "system_access"
    TOOL_USE = "tool_use"
    MODIFY_SETTINGS = "modify_settings"

class PermissionRule:
    def __init__(
        self,
        scope: PermissionScope,
        behavior: PermissionBehavior,
        conditions: Optional[Dict[str, Any]] = None,
        description: str = ""
    ):
        self.scope = scope
        self.behavior = behavior
        self.conditions = conditions or {}
        self.description = description
        self.id = str(uuid.uuid4())
    
    def matches(self, context: Dict[str, Any]) -> bool:
        """检查规则是否匹配当前上下文"""
        for key, value in self.conditions.items():
            if context.get(key) != value:
                return False
        return True

class PermissionResult:
    def __init__(
        self,
        behavior: PermissionBehavior,
        updated_input: Dict[str, Any] = None,
        rule_id: Optional[str] = None,
        message: str = ""
    ):
        self.behavior = behavior
        self.updated_input = updated_input or {}
        self.rule_id = rule_id
        self.message = message
    
    def is_allowed(self) -> bool:
        return self.behavior in [PermissionBehavior.ALLOW, PermissionBehavior.BYPASS]
    
    def is_denied(self) -> bool:
        return self.behavior == PermissionBehavior.DENY
    
    def requires_confirmation(self) -> bool:
        return self.behavior == PermissionBehavior.ASK

class PermissionDenial:
    def __init__(
        self,
        scope: PermissionScope,
        reason: str,
        context: Dict[str, Any],
        timestamp: Optional[str] = None
    ):
        self.scope = scope
        self.reason = reason
        self.context = context
        self.timestamp = timestamp or asyncio.get_event_loop().time()
        self.id = str(uuid.uuid4())

class PermissionManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def initialize(self):
        """初始化权限管理器"""
        if self._initialized:
            return
        
        self._rules: List[PermissionRule] = []
        self._denials: List[PermissionDenial] = []
        self._allowed_scopes: Set[PermissionScope] = set()
        self._denied_scopes: Set[PermissionScope] = set()
        
        # 加载默认规则
        self._load_default_rules()
        
        self._initialized = True
    
    def _load_default_rules(self):
        """加载默认权限规则"""
        from utils.config_manager import config_manager
        
        # 从配置加载权限模式
        permission_mode = config_manager.get("security.permission_mode", "default")
        
        if permission_mode == "auto":
            self._allowed_scopes = set(PermissionScope)
        elif permission_mode == "bypass":
            self._allowed_scopes = set(PermissionScope)
        else:
            # 默认模式：允许基本操作，敏感操作需要确认
            self._allowed_scopes = {
                PermissionScope.READ_FILE,
                PermissionScope.TOOL_USE
            }
            self._denied_scopes = {
                PermissionScope.WRITE_FILE,
                PermissionScope.EXECUTE_COMMAND,
                PermissionScope.MODIFY_SETTINGS
            }
            
            # 添加默认规则
            self.add_rule(PermissionRule(
                scope=PermissionScope.READ_FILE,
                behavior=PermissionBehavior.ALLOW,
                description="允许读取文件"
            ))
            
            self.add_rule(PermissionRule(
                scope=PermissionScope.WRITE_FILE,
                behavior=PermissionBehavior.ASK,
                description="写入文件需要用户确认"
            ))
            
            self.add_rule(PermissionRule(
                scope=PermissionScope.EXECUTE_COMMAND,
                behavior=PermissionBehavior.ASK,
                description="执行命令需要用户确认"
            ))
            
            self.add_rule(PermissionRule(
                scope=PermissionScope.NETWORK_ACCESS,
                behavior=PermissionBehavior.ALLOW,
                description="允许网络访问"
            ))
    
    def add_rule(self, rule: PermissionRule) -> None:
        """添加权限规则"""
        self._rules.append(rule)
    
    def remove_rule(self, rule_id: str) -> None:
        """移除权限规则"""
        self._rules = [r for r in self._rules if r.id != rule_id]
    
    def get_rules(self, scope: Optional[PermissionScope] = None) -> List[PermissionRule]:
        """获取权限规则"""
        if scope:
            return [r for r in self._rules if r.scope == scope]
        return self._rules
    
    async def check_permission(
        self,
        scope: PermissionScope,
        context: Optional[Dict[str, Any]] = None
    ) -> PermissionResult:
        """检查权限"""
        context = context or {}
        
        # 检查全局设置
        if scope in self._allowed_scopes:
            return PermissionResult(
                behavior=PermissionBehavior.ALLOW,
                message="权限已在全局允许列表中"
            )
        
        if scope in self._denied_scopes:
            denial = PermissionDenial(
                scope=scope,
                reason="权限在全局拒绝列表中",
                context=context
            )
            self._denials.append(denial)
            return PermissionResult(
                behavior=PermissionBehavior.DENY,
                message="权限被拒绝"
            )
        
        # 检查规则
        matching_rules = [rule for rule in self._rules if rule.scope == scope and rule.matches(context)]
        
        if matching_rules:
            # 按优先级排序（简单实现：最后添加的规则优先）
            rule = matching_rules[-1]
            
            if rule.behavior == PermissionBehavior.DENY:
                denial = PermissionDenial(
                    scope=scope,
                    reason=rule.description,
                    context=context
                )
                self._denials.append(denial)
            
            return PermissionResult(
                behavior=rule.behavior,
                rule_id=rule.id,
                message=rule.description
            )
        
        # 默认行为：询问用户
        return PermissionResult(
            behavior=PermissionBehavior.ASK,
            message="需要用户确认"
        )
    
    async def check_permissions(
        self,
        scopes: List[PermissionScope],
        context: Optional[Dict[str, Any]] = None
    ) -> List[PermissionResult]:
        """检查多个权限"""
        results = []
        for scope in scopes:
            result = await self.check_permission(scope, context)
            results.append(result)
        return results
    
    def set_scope_allowed(self, scope: PermissionScope, allowed: bool) -> None:
        """设置权限范围的全局允许/拒绝状态"""
        if allowed:
            self._allowed_scopes.add(scope)
            self._denied_scopes.discard(scope)
        else:
            self._denied_scopes.add(scope)
            self._allowed_scopes.discard(scope)
    
    def get_denials(self, scope: Optional[PermissionScope] = None) -> List[PermissionDenial]:
        """获取权限拒绝记录"""
        if scope:
            return [d for d in self._denials if d.scope == scope]
        return self._denials
    
    def clear_denials(self) -> None:
        """清空权限拒绝记录"""
        self._denials.clear()

class PermissionContext:
    """权限检查上下文"""
    
    def __init__(self):
        self.user_id = None
        self.session_id = None
        self.tool_name = None
        self.input_data = {}
        self.is_interactive = True
        self.requested_scopes: List[PermissionScope] = []
    
    def add_scope(self, scope: PermissionScope) -> None:
        """添加请求的权限范围"""
        if scope not in self.requested_scopes:
            self.requested_scopes.append(scope)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'user_id': self.user_id,
            'session_id': self.session_id,
            'tool_name': self.tool_name,
            'input_data': self.input_data,
            'is_interactive': self.is_interactive,
            'requested_scopes': [s.value for s in self.requested_scopes]
        }

class PermissionPromptBuilder:
    """权限提示词构建器"""
    
    @staticmethod
    def build_permission_request(
        scope: PermissionScope,
        context: Dict[str, Any],
        description: str = ""
    ) -> str:
        """构建权限请求提示词"""
        scope_descriptions = {
            PermissionScope.READ_FILE: "读取文件",
            PermissionScope.WRITE_FILE: "写入文件",
            PermissionScope.EXECUTE_COMMAND: "执行命令",
            PermissionScope.NETWORK_ACCESS: "访问网络",
            PermissionScope.SYSTEM_ACCESS: "访问系统资源",
            PermissionScope.TOOL_USE: "使用工具",
            PermissionScope.MODIFY_SETTINGS: "修改设置"
        }
        
        prompt = f"需要权限：{scope_descriptions.get(scope, scope.value)}"
        
        if description:
            prompt += f"\n说明：{description}"
        
        if context:
            prompt += "\n上下文信息："
            for key, value in context.items():
                prompt += f"\n  - {key}: {value}"
        
        return prompt

# 创建全局权限管理器实例
permission_manager = PermissionManager()

def initialize_permissions():
    """初始化权限系统"""
    permission_manager.initialize()

async def check_permission(
    scope: PermissionScope,
    context: Optional[Dict[str, Any]] = None
) -> PermissionResult:
    """便捷函数：检查权限"""
    return await permission_manager.check_permission(scope, context)

async def check_permissions(
    scopes: List[PermissionScope],
    context: Optional[Dict[str, Any]] = None
) -> List[PermissionResult]:
    """便捷函数：检查多个权限"""
    return await permission_manager.check_permissions(scopes, context)
