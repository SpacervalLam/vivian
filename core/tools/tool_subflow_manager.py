"""
工具子流程管理器

核心设计原则：
1. 子流程独立：工具子流程有自己独立的提示词
2. 状态隔离：子流程状态不污染主流程
3. 结果合并：子流程完成后返回结构化结果给主流程
4. 简洁高效：子流程提示词仅包含必要的工具信息
"""

from typing import Any, Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum, auto
import json
import asyncio
from loguru import logger


class SubflowState(Enum):
    """子流程状态"""
    IDLE = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class SubflowResult:
    """子流程执行结果"""
    success: bool
    final_message: str
    tool_calls: List[Dict[str, Any]]
    error: Optional[str] = None


class ToolSubflowManager:
    """工具子流程管理器
    
    特点：
    - 子流程有独立的简洁提示词
    - 专注于工具调用逻辑，不包含人设
    - 最终返回结构化结果供主流程构建友好回复
    """
    
    def __init__(self, tool_manager):
        self.tool_manager = tool_manager
        self.state = SubflowState.IDLE
        self._subflow_context: List[Dict[str, Any]] = []
        self._tool_call_history: List[Dict[str, Any]] = []
    
    def get_subflow_system_prompt(self) -> str:
        """获取子流程专用提示词（简洁，只关注工具使用）
        
        不包含：
        - 人设信息
        - 记忆系统
        - 复杂的对话历史
        
        只包含：
        - 工具列表
        - 工具调用格式
        - 结果处理说明
        """
        return """你是一个工具执行助手，专注于使用工具完成任务。

## 工具说明
{tool_list}

## 输出格式要求
- 只返回工具调用JSON：{"tool": "tool_name", "arguments": {...}}
- 或者返回最终结果总结：{"text": "最终结果说明"}

## 流程
1. 分析任务，选择合适工具
2. 执行工具，查看结果
3. 如需多步，继续调用工具
4. 任务完成时返回最终总结
"""
    
    async def execute_subflow(
        self,
        ai_generate_func,
        task_description: str,
        tool_list: str,
        max_steps: int = 5,
        on_tool_result: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> SubflowResult:
        """执行工具子流程
        
        Args:
            ai_generate_func: AI生成函数
            task_description: 任务描述（来自用户）
            tool_list: 可用工具列表
            max_steps: 最大步数
            on_tool_result: 工具结果回调
        
        Returns:
            SubflowResult: 子流程结果
        """
        self.state = SubflowState.RUNNING
        self._subflow_context = []
        self._tool_call_history = []
        
        # 构建子流程初始提示词（简洁！）
        system_prompt = self.get_subflow_system_prompt().format(tool_list=tool_list)
        current_prompt = f"{system_prompt}\n\n用户任务: {task_description}"
        
        try:
            for step in range(max_steps):
                logger.info(f"[ToolSubflow] Step {step + 1}/{max_steps}")
                
                # AI生成响应
                ai_response = await ai_generate_func(current_prompt)
                self._subflow_context.append({"role": "assistant", "content": ai_response})
                
                # 解析工具调用
                tool_calls = self._parse_tool_calls(ai_response)
                
                if not tool_calls:
                    # 没有工具调用，可能是任务完成
                    final_text = self._extract_final_text(ai_response)
                    self.state = SubflowState.COMPLETED
                    return SubflowResult(
                        success=True,
                        final_message=final_text,
                        tool_calls=self._tool_call_history
                    )
                
                # 执行工具
                tool_results = []
                for tc in tool_calls:
                    result = await self.tool_manager.execute_tool_call(
                        tc["tool"],
                        tc.get("arguments", {}),
                    )
                    
                    tool_result = {
                        "tool": tc["tool"],
                        "success": result.success,
                        "result": result.result,
                        "error": result.error
                    }
                    
                    self._tool_call_history.append(tool_result)
                    tool_results.append(tool_result)
                    
                    if on_tool_result:
                        on_tool_result(tool_result)
                
                # 构建下一步提示词
                current_prompt = self._build_next_step_prompt(
                    ai_response,
                    tool_results,
                    system_prompt
                )
                
                self._subflow_context.append({"role": "system", "content": current_prompt})
            
            # 达到最大步数
            logger.warning(f"[ToolSubflow] Max steps reached: {max_steps}")
            self.state = SubflowState.COMPLETED
            return SubflowResult(
                success=True,
                final_message="任务处理中，已执行多步操作",
                tool_calls=self._tool_call_history
            )
            
        except Exception as e:
            logger.error(f"[ToolSubflow] Execution failed: {e}")
            self.state = SubflowState.FAILED
            return SubflowResult(
                success=False,
                final_message="执行过程中出现错误",
                tool_calls=self._tool_call_history,
                error=str(e)
            )
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """解析工具调用"""
        try:
            # 尝试直接解析
            data = json.loads(response.strip())
            if isinstance(data, dict) and "tool" in data:
                return [data]
            if isinstance(data, list) and len(data) > 0:
                return [item for item in data if "tool" in item]
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON
        return self._extract_json_objects(response)
    
    def _extract_json_objects(self, text: str) -> List[Dict[str, Any]]:
        """提取所有JSON对象"""
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
                        results.append(json.loads(json_str))
                    except:
                        pass
        
        return results
    
    def _extract_final_text(self, response: str) -> str:
        """提取最终文本"""
        try:
            data = json.loads(response.strip())
            if isinstance(data, dict) and "text" in data:
                return data["text"]
        except:
            pass
        
        return response.strip()
    
    def _build_next_step_prompt(
        self,
        ai_response: str,
        tool_results: List[Dict[str, Any]],
        system_prompt: str
    ) -> str:
        """构建下一步提示词
        
        保持简洁，只包含：
        1. 系统提示词
        2. 上一步AI响应
        3. 工具执行结果
        """
        result_text = "\n".join([
            f"## Tool: {r['tool']}\n"
            f"Status: {'SUCCESS' if r['success'] else 'FAILED'}\n"
            f"Result: {r['result'] if r['success'] else r['error']}"
            for r in tool_results
        ])
        
        return f"""{system_prompt}

## 上一步
{ai_response}

## 工具执行结果
{result_text}

## 下一步
如果任务已完成，返回最终总结；否则继续调用工具。
"""
    
    def get_tool_call_history(self) -> List[Dict[str, Any]]:
        """获取工具调用历史"""
        return self._tool_call_history
    
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.state == SubflowState.RUNNING


# 全局实例
_subflow_manager: Optional[ToolSubflowManager] = None


def get_tool_subflow_manager(tool_manager=None) -> ToolSubflowManager:
    """获取工具子流程管理器"""
    global _subflow_manager
    if _subflow_manager is None:
        if tool_manager is None:
            raise ValueError("First call must provide tool_manager")
        _subflow_manager = ToolSubflowManager(tool_manager)
    return _subflow_manager
