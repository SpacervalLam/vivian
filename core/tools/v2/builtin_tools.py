"""
Built-in Tools - Core tools implemented using the new architecture

Demonstrates how to create tools using Tool System V2.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from loguru import logger

from . import (
    Tool,
    build_tool,
    ToolResult,
    ToolUseContext,
    PermissionResult,
    ValidationResult,
    BashProgress,
    FileReadProgress,
    ProgressBuilder,
)


class FileReadInput(BaseModel):
    """File read input"""
    file_path: str = Field(description="Absolute path of the file to read")
    offset: Optional[int] = Field(default=None, description="Starting line number (1-based)")
    limit: Optional[int] = Field(default=None, description="Number of lines to read")


class FileReadOutput(BaseModel):
    """File read output"""
    file_path: str
    content: str
    total_lines: int
    read_lines: int
    start_line: int


class FileEditInput(BaseModel):
    """File edit input"""
    file_path: str = Field(description="Absolute path of the file to edit")
    old_str: str = Field(description="Text to replace")
    new_str: str = Field(description="Replacement text")


class FileEditOutput(BaseModel):
    """File edit output"""
    file_path: str
    success: bool
    message: str


class FileWriteInput(BaseModel):
    """File write input"""
    file_path: str = Field(description="Absolute path of the file to write")
    content: str = Field(description="Content to write")


class FileWriteOutput(BaseModel):
    """File write output"""
    file_path: str
    success: bool
    bytes_written: int


class BashInput(BaseModel):
    """Bash command input"""
    command: str = Field(description="Command to execute")
    timeout: Optional[int] = Field(default=30000, description="Timeout in milliseconds")
    cwd: Optional[str] = Field(default=None, description="Working directory")


class BashOutput(BaseModel):
    """Bash command output"""
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


class GlobInput(BaseModel):
    """Glob search input"""
    pattern: str = Field(description="Glob pattern")
    path: Optional[str] = Field(default=".", description="Search path")


class GlobOutput(BaseModel):
    """Glob search output"""
    pattern: str
    path: str
    files: List[str]
    count: int


class OpenApplicationInput(BaseModel):
    """打开应用输入"""
    app_path: str = Field(description="Application path or name")


class OpenApplicationOutput(BaseModel):
    """打开应用输出"""
    app_path: str
    success: bool
    message: str


class SearchFilesInput(BaseModel):
    """搜索文件输入"""
    directory: str = Field(description="Search directory")
    pattern: str = Field(description="File name pattern")
    max_results: Optional[int] = Field(default=20, description="Maximum number of results")


class SearchFilesOutput(BaseModel):
    """搜索文件输出"""
    directory: str
    pattern: str
    files: List[str]
    count: int


def create_file_read_tool() -> Tool:
    """创建文件读取工具"""

    async def read_file(
        args: FileReadInput,
        context: ToolUseContext,
    ) -> ToolResult:
        file_path = args.file_path

        if not os.path.exists(file_path):
            return ToolResult(data={"error": f"文件不存在: {file_path}"})

        if not os.path.isfile(file_path):
            return ToolResult(data={"error": f"不是文件: {file_path}"})

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start_line = args.offset or 1
            limit = args.limit or total_lines

            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, start_idx + limit)

            selected_lines = lines[start_idx:end_idx]
            content = "".join(selected_lines)

            output = FileReadOutput(
                file_path=file_path,
                content=content,
                total_lines=total_lines,
                read_lines=len(selected_lines),
                start_line=start_line,
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="read_file",
        description="Read file contents. Supports reading large files with specified line range.",
        input_schema=FileReadInput,
        output_schema=FileReadOutput,
        call=read_file,
        search_hint="read files, view file contents, cat file",
        is_read_only=lambda input_data: True,
        is_concurrency_safe=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Read File",
        get_activity_description=lambda input_data=None: f"Reading {input_data.file_path}" if input_data else "Reading file",
    )


def create_file_edit_tool() -> Tool:
    """创建文件编辑工具"""

    async def edit_file(
        args: FileEditInput,
        context: ToolUseContext,
    ) -> ToolResult:
        file_path = args.file_path

        if not os.path.exists(file_path):
            return ToolResult(data={"error": f"文件不存在: {file_path}"})

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if args.old_str not in content:
                return ToolResult(data={
                    "error": f"未找到要替换的文本",
                    "file_path": file_path,
                })

            new_content = content.replace(args.old_str, args.new_str, 1)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            output = FileEditOutput(
                file_path=file_path,
                success=True,
                message="文件编辑成功",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"编辑文件失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="edit_file",
        description="Edit file content. Use exact matching to replace specified text.",
        input_schema=FileEditInput,
        output_schema=FileEditOutput,
        call=edit_file,
        search_hint="edit files, modify file contents, replace text",
        is_read_only=lambda input_data: False,
        is_destructive=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Edit File",
    )


def create_file_write_tool() -> Tool:
    """创建文件写入工具"""

    async def write_file(
        args: FileWriteInput,
        context: ToolUseContext,
    ) -> ToolResult:
        file_path = args.file_path

        try:
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                bytes_written = f.write(args.content)

            output = FileWriteOutput(
                file_path=file_path,
                success=True,
                bytes_written=bytes_written,
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"写入文件失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="write_file",
        description="Write file content. If file doesn't exist, create it. If it exists, overwrite it.",
        input_schema=FileWriteInput,
        output_schema=FileWriteOutput,
        call=write_file,
        search_hint="write files, create files, save content",
        is_read_only=lambda input_data: False,
        is_destructive=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Write File",
    )


def create_bash_tool() -> Tool:
    """创建Bash执行工具"""

    async def run_bash(
        args: BashInput,
        context: ToolUseContext,
    ) -> ToolResult:
        import time
        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_shell(
                args.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=args.cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=args.timeout / 1000 if args.timeout else 300,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(data={
                    "error": f"命令执行超时 ({args.timeout}ms)",
                    "command": args.command,
                })

            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            output = BashOutput(
                command=args.command,
                stdout=stdout.decode("utf-8", errors="ignore"),
                stderr=stderr.decode("utf-8", errors="ignore"),
                exit_code=process.returncode or 0,
                duration_ms=duration_ms,
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="bash",
        description="Execute Bash commands. Supports setting timeout and working directory.",
        input_schema=BashInput,
        output_schema=BashOutput,
        call=run_bash,
        search_hint="run commands, execute shell, terminal",
        is_open_world=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Bash",
        get_activity_description=lambda input_data=None: f"Running: {input_data.command[:50]}" if input_data else "Running command",
    )


def create_glob_tool() -> Tool:
    """创建Glob搜索工具"""

    async def glob_search(
        args: GlobInput,
        context: ToolUseContext,
    ) -> ToolResult:
        from glob import glob as glob_func

        search_path = args.path or "."
        pattern = args.pattern

        full_pattern = os.path.join(search_path, pattern)
        files = glob_func(full_pattern, recursive=True)

        output = GlobOutput(
            pattern=pattern,
            path=search_path,
            files=files[:100],
            count=len(files),
        )

        return ToolResult(data=output.model_dump())

    return build_tool(
        name="glob",
        description="使用Glob模式搜索文件。支持递归搜索。",
        input_schema=GlobInput,
        output_schema=GlobOutput,
        call=glob_search,
        search_hint="find files, search by pattern, file globbing",
        is_read_only=lambda input_data: True,
        is_concurrency_safe=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Glob",
    )


def create_open_application_tool() -> Tool:
    """创建打开应用工具"""

    async def open_app(
        args: OpenApplicationInput,
        context: ToolUseContext,
    ) -> ToolResult:
        app_path = args.app_path

        try:
            if os.name == "nt":
                os.startfile(app_path)
            else:
                subprocess.Popen(app_path, shell=True)

            output = OpenApplicationOutput(
                app_path=app_path,
                success=True,
                message="应用程序已启动",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"启动应用失败: {e}")
            return ToolResult(data={
                "app_path": app_path,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="open_application",
        description="启动Windows应用程序。",
        input_schema=OpenApplicationInput,
        output_schema=OpenApplicationOutput,
        call=open_app,
        search_hint="launch apps, start programs, open applications",
        aliases=["open_app", "launch_app"],
        user_facing_name=lambda input_data=None: "Open Application",
    )


def create_search_files_tool() -> Tool:
    """创建搜索文件工具"""

    async def search_files(
        args: SearchFilesInput,
        context: ToolUseContext,
    ) -> ToolResult:
        directory = args.directory
        pattern = args.pattern
        max_results = args.max_results or 20

        if not os.path.exists(directory):
            return ToolResult(data={"error": f"目录不存在: {directory}"})

        results = []
        path = Path(directory)

        for file in path.rglob(f"*{pattern}*"):
            if file.is_file():
                results.append(str(file))
                if len(results) >= max_results:
                    break

        output = SearchFilesOutput(
            directory=directory,
            pattern=pattern,
            files=results,
            count=len(results),
        )

        return ToolResult(data=output.model_dump())

    return build_tool(
        name="search_files",
        description="在指定目录中搜索文件。",
        input_schema=SearchFilesInput,
        output_schema=SearchFilesOutput,
        call=search_files,
        search_hint="find files, search by name, locate files",
        is_read_only=lambda input_data: True,
        is_concurrency_safe=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Search Files",
    )


def get_all_builtin_tools() -> List[Tool]:
    """获取所有内置工具"""
    return [
        create_file_read_tool(),
        create_file_edit_tool(),
        create_file_write_tool(),
        create_bash_tool(),
        create_glob_tool(),
        create_open_application_tool(),
        create_search_files_tool(),
    ]


# ============ 系统工具 ============

class CloseApplicationInput(BaseModel):
    """关闭应用输入"""
    process_name: str = Field(description="Process name, e.g., notepad.exe")


class CloseApplicationOutput(BaseModel):
    """关闭应用输出"""
    process_name: str
    success: bool
    message: str


def create_close_application_tool() -> Tool:
    """创建关闭应用工具"""

    async def close_app(
        args: CloseApplicationInput,
        context: ToolUseContext,
    ) -> ToolResult:
        process_name = args.process_name

        try:
            result = subprocess.run(
                ["taskkill", "/IM", process_name, "/F"],
                capture_output=True,
                text=True
            )
            success = result.returncode == 0
            message = "进程已关闭" if success else f"关闭失败: {result.stderr}"

            output = CloseApplicationOutput(
                process_name=process_name,
                success=success,
                message=message,
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"关闭应用失败: {e}")
            return ToolResult(data={
                "process_name": process_name,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="close_application",
        description="关闭一个正在运行的应用程序。",
        input_schema=CloseApplicationInput,
        output_schema=CloseApplicationOutput,
        call=close_app,
        search_hint="close apps, terminate processes, kill programs",
        user_facing_name=lambda input_data=None: "Close Application",
    )


class OpenFolderInput(BaseModel):
    """打开文件夹输入"""
    path: str = Field(description="文件夹路径")


class OpenFolderOutput(BaseModel):
    """打开文件夹输出"""
    path: str
    success: bool
    message: str


def create_open_folder_tool() -> Tool:
    """创建打开文件夹工具"""

    async def open_folder(
        args: OpenFolderInput,
        context: ToolUseContext,
    ) -> ToolResult:
        folder_path = args.path

        if not os.path.exists(folder_path):
            return ToolResult(data={
                "path": folder_path,
                "success": False,
                "message": "文件夹不存在",
            })

        try:
            if os.name == "nt":
                os.startfile(folder_path)
            else:
                subprocess.Popen(["open", folder_path])

            output = OpenFolderOutput(
                path=folder_path,
                success=True,
                message="文件夹已打开",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"打开文件夹失败: {e}")
            return ToolResult(data={
                "path": folder_path,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="open_folder",
        description="打开一个文件夹。",
        input_schema=OpenFolderInput,
        output_schema=OpenFolderOutput,
        call=open_folder,
        search_hint="open folders, explore directories",
        user_facing_name=lambda input_data=None: "Open Folder",
    )


class OpenUrlInput(BaseModel):
    """打开网址输入"""
    url: str = Field(description="网址，如 https://www.example.com")


class OpenUrlOutput(BaseModel):
    """打开网址输出"""
    url: str
    success: bool
    message: str


def create_open_url_tool() -> Tool:
    """创建打开网址工具"""

    async def open_url(
        args: OpenUrlInput,
        context: ToolUseContext,
    ) -> ToolResult:
        url = args.url

        try:
            import webbrowser
            webbrowser.open(url)

            output = OpenUrlOutput(
                url=url,
                success=True,
                message="网址已打开",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"打开网址失败: {e}")
            return ToolResult(data={
                "url": url,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="open_url",
        description="在浏览器中打开网址。",
        input_schema=OpenUrlInput,
        output_schema=OpenUrlOutput,
        call=open_url,
        search_hint="open websites, browse internet, launch browser",
        user_facing_name=lambda input_data=None: "Open URL",
    )


class SetWallpaperInput(BaseModel):
    """设置壁纸输入"""
    image_path: Optional[str] = Field(default=None, description="图片文件的完整路径（可选，不提供则自动随机选择）")


class SetWallpaperOutput(BaseModel):
    """设置壁纸输出"""
    image_path: str
    success: bool
    message: str


def create_set_wallpaper_tool() -> Tool:
    """创建设置壁纸工具"""

    async def set_wallpaper(
        args: SetWallpaperInput,
        context: ToolUseContext,
    ) -> ToolResult:
        image_path = args.image_path

        if not image_path:
            import random
            wallpaper_dirs = [
                os.path.expanduser(r"~\Pictures"),
                os.path.expanduser(r"~\Pictures\Wallpapers"),
                r"C:\Users\Public\Pictures",
                r"C:\Windows\Web\Wallpaper",
            ]
            
            all_wallpapers = []
            for wallpaper_dir in wallpaper_dirs:
                if os.path.exists(wallpaper_dir):
                    for root, _, files in os.walk(wallpaper_dir):
                        for file in files:
                            if file.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                                all_wallpapers.append(os.path.join(root, file))
            
            if not all_wallpapers:
                return ToolResult(data={
                    "image_path": "",
                    "success": False,
                    "message": "未找到壁纸图片，请提供图片路径或在 Pictures 文件夹中放置壁纸图片",
                })
            
            image_path = random.choice(all_wallpapers)

        if not os.path.exists(image_path):
            return ToolResult(data={
                "image_path": image_path,
                "success": False,
                "message": f"图片文件不存在: {image_path}",
            })

        try:
            if os.name == "nt":
                import ctypes
                SPI_SETDESKWALLPAPER = 0x0014
                SPIF_UPDATEINIFILE = 0x01
                SPIF_SENDCHANGE = 0x02

                ctypes.windll.user32.SystemParametersInfoW(
                    SPI_SETDESKWALLPAPER,
                    0,
                    image_path,
                    SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
                )
            else:
                return ToolResult(data={
                    "image_path": image_path,
                    "success": False,
                    "message": "壁纸设置仅支持Windows系统",
                })

            output = SetWallpaperOutput(
                image_path=image_path,
                success=True,
                message=f"壁纸已设置: {os.path.basename(image_path)}",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"设置壁纸失败: {e}")
            return ToolResult(data={
                "image_path": image_path,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="set_wallpaper",
        description="设置桌面壁纸。如果不提供图片路径，会自动从系统壁纸文件夹中随机选择一张。",
        input_schema=SetWallpaperInput,
        output_schema=SetWallpaperOutput,
        call=set_wallpaper,
        search_hint="set wallpaper, change desktop background, random wallpaper",
        user_facing_name=lambda input_data=None: "Set Wallpaper",
    )


class WallpaperEngineInput(BaseModel):
    """Wallpaper Engine 命令输入"""
    action: str = Field(description="操作类型：open（打开壁纸）、pause（暂停）、play（恢复）、stop（停止）、mute（静音）、unmute（取消静音）、next（下一张）")
    wallpaper_path: Optional[str] = Field(default=None, description="壁纸文件路径（仅 open 操作需要）")
    monitor: Optional[int] = Field(default=0, description="显示器索引（从0开始，默认0）")


class WallpaperEngineOutput(BaseModel):
    """Wallpaper Engine 命令输出"""
    action: str
    success: bool
    message: str


def create_wallpaper_engine_tool() -> Tool:
    """创建 Wallpaper Engine 命令行工具"""

    async def wallpaper_engine(
        args: WallpaperEngineInput,
        context: ToolUseContext,
    ) -> ToolResult:
        action = args.action.lower()
        wallpaper_path = args.wallpaper_path
        monitor = args.monitor

        wallpaper_engine_paths = [
            r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper32.exe",
            r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
            r"D:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper32.exe",
            r"D:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
            r"E:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
            r"F:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
        ]

        exe_path = None
        for path in wallpaper_engine_paths:
            if os.path.exists(path):
                exe_path = path
                break

        if not exe_path:
            try:
                import winreg
                for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    try:
                        registry_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                        key = winreg.OpenKey(hkey, registry_path)
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                if "wallpaper" in subkey_name.lower():
                                    subkey = winreg.OpenKey(key, subkey_name)
                                    try:
                                        install_path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                        if install_path:
                                            possible_exe = os.path.join(install_path, "wallpaper64.exe")
                                            if os.path.exists(possible_exe):
                                                exe_path = possible_exe
                                            possible_exe = os.path.join(install_path, "wallpaper32.exe")
                                            if os.path.exists(possible_exe) and not exe_path:
                                                exe_path = possible_exe
                                    except:
                                        pass
                                    winreg.CloseKey(subkey)
                                i += 1
                            except WindowsError:
                                break
                        winreg.CloseKey(key)
                        if exe_path:
                            break
                    except:
                        continue
            except Exception as e:
                logger.debug(f"Registry lookup failed: {e}")

        if not exe_path:
            try:
                import psutil
                for proc in psutil.process_iter(['name', 'exe']):
                    try:
                        if proc.name().lower() in ['wallpaper32.exe', 'wallpaper64.exe']:
                            exe_path = proc.exe()
                            break
                    except:
                        pass
            except Exception as e:
                logger.debug(f"Process lookup failed: {e}")

        if not exe_path:
            return ToolResult(data={
                "action": action,
                "success": False,
                "message": "Wallpaper Engine not found. Please install it first from Steam.",
            })

        try:
            import subprocess

            cmd = [exe_path, "-control"]
            
            if action == "open":
                if not wallpaper_path:
                    return ToolResult(data={
                        "action": action,
                        "success": False,
                        "message": "open requires wallpaper_path parameter",
                    })
                if not os.path.exists(wallpaper_path):
                    return ToolResult(data={
                        "action": action,
                        "success": False,
                        "message": f"Wallpaper file not found: {wallpaper_path}",
                    })
                cmd.extend(["openWallpaper", "-file", wallpaper_path, "-monitor", str(monitor)])
            elif action == "pause":
                cmd.append("pause")
            elif action == "play":
                cmd.append("play")
            elif action == "stop":
                cmd.append("stop")
            elif action == "mute":
                cmd.append("mute")
            elif action == "unmute":
                cmd.append("unmute")
            elif action == "next":
                cmd.append("nextWallpaper")
            else:
                return ToolResult(data={
                    "action": action,
                    "success": False,
                    "message": f"Unsupported action: {action}",
                })

            # Execute command - Wallpaper Engine must be running first
            subprocess.Popen(cmd)

            output = WallpaperEngineOutput(
                action=action,
                success=True,
                message=f"Wallpaper Engine {action} command sent. Note: Wallpaper Engine must be running first.",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"Wallpaper Engine operation failed: {e}")
            return ToolResult(data={
                "action": action,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="wallpaper_engine",
        description="Control Wallpaper Engine with command line. Supports: open (with wallpaper_path), pause, play (resume), stop, mute, unmute, next. Note: Wallpaper Engine must be running first.",
        input_schema=WallpaperEngineInput,
        output_schema=WallpaperEngineOutput,
        call=wallpaper_engine,
        search_hint="wallpaper engine, dynamic wallpaper, open wallpaper",
        user_facing_name=lambda input_data=None: "Wallpaper Engine",
    )


class ListWallpapersOutput(BaseModel):
    """列出壁纸输出"""
    success: bool
    message: str
    wallpapers: List[Dict[str, str]] = Field(default_factory=list, description="壁纸列表，包含id、name、path字段")


def create_list_wallpapers_tool() -> Tool:
    """创建列出壁纸工具"""

    async def list_wallpapers(
        args: dict,
        context: ToolUseContext,
    ) -> ToolResult:
        wallpaper_engine_paths = [
            r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine",
            r"D:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine",
            r"E:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine",
            r"F:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine",
        ]

        we_path = None
        for path in wallpaper_engine_paths:
            if os.path.exists(path):
                we_path = path
                break

        if not we_path:
            try:
                import psutil
                for proc in psutil.process_iter(['name', 'exe']):
                    try:
                        if proc.name().lower() in ['wallpaper32.exe', 'wallpaper64.exe']:
                            we_path = os.path.dirname(proc.exe())
                            break
                    except:
                        pass
            except:
                pass

        if not we_path:
            return ToolResult(data={
                "success": False,
                "message": "未找到 Wallpaper Engine 安装路径",
                "wallpapers": [],
            })

        workshop_path = os.path.join(os.path.dirname(os.path.dirname(we_path)), "workshop", "content", "431960")
        
        if not os.path.exists(workshop_path):
            return ToolResult(data={
                "success": False,
                "message": f"未找到 workshop 目录: {workshop_path}",
                "wallpapers": [],
            })

        wallpapers = []
        for item in os.listdir(workshop_path):
            item_path = os.path.join(workshop_path, item)
            if os.path.isdir(item_path):
                wallpaper_file = None
                wallpaper_name = item
                for root, _, files in os.walk(item_path):
                    for file in files:
                        if file.lower() == "project.json":
                            wallpaper_file = os.path.join(root, file)
                            try:
                                import json
                                with open(wallpaper_file, 'r', encoding='utf-8') as f:
                                    project_data = json.load(f)
                                    if 'title' in project_data:
                                        wallpaper_name = project_data['title']
                                    elif 'name' in project_data:
                                        wallpaper_name = project_data['name']
                            except:
                                pass
                            break
                        if file.lower().endswith((".mp4", ".wmv", ".avi")) and not wallpaper_file:
                            wallpaper_file = os.path.join(root, file)
                            wallpaper_name = os.path.splitext(file)[0]
                    if wallpaper_file:
                        break
                
                if wallpaper_file:
                    wallpapers.append({
                        "id": item,
                        "name": wallpaper_name,
                        "path": wallpaper_file,
                    })

        wallpapers.sort(key=lambda x: x["name"])

        return ToolResult(data={
            "success": True,
            "message": f"找到 {len(wallpapers)} 张壁纸",
            "wallpapers": wallpapers,
        })

    return build_tool(
        name="list_wallpapers",
        description="列出所有 Wallpaper Engine 壁纸。返回壁纸列表，包含壁纸ID、名称和文件路径。使用此工具后，可以调用 wallpaper_engine 工具的 open 操作来更换壁纸。",
        input_schema=None,
        output_schema=ListWallpapersOutput,
        call=list_wallpapers,
        search_hint="list wallpapers, show wallpapers, wallpaper list, 壁纸列表",
        user_facing_name=lambda input_data=None: "List Wallpapers",
    )


class TakeScreenshotInput(BaseModel):
    """截图输入"""
    save_path: Optional[str] = Field(default=None, description="截图保存路径（可选），默认保存到桌面")


class TakeScreenshotOutput(BaseModel):
    """截图输出"""
    save_path: str
    success: bool
    message: str


def create_take_screenshot_tool() -> Tool:
    """创建截图工具"""

    async def take_screenshot(
        args: TakeScreenshotInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            from PIL import ImageGrab
            import time

            if args.save_path:
                save_path = args.save_path
            else:
                desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                save_path = os.path.join(desktop_path, f"screenshot_{int(time.time())}.png")

            screenshot = ImageGrab.grab()
            screenshot.save(save_path)

            output = TakeScreenshotOutput(
                save_path=save_path,
                success=True,
                message=f"截图已保存到 {save_path}",
            )

            return ToolResult(data=output.model_dump())

        except ImportError:
            return ToolResult(data={
                "success": False,
                "message": "PIL未安装，无法截图",
            })
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return ToolResult(data={
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="take_screenshot",
        description="截取当前屏幕并保存。",
        input_schema=TakeScreenshotInput,
        output_schema=TakeScreenshotOutput,
        call=take_screenshot,
        search_hint="take screenshot, capture screen, print screen",
        user_facing_name=lambda input_data=None: "Take Screenshot",
    )


# ============ 窗口控制工具 ============

class MinimizeWindowInput(BaseModel):
    """最小化窗口输入"""
    hwnd: Optional[int] = Field(default=None, description="窗口句柄（可选），默认当前窗口")


class MinimizeWindowOutput(BaseModel):
    """最小化窗口输出"""
    success: bool
    message: str


def create_minimize_window_tool() -> Tool:
    """创建最小化窗口工具"""

    async def minimize_window(
        args: MinimizeWindowInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            if os.name == "nt":
                import win32gui
                import win32con

                hwnd = args.hwnd if args.hwnd else win32gui.GetForegroundWindow()
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

                output = MinimizeWindowOutput(
                    success=True,
                    message="窗口已最小化",
                )

                return ToolResult(data=output.model_dump())
            else:
                return ToolResult(data={
                    "success": False,
                    "message": "窗口控制仅支持Windows系统",
                })

        except Exception as e:
            logger.error(f"最小化窗口失败: {e}")
            return ToolResult(data={
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="minimize_window",
        description="最小化当前窗口。",
        input_schema=MinimizeWindowInput,
        output_schema=MinimizeWindowOutput,
        call=minimize_window,
        search_hint="minimize window, hide window",
        user_facing_name=lambda input_data=None: "Minimize Window",
    )


class MaximizeWindowInput(BaseModel):
    """最大化窗口输入"""
    hwnd: Optional[int] = Field(default=None, description="窗口句柄（可选），默认当前窗口")


class MaximizeWindowOutput(BaseModel):
    """最大化窗口输出"""
    success: bool
    message: str


def create_maximize_window_tool() -> Tool:
    """创建最大化窗口工具"""

    async def maximize_window(
        args: MaximizeWindowInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            if os.name == "nt":
                import win32gui
                import win32con

                hwnd = args.hwnd if args.hwnd else win32gui.GetForegroundWindow()
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

                output = MaximizeWindowOutput(
                    success=True,
                    message="窗口已最大化",
                )

                return ToolResult(data=output.model_dump())
            else:
                return ToolResult(data={
                    "success": False,
                    "message": "窗口控制仅支持Windows系统",
                })

        except Exception as e:
            logger.error(f"最大化窗口失败: {e}")
            return ToolResult(data={
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="maximize_window",
        description="最大化当前窗口。",
        input_schema=MaximizeWindowInput,
        output_schema=MaximizeWindowOutput,
        call=maximize_window,
        search_hint="maximize window, fullscreen",
        user_facing_name=lambda input_data=None: "Maximize Window",
    )


class CloseWindowInput(BaseModel):
    """关闭窗口输入"""
    hwnd: Optional[int] = Field(default=None, description="窗口句柄（可选），默认当前窗口")


class CloseWindowOutput(BaseModel):
    """关闭窗口输出"""
    success: bool
    message: str


def create_close_window_tool() -> Tool:
    """创建关闭窗口工具"""

    async def close_window(
        args: CloseWindowInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            if os.name == "nt":
                import win32gui
                import win32con

                hwnd = args.hwnd if args.hwnd else win32gui.GetForegroundWindow()
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

                output = CloseWindowOutput(
                    success=True,
                    message="窗口已关闭",
                )

                return ToolResult(data=output.model_dump())
            else:
                return ToolResult(data={
                    "success": False,
                    "message": "窗口控制仅支持Windows系统",
                })

        except Exception as e:
            logger.error(f"关闭窗口失败: {e}")
            return ToolResult(data={
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="close_window",
        description="关闭当前窗口。",
        input_schema=CloseWindowInput,
        output_schema=CloseWindowOutput,
        call=close_window,
        search_hint="close window, exit window",
        user_facing_name=lambda input_data=None: "Close Window",
    )


# ============ 系统信息工具 ============

class GetSystemInfoInput(BaseModel):
    """获取系统信息输入"""
    pass


class GetSystemInfoOutput(BaseModel):
    """获取系统信息输出"""
    platform: str
    username: str
    cwd: str
    desktop: str
    computer_name: Optional[str] = None
    user_profile: Optional[str] = None


def create_get_system_info_tool() -> Tool:
    """创建获取系统信息工具"""

    async def get_system_info(
        args: GetSystemInfoInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            info = {
                "platform": os.name,
                "username": os.getlogin(),
                "cwd": os.getcwd(),
                "desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
            }

            if os.name == "nt":
                info["computer_name"] = os.environ.get("COMPUTERNAME", "")
                info["user_profile"] = os.environ.get("USERPROFILE", "")

            output = GetSystemInfoOutput(**info)
            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="get_system_info",
        description="获取系统信息。",
        input_schema=GetSystemInfoInput,
        output_schema=GetSystemInfoOutput,
        call=get_system_info,
        search_hint="get system info, system details, environment",
        is_read_only=lambda input_data: True,
        is_concurrency_safe=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Get System Info",
    )


class GetClipboardTextInput(BaseModel):
    """获取剪贴板输入"""
    pass


class GetClipboardTextOutput(BaseModel):
    """获取剪贴板输出"""
    text: str


def create_get_clipboard_text_tool() -> Tool:
    """创建获取剪贴板工具"""

    async def get_clipboard_text(
        args: GetClipboardTextInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            if os.name == "nt":
                import win32clipboard
                import win32con

                win32clipboard.OpenClipboard()
                text = win32clipboard.GetClipboardData(win32con.CF_TEXT)
                win32clipboard.CloseClipboard()
                text = text.decode('gbk', errors='ignore') if text else ""
            else:
                text = "剪贴板功能仅支持Windows系统"

            output = GetClipboardTextOutput(text=text or "(剪贴板为空)")
            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"获取剪贴板失败: {e}")
            return ToolResult(data={"text": f"获取失败: {str(e)}"})

    return build_tool(
        name="get_clipboard_text",
        description="获取剪贴板文本内容。",
        input_schema=GetClipboardTextInput,
        output_schema=GetClipboardTextOutput,
        call=get_clipboard_text,
        search_hint="get clipboard, copy from clipboard",
        is_read_only=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Get Clipboard",
    )


class SetClipboardTextInput(BaseModel):
    """设置剪贴板输入"""
    text: str = Field(description="要设置的文本内容")


class SetClipboardTextOutput(BaseModel):
    """设置剪贴板输出"""
    success: bool
    message: str


def create_set_clipboard_text_tool() -> Tool:
    """创建设置剪贴板工具"""

    async def set_clipboard_text(
        args: SetClipboardTextInput,
        context: ToolUseContext,
    ) -> ToolResult:
        text = args.text

        try:
            if os.name == "nt":
                import win32clipboard
                import win32con

                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_TEXT, text.encode('gbk', errors='ignore'))
                win32clipboard.CloseClipboard()

                output = SetClipboardTextOutput(
                    success=True,
                    message="剪贴板已设置",
                )

                return ToolResult(data=output.model_dump())
            else:
                return ToolResult(data={
                    "success": False,
                    "message": "剪贴板功能仅支持Windows系统",
                })

        except Exception as e:
            logger.error(f"设置剪贴板失败: {e}")
            return ToolResult(data={
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="set_clipboard_text",
        description="设置剪贴板文本内容。",
        input_schema=SetClipboardTextInput,
        output_schema=SetClipboardTextOutput,
        call=set_clipboard_text,
        search_hint="set clipboard, copy to clipboard",
        user_facing_name=lambda input_data=None: "Set Clipboard",
    )


class GetRunningProcessesInput(BaseModel):
    """获取进程列表输入"""
    pass


class ProcessInfo(BaseModel):
    """进程信息"""
    name: str
    pid: str
    memory: str


class GetRunningProcessesOutput(BaseModel):
    """获取进程列表输出"""
    processes: List[ProcessInfo]


def create_get_running_processes_tool() -> Tool:
    """创建获取进程列表工具"""

    async def get_running_processes(
        args: GetRunningProcessesInput,
        context: ToolUseContext,
    ) -> ToolResult:
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
                    processes.append(ProcessInfo(
                        name=parts[0].replace('"', ''),
                        pid=parts[1].replace('"', ''),
                        memory=parts[4].replace('"', ''),
                    ))

            output = GetRunningProcessesOutput(processes=processes[:50])
            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"获取进程列表失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="get_running_processes",
        description="获取当前运行中的进程列表。",
        input_schema=GetRunningProcessesInput,
        output_schema=GetRunningProcessesOutput,
        call=get_running_processes,
        search_hint="get processes, running tasks, task list",
        is_read_only=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Get Processes",
    )


class GetActiveWindowInput(BaseModel):
    """获取活动窗口输入"""
    pass


class GetActiveWindowOutput(BaseModel):
    """获取活动窗口输出"""
    title: str


def create_get_active_window_tool() -> Tool:
    """创建获取活动窗口工具"""

    async def get_active_window(
        args: GetActiveWindowInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            if os.name == "nt":
                import win32gui
                window = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(window)
            else:
                title = "活动窗口获取仅支持Windows系统"

            output = GetActiveWindowOutput(title=title)
            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"获取活动窗口失败: {e}")
            return ToolResult(data={"title": f"获取失败: {str(e)}"})

    return build_tool(
        name="get_active_window",
        description="获取当前活动窗口的标题。",
        input_schema=GetActiveWindowInput,
        output_schema=GetActiveWindowOutput,
        call=get_active_window,
        search_hint="get active window, foreground window",
        is_read_only=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Get Active Window",
    )


# ============ 文件操作工具 ============

class CopyFileInput(BaseModel):
    """复制文件输入"""
    source: str = Field(description="源文件路径")
    destination: str = Field(description="目标路径")


class CopyFileOutput(BaseModel):
    """复制文件输出"""
    source: str
    destination: str
    success: bool
    message: str


def create_copy_file_tool() -> Tool:
    """创建复制文件工具"""

    async def copy_file(
        args: CopyFileInput,
        context: ToolUseContext,
    ) -> ToolResult:
        source = args.source
        destination = args.destination

        if not os.path.exists(source):
            return ToolResult(data={
                "source": source,
                "destination": destination,
                "success": False,
                "message": "源文件不存在",
            })

        try:
            shutil.copy2(source, destination)

            output = CopyFileOutput(
                source=source,
                destination=destination,
                success=True,
                message="文件已复制",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"复制文件失败: {e}")
            return ToolResult(data={
                "source": source,
                "destination": destination,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="copy_file",
        description="复制文件。",
        input_schema=CopyFileInput,
        output_schema=CopyFileOutput,
        call=copy_file,
        search_hint="copy file, duplicate file",
        is_destructive=lambda input_data: False,
        user_facing_name=lambda input_data=None: "Copy File",
    )


class MoveFileInput(BaseModel):
    """移动文件输入"""
    source: str = Field(description="源文件路径")
    destination: str = Field(description="目标路径")


class MoveFileOutput(BaseModel):
    """移动文件输出"""
    source: str
    destination: str
    success: bool
    message: str


def create_move_file_tool() -> Tool:
    """创建移动文件工具"""

    async def move_file(
        args: MoveFileInput,
        context: ToolUseContext,
    ) -> ToolResult:
        source = args.source
        destination = args.destination

        if not os.path.exists(source):
            return ToolResult(data={
                "source": source,
                "destination": destination,
                "success": False,
                "message": "源文件不存在",
            })

        try:
            shutil.move(source, destination)

            output = MoveFileOutput(
                source=source,
                destination=destination,
                success=True,
                message="文件已移动",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"移动文件失败: {e}")
            return ToolResult(data={
                "source": source,
                "destination": destination,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="move_file",
        description="移动文件。",
        input_schema=MoveFileInput,
        output_schema=MoveFileOutput,
        call=move_file,
        search_hint="move file, relocate file",
        is_destructive=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Move File",
    )


class DeleteFileInput(BaseModel):
    """删除文件输入"""
    file_path: str = Field(description="要删除的文件或文件夹路径")


class DeleteFileOutput(BaseModel):
    """删除文件输出"""
    file_path: str
    success: bool
    message: str


def create_delete_file_tool() -> Tool:
    """创建删除文件工具"""

    async def delete_file(
        args: DeleteFileInput,
        context: ToolUseContext,
    ) -> ToolResult:
        file_path = args.file_path

        if not os.path.exists(file_path):
            return ToolResult(data={
                "file_path": file_path,
                "success": False,
                "message": "文件或文件夹不存在",
            })

        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

            output = DeleteFileOutput(
                file_path=file_path,
                success=True,
                message="已删除",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return ToolResult(data={
                "file_path": file_path,
                "success": False,
                "message": str(e),
            })

    return build_tool(
        name="delete_file",
        description="删除文件或文件夹。",
        input_schema=DeleteFileInput,
        output_schema=DeleteFileOutput,
        call=delete_file,
        search_hint="delete file, remove file, delete folder",
        is_destructive=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Delete File",
    )


class CreateFileInput(BaseModel):
    """创建文件输入"""
    file_path: str = Field(description="要创建的文件路径")
    content: Optional[str] = Field(default="", description="文件内容（可选）")


class CreateFileOutput(BaseModel):
    """创建文件输出"""
    file_path: str
    success: bool
    message: str


def create_create_file_tool() -> Tool:
    """创建创建文件工具"""

    async def create_file(
        args: CreateFileInput,
        context: ToolUseContext,
    ) -> ToolResult:
        file_path = args.file_path
        content = args.content or ""

        try:
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            output = CreateFileOutput(
                file_path=file_path,
                success=True,
                message=f"已成功创建文件: {file_path}",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"创建文件失败: {e}")
            return ToolResult(data={
                "file_path": file_path,
                "success": False,
                "message": f"无法创建文件: {str(e)}",
            })

    return build_tool(
        name="create_file",
        description="创建新文件。",
        input_schema=CreateFileInput,
        output_schema=CreateFileOutput,
        call=create_file,
        search_hint="create file, new file, make file",
        is_destructive=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Create File",
    )


class ListFilesInput(BaseModel):
    """列出文件输入"""
    directory: Optional[str] = Field(default=".", description="要列出的目录路径，默认为当前目录")


class ListFilesOutput(BaseModel):
    """列出文件输出"""
    directory: str
    files: List[str]


def create_list_files_tool() -> Tool:
    """创建列出文件工具"""

    async def list_files(
        args: ListFilesInput,
        context: ToolUseContext,
    ) -> ToolResult:
        directory = args.directory or "."

        if not os.path.exists(directory):
            return ToolResult(data={
                "directory": directory,
                "files": [],
            })

        try:
            files = os.listdir(directory)[:20]

            output = ListFilesOutput(
                directory=directory,
                files=files,
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="list_files",
        description="列出目录中的文件。",
        input_schema=ListFilesInput,
        output_schema=ListFilesOutput,
        call=list_files,
        search_hint="list files, directory contents, ls",
        is_read_only=lambda input_data: True,
        is_concurrency_safe=lambda input_data: True,
        user_facing_name=lambda input_data=None: "List Files",
    )


# ============ 网页工具 ============

class WebFetchInput(BaseModel):
    """网页获取输入"""
    url: str = Field(description="要获取的网页URL")
    prompt: Optional[str] = Field(default=None, description="提取信息的提示词（可选）")


class WebFetchOutput(BaseModel):
    """网页获取输出"""
    url: str
    content: str
    status_code: int
    content_type: Optional[str] = None


def create_web_fetch_tool() -> Tool:
    """创建网页获取工具"""

    async def web_fetch(
        args: WebFetchInput,
        context: ToolUseContext,
    ) -> ToolResult:
        url = args.url

        try:
            import urllib.request
            import urllib.parse

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode('utf-8', errors='ignore')
                status_code = response.status
                content_type = response.headers.get('Content-Type', '')

            output = WebFetchOutput(
                url=url,
                content=content[:50000],
                status_code=status_code,
                content_type=content_type,
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"获取网页失败: {e}")
            return ToolResult(data={"error": str(e), "url": url})

    return build_tool(
        name="web_fetch",
        description="获取网页内容。用于获取指定URL的网页内容。",
        input_schema=WebFetchInput,
        output_schema=WebFetchOutput,
        call=web_fetch,
        search_hint="fetch web page, get website content, download html",
        is_read_only=lambda input_data: True,
        is_open_world=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Web Fetch",
    )


class WebSearchInput(BaseModel):
    """网络搜索输入"""
    query: str = Field(description="搜索查询关键词")
    num_results: Optional[int] = Field(default=10, description="返回结果数量")


class SearchResult(BaseModel):
    """搜索结果项"""
    title: str
    url: str
    snippet: str


class WebSearchOutput(BaseModel):
    """网络搜索输出"""
    query: str
    results: List[SearchResult]
    total: int


def create_web_search_tool() -> Tool:
    """创建网络搜索工具"""

    async def web_search(
        args: WebSearchInput,
        context: ToolUseContext,
    ) -> ToolResult:
        query = args.query
        num_results = args.num_results or 10

        try:
            import urllib.request
            import urllib.parse
            import json

            encoded_query = urllib.parse.quote_plus(query)
            search_url = f"https://ddg-api.herokuapp.com/search?q={encoded_query}&max_results={num_results}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }

            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8', errors='ignore'))

            results = [
                SearchResult(
                    title=item.get('title', ''),
                    url=item.get('url', ''),
                    snippet=item.get('description', '')
                )
                for item in data[:num_results]
            ]

            output = WebSearchOutput(
                query=query,
                results=results,
                total=len(results),
            )

            return ToolResult(data=output.model_dump())

        except ImportError:
            return ToolResult(data={"error": "需要安装 requests 库进行网络搜索"})
        except Exception as e:
            logger.error(f"网络搜索失败: {e}")
            return ToolResult(data={"error": str(e), "query": query})

    return build_tool(
        name="web_search",
        description="搜索网络内容。使用搜索引擎搜索相关信息。",
        input_schema=WebSearchInput,
        output_schema=WebSearchOutput,
        call=web_search,
        search_hint="search web, internet search, google search",
        is_read_only=lambda input_data: True,
        is_open_world=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Web Search",
    )


class GrepInput(BaseModel):
    """Grep搜索输入"""
    pattern: str = Field(description="要搜索的正则表达式或关键词")
    path: Optional[str] = Field(default=".", description="Search path")
    file_pattern: Optional[str] = Field(default=None, description="文件匹配模式，如 *.py")
    case_sensitive: Optional[bool] = Field(default=True, description="是否区分大小写")
    max_results: Optional[int] = Field(default=100, description="Maximum number of results")
    context_lines: Optional[int] = Field(default=0, description="结果周围显示的行数")


class GrepMatch(BaseModel):
    """Grep匹配结果"""
    file_path: str
    line_number: int
    line_content: str
    context: Optional[List[str]] = None


class GrepOutput(BaseModel):
    """Grep搜索输出"""
    pattern: str
    path: str
    matches: List[GrepMatch]
    total_matches: int
    files_searched: int


def create_grep_tool() -> Tool:
    """创建Grep搜索工具"""

    async def grep_search(
        args: GrepInput,
        context: ToolUseContext,
    ) -> ToolResult:
        pattern = args.pattern
        search_path = args.path or "."
        file_pattern = args.file_pattern
        case_sensitive = args.case_sensitive if args.case_sensitive is not None else True
        max_results = args.max_results or 100
        context_lines = args.context_lines or 0

        try:
            import re

            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)

            matches = []
            files_searched = 0

            search_path_obj = Path(search_path).resolve()
            search_pattern = file_pattern if file_pattern else "*"

            try:
                file_iterator = search_path_obj.rglob(search_pattern)
                for file_path in file_iterator:
                    if not file_path.is_file():
                        continue

                    try:
                        files_searched += 1
                        if files_searched > 1000:
                            break

                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            lines = f.readlines()

                        for line_no, line in enumerate(lines, 1):
                            if regex.search(line):
                                if len(matches) >= max_results:
                                    break

                                match = GrepMatch(
                                    file_path=str(file_path),
                                    line_number=line_no,
                                    line_content=line.rstrip(),
                                )

                                if context_lines > 0 and line_no <= len(lines):
                                    start_idx = max(0, line_no - 1 - context_lines)
                                    end_idx = min(len(lines), line_no + context_lines)
                                    match.context = [lines[i].rstrip() for i in range(start_idx, end_idx)]

                                matches.append(match)

                        if len(matches) >= max_results:
                            break

                    except (PermissionError, OSError, UnicodeDecodeError):
                        continue

            except Exception as e:
                logger.warning(f"rglob failed: {e}")

            output = GrepOutput(
                pattern=pattern,
                path=search_path,
                matches=matches,
                total_matches=len(matches),
                files_searched=files_searched,
            )

            return ToolResult(data=output.model_dump())

        except re.error as e:
            return ToolResult(data={"error": f"正则表达式错误: {str(e)}"})
        except Exception as e:
            logger.error(f"Grep搜索失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="grep",
        description="在文件中搜索匹配的内容。支持正则表达式和上下文显示。",
        input_schema=GrepInput,
        output_schema=GrepOutput,
        call=grep_search,
        search_hint="search in files, grep, find text, regex search",
        is_read_only=lambda input_data: True,
        is_concurrency_safe=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Grep Search",
    )


class ToolSearchInput(BaseModel):
    """工具搜索输入"""
    query: str = Field(description="搜索查询")
    category: Optional[str] = Field(default=None, description="工具类别筛选")
    limit: Optional[int] = Field(default=5, description="返回结果数量限制")


class ToolSearchResult(BaseModel):
    """工具搜索结果"""
    name: str
    description: str
    relevance_score: float


class ToolSearchOutput(BaseModel):
    """工具搜索输出"""
    query: str
    results: List[ToolSearchResult]
    total: int


def create_tool_search_tool() -> Tool:
    """创建工具搜索工具"""

    async def tool_search(
        args: ToolSearchInput,
        context: ToolUseContext,
    ) -> ToolResult:
        query = args.query.lower()
        category = args.category
        limit = args.limit or 5

        try:
            from . import get_tool_system

            tool_system = get_tool_system()
            all_tools = tool_system.list_tools()

            results = []
            for tool in all_tools:
                score = 0.0

                tool_name = tool.name.lower()
                tool_desc = tool.description.lower()
                tool_hint = getattr(tool, 'search_hint', '').lower()

                if query in tool_name:
                    score += 10.0
                if query in tool_desc:
                    score += 5.0
                if query in tool_hint:
                    score += 3.0

                for word in query.split():
                    if len(word) > 2:
                        if word in tool_name:
                            score += 2.0
                        if word in tool_desc:
                            score += 1.0

                if score > 0:
                    results.append(ToolSearchResult(
                        name=tool.name,
                        description=tool.description,
                        relevance_score=score,
                    ))

            results.sort(key=lambda x: x.relevance_score, reverse=True)
            results = results[:limit]

            output = ToolSearchOutput(
                query=args.query,
                results=results,
                total=len(results),
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"工具搜索失败: {e}")
            return ToolResult(data={"error": str(e)})

    return build_tool(
        name="tool_search",
        description="搜索可用的工具。根据功能描述搜索匹配的工具。",
        input_schema=ToolSearchInput,
        output_schema=ToolSearchOutput,
        call=tool_search,
        search_hint="search tools, find tools, tool lookup",
        is_read_only=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Tool Search",
    )


# ============ 代码执行和定时任务工具 ============

class ExecuteCodeInput(BaseModel):
    """执行代码输入"""
    code: str = Field(description="要执行的 Python 代码")


class ExecuteCodeOutput(BaseModel):
    """执行代码输出"""
    output: str


def create_execute_code_tool() -> Tool:
    """创建执行代码工具"""

    async def execute_code(
        args: ExecuteCodeInput,
        context: ToolUseContext,
    ) -> ToolResult:
        code = args.code

        try:
            import io
            from contextlib import redirect_stderr, redirect_stdout

            output_buffer = io.StringIO()
            with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
                exec(
                    code,
                    {
                        "os": os,
                        "subprocess": subprocess,
                        "time": __import__('time'),
                    },
                )

            result = output_buffer.getvalue()
            if not result:
                result = "执行成功，无控制台输出。"

            output = ExecuteCodeOutput(output=result)
            return ToolResult(data=output.model_dump())

        except Exception as e:
            error_msg = f"执行出错: {str(e)}"
            logger.error(f"代码执行失败: {error_msg}")
            return ToolResult(data={"output": error_msg})

    return build_tool(
        name="execute_code",
        description="执行 Python 代码。",
        input_schema=ExecuteCodeInput,
        output_schema=ExecuteCodeOutput,
        call=execute_code,
        search_hint="run code, execute python, eval code",
        is_open_world=lambda input_data: True,
        user_facing_name=lambda input_data=None: "Execute Code",
    )


class SetTimerInput(BaseModel):
    """设置定时任务输入"""
    time_spec: str = Field(description="时间规格，ISO 8601格式。持续时间：PTnHnMnS（如PT2M表示2分钟后）；日期时间：YYYY-MM-DDTHH:MM:SS")
    message: Optional[str] = Field(default=None, description="提醒消息内容（当不需要执行工具时使用）")
    tool_name: Optional[str] = Field(default=None, description="要定时执行的工具名称（当需要执行工具时使用）")
    tool_arguments: Optional[Dict[str, Any]] = Field(default=None, description="工具参数（与tool_name配合使用）")
    repeat_interval: Optional[int] = Field(default=None, description="重复间隔（秒），默认None表示单次")


class SetTimerOutput(BaseModel):
    """设置定时任务输出"""
    success: bool
    message: str


def create_set_timer_tool() -> Tool:
    """创建设置定时任务工具"""

    async def set_timer(
        args: SetTimerInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            from core.scheduler import get_scheduler
            from datetime import datetime

            scheduler = get_scheduler()
            time_spec = args.time_spec
            message = args.message
            tool_name_param = args.tool_name
            tool_arguments = args.tool_arguments or {}
            repeat_interval = args.repeat_interval

            if not time_spec:
                return ToolResult(data={"success": False, "message": "请提供时间规格"})

            scheduled_time = scheduler.parse_time_spec(time_spec)

            if message:
                task_id = scheduler.schedule_reminder(
                    message=message,
                    scheduled_time=scheduled_time,
                    repeat_interval=repeat_interval
                )
                result_msg = f"定时提醒已设置，任务ID: {task_id}，提醒时间: {datetime.fromtimestamp(scheduled_time).strftime('%Y-%m-%d %H:%M:%S')}"

            elif tool_name_param:
                task_id = scheduler.schedule_tool_call(
                    tool_name=tool_name_param,
                    tool_arguments=tool_arguments,
                    scheduled_time=scheduled_time,
                    repeat_interval=repeat_interval
                )
                result_msg = f"定时任务已设置，任务ID: {task_id}，执行时间: {datetime.fromtimestamp(scheduled_time).strftime('%Y-%m-%d %H:%M:%S')}"

            else:
                return ToolResult(data={"success": False, "message": "请提供提醒消息或要执行的工具"})

            output = SetTimerOutput(
                success=True,
                message=result_msg,
            )

            return ToolResult(data=output.model_dump())

        except ValueError as e:
            return ToolResult(data={"success": False, "message": f"时间解析失败: {str(e)}"})
        except Exception as e:
            logger.error(f"设置定时任务失败: {e}")
            return ToolResult(data={"success": False, "message": f"设置失败: {str(e)}"})

    return build_tool(
        name="set_timer",
        description="设置定时提醒或定时执行工具。",
        input_schema=SetTimerInput,
        output_schema=SetTimerOutput,
        call=set_timer,
        search_hint="set timer, schedule task, reminder",
        user_facing_name=lambda input_data=None: "Set Timer",
    )


class CancelTimerInput(BaseModel):
    """取消定时任务输入"""
    task_id: str = Field(description="要取消的任务ID")


class CancelTimerOutput(BaseModel):
    """取消定时任务输出"""
    success: bool
    message: str


def create_cancel_timer_tool() -> Tool:
    """创建取消定时任务工具"""

    async def cancel_timer(
        args: CancelTimerInput,
        context: ToolUseContext,
    ) -> ToolResult:
        task_id = args.task_id

        if not task_id:
            return ToolResult(data={"success": False, "message": "请提供任务ID"})

        try:
            from core.scheduler import get_scheduler

            scheduler = get_scheduler()
            success = scheduler.cancel_task(task_id)

            output = CancelTimerOutput(
                success=success,
                message="任务已取消" if success else "取消失败，任务不存在",
            )

            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"取消定时任务失败: {e}")
            return ToolResult(data={"success": False, "message": f"取消失败: {str(e)}"})

    return build_tool(
        name="cancel_timer",
        description="取消定时任务。",
        input_schema=CancelTimerInput,
        output_schema=CancelTimerOutput,
        call=cancel_timer,
        search_hint="cancel timer, stop task, remove schedule",
        user_facing_name=lambda input_data=None: "Cancel Timer",
    )


class ListTimersInput(BaseModel):
    """列出定时任务输入"""
    pass


class TimerInfo(BaseModel):
    """定时任务信息"""
    task_id: str
    type: str
    scheduled_time: str
    remaining_time: str
    status: str
    message: Optional[str] = None
    tool_name: Optional[str] = None
    repeat_interval: Optional[str] = None


class ListTimersOutput(BaseModel):
    """列出定时任务输出"""
    tasks: List[TimerInfo]


def create_list_timers_tool() -> Tool:
    """创建列出定时任务工具"""

    async def list_timers(
        args: ListTimersInput,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            from core.scheduler import get_scheduler

            scheduler = get_scheduler()
            tasks = scheduler.list_tasks()

            task_list = []
            for task in tasks:
                task_info = TimerInfo(
                    task_id=task.id,
                    type=task.task_type.value,
                    scheduled_time=task.get_scheduled_time_str(),
                    remaining_time=task.get_remaining_time(),
                    status=task.status.value,
                )
                if task.message:
                    task_info.message = task.message
                if task.tool_name:
                    task_info.tool_name = task.tool_name
                if task.repeat_interval:
                    task_info.repeat_interval = f"{task.repeat_interval}秒"
                task_list.append(task_info)

            output = ListTimersOutput(tasks=task_list)
            return ToolResult(data=output.model_dump())

        except Exception as e:
            logger.error(f"获取定时任务列表失败: {e}")
            return ToolResult(data={"tasks": [], "error": str(e)})

    return build_tool(
        name="list_timers",
        description="获取所有定时任务列表。",
        input_schema=ListTimersInput,
        output_schema=ListTimersOutput,
        call=list_timers,
        search_hint="list timers, show schedules, active tasks",
        is_read_only=lambda input_data: True,
        user_facing_name=lambda input_data=None: "List Timers",
    )


# ============ 更新工具列表和注册函数 ============

def get_all_builtin_tools() -> List[Tool]:
    """获取所有内置工具"""
    return [
        # 已有的工具
        create_file_read_tool(),
        create_file_edit_tool(),
        create_file_write_tool(),
        create_bash_tool(),
        create_glob_tool(),
        create_open_application_tool(),
        create_search_files_tool(),
        # 新增系统工具
        create_close_application_tool(),
        create_open_folder_tool(),
        create_open_url_tool(),
        create_set_wallpaper_tool(),
        create_wallpaper_engine_tool(),
        create_list_wallpapers_tool(),
        create_take_screenshot_tool(),
        # 新增窗口控制工具
        create_minimize_window_tool(),
        create_maximize_window_tool(),
        create_close_window_tool(),
        # 新增系统信息工具
        create_get_system_info_tool(),
        create_get_clipboard_text_tool(),
        create_set_clipboard_text_tool(),
        create_get_running_processes_tool(),
        create_get_active_window_tool(),
        # 新增文件操作工具
        create_copy_file_tool(),
        create_move_file_tool(),
        create_delete_file_tool(),
        create_create_file_tool(),
        create_list_files_tool(),
        # 新增网络和搜索工具
        create_web_fetch_tool(),
        create_web_search_tool(),
        create_grep_tool(),
        create_tool_search_tool(),
        # 新增代码执行和定时任务工具
        create_execute_code_tool(),
        create_set_timer_tool(),
        create_cancel_timer_tool(),
        create_list_timers_tool(),
    ]


def register_builtin_tools() -> None:
    """注册所有内置工具"""
    from . import register_tool

    for tool in get_all_builtin_tools():
        register_tool(tool, category="builtin")

    logger.info(f"已注册 {len(get_all_builtin_tools())} 个内置工具")
