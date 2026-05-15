"""
系统工具集 - SystemTools

提供一系列系统操作工具：
1. 启动应用程序
2. 切换桌面壁纸
3. 打开文件夹
4. 打开网址
5. 关闭应用程序
6. 获取系统信息
7. 文件操作（复制、移动、删除）
8. 截图
9. 控制窗口（最小化、最大化、关闭）

灵感来源：Claude Code的计算机操作能力
"""

import os
import subprocess
import shutil
import ctypes
import time
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

from loguru import logger

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("[SystemTools] PIL未安装，截图功能不可用")

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32clipboard
    import win32ui
    from ctypes import windll
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logger.warning("[SystemTools] pywin32未安装，部分功能不可用")


def get_desktop_path() -> str:
    """获取桌面路径"""
    return os.path.join(os.path.expanduser("~"), "Desktop")


def get_wallpaper_path() -> str:
    """获取当前壁纸路径"""
    if not WIN32_AVAILABLE:
        return ""

    try:
        key = win32api.RegOpenKeyEx(
            win32con.HKEY_CURRENT_USER,
            r"Control Panel\Desktop",
            0,
            win32con.KEY_READ
        )
        value, _ = win32api.RegQueryValueEx(key, "Wallpaper")
        win32api.RegCloseKey(key)
        return value
    except Exception as e:
        logger.error(f"获取壁纸路径失败: {e}")
        return ""


def set_wallpaper(image_path: str) -> bool:
    """
    设置桌面壁纸

    Args:
        image_path: 图片路径

    Returns:
        是否成功
    """
    if not WIN32_AVAILABLE:
        return False

    if not os.path.exists(image_path):
        logger.error(f"壁纸文件不存在: {image_path}")
        return False

    try:
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02

        windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            image_path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        logger.info(f"壁纸已设置为: {image_path}")
        return True
    except Exception as e:
        logger.error(f"设置壁纸失败: {e}")
        return False


def open_application(app_path: str) -> bool:
    """
    启动应用程序

    Args:
        app_path: 应用程序路径（exe路径、快捷方式或命令名）

    Returns:
        是否成功
    """
    try:
        # 尝试使用 os.startfile (Windows专用，支持命令名如 "notepad")
        try:
            os.startfile(app_path)
            logger.info(f"已启动应用: {app_path}")
            return True
        except (AttributeError, WindowsError):
            # os.startfile 失败时使用 subprocess
            pass
        
        # 使用 subprocess.Popen 尝试启动
        subprocess.Popen(app_path, shell=True)
        logger.info(f"已启动应用: {app_path}")
        return True
    except Exception as e:
        logger.error(f"启动应用失败: {e}")
        return False


def close_application(process_name: str) -> bool:
    """
    关闭应用程序

    Args:
        process_name: 进程名称（如 "notepad.exe"）

    Returns:
        是否成功
    """
    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"已关闭进程: {process_name}")
            return True
        else:
            logger.warning(f"关闭进程失败: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"关闭应用失败: {e}")
        return False


def open_folder(path: str) -> bool:
    """
    打开文件夹

    Args:
        path: 文件夹路径

    Returns:
        是否成功
    """
    if not os.path.exists(path):
        logger.error(f"文件夹不存在: {path}")
        return False

    try:
        os.startfile(path)
        logger.info(f"已打开文件夹: {path}")
        return True
    except Exception as e:
        logger.error(f"打开文件夹失败: {e}")
        return False


def open_url(url: str) -> bool:
    """
    打开网址

    Args:
        url: 网址

    Returns:
        是否成功
    """
    try:
        import webbrowser
        webbrowser.open(url)
        logger.info(f"已打开网址: {url}")
        return True
    except Exception as e:
        logger.error(f"打开网址失败: {e}")
        return False


def get_system_info() -> dict:
    """
    获取系统信息

    Returns:
        系统信息字典
    """
    info = {
        "platform": os.name,
        "username": os.getlogin(),
        "cwd": os.getcwd(),
        "desktop": get_desktop_path(),
    }

    if WIN32_AVAILABLE:
        try:
            info["computer_name"] = os.environ.get("COMPUTERNAME", "")
            info["user_profile"] = os.environ.get("USERPROFILE", "")
            info["wallpaper"] = get_wallpaper_path()
        except Exception as e:
            logger.warning(f"获取系统信息失败: {e}")

    return info


def copy_file(source: str, destination: str) -> bool:
    """
    复制文件

    Args:
        source: 源文件路径
        destination: 目标路径

    Returns:
        是否成功
    """
    try:
        shutil.copy2(source, destination)
        logger.info(f"已复制文件: {source} -> {destination}")
        return True
    except Exception as e:
        logger.error(f"复制文件失败: {e}")
        return False


def move_file(source: str, destination: str) -> bool:
    """
    移动文件

    Args:
        source: 源文件路径
        destination: 目标路径

    Returns:
        是否成功
    """
    try:
        shutil.move(source, destination)
        logger.info(f"已移动文件: {source} -> {destination}")
        return True
    except Exception as e:
        logger.error(f"移动文件失败: {e}")
        return False


def delete_file(file_path: str) -> bool:
    """
    删除文件

    Args:
        file_path: 文件路径

    Returns:
        是否成功
    """
    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)
        logger.info(f"已删除: {file_path}")
        return True
    except Exception as e:
        logger.error(f"删除文件失败: {e}")
        return False


def take_screenshot(save_path: Optional[str] = None) -> Optional[str]:
    """
    截图

    Args:
        save_path: 保存路径（可选），默认保存到桌面

    Returns:
        截图保存路径，失败返回None
    """
    if not PIL_AVAILABLE:
        logger.error("PIL未安装，无法截图")
        return None

    try:
        if save_path is None:
            save_path = os.path.join(get_desktop_path(), f"screenshot_{int(time.time())}.png")

        screenshot = ImageGrab.grab()
        screenshot.save(save_path)
        logger.info(f"截图已保存: {save_path}")
        return save_path
    except Exception as e:
        logger.error(f"截图失败: {e}")
        return None


def minimize_window(hwnd: int = None) -> bool:
    """
    最小化窗口

    Args:
        hwnd: 窗口句柄（可选），默认当前窗口

    Returns:
        是否成功
    """
    if not WIN32_AVAILABLE:
        return False

    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        return True
    except Exception as e:
        logger.error(f"最小化窗口失败: {e}")
        return False


def maximize_window(hwnd: int = None) -> bool:
    """
    最大化窗口

    Args:
        hwnd: 窗口句柄（可选），默认当前窗口

    Returns:
        是否成功
    """
    if not WIN32_AVAILABLE:
        return False

    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        return True
    except Exception as e:
        logger.error(f"最大化窗口失败: {e}")
        return False


def close_window(hwnd: int = None) -> bool:
    """
    关闭窗口

    Args:
        hwnd: 窗口句柄（可选），默认当前窗口

    Returns:
        是否成功
    """
    if not WIN32_AVAILABLE:
        return False

    try:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow()
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return True
    except Exception as e:
        logger.error(f"关闭窗口失败: {e}")
        return False


def get_clipboard_text() -> str:
    """
    获取剪贴板文本

    Returns:
        剪贴板文本内容
    """
    if not WIN32_AVAILABLE:
        return ""

    try:
        win32clipboard.OpenClipboard()
        text = win32clipboard.GetClipboardData(win32con.CF_TEXT)
        win32clipboard.CloseClipboard()
        return text.decode('gbk', errors='ignore')
    except Exception as e:
        logger.error(f"获取剪贴板失败: {e}")
        return ""


def set_clipboard_text(text: str) -> bool:
    """
    设置剪贴板文本

    Args:
        text: 文本内容

    Returns:
        是否成功
    """
    if not WIN32_AVAILABLE:
        return False

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_TEXT, text.encode('gbk', errors='ignore'))
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        logger.error(f"设置剪贴板失败: {e}")
        return False


def get_running_processes() -> list:
    """
    获取运行中的进程列表

    Returns:
        进程信息列表
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True
        )
        processes = []
        for line in result.stdout.strip().split('\n'):
            parts = line.split('","')
            if len(parts) >= 5:
                processes.append({
                    "name": parts[0].replace('"', ''),
                    "pid": parts[1].replace('"', ''),
                    "memory": parts[4].replace('"', '')
                })
        return processes[:50]  # 返回前50个
    except Exception as e:
        logger.error(f"获取进程列表失败: {e}")
        return []


def search_files(directory: str, pattern: str, max_results: int = 20) -> list:
    """
    搜索文件

    Args:
        directory: 搜索目录
        pattern: 文件名模式（支持通配符）
        max_results: 最大返回数量

    Returns:
        匹配的文件路径列表
    """
    try:
        results = []
        path = Path(directory)
        if not path.exists():
            return []

        for file in path.rglob(f"*{pattern}*"):
            if file.is_file():
                results.append(str(file))
                if len(results) >= max_results:
                    break
        return results
    except Exception as e:
        logger.error(f"搜索文件失败: {e}")
        return []


def create_file(file_path: str, content: str = "") -> str:
    """创建新文件"""
    try:
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"已创建文件: {file_path}")
        return f"已成功创建文件: {file_path}"
    except Exception as e:
        logger.error(f"创建文件失败: {e}")
        return f"无法创建文件 {file_path}: {str(e)}"


def list_files(directory: str = ".") -> str:
    """列出目录中的文件"""
    try:
        files = os.listdir(directory)
        return f"目录 {directory} 中的文件:\n" + "\n".join(files[:20])
    except Exception as e:
        logger.error(f"列出文件失败: {e}")
        return f"无法列出目录 {directory} 中的文件: {str(e)}"


def get_active_window() -> str:
    """获取当前活动窗口标题"""
    try:
        if WIN32_AVAILABLE:
            window = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(window)
            return title
        return "无法在非Windows系统获取活动窗口"
    except Exception as e:
        logger.error(f"获取活动窗口失败: {e}")
        return f"无法获取活动窗口: {str(e)}"


def execute_code(code: str) -> str:
    """执行 Python 代码并捕获输出"""
    import io
    from contextlib import redirect_stderr, redirect_stdout
    output_buffer = io.StringIO()
    try:
        with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
            exec(
                code,
                {
                    "os": os,
                    "subprocess": subprocess,
                    "time": time,
                },
            )
        result = output_buffer.getvalue()
        if not result:
            result = "执行成功，无控制台输出。"
        logger.info(f"代码执行成功: {result[:50]}...")
        return result
    except Exception as e:
        error_msg = f"执行出错: {str(e)}"
        logger.error(f"代码执行失败: {error_msg}")
        return error_msg


# 工具注册信息
SYSTEM_TOOLS = [
    {
        "name": "open_application",
        "description": "启动一个Windows应用程序",
        "parameters": {
            "app_path": {
                "type": "string",
                "description": "应用程序的完整路径，如 C:\\Program Files\\Notepad++\\notepad++.exe"
            }
        }
    },
    {
        "name": "close_application",
        "description": "关闭一个正在运行的应用程序",
        "parameters": {
            "process_name": {
                "type": "string",
                "description": "进程名称，如 notepad.exe"
            }
        }
    },
    {
        "name": "open_folder",
        "description": "打开一个文件夹",
        "parameters": {
            "path": {
                "type": "string",
                "description": "文件夹路径"
            }
        }
    },
    {
        "name": "open_url",
        "description": "在浏览器中打开网址",
        "parameters": {
            "url": {
                "type": "string",
                "description": "网址，如 https://www.example.com"
            }
        }
    },
    {
        "name": "set_wallpaper",
        "description": "设置桌面壁纸",
        "parameters": {
            "image_path": {
                "type": "string",
                "description": "图片文件的完整路径"
            }
        }
    },
    {
        "name": "take_screenshot",
        "description": "截取当前屏幕并保存",
        "parameters": {
            "save_path": {
                "type": "string",
                "description": "截图保存路径（可选），默认保存到桌面",
                "required": False
            }
        }
    },
    {
        "name": "minimize_window",
        "description": "最小化当前窗口",
        "parameters": {}
    },
    {
        "name": "maximize_window",
        "description": "最大化当前窗口",
        "parameters": {}
    },
    {
        "name": "close_window",
        "description": "关闭当前窗口",
        "parameters": {}
    },
    {
        "name": "get_system_info",
        "description": "获取系统信息",
        "parameters": {}
    },
    {
        "name": "get_clipboard_text",
        "description": "获取剪贴板文本内容",
        "parameters": {}
    },
    {
        "name": "set_clipboard_text",
        "description": "设置剪贴板文本内容",
        "parameters": {
            "text": {
                "type": "string",
                "description": "要设置的文本内容"
            }
        }
    },
    {
        "name": "search_files",
        "description": "在指定目录中搜索文件",
        "parameters": {
            "directory": {
                "type": "string",
                "description": "搜索的目录路径"
            },
            "pattern": {
                "type": "string",
                "description": "文件名匹配模式，如 .pdf 或 report"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回数量，默认为20",
                "required": False
            }
        }
    },
    {
        "name": "copy_file",
        "description": "复制文件",
        "parameters": {
            "source": {
                "type": "string",
                "description": "源文件路径"
            },
            "destination": {
                "type": "string",
                "description": "目标路径"
            }
        }
    },
    {
        "name": "move_file",
        "description": "移动文件",
        "parameters": {
            "source": {
                "type": "string",
                "description": "源文件路径"
            },
            "destination": {
                "type": "string",
                "description": "目标路径"
            }
        }
    },
    {
        "name": "delete_file",
        "description": "删除文件或文件夹",
        "parameters": {
            "file_path": {
                "type": "string",
                "description": "要删除的文件或文件夹路径"
            }
        }
    },
    {
        "name": "get_running_processes",
        "description": "获取当前运行中的进程列表",
        "parameters": {}
    },
    {
        "name": "create_file",
        "description": "创建新文件",
        "parameters": {
            "file_path": {
                "type": "string",
                "description": "要创建的文件路径"
            },
            "content": {
                "type": "string",
                "description": "文件内容（可选）",
                "required": False
            }
        }
    },
    {
        "name": "list_files",
        "description": "列出目录中的文件",
        "parameters": {
            "directory": {
                "type": "string",
                "description": "要列出的目录路径，默认为当前目录",
                "required": False
            }
        }
    },
    {
        "name": "get_active_window",
        "description": "获取当前活动窗口的标题",
        "parameters": {}
    },
    {
        "name": "execute_code",
        "description": "执行 Python 代码",
        "parameters": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码"
            }
        }
    },
    {
        "name": "set_timer",
        "description": "设置定时提醒或定时执行工具",
        "parameters": {
            "time_spec": {
                "type": "string",
                "description": "时间规格，仅支持 ISO 8601 格式。持续时间格式：PTnHnMnS（如 PT2M 表示2分钟后，PT1H30M 表示1小时30分钟后，PT30S 表示30秒后）；日期时间格式：YYYY-MM-DDTHH:MM:SS（如 2024-01-15T10:30:00）"
            },
            "message": {
                "type": "string",
                "description": "提醒消息内容（当不需要执行工具时使用）",
                "required": False
            },
            "tool_name": {
                "type": "string",
                "description": "要定时执行的工具名称（当需要执行工具时使用）",
                "required": False
            },
            "tool_arguments": {
                "type": "object",
                "description": "工具参数（JSON格式，与tool_name配合使用）",
                "required": False
            },
            "repeat_interval": {
                "type": "integer",
                "description": "重复间隔（秒），设置后任务会重复执行，默认None表示单次",
                "required": False
            }
        }
    },
    {
        "name": "cancel_timer",
        "description": "取消定时任务",
        "parameters": {
            "task_id": {
                "type": "string",
                "description": "要取消的任务ID"
            }
        }
    },
    {
        "name": "list_timers",
        "description": "获取所有定时任务列表",
        "parameters": {}
    }
]


def get_all_tools_list() -> list:
    """
    获取所有系统工具列表（用于提供给AI）

    Returns:
        工具列表
    """
    return SYSTEM_TOOLS


def execute_system_tool(tool_name: str, **kwargs) -> dict:
    """
    执行系统工具

    Args:
        tool_name: 工具名称
        **kwargs: 工具参数

    Returns:
        执行结果字典
    """
    try:
        if tool_name == "open_application":
            # 支持传入 app_path 或 app_name 两种参数名
            app_path = kwargs.get("app_path") or kwargs.get("app_name") or ""
            success = open_application(app_path)
            return {"success": success, "result": f"应用{'已启动' if success else '启动失败'}"}

        elif tool_name == "close_application":
            success = close_application(kwargs.get("process_name", ""))
            return {"success": success, "result": f"进程{'已关闭' if success else '关闭失败'}"}

        elif tool_name == "open_folder":
            success = open_folder(kwargs.get("path", ""))
            return {"success": success, "result": f"文件夹{'已打开' if success else '打开失败'}"}

        elif tool_name == "open_url":
            success = open_url(kwargs.get("url", ""))
            return {"success": success, "result": f"网址{'已打开' if success else '打开失败'}"}

        elif tool_name == "set_wallpaper":
            success = set_wallpaper(kwargs.get("image_path", ""))
            return {"success": success, "result": f"壁纸{'已设置' if success else '设置失败'}"}

        elif tool_name == "take_screenshot":
            save_path = take_screenshot(kwargs.get("save_path"))
            success = save_path is not None
            return {"success": success, "result": f"截图{'已保存到' + save_path if success else '保存失败'}"}

        elif tool_name == "minimize_window":
            success = minimize_window()
            return {"success": success, "result": "窗口已最小化" if success else "操作失败"}

        elif tool_name == "maximize_window":
            success = maximize_window()
            return {"success": success, "result": "窗口已最大化" if success else "操作失败"}

        elif tool_name == "close_window":
            success = close_window()
            return {"success": success, "result": "窗口已关闭" if success else "操作失败"}

        elif tool_name == "get_system_info":
            info = get_system_info()
            return {"success": True, "result": info}

        elif tool_name == "get_clipboard_text":
            text = get_clipboard_text()
            return {"success": True, "result": text or "(剪贴板为空)"}

        elif tool_name == "set_clipboard_text":
            success = set_clipboard_text(kwargs.get("text", ""))
            return {"success": success, "result": f"剪贴板{'已设置' if success else '设置失败'}"}

        elif tool_name == "search_files":
            results = search_files(
                kwargs.get("directory", ""),
                kwargs.get("pattern", ""),
                kwargs.get("max_results", 20)
            )
            return {"success": True, "result": results or "未找到匹配文件"}

        elif tool_name == "copy_file":
            success = copy_file(kwargs.get("source", ""), kwargs.get("destination", ""))
            return {"success": success, "result": f"文件{'已复制' if success else '复制失败'}"}

        elif tool_name == "move_file":
            success = move_file(kwargs.get("source", ""), kwargs.get("destination", ""))
            return {"success": success, "result": f"文件{'已移动' if success else '移动失败'}"}

        elif tool_name == "delete_file":
            success = delete_file(kwargs.get("file_path", ""))
            return {"success": success, "result": f"{'已删除' if success else '删除失败'}"}

        elif tool_name == "get_running_processes":
            processes = get_running_processes()
            return {"success": True, "result": processes}

        elif tool_name == "create_file":
            result = create_file(kwargs.get("file_path", ""), kwargs.get("content", ""))
            return {"success": "成功" in result, "result": result}

        elif tool_name == "list_files":
            result = list_files(kwargs.get("directory", "."))
            return {"success": True, "result": result}

        elif tool_name == "get_active_window":
            result = get_active_window()
            return {"success": True, "result": result}

        elif tool_name == "execute_code":
            result = execute_code(kwargs.get("code", ""))
            return {"success": True, "result": result}

        elif tool_name == "set_timer":
            try:
                from core.scheduler import get_scheduler
                
                scheduler = get_scheduler()
                time_spec = kwargs.get("time_spec", "")
                message = kwargs.get("message", "")
                tool_name_param = kwargs.get("tool_name", "")
                tool_arguments = kwargs.get("tool_arguments", {})
                repeat_interval = kwargs.get("repeat_interval")
                
                if not time_spec:
                    return {"success": False, "result": "请提供时间规格"}
                
                scheduled_time = scheduler.parse_time_spec(time_spec)
                
                if message:
                    task_id = scheduler.schedule_reminder(
                        message=message,
                        scheduled_time=scheduled_time,
                        repeat_interval=repeat_interval
                    )
                    return {"success": True, "result": f"定时提醒已设置，任务ID: {task_id}，提醒时间: {datetime.fromtimestamp(scheduled_time).strftime('%Y-%m-%d %H:%M:%S')}"}
                
                elif tool_name_param:
                    task_id = scheduler.schedule_tool_call(
                        tool_name=tool_name_param,
                        tool_arguments=tool_arguments,
                        scheduled_time=scheduled_time,
                        repeat_interval=repeat_interval
                    )
                    return {"success": True, "result": f"定时任务已设置，任务ID: {task_id}，执行时间: {datetime.fromtimestamp(scheduled_time).strftime('%Y-%m-%d %H:%M:%S')}"}
                
                else:
                    return {"success": False, "result": "请提供提醒消息或要执行的工具"}
                    
            except ValueError as e:
                return {"success": False, "result": f"时间解析失败: {str(e)}"}
            except Exception as e:
                logger.error(f"设置定时任务失败: {e}")
                return {"success": False, "result": f"设置失败: {str(e)}"}

        elif tool_name == "cancel_timer":
            try:
                from core.scheduler import get_scheduler
                
                scheduler = get_scheduler()
                task_id = kwargs.get("task_id", "")
                
                if not task_id:
                    return {"success": False, "result": "请提供任务ID"}
                
                success = scheduler.cancel_task(task_id)
                return {"success": success, "result": f"任务{'已取消' if success else '取消失败，任务不存在'}"}
                
            except Exception as e:
                logger.error(f"取消定时任务失败: {e}")
                return {"success": False, "result": f"取消失败: {str(e)}"}

        elif tool_name == "list_timers":
            try:
                from core.scheduler import get_scheduler
                
                scheduler = get_scheduler()
                tasks = scheduler.list_tasks()
                
                if not tasks:
                    return {"success": True, "result": "暂无定时任务"}
                
                task_list = []
                for task in tasks:
                    task_info = {
                        "task_id": task.id,
                        "type": task.task_type.value,
                        "scheduled_time": task.get_scheduled_time_str(),
                        "remaining_time": task.get_remaining_time(),
                        "status": task.status.value
                    }
                    if task.message:
                        task_info["message"] = task.message
                    if task.tool_name:
                        task_info["tool_name"] = task.tool_name
                    if task.repeat_interval:
                        task_info["repeat_interval"] = f"{task.repeat_interval}秒"
                    task_list.append(task_info)
                
                return {"success": True, "result": task_list}
                
            except Exception as e:
                logger.error(f"获取定时任务列表失败: {e}")
                return {"success": False, "result": f"获取失败: {str(e)}"}

        else:
            return {"success": False, "result": f"未知工具: {tool_name}"}

    except Exception as e:
        logger.error(f"执行工具 {tool_name} 失败: {e}")
        return {"success": False, "result": f"执行出错: {str(e)}"}