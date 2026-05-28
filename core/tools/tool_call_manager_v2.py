"""
Tool Call Manager - Tool system implementation

Core Features:
- Manage all available tools
- Handle tool list generation
- Execute tool calls
- Support multi-step tool calls
- Interact with AI models
- Integrate permission context
"""

import json
import os
import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from core.tools.v2 import (
    ToolSystem,
    PermissionContext,
    ToolResult,
    ToolUseContext,
    ExecutionResult,
    get_tool_system,
)
from .execution import execute_tool_use


class ToolCallStatus(Enum):
    """Tool call status"""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    PERMISSION_REQUIRED = "permission_required"
    NON_BLOCKING = "non_blocking"


NON_BLOCKING_TOOLS = {
    "open_application",
    "open_url",
    "open_folder",
    "set_timer",
    "take_screenshot",
}
"""Non-blocking tool list - these tools return immediately after starting without waiting for completion"""


@dataclass
class ToolCall:
    """Tool call record"""
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    status: ToolCallStatus = ToolCallStatus.PENDING


@dataclass
class ToolCallResult:
    """Tool call result"""
    success: bool
    result: Any
    tool_name: str
    tool_call_id: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False


class ToolListTool:
    """Tool list tool - a special meta tool for getting available tools list"""

    def __init__(self, tool_system: ToolSystem):
        self.name = "tool_list"
        self.description = (
            "A special meta tool to get the list of all available tools and their usage instructions. "
            "When you need to perform system operations (like launching apps, setting wallpaper, searching files, etc.), "
            "you should call this tool to get the list of available tools. "
            "Then select the appropriate tool based on user requirements."
        )
        self._tool_system = tool_system
        self._definition_loader = None
        self._load_definition_loader()

    def _load_definition_loader(self):
        """Load tool definition loader for dynamic tool loading from Markdown"""
        logger.info("[ToolListTool] Tool definition loader is deprecated, using built-in tools only")

    def load_from_md(self, file_path: str) -> bool:
        """
        Load tool definitions from Markdown file
        
        Args:
            file_path: Path to Markdown file containing tool definitions
        
        Returns:
            True if loaded successfully
        """
        if not self._definition_loader:
            logger.warning("[ToolListTool] Definition loader not available")
            return False
        
        return self._definition_loader.load_from_file(file_path)
    
    def load_from_md_directory(self, dir_path: str) -> int:
        """
        Load tool definitions from all Markdown files in a directory
        
        Args:
            dir_path: Directory path containing tool definition files
        
        Returns:
            Number of tools loaded
        """
        if not self._definition_loader:
            logger.warning("[ToolListTool] Definition loader not available")
            return 0
        
        return self._definition_loader.load_from_directory(dir_path)
    
    def get_tools_for_ai(self) -> str:
        """Get formatted tool list for AI (compact version, saves tokens)"""
        if self._tool_system is None:
            return "Tool system not initialized"

        tools = self._tool_system.get_anthropic_tools()
        if not tools:
            return "No tools available"

        lines = ["# Available Tools\n"]
        lines.append(f"Total: {len(tools)} tools\n")
        lines.append("To view detailed description of a tool, call tool_list with tool_name parameter\n")

        for tool in tools:
            lines.append(f"- {tool['name']}: {tool['description']}")

        return "\n".join(lines)

    def export_to_md(self, file_path: str) -> str:
        """Export current tool list to Markdown file"""
        content = self.get_tools_for_ai()
        try:
            dirpath = os.path.dirname(file_path)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"[ToolListTool] Tool documentation exported to: {file_path}")
        except Exception as e:
            logger.error(f"[ToolListTool] Failed to export tool documentation: {e}")
        return content

    def get_tool_md(self, tool_name: str) -> str:
        """Get Markdown description for a single tool"""
        if self._tool_system is None:
            return "Tool system not initialized"

        tool = self._tool_system.get_tool(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}"

        lines = [f"## {tool.name}", f"Description: {tool.description}"]
        schema = tool.get_json_schema()
        params = schema.get('properties', {})
        if params:
            lines.append("Parameters:")
            for param_name, param_info in params.items():
                param_type = param_info.get('type', 'any')
                desc = param_info.get('description', '')
                lines.append(f"  - {param_name} ({param_type}): {desc}")

        return "\n".join(lines)

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """Get tool list (JSON format)"""
        if self._tool_system is None:
            return []

        return self._tool_system.get_anthropic_tools()

    def get_tools_schema(self) -> Dict[str, Any]:
        """Return concise JSON schema for injection into LLM prompts"""
        if self._tool_system is None:
            return {}

        schema = {}
        tools = self._tool_system.list_tools()
        for tool in tools:
            params = {}
            json_schema = tool.get_json_schema()
            for p_name, p_info in json_schema.get('properties', {}).items():
                params[p_name] = {
                    'type': p_info.get('type', 'string'),
                    'required': p_name in json_schema.get('required', []),
                    'description': p_info.get('description', '')
                }
            schema[tool.name] = {
                'description': tool.description,
                'parameters': params
            }
        return schema

    def run(self) -> str:
        """Execute tool (return tool list)"""
        return self.get_tools_for_ai()


class ToolCallManager:
    """
    Tool Call Manager
    
    Responsible for:
    1. Managing tool list
    2. Parsing AI function call requests
    3. Executing tool calls (with permission context integration)
    4. Handling multi-step tool calls
    5. Formatting tool results for AI
    """

    def __init__(
        self,
        tool_system: Optional[ToolSystem] = None,
        permission_context: Optional[PermissionContext] = None,
    ):
        self._tool_system = tool_system or get_tool_system()
        self._permission_context = permission_context
        self._tool_list_tool = None
        self._tool_call_history: List[ToolCall] = []
        self._max_iterations = 10

        if self._tool_system:
            self._tool_list_tool = ToolListTool(self._tool_system)

        logger.debug("[ToolCallManagerV2] Tool call manager V2 initialized")

    def set_tool_system(self, tool_system: ToolSystem):
        """Set tool system"""
        self._tool_system = tool_system
        if self._tool_system:
            self._tool_list_tool = ToolListTool(self._tool_system)
        logger.debug("[ToolCallManagerV2] Tool system set")

    def set_permission_context(self, permission_context: PermissionContext):
        """Set permission context"""
        self._permission_context = permission_context
        logger.debug("[ToolCallManagerV2] Permission context set")

    def set_max_iterations(self, max_iterations: int):
        """Set maximum iterations"""
        self._max_iterations = max(max_iterations, 1)
        logger.debug(f"[ToolCallManagerV2] Maximum iterations set to: {self._max_iterations}")

    def _tool_requires_parameters(self, tool_name: str) -> bool:
        """Check if a tool requires parameters"""
        if self._tool_system is None:
            return True
        
        tool = self._tool_system.get_tool(tool_name)
        if not tool:
            return True
        
        try:
            schema = tool.get_json_schema()
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            return len(properties) > 0 or len(required) > 0
        except Exception as e:
            logger.error(f"[ToolCallManagerV2] Failed to check tool parameters: {e}")
            return True

    def get_system_prompt(self, user_input: str = "") -> str:
        """Get system prompt with tool information - optimized for token efficiency"""
        if self._tool_list_tool is None:
            return "Tool system not initialized"

        tools_list = self._tool_list_tool.get_tools_for_ai()

        return (
            f"{tools_list}\n\n"
            "## Tool Usage\n"
            "Use tools for system operations. MUST return tool call JSON for actions like opening apps/files/urls.\n\n"
            "## Output Format (JSON Only)\n"
            "Chat: {\"text\":\"reply\",\"motion\":\"idle\",\"expression\":\"\",\"importance_user\":0.5}\n"
            "Tool: {\"text\":\"Explanation\",\"tool\":\"name\",\"arguments\":{\"param\":\"value\"}}\n"
            "Multi: [{\"tool\":\"t1\",...},{\"tool\":\"t2\",...}]\n\n"
            "Note: Same language as user, text field first for streaming."
        )

    _TOOL_ALIASES = {
        "open_app": "open_application",
        "close_app": "close_application",
        "open_dir": "open_folder",
        "launch_app": "open_application",
        "start_app": "open_application"
    }

    def parse_tool_calls(self, ai_response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from AI response - supports multiple JSON objects and arrays"""
        tool_calls = []

        try:
            json_objects = self._extract_all_json_objects(ai_response)
            
            for data in json_objects:
                if "tool" in data and "arguments" in data:
                    tool_calls.append(data)
                elif "tool_calls" in data:
                    for tc in data["tool_calls"]:
                        tool_calls.append({
                            "tool": tc.get("name", tc.get("tool")),
                            "arguments": tc.get("args", tc.get("arguments", {}))
                        })
            
            if not tool_calls:
                try:
                    data = json.loads(ai_response)
                    if isinstance(data, dict):
                        if "tool" in data and "arguments" in data:
                            tool_calls.append(data)
                        elif "tool_calls" in data:
                            for tc in data["tool_calls"]:
                                tool_calls.append({
                                    "tool": tc.get("name", tc.get("tool")),
                                    "arguments": tc.get("args", tc.get("arguments", {}))
                                })
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "tool" in item and "arguments" in item:
                                tool_calls.append(item)
                except json.JSONDecodeError:
                    pass

            if not tool_calls:
                import re
                pattern = r'(\w+)\s*\((.*?)\)'
                matches = re.findall(pattern, ai_response, re.DOTALL)
                for match in matches:
                    tool_name = match[0]
                    args_str = match[1]

                    args = {}
                    if args_str.strip():
                        kv_pattern = r'(\w+)\s*=\s*["\']?([^"\',\)]+)["\']?'
                        for kv_match in re.findall(kv_pattern, args_str):
                            args[kv_match[0]] = kv_match[1]

                        if not args and args_str.strip():
                            arg_value = args_str.strip().strip('\'"')
                            if tool_name in ["open_app", "open_application"]:
                                args["app_name"] = arg_value
                            elif tool_name in ["close_app", "close_application"]:
                                args["process_name"] = arg_value
                            elif tool_name in ["open_folder", "open_dir"]:
                                args["path"] = arg_value
                            elif tool_name in ["open_url"]:
                                args["url"] = arg_value

                    if tool_name != "tool_list":
                        tool_calls.append({
                            "tool": tool_name,
                            "arguments": args
                        })

        except Exception as e:
            logger.error(f"[ToolCallManagerV2] Failed to parse tool calls: {e}")

        return tool_calls

    async def execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_context: Optional[PermissionContext] = None,
    ) -> ToolCallResult:
        """Execute a single tool call"""
        if tool_name in self._TOOL_ALIASES:
            logger.info(f"[ToolCallManagerV2] Converting tool alias '{tool_name}' to actual tool name '{self._TOOL_ALIASES[tool_name]}'")
            tool_name = self._TOOL_ALIASES[tool_name]

        if tool_name == "open_application" and not arguments.get("app_path"):
            app_name = arguments.get("app_name", arguments.get("name", ""))
            if app_name:
                common_apps = {
                    "notepad": "notepad.exe",
                    "记事本": "notepad.exe",
                    "微信": "WeChat.exe",
                    "WeChat": "WeChat.exe",
                    "QQ": "QQ.exe",
                    "浏览器": "msedge.exe",
                    "Edge": "msedge.exe",
                    "Chrome": "chrome.exe",
                    "计算器": "calc.exe",
                    "Calculator": "calc.exe"
                }
                if app_name in common_apps:
                    arguments["app_path"] = common_apps[app_name]
                    logger.info(f"[ToolCallManagerV2] Auto-filled app path: {app_name} -> {arguments['app_path']}")
                else:
                    if "\\" in app_name or "/" in app_name or app_name.lower().endswith('.exe'):
                        arguments["app_path"] = app_name

        tool_call_id = f"call_{len(self._tool_call_history)}_{int(asyncio.get_event_loop().time() * 1000)}"

        try:
            if tool_name == "tool_list":
                if self._tool_list_tool:
                    requested_tool = arguments.get("tool") or arguments.get("name")
                    default_md = os.path.join(os.path.dirname(__file__), "TOOLS.md")
                    full_content = self._tool_list_tool.export_to_md(default_md)
                    schema = self._tool_list_tool.get_tools_schema()
                    if requested_tool:
                        single_md = self._tool_list_tool.get_tool_md(requested_tool)
                        single_schema = schema.get(requested_tool)
                        return ToolCallResult(
                            success=True,
                            result={
                                "file": default_md,
                                "full_content": full_content,
                                "tool": requested_tool,
                                "content": single_md,
                                "schema": single_schema
                            },
                            tool_name=tool_name,
                            tool_call_id=tool_call_id
                        )
                    else:
                        return ToolCallResult(
                            success=True,
                            result={"file": default_md, "content": full_content, "schema": schema},
                            tool_name=tool_name,
                            tool_call_id=tool_call_id
                        )
                else:
                    return ToolCallResult(
                        success=False,
                        result=None,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        error="Tool list tool not initialized"
                    )

            if self._tool_system is None:
                return ToolCallResult(
                    success=False,
                    result=None,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    error="Tool system not initialized"
                )

            ctx = permission_context or self._permission_context
            logger.info(f"[ToolCallManagerV2] Executing tool: {tool_name}, args: {arguments}, permission context: {ctx}")

            tool_use_context = ToolUseContext(
                permission_context=ctx,
                tools=self._tool_system,
            )

            result = await execute_tool_use(
                tool_name=tool_name,
                arguments=arguments,
                tool_system=self._tool_system,
                context=tool_use_context,
            )

            requires_confirmation = "需要用户确认" in str(result.data)
            
            return ToolCallResult(
                success=True,
                result=result.data,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error=None,
                requires_confirmation=requires_confirmation,
            )

        except Exception as e:
            logger.error(f"[ToolCallManagerV2] Unexpected error executing tool {tool_name}: {e}", exc_info=True)
            return ToolCallResult(
                success=False,
                result=None,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error=f"工具执行发生意外错误: {str(e)}"
            )

    async def _execute_non_blocking_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_context: Optional[PermissionContext] = None,
    ):
        """Execute non-blocking tool (in background)"""
        try:
            logger.info(f"[ToolCallManagerV2] Executing non-blocking tool in background: {tool_name}")
            await self.execute_tool_call(
                tool_name,
                arguments,
                permission_context=permission_context,
            )
            logger.info(f"[ToolCallManagerV2] Non-blocking tool {tool_name} completed")
        except Exception as e:
            logger.error(f"[ToolCallManagerV2] Non-blocking tool {tool_name} failed: {e}")
    
    async def _execute_parallel_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        permission_context: Optional[PermissionContext] = None,
    ) -> List[ToolCallResult]:
        """Execute multiple tool calls in parallel"""
        if not tool_calls:
            return []
        
        tasks = []
        for tc in tool_calls:
            tool_name = tc["tool"]
            arguments = tc["arguments"]
            
            task = self.execute_tool_call(
                tool_name,
                arguments,
                permission_context=permission_context,
            )
            tasks.append(task)
        
        logger.info(f"[ToolCallManagerV2] Waiting for {len(tasks)} parallel tasks to complete")
        results = await asyncio.gather(*tasks)
        logger.info(f"[ToolCallManagerV2] All parallel tasks completed")
        
        return results

    def _extract_immediate_response(self, ai_response: str) -> str:
        """Extract immediate response text from AI response (non-JSON part)"""
        try:
            if not ai_response or not ai_response.strip():
                return ""
            
            trimmed_response = ai_response.strip()
            
            # 尝试解析为 JSON 数组
            if trimmed_response.startswith('['):
                try:
                    data = json.loads(trimmed_response)
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            if isinstance(item, dict) and "text" in item:
                                return item["text"].strip()
                except json.JSONDecodeError:
                    pass
            
            # 使用与 _extract_all_json_objects 相同的逻辑找出所有 JSON 位置
            stack = []
            json_ranges = []
            start_idx = -1
            
            for i, char in enumerate(ai_response):
                if char == '{':
                    if not stack:
                        start_idx = i
                    stack.append(char)
                elif char == '}' and stack:
                    stack.pop()
                    if not stack:
                        json_ranges.append((start_idx, i + 1))
            
            if not json_ranges:
                return ai_response.strip()
            
            # 找出第一个 JSON 之前的文本
            first_json_start = json_ranges[0][0]
            immediate_text = ai_response[:first_json_start].strip()
            
            # 如果文本为空，尝试从第一个 JSON 中提取 text 字段
            if not immediate_text and len(json_ranges) > 0:
                first_json_end = json_ranges[0][1]
                first_json_str = ai_response[json_ranges[0][0]:first_json_end]
                try:
                    first_json = json.loads(first_json_str)
                    if "text" in first_json:
                        immediate_text = first_json["text"].strip()
                except:
                    pass
            
            # 如果还是空，找最后一个 JSON 之后的文本
            if not immediate_text and len(json_ranges) > 0:
                last_json_end = json_ranges[-1][1]
                immediate_text = ai_response[last_json_end:].strip()
            
            return immediate_text
        except Exception as e:
            logger.error(f"[ToolCallManagerV2] Failed to extract immediate response: {e}")
            return ai_response.strip()

    async def execute_multi_step(
        self,
        ai_generate_func,
        initial_prompt: str,
        max_steps: int = None,
        permission_context: Optional[PermissionContext] = None,
        on_immediate_response: Optional[Callable[[str], None]] = None,
    ) -> Tuple[str, List[ToolCall]]:
        """Execute multi-step tool calls
        
        Args:
            ai_generate_func: AI generation function
            initial_prompt: Initial prompt
            max_steps: Maximum iterations
            permission_context: Permission context
            on_immediate_response: Immediate response callback (for returning initial response before tool execution)
        
        Returns:
            Final response text and tool call history
        """
        if max_steps is None:
            max_steps = self._max_iterations

        current_prompt = initial_prompt
        self._tool_call_history = []
        injected_tools = set()
        immediate_response = ""

        for step in range(max_steps):
            logger.info(f"[ToolCallManagerV2] Executing step {step + 1}/{max_steps}")

            ai_response = await ai_generate_func(current_prompt)

            if not ai_response:
                return ai_response, self._tool_call_history

            potential_call_phrases = ["调用 工具", "调用工具", "需要一个工具", "需要调用", "use tool", "call a tool"]
            lower_resp = ai_response.lower()

            tool_calls = self.parse_tool_calls(ai_response)
            
            immediate_response = self._extract_immediate_response(ai_response)

            if not tool_calls:
                need_tool_call = False
                keywords = ["打开", "open", "访问", "visit", "search", "搜索", 
                           "execute", "执行", "run", "运行", "start", "启动",
                           "notepad", "browser", "浏览器", "folder", "文件夹"]
                for keyword in keywords:
                    if keyword.lower() in ai_response.lower():
                        need_tool_call = True
                        break
                
                if any(p in lower_resp for p in potential_call_phrases) or need_tool_call:
                    if self._tool_list_tool:
                        default_md = os.path.join(os.path.dirname(__file__), "TOOLS.md")
                        full_content = self._tool_list_tool.export_to_md(default_md)
                        current_prompt = f"{ai_response}\n\nAvailable tools:\n{full_content}\n\nPlease select the appropriate tool and return tool call JSON! Don't just say words without calling a tool!"
                        continue
                return ai_response, self._tool_call_history

            for tc in tool_calls:
                tool_name = tc.get("tool")
                args = tc.get("arguments") or {}
                if tool_name and (not args or all(v in (None, "", {}) for v in args.values())):
                    tool_needs_params = self._tool_requires_parameters(tool_name)
                    if tool_needs_params and tool_name not in injected_tools and self._tool_list_tool:
                        single_md = self._tool_list_tool.get_tool_md(tool_name)
                        injected_tools.add(tool_name)
                        example_json = '{"tool": "' + tool_name + '", "arguments": {...}}'
                        current_prompt = (
                            ai_response
                            + "\n\nTool "
                            + tool_name
                            + " description (please provide parameters based on the following and call this tool again):\n"
                            + single_md
                            + "\n\nPlease return tool call JSON example:"
                            + example_json
                        )
                        break

            if any(t in injected_tools for t in [tc.get("tool") for tc in tool_calls]):
                continue

            tool_results = []
            non_blocking_results = []
            
            blocking_calls = []
            
            for tc in tool_calls:
                tool_name = tc["tool"]
                arguments = tc["arguments"]
                
                if tool_name in NON_BLOCKING_TOOLS:
                    logger.info(f"[ToolCallManagerV2] Non-blocking tool: {tool_name}, starting immediately and continuing")
                    
                    asyncio.create_task(
                        self._execute_non_blocking_tool(tool_name, arguments, permission_context)
                    )
                    
                    non_blocking_results.append({
                        "tool": tool_name,
                        "arguments": arguments,
                        "status": "started",
                        "message": "Tool started (non-blocking mode)"
                    })
                    
                    self._tool_call_history.append(ToolCall(
                        id=str(asyncio.get_event_loop().time()),
                        name=tool_name,
                        arguments=arguments,
                        result={"status": "started", "message": "Tool started"},
                        status=ToolCallStatus.NON_BLOCKING
                    ))
                else:
                    blocking_calls.append({"tool": tool_name, "arguments": arguments})
            
            if blocking_calls:
                logger.info(f"[ToolCallManagerV2] Executing {len(blocking_calls)} blocking tools in parallel")
                parallel_results = await self._execute_parallel_tools(
                    blocking_calls, permission_context
                )
                
                for tc, result in zip(blocking_calls, parallel_results):
                    tool_name = tc["tool"]
                    arguments = tc["arguments"]
                    
                    status = ToolCallStatus.SUCCESS if result.success else ToolCallStatus.ERROR
                    if result.requires_confirmation:
                        status = ToolCallStatus.PERMISSION_REQUIRED

                    self._tool_call_history.append(ToolCall(
                        id=result.tool_call_id,
                        name=result.tool_name,
                        arguments=arguments,
                        result=result.result,
                        error=result.error,
                        status=status
                    ))

                    tool_results.append({
                        "tool": result.tool_name,
                        "result": result.result,
                        "error": result.error,
                        "requires_confirmation": result.requires_confirmation
                    })
            
            if non_blocking_results and not tool_results:
                logger.info(f"[ToolCallManagerV2] All tools are non-blocking, continuing immediately")
                
                if step >= 2:
                    tool_names = [r["tool"] for r in non_blocking_results]
                    summary_msg = f"I've started the following operations for you: {', '.join(tool_names)}. "
                    summary_msg += "The task has been initiated successfully!"
                    logger.info(f"[ToolCallManagerV2] Non-blocking tools completed, returning summary")
                    return summary_msg, self._tool_call_history
                
                current_prompt = f"""
Continue the previous conversation. In the last step you requested the following non-blocking tools:

{json.dumps(non_blocking_results, ensure_ascii=False, indent=2)}

These tools have been started and executed. You should now provide a final summary to the user about what was accomplished.
If the task is complete, give a friendly confirmation message to the user WITHOUT calling any more tools.
Your response should be a direct message to the user summarizing what was done.
"""
            else:
                all_results = non_blocking_results + tool_results
                current_prompt = f"""
Continue the previous conversation. In the last step you requested the following tools:

{json.dumps(all_results, ensure_ascii=False, indent=2)}

Based on the tool execution results, you should proceed with the next step or report results to the user.
If you have completed the user's requested task, please give the final response.
If you need to continue operations, please call the next tool.
"""
            
            if on_immediate_response and immediate_response:
                logger.info(f"[ToolCallManagerV2] Triggering immediate response callback: {immediate_response[:50]}...")
                on_immediate_response(immediate_response)

        logger.warning(f"[ToolCallManagerV2] Reached maximum iterations: {max_steps}")
        return "Sorry, I need more steps to complete this task. Please try again later or simplify your request.", self._tool_call_history

    def format_tool_results_for_ai(self, tool_results: List[ToolCallResult]) -> str:
        """Format tool results for AI to continue processing"""
        lines = ["## Tool Execution Results\n"]

        for result in tool_results:
            status = "SUCCESS" if result.success else "FAILED"
            if result.requires_confirmation:
                status = "NEEDS_CONFIRMATION"
            lines.append(f"\n### {result.tool_name} [{status}]")
            if result.success:
                if isinstance(result.result, dict):
                    lines.append("```json")
                    lines.append(json.dumps(result.result, ensure_ascii=False, indent=2))
                    lines.append("```")
                elif isinstance(result.result, list):
                    lines.append("```json")
                    lines.append(json.dumps(result.result, ensure_ascii=False, indent=2))
                    lines.append("```")
                else:
                    lines.append(str(result.result))
            else:
                lines.append(f"Error: {result.error}")

        return "\n".join(lines)

    def get_tool_call_history(self) -> List[ToolCall]:
        """Get tool call history"""
        return self._tool_call_history

    def clear_history(self):
        """Clear tool call history"""
        self._tool_call_history = []
        logger.debug("[ToolCallManagerV2] Tool call history cleared")
    
    def _extract_all_json_objects(self, text: str) -> List[Dict[str, Any]]:
        """Extract all valid JSON objects from text (consistent with json_processor)"""
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


_tool_call_manager: Optional[ToolCallManager] = None


def get_tool_call_manager() -> ToolCallManager:
    """Get ToolCallManager singleton"""
    global _tool_call_manager
    if _tool_call_manager is None:
        _tool_call_manager = ToolCallManager()
    return _tool_call_manager


def init_tool_call_manager(
    tool_system: Optional[ToolSystem] = None,
    permission_context: Optional[PermissionContext] = None,
) -> ToolCallManager:
    """Initialize ToolCallManager"""
    global _tool_call_manager
    _tool_call_manager = ToolCallManager(tool_system, permission_context)
    return _tool_call_manager
