from typing import Optional, Tuple


class CommandParser:
    """
    解析 / 开头的硬指令，用于系统调试或强制操作
    """

    def __init__(self):
        self.commands = {
            "/clear": "clear_history",
            "/reset": "reset_brain",
            "/remember": "force_remember",
        }

    def parse(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        text = text.strip()
        if not text.startswith("/"):
            return None, None

        parts = text.split(" ", 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        # 去掉 /
        cmd_key = cmd[1:]

        return cmd_key, args
