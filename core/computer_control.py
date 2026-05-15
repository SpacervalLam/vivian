import os
import platform
import subprocess
import sys

import win32api
import win32con
import win32gui
from loguru import logger


class ComputerController:
    """电脑控制执行引擎
    
    接收代码 -> 本地沙箱执行代码 -> 获取结果
    """

    def __init__(self):
        self.os_type = platform.system()
        self.logger = logger
        self.app_map = {
            "微信": {"proc": "WeChat.exe", "path": "WeChat.exe"},
            "wechat": {"proc": "WeChat.exe", "path": "WeChat.exe"},
            "浏览器": {
                "proc": ["msedge.exe", "chrome.exe"],
                "path": "msedge.exe",
            },
            "edge": {"proc": "msedge.exe", "path": "msedge.exe"},
            "chrome": {"proc": "chrome.exe", "path": "chrome.exe"},
            "记事本": {"proc": "notepad.exe", "path": "notepad.exe"},
            "计算器": {"proc": "CalculatorApp.exe", "path": "calc.exe"},
            "音乐": {"proc": "CloudMusic.exe", "path": "cloudmusic.exe"},
            "vscode": {"proc": "Code.exe", "path": "Code.exe"},
            "cmd": {"proc": "cmd.exe", "path": "cmd.exe"},
            "任务管理器": {"proc": "Taskmgr.exe", "path": "taskmgr.exe"},
            "文件资源管理器": {"proc": "explorer.exe", "path": "explorer.exe"},
            "资源管理器": {"proc": "explorer.exe", "path": "explorer.exe"},
            "画图": {"proc": "mspaint.exe", "path": "mspaint.exe"},
            "照片": {
                "proc": "Photos.exe",
                "path": "explorer.exe shell:AppsFolder\\Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
            },
            "视频": {
                "proc": "Movies & TV.exe",
                "path": "explorer.exe shell:AppsFolder\\Microsoft.ZuneVideo_8wekyb3d8bbwe!Microsoft.ZuneVideo",
            },
        }
        self.logger.info(f"ComputerController initialized for {self.os_type}")

    def execute_code(self, code: str) -> str:
        """
        执行 Python 代码并捕获输出
        """
        self.logger.info(f"准备执行代码: {code[:50]}...")

        # 捕获标准输出
        import io
        from contextlib import redirect_stderr, redirect_stdout

        output_buffer = io.StringIO()

        try:
            # 这里的 globals() 传递 context，可以注入一些辅助函数
            with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                exec(
                    code,
                    {
                        "os": os,
                        "subprocess": subprocess,
                        "sys": sys,
                        "win32gui": win32gui,
                        "controller": self,  # 将自身注入，方便递归调用
                    },
                )

            result = output_buffer.getvalue()
            if not result:
                result = "执行成功，无控制台输出。"
            self.logger.info(f"代码执行成功: {result[:50]}...")
            return result

        except Exception as e:
            error_msg = f"执行出错: {str(e)}"
            self.logger.error(f"代码执行失败: {error_msg}")
            return error_msg

    def open_app(self, app_name: str) -> str:
        """
        智能打开应用，带状态检测
        """
        self.logger.info(f"尝试打开应用: {app_name}")
        app_name_lower = app_name.lower()
        target = self.app_map.get(app_name, None)

        # 如果不在映射表中，尝试去匹配映射表的 Key
        if not target:
            for key, val in self.app_map.items():
                if key in app_name_lower:
                    target = val
                    break

        proc_name = target["proc"] if target else None
        run_cmd = target["path"] if target else app_name

        # 1. 状态检测 (避免重复打开)
        # 对于像微信、音乐播放器这类应用，通常只需要一个实例
        singleton_apps = ["WeChat.exe", "CloudMusic.exe", "msedge.exe", "chrome.exe"]

        if proc_name:
            # 如果 proc_name 是列表（比如浏览器可能是 chrome 或 edge），检查任一
            procs_to_check = proc_name if isinstance(proc_name, list) else [proc_name]

            is_running = False
            for p in procs_to_check:
                if self._check_process_running(p):
                    is_running = True
                    break

            if is_running and (
                proc_name in singleton_apps
                or any(s in str(proc_name) for s in singleton_apps)
            ):
                # 尝试置顶窗口 (高级功能，这里简化)
                return f"{app_name} 已经在运行啦，不需要重复打开哦~"

        # 2. 启动应用
        try:
            if self.os_type == "Windows":
                # 使用 start 命令非阻塞启动
                subprocess.Popen(f"start {run_cmd}", shell=True)
            elif self.os_type == "Darwin":
                subprocess.Popen(["open", "-a", run_cmd])
            else:  # Linux
                subprocess.Popen(["nohup", run_cmd, "&"], shell=True)

            return f"正在启动 {app_name}..."
        except Exception as e:
            error_msg = f"无法打开 {app_name}: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def _check_process_running(self, process_name: str) -> bool:
        """
        检查进程是否存在 (利用 tasklist 比 psutil 轻量，虽然慢一点点)
        """
        try:
            # 使用tasklist命令检查进程
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
                capture_output=True,
                text=True,
            )
            return process_name.lower() in result.stdout.lower()
        except Exception:
            return False

    def open_url(self, url: str) -> str:
        """
        在默认浏览器中打开网址
        """
        import webbrowser
        self.logger.info(f"尝试打开网址: {url}")
        try:
            webbrowser.open(url)
            return f"已在浏览器中打开 {url}"
        except Exception as e:
            error_msg = f"无法打开网址 {url}: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def close_app(self, app_name: str) -> str:
        """
        关闭应用程序
        """
        self.logger.info(f"尝试关闭应用: {app_name}")
        try:
            if self.os_type == "Windows":
                # 使用新的app_map查找进程名
                app_name_lower = app_name.lower()
                target = self.app_map.get(app_name, None)

                # 如果不在映射表中，尝试去匹配映射表的 Key
                if not target:
                    for key, val in self.app_map.items():
                        if key in app_name_lower:
                            target = val
                            break

                target_process = target["proc"] if target else app_name + ".exe"

                # 如果是列表，关闭所有相关进程
                if isinstance(target_process, list):
                    for proc in target_process:
                        subprocess.run(
                            ["taskkill", "/F", "/IM", proc], capture_output=True
                        )
                    return f"已尝试关闭所有相关的 {app_name} 进程"
                else:
                    result = subprocess.run(
                        ["taskkill", "/F", "/IM", target_process],
                        capture_output=True,
                        text=True,
                    )
                    if "成功" in result.stdout:
                        return f"已成功关闭 {app_name}"
                    else:
                        return f"无法关闭 {app_name}，可能已经关闭了"

            elif self.os_type == "Darwin":  # macOS
                subprocess.run(["pkill", app_name])
                return f"已尝试关闭 {app_name}"

            else:  # Linux
                subprocess.run(["pkill", app_name])
                return f"已尝试关闭 {app_name}"

        except Exception as e:
            error_msg = f"无法关闭 {app_name}: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def create_file(self, file_path: str, content: str = "") -> str:
        """
        创建新文件
        """
        self.logger.info(f"尝试创建文件: {file_path}")
        try:
            # 确保目录存在
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return f"已成功创建文件: {file_path}"
        except Exception as e:
            error_msg = f"无法创建文件 {file_path}: {str(e)}"
            self.logger.error(error_msg)
            return error_msg

    def get_active_window(self) -> str:
        """
        获取当前活动窗口标题
        """
        try:
            if self.os_type == "Windows":
                window = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(window)
                return title
            else:
                return "无法在非Windows系统获取活动窗口"
        except Exception as e:
            self.logger.error(f"获取活动窗口失败: {str(e)}")
            return "无法获取活动窗口"

    def screenshot(self) -> str:
        """
        截取当前屏幕
        """
        try:
            if self.os_type == "Windows":
                import pyautogui

                screenshot = pyautogui.screenshot()
                temp_file = os.path.join(os.gettempdir(), "screenshot.png")
                screenshot.save(temp_file)
                return f"已保存截图到: {temp_file}"
            else:
                return "无法在非Windows系统截图"
        except Exception as e:
            self.logger.error(f"截图失败: {str(e)}")
            return "截图失败"

    def get_system_info(self) -> str:
        """
        获取系统信息
        """
        try:
            if self.os_type == "Windows":
                result = subprocess.run(
                    ["systeminfo"], capture_output=True, text=True, encoding="gbk"
                )
                return result.stdout[:1000]  # 只返回前1000字符
            else:
                result = subprocess.run(["uname", "-a"], capture_output=True, text=True)
                return result.stdout
        except Exception as e:
            self.logger.error(f"获取系统信息失败: {str(e)}")
            return "无法获取系统信息"

    def list_files(self, directory: str = ".") -> str:
        """
        列出目录中的文件
        """
        try:
            files = os.listdir(directory)
            return f"目录 {directory} 中的文件:\n" + "\n".join(
                files[:20]
            )  # 最多返回20个文件
        except Exception as e:
            error_msg = f"无法列出目录 {directory} 中的文件: {str(e)}"
            self.logger.error(error_msg)
            return error_msg
