import asyncio
import os
import random
import sys
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, TypeVar
from abc import ABC, abstractmethod
from datetime import datetime
import uuid

class TaskType(Enum):
    LOCAL_BASH = "local_bash"
    LOCAL_AGENT = "local_agent"
    REMOTE_AGENT = "remote_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    LOCAL_WORKFLOW = "local_workflow"
    MONITOR_MCP = "monitor_mcp"
    DREAM = "dream"
    SCHEDULED_REMINDER = "scheduled_reminder"      # 定时提醒任务
    SCHEDULED_TOOL_CALL = "scheduled_tool_call"    # 定时工具调用任务

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"

class TaskHandle:
    def __init__(self, task_id: str, cleanup: Optional[Callable] = None):
        self.task_id = task_id
        self.cleanup = cleanup

class TaskStateBase:
    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        description: str,
        tool_use_id: Optional[str] = None
    ):
        self.id = task_id
        self.type = task_type
        self.status = TaskStatus.PENDING
        self.description = description
        self.tool_use_id = tool_use_id
        self.start_time = datetime.now().timestamp()
        self.end_time = None
        self.total_paused_ms = 0
        self.output_file = self._get_output_path(task_id)
        self.output_offset = 0
        self.notified = False
    
    def _get_output_path(self, task_id: str) -> str:
        """获取任务输出文件路径"""
        if sys.platform == "win32":
            app_data = os.getenv("APPDATA")
            user_data_dir = os.path.join(app_data, "Vivian")
        else:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".vivian")
        output_dir = os.path.join(user_data_dir, "tasks", "outputs")
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, f"{task_id}.log")

class TaskContext:
    def __init__(self):
        self.abort_controller = asyncio.Event()
        self.get_app_state = None
        self.set_app_state = None

class BaseTask(ABC):
    def __init__(self, task_type: TaskType):
        self.type = task_type
        self.name = self.__class__.__name__
        self._task_state = None
    
    @abstractmethod
    async def run(self, context: TaskContext) -> Any:
        pass
    
    async def kill(self, task_id: str, set_app_state: Callable) -> None:
        """终止任务"""
        pass

class TaskRegistry:
    _instance = None
    _task_types = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register_task_type(cls, task_type: TaskType, task_class: type):
        """注册任务类型"""
        cls._task_types[task_type] = task_class
    
    @classmethod
    def create_task(cls, task_type: TaskType, **kwargs) -> BaseTask:
        """创建任务实例"""
        task_class = cls._task_types.get(task_type)
        if not task_class:
            raise ValueError(f"Unknown task type: {task_type}")
        return task_class(task_type, **kwargs)
    
    @classmethod
    def list_task_types(cls) -> List[TaskType]:
        """获取所有任务类型"""
        return list(cls._task_types.keys())

class TaskManager:
    def __init__(self):
        self._tasks: Dict[str, BaseTask] = {}
        self._task_states: Dict[str, TaskStateBase] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_task(
        self,
        task_type: TaskType,
        description: str,
        tool_use_id: Optional[str] = None,
        **kwargs
    ) -> TaskHandle:
        """创建任务"""
        task_id = self._generate_task_id(task_type)
        task_state = TaskStateBase(task_id, task_type, description, tool_use_id)
        self._task_states[task_id] = task_state
        
        task = TaskRegistry.create_task(task_type, **kwargs)
        self._tasks[task_id] = task
        
        return TaskHandle(task_id=task_id)
    
    async def start_task(self, task_id: str) -> None:
        """启动任务"""
        if task_id not in self._task_states:
            raise ValueError(f"Task not found: {task_id}")
        
        task_state = self._task_states[task_id]
        if task_state.status != TaskStatus.PENDING:
            raise ValueError(f"Task is not pending: {task_id}")
        
        task_state.status = TaskStatus.RUNNING
        task_state.start_time = datetime.now().timestamp()
        
        task = self._tasks[task_id]
        context = TaskContext()
        
        async def task_wrapper():
            try:
                result = await task.run(context)
                task_state.status = TaskStatus.COMPLETED
                task_state.end_time = datetime.now().timestamp()
                self._save_output(task_id, str(result))
            except Exception as e:
                task_state.status = TaskStatus.FAILED
                task_state.end_time = datetime.now().timestamp()
                self._save_output(task_id, f"Error: {e}")
            finally:
                del self._running_tasks[task_id]
        
        self._running_tasks[task_id] = asyncio.create_task(task_wrapper())
    
    async def kill_task(self, task_id: str) -> None:
        """终止任务"""
        if task_id not in self._task_states:
            raise ValueError(f"Task not found: {task_id}")
        
        task = self._tasks.get(task_id)
        if task:
            await task.kill(task_id, lambda x: None)
        
        task_state = self._task_states[task_id]
        task_state.status = TaskStatus.KILLED
        task_state.end_time = datetime.now().timestamp()
        
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]
    
    def get_task_state(self, task_id: str) -> Optional[TaskStateBase]:
        """获取任务状态"""
        return self._task_states.get(task_id)
    
    def list_tasks(self) -> List[TaskStateBase]:
        """获取所有任务状态"""
        return list(self._task_states.values())
    
    def _generate_task_id(self, task_type: TaskType) -> str:
        """生成任务ID"""
        prefixes = {
            TaskType.LOCAL_BASH: 'b',
            TaskType.LOCAL_AGENT: 'a',
            TaskType.REMOTE_AGENT: 'r',
            TaskType.IN_PROCESS_TEAMMATE: 't',
            TaskType.LOCAL_WORKFLOW: 'w',
            TaskType.MONITOR_MCP: 'm',
            TaskType.DREAM: 'd',
            TaskType.SCHEDULED_REMINDER: 's',
            TaskType.SCHEDULED_TOOL_CALL: 'c',
        }
        
        prefix = prefixes.get(task_type, 'x')
        alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
        random_bytes = os.urandom(8)
        task_id = prefix
        
        for byte in random_bytes:
            task_id += alphabet[byte % len(alphabet)]
        
        return task_id
    
    def _save_output(self, task_id: str, output: str) -> None:
        """保存任务输出"""
        task_state = self._task_states.get(task_id)
        if task_state:
            with open(task_state.output_file, 'a', encoding='utf-8') as f:
                f.write(output + '\n')

class LocalBashTask(BaseTask):
    def __init__(self, task_type: TaskType, command: str):
        super().__init__(task_type)
        self.command = command
    
    async def run(self, context: TaskContext) -> Any:
        """执行Bash命令"""
        process = await asyncio.create_subprocess_shell(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Command failed: {stderr.decode('utf-8')}")
        
        return stdout.decode('utf-8')

class LocalAgentTask(BaseTask):
    def __init__(self, task_type: TaskType, prompt: str):
        super().__init__(task_type)
        self.prompt = prompt
    
    async def run(self, context: TaskContext) -> Any:
        """执行本地代理任务"""
        from core.query_engine import ask
        
        result = ""
        async for message in ask(self.prompt):
            if message.get('type') == 'result':
                result = message.get('result', '')
        
        return result

class RemoteAgentTask(BaseTask):
    def __init__(self, task_type: TaskType, prompt: str):
        super().__init__(task_type)
        self.prompt = prompt
    
    async def run(self, context: TaskContext) -> Any:
        """执行远程代理任务"""
        from core.ai_manager import AIManager
        from utils.config_manager import config_manager
        
        ai_config = config_manager.get("ai", {})
        ai_manager = AIManager(ai_config)
        return await ai_manager.aquery_short(self.prompt, use_history=False)

class ScheduledReminderTask(BaseTask):
    """定时提醒任务"""
    def __init__(self, task_type: TaskType, message: str, scheduled_time: float):
        super().__init__(task_type)
        self.message = message
        self.scheduled_time = scheduled_time
        self._callback = None
    
    def set_callback(self, callback: Callable):
        """设置回调函数"""
        self._callback = callback
    
    async def run(self, context: TaskContext) -> Any:
        """执行定时提醒"""
        # 存入记忆
        try:
            from core.memory_manager import get_memory_manager
            memory_manager = get_memory_manager()
            memory_manager.add_short_term_memory(
                content=f"定时提醒: {self.message}",
                role="system",
                importance=0.7,
                tags=["timer", "reminder"],
                metadata={
                    "task_id": self._task_state.id if self._task_state else "",
                    "scheduled_time": self.scheduled_time
                }
            )
        except Exception as e:
            pass
        
        # 触发回调
        if self._callback:
            self._callback({
                "type": "reminder",
                "task_id": self._task_state.id if self._task_state else "",
                "message": self.message,
                "scheduled_time": self.scheduled_time
            })
        
        return f"提醒已发送: {self.message}"

class ScheduledToolCallTask(BaseTask):
    """定时工具调用任务"""
    def __init__(self, task_type: TaskType, tool_name: str, tool_arguments: Dict[str, Any], scheduled_time: float):
        super().__init__(task_type)
        self.tool_name = tool_name
        self.tool_arguments = tool_arguments
        self.scheduled_time = scheduled_time
        self._callback = None
    
    def set_callback(self, callback: Callable):
        """设置回调函数"""
        self._callback = callback
    
    async def run(self, context: TaskContext) -> Any:
        """执行定时工具调用"""
        try:
            from core.tools import get_tool_call_manager
            tool_call_manager = get_tool_call_manager()
            
            result = await tool_call_manager.execute_tool_call(
                self.tool_name,
                self.tool_arguments
            )
            
            # 存入记忆
            try:
                from core.memory_manager import get_memory_manager
                memory_manager = get_memory_manager()
                memory_manager.add_short_term_memory(
                    content=f"定时任务执行工具: {self.tool_name}, 参数: {self.tool_arguments}, 结果: {'成功' if result.success else '失败'}",
                    role="system",
                    importance=0.6,
                    tags=["timer", "tool_call"],
                    metadata={
                        "task_id": self._task_state.id if self._task_state else "",
                        "scheduled_time": self.scheduled_time,
                        "tool_name": self.tool_name,
                        "tool_arguments": self.tool_arguments,
                        "success": result.success,
                        "result": result.result
                    }
                )
            except Exception as e:
                pass
            
            # 触发回调
            if self._callback and result.success:
                self._callback({
                    "type": "tool_result",
                    "task_id": self._task_state.id if self._task_state else "",
                    "tool_name": self.tool_name,
                    "success": result.success,
                    "result": result.result
                })
            
            return f"工具调用完成: {self.tool_name}"
            
        except Exception as e:
            raise Exception(f"工具调用失败: {e}")

# 注册任务类型
TaskRegistry.register_task_type(TaskType.LOCAL_BASH, LocalBashTask)
TaskRegistry.register_task_type(TaskType.LOCAL_AGENT, LocalAgentTask)
TaskRegistry.register_task_type(TaskType.REMOTE_AGENT, RemoteAgentTask)
TaskRegistry.register_task_type(TaskType.SCHEDULED_REMINDER, ScheduledReminderTask)
TaskRegistry.register_task_type(TaskType.SCHEDULED_TOOL_CALL, ScheduledToolCallTask)

# 创建全局任务管理器实例
task_manager = TaskManager()
