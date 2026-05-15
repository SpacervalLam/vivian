import asyncio
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic
from abc import ABC, abstractmethod
from enum import Enum
import uuid
from loguru import logger

Input = TypeVar('Input')
Output = TypeVar('Output')
Progress = TypeVar('Progress')

class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"

class PermissionResult:
    def __init__(self, behavior: PermissionBehavior, updated_input: Dict[str, Any] = None):
        self.behavior = behavior
        self.updated_input = updated_input or {}

class ValidationResult:
    def __init__(self, result: bool, message: str = "", error_code: int = 0):
        self.result = result
        self.message = message
        self.error_code = error_code

class ToolProgressData:
    def __init__(self, **kwargs):
        self.type = kwargs.get('type', 'progress')
        self.message = kwargs.get('message', '')
        self.percentage = kwargs.get('percentage', 0)

class ToolResult(Generic[Output]):
    def __init__(self, data: Output, new_messages: List = None, context_modifier: Callable = None):
        self.data = data
        self.new_messages = new_messages or []
        self.context_modifier = context_modifier

class ToolUseContext:
    def __init__(self):
        self.options = {
            'commands': [],
            'debug': False,
            'main_loop_model': '',
            'tools': [],
            'verbose': False,
            'thinking_config': {},
            'mcp_clients': [],
            'mcp_resources': {},
            'is_non_interactive_session': False,
            'agent_definitions': {'active_agents': [], 'all_agents': []},
            'max_budget_usd': None,
            'custom_system_prompt': None,
            'append_system_prompt': None
        }
        self.abort_controller = asyncio.Event()
        self.read_file_state = {}
        self.get_app_state = None
        self.set_app_state = None
        self.user_modified = False
        self.messages = []

class BaseTool(ABC, Generic[Input, Output, Progress]):
    def __init__(self):
        self.name = self.__class__.__name__
        self.aliases = []
        self.search_hint = ""
        
    @abstractmethod
    async def call(
        self,
        args: Input,
        context: ToolUseContext,
        can_use_tool: Callable,
        parent_message: Any = None,
        on_progress: Callable = None
    ) -> ToolResult[Output]:
        pass
    
    @abstractmethod
    async def description(
        self,
        input: Input,
        options: Dict[str, Any]
    ) -> str:
        pass
    
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        pass
    
    def output_schema(self) -> Optional[Dict[str, Any]]:
        return None
    
    def is_enabled(self) -> bool:
        return True
    
    def is_concurrency_safe(self, input: Input) -> bool:
        return False
    
    def is_read_only(self, input: Input) -> bool:
        return False
    
    def is_destructive(self, input: Input) -> bool:
        return False
    
    def interrupt_behavior(self) -> str:
        return 'block'
    
    def is_search_or_read_command(self, input: Input) -> Dict[str, bool]:
        return {'is_search': False, 'is_read': False, 'is_list': False}
    
    def is_open_world(self, input: Input) -> bool:
        return False
    
    def requires_user_interaction(self) -> bool:
        return False
    
    def is_mcp(self) -> bool:
        return False
    
    def is_lsp(self) -> bool:
        return False
    
    def should_defer(self) -> bool:
        return False
    
    def always_load(self) -> bool:
        return False
    
    async def validate_input(self, input: Input, context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)
    
    async def check_permissions(self, input: Input, context: ToolUseContext) -> PermissionResult:
        return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=input)
    
    def get_path(self, input: Input) -> Optional[str]:
        return None
    
    def prompt(self, options: Dict[str, Any]) -> str:
        return f"Use {self.name} tool"
    
    def user_facing_name(self, input: Optional[Input] = None) -> str:
        return self.name
    
    def get_tool_use_summary(self, input: Optional[Input] = None) -> Optional[str]:
        return None
    
    def get_activity_description(self, input: Optional[Input] = None) -> Optional[str]:
        return None
    
    def to_auto_classifier_input(self, input: Input) -> Any:
        return ""
    
    def map_tool_result_to_tool_result_block_param(self, content: Output, tool_use_id: str) -> Dict[str, Any]:
        return {
            'type': 'tool_result',
            'tool_use_id': tool_use_id,
            'content': [{'type': 'text', 'text': str(content)}]
        }

class ToolBuilder:
    @staticmethod
    def build(tool_def: Dict[str, Any]) -> BaseTool:
        """从工具定义构建工具实例"""
        class DynamicTool(BaseTool):
            def __init__(self):
                super().__init__()
                self.name = tool_def.get('name', 'DynamicTool')
                self.aliases = tool_def.get('aliases', [])
                self.search_hint = tool_def.get('search_hint', '')
                
            async def call(self, args, context, can_use_tool, parent_message=None, on_progress=None):
                call_fn = tool_def.get('call')
                if call_fn:
                    return await call_fn(args, context, can_use_tool, parent_message, on_progress)
                return ToolResult(data={})
            
            async def description(self, input, options):
                desc_fn = tool_def.get('description')
                if desc_fn:
                    return await desc_fn(input, options)
                return f"Use {self.name}"
            
            def input_schema(self):
                return tool_def.get('input_schema', {'type': 'object', 'properties': {}})
            
            def is_enabled(self):
                fn = tool_def.get('is_enabled')
                return fn() if fn else True
            
            def is_concurrency_safe(self, input):
                fn = tool_def.get('is_concurrency_safe')
                return fn(input) if fn else False
            
            def is_read_only(self, input):
                fn = tool_def.get('is_read_only')
                return fn(input) if fn else False
            
            def is_destructive(self, input):
                fn = tool_def.get('is_destructive')
                return fn(input) if fn else False
            
            async def validate_input(self, input, context):
                fn = tool_def.get('validate_input')
                if fn:
                    return await fn(input, context)
                return ValidationResult(result=True)
            
            async def check_permissions(self, input, context):
                fn = tool_def.get('check_permissions')
                if fn:
                    return await fn(input, context)
                return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=input)
        
        return DynamicTool()

class ToolRegistry:
    _instance = None
    _tools = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register_tool(cls, tool: BaseTool):
        """注册工具"""
        cls._tools[tool.name] = tool
        for alias in tool.aliases:
            cls._tools[alias] = tool
    
    @classmethod
    def get_tool(cls, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return cls._tools.get(name)
    
    @classmethod
    def list_tools(cls) -> List[BaseTool]:
        """获取所有工具列表"""
        return list({tool.name: tool for tool in cls._tools.values()}.values())
    
    @classmethod
    def search_tools(cls, query: str) -> List[BaseTool]:
        """搜索工具"""
        query_lower = query.lower()
        results = []
        seen = set()
        
        for name, tool in cls._tools.items():
            if tool.name in seen:
                continue
            seen.add(tool.name)
            
            if (query_lower in tool.name.lower() or 
                query_lower in tool.search_hint.lower() or
                any(query_lower in alias.lower() for alias in tool.aliases)):
                results.append(tool)
        
        return results

class ToolCallManager:
    def __init__(self):
        self._tool_results = {}
        self.permission_manager = None
        self._tool_list_tool = None
    
    def set_permission_manager(self, permission_manager):
        self.permission_manager = permission_manager
    
    def get_system_prompt(self) -> str:
        """
        获取包含工具信息的系统提示

        Returns:
            系统提示字符串
        """
        if self._tool_list_tool is None:
            return "工具系统未初始化"

        return (
            "You can call tools to perform system operations. To save tokens,\n"
            "if you need to see complete tool parameters, please call tool_list or request injection of complete tool documentation (file: core/tools/TOOLS.md).\n"
            "When calling tools, return JSON format: {\"tool\": \"tool_name\", \"arguments\": {\"param_name\": \"value\"}}.\n"
            "Example: {\"tool\": \"open_application\", \"arguments\": {\"app_path\": \"C:\\\\Windows\\\\notepad.exe\"}}\n"
        )

    async def execute_tool(
        self,
        tool: BaseTool,
        input_data: Dict[str, Any],
        context: ToolUseContext
    ) -> ToolResult:
        """执行工具调用"""
        tool_use_id = str(uuid.uuid4())
        
        # 验证输入
        validation = await tool.validate_input(input_data, context)
        if not validation.result:
            return ToolResult(data={'error': validation.message, 'error_code': validation.error_code})
        
# 全局工具使用权限检查
        if self.permission_manager:
            from core.permission_system import PermissionScope

            permission = await self.permission_manager.check_permission(
                PermissionScope.TOOL_USE,
                {
                    'tool_name': tool.name,
                    'input_data': input_data,
                    'is_interactive': not context.options.get('is_non_interactive_session', False),
                },
            )
            if permission.is_denied():
                return ToolResult(data={'error': 'Permission denied'})
            elif permission.requires_confirmation():
                return ToolResult(data={'error': 'User confirmation required'})

        # 工具自身权限检查
        permission = await tool.check_permissions(input_data, context)
        if permission.behavior == PermissionBehavior.DENY:
            return ToolResult(data={'error': 'Permission denied'})
        elif permission.behavior == PermissionBehavior.ASK:
            return ToolResult(data={'error': 'User confirmation required'})
        
        # 更新输入（权限系统可能修改输入）
        input_data = permission.updated_input
        
        # 执行工具
        async def can_use_tool(_tool, _input, _context, _assistant_message, _tool_use_id, _force_decision):
            return {'behavior': 'allow'}
        
        result = await tool.call(
            args=input_data,
            context=context,
            can_use_tool=can_use_tool,
            on_progress=lambda progress: self._on_tool_progress(tool_use_id, progress)
        )
        
        self._tool_results[tool_use_id] = result
        return result
    
    def _on_tool_progress(self, tool_use_id: str, progress: ToolProgressData):
        """处理工具进度"""
        logger.debug(f"Tool {tool_use_id} progress: {progress.message} ({progress.percentage}%)")
    
    def get_tool_result(self, tool_use_id: str) -> Optional[ToolResult]:
        """获取工具执行结果"""
        return self._tool_results.get(tool_use_id)

def build_tool(tool_def: Dict[str, Any]) -> BaseTool:
    """便捷函数：从定义构建工具"""
    return ToolBuilder.build(tool_def)

def register_tool(tool: BaseTool):
    """便捷函数：注册工具"""
    ToolRegistry.register_tool(tool)

def get_tool(name: str) -> Optional[BaseTool]:
    """便捷函数：获取工具"""
    return ToolRegistry.get_tool(name)

def list_tools() -> List[BaseTool]:
    """便捷函数：获取所有工具"""
    return ToolRegistry.list_tools()
