"""
定时任务调度器 (Scheduler)

核心功能：
1. 支持绝对时间和相对时间的定时任务
2. 支持消息提醒和工具调用两种任务类型
3. 任务持久化存储
4. 任务列表管理（查看、取消）

设计原则：
- 复用现有的工具调用框架
- 集成打扰控制器，尊重用户状态
- 支持任务持久化，重启后继续执行
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from loguru import logger


class TaskType(Enum):
    """定时任务类型"""
    REMINDER = "reminder"      # 消息提醒
    TOOL_CALL = "tool_call"    # 工具调用


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 已完成
    CANCELLED = "cancelled"    # 已取消
    FAILED = "failed"          # 执行失败


class ScheduledTask:
    """定时任务数据模型"""
    
    def __init__(
        self,
        task_id: Optional[str] = None,
        task_type: TaskType = TaskType.REMINDER,
        scheduled_time: float = 0,
        message: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_arguments: Optional[Dict[str, Any]] = None,
        repeat_interval: Optional[int] = None,
        status: TaskStatus = TaskStatus.PENDING,
        created_at: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.id = task_id or str(uuid.uuid4())[:8]
        self.task_type = task_type
        self.scheduled_time = scheduled_time
        self.message = message
        self.tool_name = tool_name
        self.tool_arguments = tool_arguments or {}
        self.repeat_interval = repeat_interval
        self.status = status
        self.created_at = created_at or time.time()
        self.metadata = metadata or {}
        self._timer: Optional[QTimer] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "task_type": self.task_type.value,
            "scheduled_time": self.scheduled_time,
            "message": self.message,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "repeat_interval": self.repeat_interval,
            "status": self.status.value,
            "created_at": self.created_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledTask":
        """从字典创建任务"""
        return cls(
            task_id=data.get("id"),
            task_type=TaskType(data.get("task_type", "reminder")),
            scheduled_time=data.get("scheduled_time", 0),
            message=data.get("message"),
            tool_name=data.get("tool_name"),
            tool_arguments=data.get("tool_arguments", {}),
            repeat_interval=data.get("repeat_interval"),
            status=TaskStatus(data.get("status", "pending")),
            created_at=data.get("created_at"),
            metadata=data.get("metadata", {})
        )
    
    def get_scheduled_time_str(self) -> str:
        """获取计划时间的可读字符串"""
        return datetime.fromtimestamp(self.scheduled_time).strftime("%Y-%m-%d %H:%M:%S")
    
    def get_remaining_time(self) -> str:
        """获取剩余时间"""
        remaining = self.scheduled_time - time.time()
        if remaining <= 0:
            return "即将执行"
        
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分钟{seconds}秒"
        else:
            return f"{seconds}秒"


class Scheduler(QObject):
    """定时任务调度器（集成任务系统）"""

    # 信号，用于在主线程中触发回调
    task_triggered = pyqtSignal(str)  # task_id

    def __init__(self):
        super().__init__()
        self._tasks: Dict[str, ScheduledTask] = {}
        self._pending_tasks: Dict[str, ScheduledTask] = {}  # 待执行的任务
        self._persistence_path = self._get_persistence_path()
        self._callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._check_timer: Optional[QTimer] = None

        # 连接信号
        self.task_triggered.connect(self._on_task_triggered_signal)

        # 加载持久化任务
        self._load_tasks()

        # 启动检查定时器，每秒检查一次待执行任务
        self._start_check_timer()
        
        # 集成任务系统
        from core.task_system import task_manager, TaskType
        self._task_manager = task_manager
        self._task_types = TaskType
        
    def _get_persistence_path(self) -> str:
        """获取持久化文件路径"""
        if os.name == "nt":
            app_data = os.getenv("APPDATA")
            user_data_dir = os.path.join(app_data, "Vivian")
        else:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".vivian")
        
        os.makedirs(user_data_dir, exist_ok=True)
        return os.path.join(user_data_dir, "scheduled_tasks.json")
    
    def _load_tasks(self):
        """加载持久化的任务"""
        try:
            if os.path.exists(self._persistence_path):
                with open(self._persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for task_data in data.get("tasks", []):
                        task = ScheduledTask.from_dict(task_data)
                        # 只加载未完成的任务
                        if task.status == TaskStatus.PENDING and task.scheduled_time > time.time():
                            self._tasks[task.id] = task
                            self._schedule_task(task)
                logger.info(f"[Scheduler] 已加载 {len(self._tasks)} 个定时任务")
        except Exception as e:
            logger.error(f"[Scheduler] 加载任务失败: {e}")
    
    def _save_tasks(self):
        """持久化任务"""
        try:
            data = {
                "tasks": [task.to_dict() for task in self._tasks.values()],
                "saved_at": time.time()
            }
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[Scheduler] 保存任务失败: {e}")
    
    def _start_check_timer(self):
        """启动检查定时器，每秒检查一次待执行任务"""
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(1000)  # 每秒检查一次
        self._check_timer.timeout.connect(self._check_pending_tasks)
        self._check_timer.start()
        logger.debug("[Scheduler] 检查定时器已启动")

    def _check_pending_tasks(self):
        """检查待执行任务"""
        now = time.time()
        task_ids_to_execute = []

        for task_id, task in list(self._pending_tasks.items()):
            if task.scheduled_time <= now:
                task_ids_to_execute.append(task_id)

        # 在主线程中触发任务执行
        for task_id in task_ids_to_execute:
            self.task_triggered.emit(task_id)

    def _on_task_triggered_signal(self, task_id: str):
        """任务触发信号处理（使用任务系统）"""
        scheduled_task = self._pending_tasks.pop(task_id, None)
        if scheduled_task:
            asyncio.create_task(self._execute_task_with_task_system(scheduled_task))
    
    async def _execute_task_with_task_system(self, scheduled_task: ScheduledTask):
        """使用任务系统执行任务"""
        try:
            # 检查打扰控制器
            can_interrupt = True
            try:
                from core.interruption_controller import get_interruption_controller
                controller = get_interruption_controller()
                can_interrupt, reason = controller.should_interrupt("high")
                if not can_interrupt:
                    logger.debug(f"[Scheduler] 打扰被阻止: {reason}")
                    # 推迟任务执行
                    self._schedule_task(scheduled_task)
                    return
            except ImportError:
                pass
            
            # 创建任务系统任务
            if scheduled_task.task_type == TaskType.REMINDER:
                task_handle = await self._task_manager.create_task(
                    task_type=self._task_types.SCHEDULED_REMINDER,
                    description=f"定时提醒: {scheduled_task.message}",
                    message=scheduled_task.message,
                    scheduled_time=scheduled_task.scheduled_time
                )
                
                # 获取任务实例并设置回调
                task = self._task_manager._tasks.get(task_handle.task_id)
                if task:
                    task.set_callback(self._callback)
                    task._task_state = self._task_manager._task_states.get(task_handle.task_id)
                
                # 启动任务
                await self._task_manager.start_task(task_handle.task_id)
                
            elif scheduled_task.task_type == TaskType.TOOL_CALL:
                task_handle = await self._task_manager.create_task(
                    task_type=self._task_types.SCHEDULED_TOOL_CALL,
                    description=f"定时工具调用: {scheduled_task.tool_name}",
                    tool_name=scheduled_task.tool_name,
                    tool_arguments=scheduled_task.tool_arguments,
                    scheduled_time=scheduled_task.scheduled_time
                )
                
                # 获取任务实例并设置回调
                task = self._task_manager._tasks.get(task_handle.task_id)
                if task:
                    task.set_callback(self._callback)
                    task._task_state = self._task_manager._task_states.get(task_handle.task_id)
                
                # 启动任务
                await self._task_manager.start_task(task_handle.task_id)
            
            # 如果是重复任务，重新调度
            if scheduled_task.repeat_interval:
                scheduled_task.scheduled_time = time.time() + scheduled_task.repeat_interval
                self._schedule_task(scheduled_task)
            else:
                self._cleanup_task(scheduled_task.id)
            
        except Exception as e:
            logger.error(f"[Scheduler] 执行任务失败: {e}")

    def _schedule_task(self, task: ScheduledTask):
        """调度任务"""
        now = time.time()
        delay = task.scheduled_time - now

        if delay <= 0:
            # 任务已经过期，立即执行
            self.task_triggered.emit(task.id)
            return

        # 添加到待执行任务字典
        self._pending_tasks[task.id] = task
        logger.debug(f"[Scheduler] 任务 {task.id} 已调度，将在 {delay:.2f} 秒后执行")
    

    
    def _cleanup_task(self, task_id: str):
        """清理任务"""
        self._pending_tasks.pop(task_id, None)
        self._tasks.pop(task_id, None)
        self._save_tasks()
    
    def set_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """设置任务触发回调"""
        self._callback = callback
    
    def schedule_reminder(
        self,
        message: str,
        scheduled_time: float,
        repeat_interval: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        调度一个提醒任务
        
        Args:
            message: 提醒消息内容
            scheduled_time: 计划执行时间戳
            repeat_interval: 重复间隔（秒），None表示单次
            metadata: 元数据
        
        Returns:
            任务ID
        """
        task = ScheduledTask(
            task_type=TaskType.REMINDER,
            scheduled_time=scheduled_time,
            message=message,
            repeat_interval=repeat_interval,
            metadata=metadata
        )
        
        self._tasks[task.id] = task
        self._schedule_task(task)
        self._save_tasks()
        
        logger.info(f"[Scheduler] 已创建提醒任务 {task.id}: {message}")
        return task.id
    
    def schedule_tool_call(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        scheduled_time: float,
        repeat_interval: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        调度一个工具调用任务
        
        Args:
            tool_name: 工具名称
            tool_arguments: 工具参数
            scheduled_time: 计划执行时间戳
            repeat_interval: 重复间隔（秒），None表示单次
            metadata: 元数据
        
        Returns:
            任务ID
        """
        task = ScheduledTask(
            task_type=TaskType.TOOL_CALL,
            scheduled_time=scheduled_time,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            repeat_interval=repeat_interval,
            metadata=metadata
        )
        
        self._tasks[task.id] = task
        self._schedule_task(task)
        self._save_tasks()
        
        logger.info(f"[Scheduler] 已创建工具调用任务 {task.id}: {tool_name}")
        return task.id
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
        
        Returns:
            是否成功取消
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"[Scheduler] 任务 {task_id} 不存在")
            return False

        task.status = TaskStatus.CANCELLED
        self._cleanup_task(task_id)

        logger.info(f"[Scheduler] 任务 {task_id} 已取消")
        return True
    
    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        return self._tasks.get(task_id)
    
    def list_tasks(self) -> List[ScheduledTask]:
        """获取所有任务列表"""
        return list(self._tasks.values())
    
    def parse_time_spec(self, time_spec: str) -> float:
        """
        解析时间规格（仅支持 ISO 8601 格式）

        支持的格式：
        - ISO 8601 日期时间: "2024-01-15T10:30:00", "2024-01-15T10:30"
        - ISO 8601 持续时间: "PT2M", "PT2H30M", "P1DT2H", "PT30S"

        Args:
            time_spec: ISO 8601 时间字符串

        Returns:
            时间戳

        Raises:
            ValueError: 无法解析的时间格式
        """
        now = datetime.now()

        # 1. 尝试解析 ISO 8601 日期时间格式
        iso_datetime_formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ]
        for fmt in iso_datetime_formats:
            try:
                dt = datetime.strptime(time_spec.strip(), fmt)
                return dt.timestamp()
            except ValueError:
                continue

        # 2. 尝试解析 ISO 8601 持续时间格式 (PnYnMnDTnHnMnS)
        iso_duration_result = self._parse_iso_duration(time_spec.strip())
        if iso_duration_result is not None:
            return (now + iso_duration_result).timestamp()

        raise ValueError(f"不支持的时间格式，请使用 ISO 8601 格式。例如：PT2M（2分钟后）、PT1H30M（1小时30分钟后）、2024-01-15T10:30:00（指定时间）")

    def _parse_iso_duration(self, time_spec: str) -> Optional[timedelta]:
        """
        解析 ISO 8601 持续时间格式 (PnYnMnDTnHnMnS)

        格式说明：
        - P: 开始标记
        - Y: 年
        - M: 月
        - D: 日
        - T: 时间部分开始标记
        - H: 小时
        - M: 分钟
        - S: 秒

        示例：
        - "PT2M"      -> 2分钟
        - "PT2H30M"   -> 2小时30分钟
        - "P1DT2H"    -> 1天2小时
        - "P1Y2M3DT4H5M6S" -> 1年2月3天4小时5分钟6秒

        Args:
            time_spec: ISO 8601 持续时间字符串

        Returns:
            timedelta 对象，解析失败返回 None
        """
        if not time_spec.startswith('P'):
            return None

        import re

        # 匹配格式：PnYnMnDTnHnMnS
        pattern = r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$'
        match = re.match(pattern, time_spec)

        if not match:
            return None

        years = int(match.group(1)) if match.group(1) else 0
        months = int(match.group(2)) if match.group(2) else 0
        days = int(match.group(3)) if match.group(3) else 0
        hours = int(match.group(4)) if match.group(4) else 0
        minutes = int(match.group(5)) if match.group(5) else 0
        seconds = int(match.group(6)) if match.group(6) else 0

        # 将年和月转换为近似天数（简化处理）
        total_days = days + years * 365 + months * 30

        return timedelta(days=total_days, hours=hours, minutes=minutes, seconds=seconds)
    
    def shutdown(self):
        """关闭调度器"""
        if self._check_timer:
            self._check_timer.stop()
            self._check_timer.deleteLater()
        self._pending_tasks.clear()
        self._tasks.clear()
        logger.info("[Scheduler] 调度器已关闭")


# 全局单例
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def init_scheduler(callback: Optional[Callable] = None) -> Scheduler:
    """初始化调度器"""
    global _scheduler
    _scheduler = Scheduler()
    if callback:
        _scheduler.set_callback(callback)
    return _scheduler