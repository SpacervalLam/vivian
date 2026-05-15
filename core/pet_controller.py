import json
import math
from enum import IntEnum
from typing import Any, Dict, List, Optional, Union

from loguru import logger


class ControlCommandType(IntEnum):
    MOTION = 1
    EXPRESSION = 2
    MOUSE_FOLLOW = 3
    WINDOW_SIZE = 4
    WINDOW_POSITION = 5
    OPACITY = 6
    SLEEP = 7


class PetController:
    def __init__(self, main_window=None):
        self.main_window = main_window
        self._animation_manager = None
        self._expression_manager = None
        self._live2d_widget = None
        self._state_machine = None
        
        self._validate_and_set_managers()

    def _validate_and_set_managers(self):
        if self.main_window:
            if hasattr(self.main_window, 'animation_manager'):
                self._animation_manager = self.main_window.animation_manager
            if hasattr(self.main_window, 'expression_manager'):
                self._expression_manager = self.main_window.expression_manager
            if hasattr(self.main_window, 'live2d_widget'):
                self._live2d_widget = self.main_window.live2d_widget
            if hasattr(self.main_window, 'state_machine'):
                self._state_machine = self.main_window.state_machine

    def set_managers(self, **kwargs):
        if 'animation_manager' in kwargs:
            self._animation_manager = kwargs['animation_manager']
        if 'expression_manager' in kwargs:
            self._expression_manager = kwargs['expression_manager']
        if 'live2d_widget' in kwargs:
            self._live2d_widget = kwargs['live2d_widget']
        if 'state_machine' in kwargs:
            self._state_machine = kwargs['state_machine']

    def play_motion(
        self,
        name: str,
        priority: int = 50,
        interruptible: bool = True,
        loop: bool = False
    ) -> Dict[str, Any]:
        """播放指定动作
        
        Args:
            name: 动作名称
            priority: 优先级 (0-200)，值越高优先级越高
            interruptible: 是否可被打断
            loop: 是否循环播放
        
        Returns:
            执行结果字典，包含success和message字段
        """
        if not self._animation_manager:
            return {"success": False, "message": "AnimationManager未初始化"}
        
        if not isinstance(name, str) or not name.strip():
            return {"success": False, "message": "动作名称无效"}
        
        if not isinstance(priority, int) or priority < 0 or priority > 200:
            return {"success": False, "message": "优先级必须在0-200范围内"}
        
        result = self._animation_manager.play_motion(
            name=name,
            priority=priority,
            interruptible=interruptible,
            loop=loop
        )
        
        if result:
            return {
                "success": True,
                "message": f"动作 '{name}' 已开始播放",
                "motion_name": name,
                "priority": priority
            }
        else:
            return {"success": False, "message": f"未找到动作 '{name}'"}

    def stop_motion(self, force: bool = False) -> Dict[str, Any]:
        """停止当前播放的动作
        
        Args:
            force: 是否强制停止（忽略不可中断标志）
        
        Returns:
            执行结果字典
        """
        if not self._animation_manager:
            return {"success": False, "message": "AnimationManager未初始化"}
        
        success = self._animation_manager.stop_motion(force=force)
        return {
            "success": success,
            "message": "动作已停止" if success else "无法停止当前动作"
        }

    def stop_all_motions(self) -> Dict[str, Any]:
        """停止所有动作（包括队列中的）"""
        if not self._animation_manager:
            return {"success": False, "message": "AnimationManager未初始化"}
        
        self._animation_manager.stop_all_motions()
        return {"success": True, "message": "所有动作已停止"}

    def set_expression(
        self,
        name: str,
        duration_ms: Optional[int] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """设置表情
        
        Args:
            name: 表情名称
            duration_ms: 表情持续时间（毫秒），None表示永久
            force: 是否强制覆盖当前表情
        
        Returns:
            执行结果字典
        """
        if not self._expression_manager:
            return {"success": False, "message": "ExpressionManager未初始化"}
        
        if not isinstance(name, str) or not name.strip():
            return {"success": False, "message": "表情名称无效"}
        
        if duration_ms is not None:
            if not isinstance(duration_ms, int) or duration_ms < 0:
                return {"success": False, "message": "持续时间必须为非负整数"}
        
        success = self._expression_manager.set_expression(
            name=name,
            duration_ms=duration_ms,
            force=force
        )
        
        return {
            "success": success,
            "message": f"表情 '{name}' 已设置" if success else f"无法设置表情 '{name}'",
            "expression_name": name
        }

    def reset_expression(self) -> Dict[str, Any]:
        """重置表情为默认状态"""
        if not self._expression_manager:
            return {"success": False, "message": "ExpressionManager未初始化"}
        
        self._expression_manager.reset_expression()
        return {"success": True, "message": "表情已重置为默认"}

    def set_mouse_follow(self, enabled: bool) -> Dict[str, Any]:
        """设置鼠标跟随状态
        
        Args:
            enabled: 是否启用鼠标跟随
        
        Returns:
            执行结果字典
        """
        if not self._live2d_widget:
            return {"success": False, "message": "Live2DWidget未初始化"}
        
        if not isinstance(enabled, bool):
            return {"success": False, "message": "参数必须为布尔值"}
        
        self._live2d_widget.set_mouse_follow(enabled)
        return {
            "success": True,
            "message": f"鼠标跟随已{'开启' if enabled else '关闭'}",
            "enabled": enabled
        }

    def get_mouse_follow(self) -> Dict[str, Any]:
        """获取当前鼠标跟随状态"""
        if not self._live2d_widget:
            return {"success": False, "message": "Live2DWidget未初始化"}
        
        enabled = self._live2d_widget.get_mouse_follow()
        return {"success": True, "enabled": enabled}

    def set_window_size(self, width: int, height: int) -> Dict[str, Any]:
        """设置窗口尺寸
        
        Args:
            width: 窗口宽度（像素）
            height: 窗口高度（像素）
        
        Returns:
            执行结果字典
        """
        if not self.main_window:
            return {"success": False, "message": "主窗口未初始化"}
        
        if not isinstance(width, int) or width <= 0:
            return {"success": False, "message": "宽度必须为正整数"}
        
        if not isinstance(height, int) or height <= 0:
            return {"success": False, "message": "高度必须为正整数"}
        
        min_size = 100
        max_size = 2000
        
        # 获取屏幕几何信息以防止窗口超出屏幕
        from PyQt5.QtWidgets import QApplication
        screen_geo = QApplication.primaryScreen().geometry()
        
        # 获取当前窗口位置
        current_pos = self.main_window.pos()
        
        width = max(min(width, max_size), min_size)
        height = max(min(height, max_size), min_size)
        
        # 确保窗口不会超出屏幕右侧或底部
        max_available_width = screen_geo.width() - current_pos.x()
        max_available_height = screen_geo.height() - current_pos.y()
        
        # 保持至少 10px 的边距，避免完全超出屏幕
        width = min(width, max_available_width - 10)
        height = min(height, max_available_height - 10)
        
        # 确保最小尺寸仍然得到尊重
        width = max(min_size, width)
        height = max(min_size, height)
        
        self.main_window.resize(width, height)
        
        return {
            "success": True,
            "message": f"窗口尺寸已设置为 {width}x{height}",
            "width": width,
            "height": height
        }

    def set_window_position(self, x: int, y: int) -> Dict[str, Any]:
        """设置窗口位置
        
        Args:
            x: 窗口左上角X坐标
            y: 窗口左上角Y坐标
        
        Returns:
            执行结果字典
        """
        if not self.main_window:
            return {"success": False, "message": "主窗口未初始化"}
        
        if not isinstance(x, int):
            return {"success": False, "message": "X坐标必须为整数"}
        
        if not isinstance(y, int):
            return {"success": False, "message": "Y坐标必须为整数"}
        
        self.main_window.move(x, y)
        
        return {
            "success": True,
            "message": f"窗口位置已设置为 ({x}, {y})",
            "x": x,
            "y": y
        }

    def get_window_position(self) -> Dict[str, Any]:
        """获取当前窗口位置"""
        if not self.main_window:
            return {"success": False, "message": "主窗口未初始化"}
        
        pos = self.main_window.pos()
        return {"success": True, "x": pos.x(), "y": pos.y()}

    def get_window_size(self) -> Dict[str, Any]:
        """获取当前窗口尺寸"""
        if not self.main_window:
            return {"success": False, "message": "主窗口未初始化"}
        
        size = self.main_window.size()
        return {"success": True, "width": size.width(), "height": size.height()}

    def set_opacity(self, opacity: float) -> Dict[str, Any]:
        """设置窗口透明度
        
        Args:
            opacity: 透明度值 (0.0-1.0)，0为完全透明，1为完全不透明
        
        Returns:
            执行结果字典
        """
        if not self.main_window:
            return {"success": False, "message": "主窗口未初始化"}
        
        if not isinstance(opacity, (int, float)):
            return {"success": False, "message": "透明度必须为数值"}
        
        opacity = max(0.0, min(1.0, float(opacity)))
        
        self.main_window.setWindowOpacity(opacity)
        
        return {
            "success": True,
            "message": f"窗口透明度已设置为 {opacity:.2f}",
            "opacity": opacity
        }

    def get_opacity(self) -> Dict[str, Any]:
        """获取当前窗口透明度"""
        if not self.main_window:
            return {"success": False, "message": "主窗口未初始化"}
        
        opacity = self.main_window.windowOpacity()
        return {"success": True, "opacity": opacity}

    def set_sleep(self, asleep: bool) -> Dict[str, Any]:
        """设置睡眠状态
        
        Args:
            asleep: 是否进入睡眠状态
        
        Returns:
            执行结果字典
        """
        if not self._live2d_widget:
            return {"success": False, "message": "Live2DWidget未初始化"}
        
        if not isinstance(asleep, bool):
            return {"success": False, "message": "参数必须为布尔值"}
        
        self._live2d_widget.set_asleep(asleep)
        
        if asleep:
            self.set_expression("sleepy")
            self.set_mouse_follow(False)
        
        return {
            "success": True,
            "message": f"睡眠状态已{'开启' if asleep else '关闭'}",
            "asleep": asleep
        }

    def get_sleep_state(self) -> Dict[str, Any]:
        """获取当前睡眠状态"""
        if not self._live2d_widget:
            return {"success": False, "message": "Live2DWidget未初始化"}
        
        asleep = getattr(self._live2d_widget, 'is_asleep', False)
        return {"success": True, "asleep": asleep}
    
    def set_avoid_mouse(self, enabled: bool) -> Dict[str, Any]:
        """设置智能躲避鼠标模式
        
        当鼠标靠近桌宠窗口时，桌宠会自动"避开"
        
        Args:
            enabled: 是否启用智能躲避
            
        Returns:
            执行结果字典
        """
        if not self._live2d_widget:
            return {"success": False, "message": "Live2DWidget未初始化"}
        
        if not isinstance(enabled, bool):
            return {"success": False, "message": "参数必须为布尔值"}
        
        self._live2d_widget.set_avoid_mouse(enabled)
        
        return {
            "success": True,
            "message": f"智能躲避模式已{'开启' if enabled else '关闭'}",
            "enabled": enabled
        }
    
    def get_avoid_mouse(self) -> Dict[str, Any]:
        """获取智能躲避鼠标模式状态"""
        if not self._live2d_widget:
            return {"success": False, "message": "Live2DWidget未初始化"}
        
        enabled = self._live2d_widget.get_avoid_mouse()
        return {"success": True, "enabled": enabled}

    def list_available_motions(self) -> Dict[str, Any]:
        """获取可用的动作列表"""
        if not self._animation_manager or not hasattr(self._animation_manager, 'resource_loader'):
            return {"success": False, "message": "资源加载器未初始化"}
        
        motions = self._animation_manager.resource_loader.list_motion_names()
        return {"success": True, "motions": motions}

    def list_available_expressions(self) -> Dict[str, Any]:
        """获取可用的表情列表"""
        if not self._expression_manager:
            return {"success": False, "message": "ExpressionManager未初始化"}
        
        expressions = self._expression_manager.list_expressions()
        return {"success": True, "expressions": expressions}

    def get_status(self) -> Dict[str, Any]:
        """获取桌宠当前状态的完整信息"""
        status = {}
        
        if self._animation_manager:
            status["motion"] = self._animation_manager.get_statistics()
        
        if self._expression_manager:
            status["expression"] = self._expression_manager.get_statistics()
        
        if self._state_machine:
            status["state"] = self._state_machine.get_statistics()
        
        window_pos = self.get_window_position()
        if window_pos["success"]:
            status["window_position"] = {"x": window_pos["x"], "y": window_pos["y"]}
        
        window_size = self.get_window_size()
        if window_size["success"]:
            status["window_size"] = {"width": window_size["width"], "height": window_size["height"]}
        
        opacity = self.get_opacity()
        if opacity["success"]:
            status["opacity"] = opacity["opacity"]
        
        mouse_follow = self.get_mouse_follow()
        if mouse_follow["success"]:
            status["mouse_follow"] = mouse_follow["enabled"]
        
        sleep_state = self.get_sleep_state()
        if sleep_state["success"]:
            status["sleep"] = sleep_state["asleep"]
        
        return {"success": True, "status": status}

    def execute_command(self, command: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """执行控制命令
        
        Args:
            command: 命令字典或JSON字符串，包含action字段和相关参数
        
        Returns:
            执行结果字典
        """
        if isinstance(command, str):
            try:
                command = json.loads(command)
            except json.JSONDecodeError:
                return {"success": False, "message": "无效的JSON格式"}
        
        if not isinstance(command, dict) or "action" not in command:
            return {"success": False, "message": "命令格式无效，缺少action字段"}
        
        action = command["action"]
        params = command.get("params", {})
        
        action_map = {
            "play_motion": self.play_motion,
            "stop_motion": self.stop_motion,
            "stop_all_motions": self.stop_all_motions,
            "set_expression": self.set_expression,
            "reset_expression": self.reset_expression,
            "set_mouse_follow": self.set_mouse_follow,
            "get_mouse_follow": self.get_mouse_follow,
            "set_window_size": self.set_window_size,
            "set_window_position": self.set_window_position,
            "get_window_position": self.get_window_position,
            "get_window_size": self.get_window_size,
            "set_opacity": self.set_opacity,
            "get_opacity": self.get_opacity,
            "set_sleep": self.set_sleep,
            "get_sleep_state": self.get_sleep_state,
            "set_avoid_mouse": self.set_avoid_mouse,
            "get_avoid_mouse": self.get_avoid_mouse,
            "list_motions": self.list_available_motions,
            "list_expressions": self.list_available_expressions,
            "get_status": self.get_status,
        }
        
        if action not in action_map:
            return {"success": False, "message": f"未知动作: {action}"}
        
        try:
            return action_map[action](**params)
        except TypeError as e:
            return {"success": False, "message": f"参数错误: {str(e)}"}
        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            return {"success": False, "message": f"执行失败: {str(e)}"}

    def batch_execute(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量执行多个命令
        
        Args:
            commands: 命令列表
        
        Returns:
            每个命令的执行结果列表
        """
        results = []
        for command in commands:
            result = self.execute_command(command)
            results.append(result)
        return results