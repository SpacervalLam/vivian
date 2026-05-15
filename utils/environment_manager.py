import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Tuple
from loguru import logger

try:
    import ctypes
    from ctypes import wintypes

    import win32api
    import win32clipboard
    import win32con
    import win32gui
    import win32process

    WIN32_AVAILABLE = True
    logger.info("[EnvironmentManager] pywin32 库已安装，支持环境感知")
except ImportError:
    WIN32_AVAILABLE = False
    logger.warning("[EnvironmentManager] pywin32 库未安装，无法使用环境感知功能")

try:
    import psutil

    PSUTIL_AVAILABLE = True
    logger.info("[EnvironmentManager] psutil 库已安装，支持系统资源监控")
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("[EnvironmentManager] psutil 库未安装，无法监控系统资源")


class EnvironmentManager:
    """环境管理器，负责监控和获取系统环境信息"""

    def __init__(self, monitor_interval: int = 5):
        self.monitor_interval = monitor_interval
        self.environment_info = {
            "current_window": "",
            "window_class": "",
            "window_rect": (0, 0, 0, 0),
            "clipboard_content": "",
            "mouse_position": (0, 0),
            "system_time": "",
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "battery_level": 100,
            "is_plugged_in": True,
            "network_status": "connected",
            "active_processes": [],
            "keyboard_activity": False,
            "last_key_press_time": 0,
            "mouse_activity": True,
            "last_mouse_move_time": time.time(),
        }

        self.keyboard_hook = None
        self.is_monitoring = False
        self.monitor_thread = None

        if WIN32_AVAILABLE:
            self.start_monitoring()

    def start_monitoring(self):
        """启动环境监控"""
        if not self.is_monitoring and WIN32_AVAILABLE:
            self.is_monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_environment, daemon=True
            )
            self.monitor_thread.start()
            self._install_keyboard_hook()
            logger.info("[EnvironmentManager] 环境监控已启动")

    def stop_monitoring(self):
        """停止环境监控"""
        if self.is_monitoring:
            self.is_monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=1.0)
            self._uninstall_keyboard_hook()
            logger.info("[EnvironmentManager] 环境监控已停止")

    def _monitor_environment(self):
        """监控环境变化"""
        while self.is_monitoring:
            try:
                self._update_system_time()
                self._update_active_window()
                self._update_mouse_position()
                self._update_system_resources()
                self._update_active_processes()
            except Exception as e:
                logger.error(f"[EnvironmentManager] 环境监控失败: {e}")

            time.sleep(self.monitor_interval)

    def _update_system_time(self):
        """更新系统时间"""
        self.environment_info["system_time"] = datetime.now().isoformat()

    def _update_active_window(self):
        """更新当前活动窗口信息"""
        if WIN32_AVAILABLE:
            try:
                window = win32gui.GetForegroundWindow()
                self.environment_info["current_window"] = win32gui.GetWindowText(window)
                self.environment_info["window_class"] = win32gui.GetClassName(window)
                self.environment_info["window_rect"] = win32gui.GetWindowRect(window)
            except Exception:
                pass

    def _update_mouse_position(self):
        """更新鼠标位置"""
        if WIN32_AVAILABLE:
            try:
                mouse_pos = win32api.GetCursorPos()
                self.environment_info["mouse_position"] = mouse_pos

                current_time = time.time()
                self.environment_info["last_mouse_move_time"] = current_time
                self.environment_info["mouse_activity"] = True

            except Exception:
                pass

    def _update_system_resources(self):
        """更新系统资源使用情况"""
        if PSUTIL_AVAILABLE:
            try:
                self.environment_info["cpu_usage"] = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                self.environment_info["memory_usage"] = memory.percent

                battery = psutil.sensors_battery()
                if battery:
                    self.environment_info["battery_level"] = battery.percent
                    self.environment_info["is_plugged_in"] = battery.power_plugged

                net_stats = psutil.net_io_counters()
                self.environment_info["network_status"] = (
                    "connected" if net_stats.bytes_sent > 0 else "disconnected"
                )

            except Exception:
                pass

    def _update_active_processes(self):
        """更新活跃进程列表"""
        if PSUTIL_AVAILABLE:
            try:
                processes = []
                for proc in psutil.process_iter(["name", "cpu_percent"]):
                    try:
                        proc_info = proc.info
                        processes.append((proc_info["name"], proc_info["cpu_percent"]))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                processes.sort(key=lambda x: x[1], reverse=True)
                self.environment_info["active_processes"] = processes[:5]

            except Exception:
                pass

    def _install_keyboard_hook(self):
        """安装键盘钩子"""
        if not WIN32_AVAILABLE:
            return

        try:

            def keyboard_callback(nCode, wParam, lParam):
                if nCode == win32con.HC_ACTION:
                    if wParam in [win32con.WM_KEYDOWN, win32con.WM_SYSKEYDOWN]:
                        self.environment_info["keyboard_activity"] = True
                        self.environment_info["last_key_press_time"] = time.time()
                return win32gui.CallNextHookEx(
                    self.keyboard_hook, nCode, wParam, lParam
                )

            user32 = ctypes.windll.user32
            self.keyboard_hook = user32.SetWindowsHookExW(
                win32con.WH_KEYBOARD_LL, keyboard_callback, None, 0
            )

        except Exception:
            self.keyboard_hook = None

    def _uninstall_keyboard_hook(self):
        """卸载键盘钩子"""
        if WIN32_AVAILABLE and self.keyboard_hook:
            try:
                user32 = ctypes.windll.user32
                user32.UnhookWindowsHookEx(self.keyboard_hook)
                self.keyboard_hook = None
            except Exception:
                pass

    def get_clipboard_content(self) -> str:
        """获取剪贴板内容"""
        if not WIN32_AVAILABLE:
            return ""

        try:
            win32clipboard.OpenClipboard()
            content = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            self.environment_info["clipboard_content"] = content
            return content
        except Exception as e:
            logger.warning(f"[EnvironmentManager] 获取剪贴板内容失败: {e}")
            return ""

    def get_active_window(self) -> str:
        """获取当前活动窗口"""
        return self.environment_info["current_window"]

    def get_window_class(self) -> str:
        """获取当前活动窗口的类名"""
        return self.environment_info["window_class"]

    def get_window_rect(self) -> tuple:
        """获取当前活动窗口的矩形区域"""
        return self.environment_info["window_rect"]

    def get_mouse_position(self) -> tuple:
        """获取当前鼠标位置"""
        return self.environment_info["mouse_position"]

    def get_system_resources(self) -> dict:
        """获取系统资源使用情况"""
        return {
            "cpu_usage": self.environment_info["cpu_usage"],
            "memory_usage": self.environment_info["memory_usage"],
            "battery_level": self.environment_info["battery_level"],
            "is_plugged_in": self.environment_info["is_plugged_in"],
            "network_status": self.environment_info["network_status"],
        }

    def get_active_processes(self) -> list:
        """获取活跃进程列表"""
        return self.environment_info["active_processes"]

    def get_user_activity(self) -> dict:
        """获取用户活动信息"""
        current_time = time.time()

        keyboard_idle_time = current_time - self.environment_info["last_key_press_time"]
        mouse_idle_time = current_time - self.environment_info["last_mouse_move_time"]

        return {
            "keyboard_active": self.environment_info["keyboard_activity"],
            "keyboard_idle_time": keyboard_idle_time,
            "mouse_active": self.environment_info["mouse_activity"],
            "mouse_idle_time": mouse_idle_time,
            "last_key_press_time": self.environment_info["last_key_press_time"],
            "last_mouse_move_time": self.environment_info["last_mouse_move_time"],
            "is_idle": keyboard_idle_time > 60 and mouse_idle_time > 60,
        }

    def get_environment_info(self) -> Dict[str, Any]:
        """获取完整的环境信息"""
        return self.environment_info.copy()

    def get_current_state(self) -> Dict[str, Any]:
        """获取当前环境状态，用于主动交互决策"""
        current_time = datetime.now()
        
        return {
            "active_window": self.environment_info["current_window"],
            "window_class": self.environment_info["window_class"],
            "system_time": current_time.isoformat(),
            "hour": current_time.hour,
            "minute": current_time.minute,
            "day_of_week": current_time.weekday(),  # 0-6, 0=Monday
            "is_work_hours": 9 <= current_time.hour < 18,
            "is_night": current_time.hour >= 22 or current_time.hour < 6,
            "cpu_usage": self.environment_info["cpu_usage"],
            "memory_usage": self.environment_info["memory_usage"],
            "battery_level": self.environment_info["battery_level"],
            "is_plugged_in": self.environment_info["is_plugged_in"],
            "user_activity": self.get_user_activity(),
            "clipboard_content": self.environment_info["clipboard_content"],
            "mouse_position": self.environment_info["mouse_position"],
            "active_processes": [proc[0] for proc in self.environment_info["active_processes"]],
        }

    def set_monitor_interval(self, interval: int):
        """设置监控间隔"""
        self.monitor_interval = max(1, interval)
        logger.debug(f"[EnvironmentManager] 监控间隔已设置为: {self.monitor_interval}秒")

    def __del__(self):
        """析构函数，确保资源被正确释放"""
        self.stop_monitoring()
