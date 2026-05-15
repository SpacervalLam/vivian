"""
工具调用管理器

核心功能：
- 管理所有可用工具
- 处理工具列表的生成
- 执行工具调用
- 支持多轮工具调用
- 与AI模型交互
"""

import json
import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class ToolCallStatus(Enum):
    """工具调用状态"""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"


@dataclass
class ToolCall:
    """工具调用记录"""
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    status: ToolCallStatus = ToolCallStatus.PENDING


@dataclass
class ToolCallResult:
    """工具调用结果"""
    success: bool
    result: Any
    tool_name: str
    tool_call_id: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolListTool:
    """
    工具列表工具 - 这是一个特殊的元工具

    它不是一个执行具体操作的工具，而是用于向AI提供所有可用工具的信息。
    当AI需要使用工具时，会调用此工具来获取工具列表和使用说明。
    """

    def __init__(self, tool_manager):
        """
        初始化工具列表工具

        Args:
            tool_manager: 工具管理器实例
        """
        self.name = "tool_list"
        self.description = (
            "这是一个特殊的元工具，用于获取所有可用工具的列表和使用说明。"
            "当你需要执行系统操作（如启动应用、设置壁纸、搜索文件等）时，你应该调用此工具来获取可用工具列表。"
            "然后根据用户需求选择合适的工具进行调用。"
        )
        self._tool_manager = tool_manager

    def get_tools_for_ai(self) -> str:
        """
        获取供AI使用的工具列表格式化字符串

        Returns:
            格式化后的工具列表
        """
        if self._tool_manager is None:
            return "工具管理器未初始化"

        tools = self._tool_manager.get_all_tools_info()
        if not tools:
            return "当前没有可用的工具"

        lines = ["# 可用工具列表\n"]
        lines.append(f"共 {len(tools)} 个工具：\n")

        for tool_name, tool_info in tools.items():
            lines.append(f"## {tool_name}")
            lines.append(f"描述: {tool_info['description']}")

            params = tool_info.get('parameters', {})
            if params:
                lines.append("参数:")
                for param_name, param_info in params.items():
                    required = "必填" if param_info.get('required', False) else "可选"
                    param_type = param_info.get('type', 'any')
                    desc = param_info.get('description', '')
                    default = param_info.get('default')
                    default_str = f", 默认值: {default}" if default is not None else ""
                    lines.append(f"  - {param_name} ({param_type}) [{required}]{default_str}: {desc}")

            lines.append("")

        return "\n".join(lines)

    def export_to_md(self, file_path: str) -> str:
        """
        将当前工具列表导出为 Markdown 文件

        Args:
            file_path: 要写入的文件路径

        Returns:
            写入的内容字符串
        """
        content = self.get_tools_for_ai()
        try:
            dirpath = os.path.dirname(file_path)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"[ToolListTool] 工具说明已导出到: {file_path}")
        except Exception as e:
            logger.error(f"[ToolListTool] 导出工具说明失败: {e}")
        return content

    def get_tool_md(self, tool_name: str) -> str:
        """
        获取单个工具的 Markdown 说明段落

        Args:
            tool_name: 工具名称

        Returns:
            工具的 Markdown 字符串，如果不存在则返回错误信息
        """
        if self._tool_manager is None:
            return "工具管理器未初始化"

        tools = self._tool_manager.get_all_tools_info()
        info = tools.get(tool_name)
        if not info:
            return f"未知工具: {tool_name}"

        lines = [f"## {tool_name}", f"描述: {info.get('description', '')}"]
        params = info.get('parameters', {})
        if params:
            lines.append("参数:")
            for param_name, param_info in params.items():
                required = "必填" if param_info.get('required', False) else "可选"
                param_type = param_info.get('type', 'any')
                desc = param_info.get('description', '')
                default = param_info.get('default')
                default_str = f", 默认值: {default}" if default is not None else ""
                lines.append(f"  - {param_name} ({param_type}) [{required}]{default_str}: {desc}")

        return "\n".join(lines)

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """
        获取工具列表（JSON格式）

        Returns:
            工具信息列表
        """
        if self._tool_manager is None:
            return []

        return [
            {
                "name": info["name"],
                "description": info["description"],
                "parameters": info.get("parameters", {})
            }
            for name, info in self._tool_manager.get_all_tools_info().items()
        ]

    def get_tools_schema(self) -> Dict[str, Any]:
        """
        返回一个便于注入到 LLM 提示词的简洁 JSON schema，包含每个工具的参数描述。

        Returns:
            dict: {tool_name: {description, parameters: {param_name: {type, required, description}}}}
        """
        if self._tool_manager is None:
            return {}

        schema = {}
        for name, info in self._tool_manager.get_all_tools_info().items():
            params = {}
            for p_name, p_info in info.get('parameters', {}).items():
                params[p_name] = {
                    'type': p_info.get('type', 'string'),
                    'required': p_info.get('required', False),
                    'description': p_info.get('description', '')
                }
            schema[name] = {
                'description': info.get('description', ''),
                'parameters': params
            }
        return schema

    def run(self) -> str:
        """
        执行工具（返回工具列表）

        Returns:
            工具列表字符串
        """
        return self.get_tools_for_ai()


class ToolCallManager:
    """
    工具调用管理器

    负责：
    1. 管理工具列表
    2. 解析AI的函数调用请求
    3. 执行工具调用
    4. 处理多轮工具调用
    5. 格式化工具结果返回给AI
    """

    def __init__(self, tool_manager=None):
        """
        初始化工具调用管理器

        Args:
            tool_manager: 工具管理器实例
        """
        self._tool_manager = tool_manager
        self._tool_list_tool = None
        self._tool_call_history: List[ToolCall] = []
        self._max_iterations = 10  # 最大迭代次数

        # 初始化工具列表工具
        if self._tool_manager:
            self._tool_list_tool = ToolListTool(self._tool_manager)

        logger.debug("[ToolCallManager] 工具调用管理器初始化完成")

    def set_tool_manager(self, tool_manager):
        """设置工具管理器"""
        self._tool_manager = tool_manager
        if self._tool_manager:
            self._tool_list_tool = ToolListTool(self._tool_manager)
        logger.debug("[ToolCallManager] 工具管理器已设置")

    def set_max_iterations(self, max_iterations: int):
        """设置最大迭代次数"""
        self._max_iterations = max(max_iterations, 1)
        logger.debug(f"[ToolCallManager] 最大迭代次数设置为: {self._max_iterations}")

    def get_system_prompt(self) -> str:
        """
        获取包含工具信息的系统提示

        Returns:
            系统提示字符串
        """
        # 精简版系统提示：默认不在每次请求中嵌入完整工具清单，以节省 token。
        # 当模型决定要使用某个工具时，应先调用 `tool_list` 或请求注入完整工具说明（core/tools/TOOLS.md）。
        if self._tool_list_tool is None:
            return "工具系统未初始化"

        return (
            "You can call tools to perform system operations. To save tokens,\n"
            "if you need to see complete tool parameters, please call tool_list or request injection of complete tool documentation (file: core/tools/TOOLS.md).\n"
            "When calling tools, return JSON format: {\"tool\": \"tool_name\", \"arguments\": {\"param_name\": \"value\"}}.\n"
            "Example: {\"tool\": \"open_application\", \"arguments\": {\"app_path\": \"C:\\\\Windows\\\\notepad.exe\"}}\n"
        )

    def parse_tool_calls(self, ai_response: str) -> List[Dict[str, Any]]:
        """
        解析AI响应中的工具调用

        Args:
            ai_response: AI响应文本

        Returns:
            工具调用列表
        """
        tool_calls = []

        try:
            # 尝试解析JSON格式的工具调用
            # 格式1: {"tool": "xxx", "arguments": {...}}
            # 格式2: {"tool_calls": [{"name": "xxx", "args": {...}}]}
            # 格式3: tool_name(arg1=value1, arg2=value2)

            # 首先尝试直接解析JSON
            try:
                data = json.loads(ai_response)
                if isinstance(data, dict):
                    # 直接的工具调用格式
                    if "tool" in data and "arguments" in data:
                        tool_calls.append(data)
                    # 支持批量工具调用字段
                    elif "tool_calls" in data:
                        for tc in data["tool_calls"]:
                            tool_calls.append({
                                "tool": tc.get("name", tc.get("tool")),
                                "arguments": tc.get("args", tc.get("arguments", {}))
                            })
            except json.JSONDecodeError:
                pass

            # 尝试解析Python函数调用格式
            if not tool_calls:
                import re
                # 匹配普通函数调用: function_name(arg1, arg2)
                pattern = r'(\w+)\s*\((.*?)\)'
                matches = re.findall(pattern, ai_response, re.DOTALL)
                for match in matches:
                    tool_name = match[0]
                    args_str = match[1]

                    # 解析参数
                    args = {}
                    if args_str.strip():
                        # 简单的键值对解析
                        kv_pattern = r'(\w+)\s*=\s*["\']?([^"\',\)]+)["\']?'
                        for kv_match in re.findall(kv_pattern, args_str):
                            args[kv_match[0]] = kv_match[1]
                        
                        # 如果没有键值对，尝试解析位置参数
                        if not args and args_str.strip():
                            # 移除引号
                            arg_value = args_str.strip().strip('\'"')
                            # 根据工具名确定参数名
                            if tool_name in ["open_app", "open_application"]:
                                args["app_name"] = arg_value
                            elif tool_name in ["close_app", "close_application"]:
                                args["process_name"] = arg_value
                            elif tool_name in ["open_folder", "open_dir"]:
                                args["path"] = arg_value
                            elif tool_name in ["open_url"]:
                                args["url"] = arg_value

                    if tool_name != "tool_list":  # 排除工具列表本身
                        tool_calls.append({
                            "tool": tool_name,
                            "arguments": args
                        })

        except Exception as e:
            logger.error(f"[ToolCallManager] 解析工具调用失败: {e}")

        return tool_calls

    # 工具名称别名映射（解决AI返回的工具名与实际工具名不匹配的问题）
    _TOOL_ALIASES = {
        "open_app": "open_application",
        "close_app": "close_application",
        "open_dir": "open_folder",
        "launch_app": "open_application",
        "start_app": "open_application"
    }

    async def execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> ToolCallResult:
        """
        执行单个工具调用

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用结果
        """
        # 处理工具别名
        if tool_name in self._TOOL_ALIASES:
            logger.info(f"[ToolCallManager] 将工具别名 '{tool_name}' 转换为实际工具名 '{self._TOOL_ALIASES[tool_name]}'")
            tool_name = self._TOOL_ALIASES[tool_name]
        
        # 处理特殊情况：open_application 需要默认路径
        if tool_name == "open_application" and not arguments.get("app_path"):
            # 如果没有提供路径，尝试从参数中提取应用名称
            app_name = arguments.get("app_name", arguments.get("name", ""))
            if app_name:
                # 尝试构建常见应用的路径
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
                    logger.info(f"[ToolCallManager] 自动填充应用路径: {app_name} -> {arguments['app_path']}")
                else:
                    # 如果传入的 app_name 实际是一个可执行文件的完整路径，直接使用它
                    if "\\" in app_name or "/" in app_name or app_name.lower().endswith('.exe'):
                        arguments["app_path"] = app_name
                        logger.info(f"[ToolCallManager] 使用传入的可执行路径作为 app_path: {arguments['app_path']}")
        
        tool_call_id = f"call_{len(self._tool_call_history)}_{int(asyncio.get_event_loop().time() * 1000)}"

        try:
            # 特殊处理工具列表工具
            if tool_name == "tool_list":
                if self._tool_list_tool:
                    # 支持按需获取单个工具说明：如果调用时传入参数 {"tool": "open_application"}
                    # 则只返回该工具的说明段落，避免把完整清单注入到提示词中。
                    requested_tool = arguments.get("tool") or arguments.get("name")
                    default_md = os.path.join(os.path.dirname(__file__), "TOOLS.md")
                    # 始终同步导出完整说明文件，便于人工查看或按需注入完整文档
                    full_content = self._tool_list_tool.export_to_md(default_md)
                    # 构建 JSON schema，方便 LLM 注入和解析
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
                        error="工具列表工具未初始化"
                    )

            # 执行普通工具
            if self._tool_manager is None:
                return ToolCallResult(
                    success=False,
                    result=None,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    error="工具管理器未初始化"
                )

            # 检查工具是否存在
            tool = self._tool_manager.get_tool(tool_name)
            if tool is None:
                # 尝试执行系统工具
                try:
                    from core.tools.system_tools import execute_system_tool
                    result = execute_system_tool(tool_name, **arguments)
                    return ToolCallResult(
                        success=result.get("success", False),
                        result=result.get("result"),
                        tool_name=tool_name,
                        tool_call_id=tool_call_id
                    )
                except Exception as e:
                    return ToolCallResult(
                        success=False,
                        result=None,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        error=f"工具不存在: {tool_name}, 错误: {str(e)}"
                    )

            # 执行工具
            logger.info(f"[ToolCallManager] 执行工具: {tool_name}, 参数: {arguments}")
            result = await self._tool_manager.arun_tool(tool_name, **arguments)

            return ToolCallResult(
                success=result.success,
                result=result.result,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error=result.error
            )

        except Exception as e:
            logger.error(f"[ToolCallManager] 执行工具 {tool_name} 失败: {e}")
            return ToolCallResult(
                success=False,
                result=None,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                error=str(e)
            )

    async def execute_multi_step(
        self,
        ai_generate_func,
        initial_prompt: str,
        max_steps: int = None
    ) -> Tuple[str, List[ToolCall]]:
        """
        执行多轮工具调用

        Args:
            ai_generate_func: AI生成函数，签名: async def(prompt: str) -> str
            initial_prompt: 初始提示
            max_steps: 最大步数，默认使用_max_iterations

        Returns:
            (最终回复, 工具调用历史)
        """
        if max_steps is None:
            max_steps = self._max_iterations

        current_prompt = initial_prompt
        self._tool_call_history = []
        injected_tools = set()

        for step in range(max_steps):
            logger.info(f"[ToolCallManager] 执行步骤 {step + 1}/{max_steps}")

            # 调用AI生成回复
            ai_response = await ai_generate_func(current_prompt)

            # 如果AI没有明确要调用哪个工具，但文本中提到了"调用"和"工具"，
            # 我们主动返回工具列表以引导模型（按需注入，避免一次性给全部内容）
            if not ai_response:
                return ai_response, self._tool_call_history

            # 简单语言检测：如果没有解析到工具调用，但用户/模型提到需要调用工具，则注入 tool_list
            potential_call_phrases = ["调用 工具", "调用工具", "需要一个工具", "需要调用", "use tool", "call a tool"]
            lower_resp = ai_response.lower()

            # 解析工具调用
            tool_calls = self.parse_tool_calls(ai_response)

            if not tool_calls:
                # 检测到模型意图使用工具但未指定具体工具，主动注入工具列表并继续下一轮
                if any(p in lower_resp for p in potential_call_phrases):
                    if self._tool_list_tool:
                        default_md = os.path.join(os.path.dirname(__file__), "TOOLS.md")
                        full_content = self._tool_list_tool.export_to_md(default_md)
                        current_prompt = f"{ai_response}\n\n可用工具列表（简要）：\n{full_content}\n\n请基于上面的说明告诉我你要调用哪个工具以及参数。"
                        continue
                # 如果没有工具调用且没有意图指示，直接返回AI回复
                return ai_response, self._tool_call_history

            if not tool_calls:
                # 没有工具调用，直接返回AI回复
                return ai_response, self._tool_call_history

            # 检查是否有工具被请求但未提供参数，若是则注入该工具的说明到下一轮提示
            for tc in tool_calls:
                tool_name = tc.get("tool")
                args = tc.get("arguments") or {}
                if tool_name and (not args or all(v in (None, "", {}) for v in args.values())):
                    # 未提供参数，注入该工具说明（仅注入一次以避免循环）
                    if tool_name not in injected_tools and self._tool_list_tool:
                        single_md = self._tool_list_tool.get_tool_md(tool_name)
                        injected_tools.add(tool_name)
                        # 构建一个安全的字符串示例，避免 f-string 中的嵌套大括号问题
                        example_json = '{"tool": "' + tool_name + '", "arguments": {...}}'
                        current_prompt = (
                            ai_response
                            + "\n\n工具 "
                            + tool_name
                            + " 的说明（请根据下列说明提供参数并再次调用此工具）：\n"
                            + single_md
                            + "\n\n请返回工具调用的 JSON 示例："
                            + example_json
                        )
                        # 跳到下一轮，让模型根据注入的说明补充参数
                        break

            # 如果我们刚刚注入了说明并跳出循环，继续下一步生成
            if any(t in injected_tools for t in [tc.get("tool") for tc in tool_calls]):
                continue

            # 执行工具调用
            tool_results = []
            for tc in tool_calls:
                result = await self.execute_tool_call(tc["tool"], tc["arguments"])

                # 记录工具调用
                self._tool_call_history.append(ToolCall(
                    id=result.tool_call_id,
                    name=result.tool_name,
                    arguments=tc["arguments"],
                    result=result.result,
                    error=result.error,
                    status=ToolCallStatus.SUCCESS if result.success else ToolCallStatus.ERROR
                ))

                # 格式化结果
                tool_results.append({
                    "tool": result.tool_name,
                    "result": result.result,
                    "error": result.error
                })

            # 将工具结果添加到提示中，继续对话
            current_prompt = f"""
继续之前的对话。上一轮你要求执行了以下工具：

{json.dumps(tool_results, ensure_ascii=False, indent=2)}

根据工具执行结果，你需要进行下一步操作或向用户报告结果。
如果你已经完成了用户请求的任务，请给出最终回复。
如果还需要继续操作，请调用下一个工具。
"""

        # 达到最大迭代次数
        logger.warning(f"[ToolCallManager] 达到最大迭代次数 {max_steps}")
        return "抱歉，我需要更多步骤来完成这个任务。请稍后再试或简化您的请求。", self._tool_call_history

    def format_tool_results_for_ai(self, tool_results: List[ToolCallResult]) -> str:
        """
        格式化工具结果供AI继续处理

        Args:
            tool_results: 工具结果列表

        Returns:
            格式化后的字符串
        """
        lines = ["## 工具执行结果\n"]

        for result in tool_results:
            status = "✅ 成功" if result.success else "❌ 失败"
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
                lines.append(f"错误: {result.error}")

        return "\n".join(lines)

    def get_tool_call_history(self) -> List[ToolCall]:
        """获取工具调用历史"""
        return self._tool_call_history

    def clear_history(self):
        """清空工具调用历史"""
        self._tool_call_history = []
        logger.debug("[ToolCallManager] 工具调用历史已清空")


# 全局单例
_tool_call_manager: Optional[ToolCallManager] = None


def get_tool_call_manager() -> ToolCallManager:
    """获取工具调用管理器单例"""
    global _tool_call_manager
    if _tool_call_manager is None:
        _tool_call_manager = ToolCallManager()
    return _tool_call_manager


def init_tool_call_manager(tool_manager) -> ToolCallManager:
    """初始化工具调用管理器"""
    global _tool_call_manager
    _tool_call_manager = ToolCallManager(tool_manager)
    return _tool_call_manager