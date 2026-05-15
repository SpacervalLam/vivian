from typing import Any, Dict

from loguru import logger

from core.command_parser import CommandParser


class CommandHandler:
    """用户命令处理类"""

    def __init__(self, memory_manager):
        """初始化命令处理器"""
        self.command_parser = CommandParser()
        self.memory_manager = memory_manager
    
    def parse(self, text: str):
        """解析用户输入是否为命令"""
        return self.command_parser.parse(text)

    def handle_command(self, cmd: str, args: str) -> Dict[str, Any]:
        """处理用户命令
        
        Args:
            cmd: 命令名称
            args: 命令参数
        
        Returns:
            dict: 命令执行结果
        """
        logger.debug(f"[CommandHandler] 处理命令: {cmd}, 参数: {args}")

        if cmd == "remember":
            return self._handle_remember_command(args)
        elif cmd == "forget":
            return self._handle_forget_command(args)
        elif cmd == "list_memories":
            return self._handle_list_memories_command(args)
        elif cmd == "clear":
            return self._handle_clear_command()
        else:
            return {
                "text": f"未知命令: {cmd}\n{self.command_parser.format_help()}",
                "motion": "idle",
                "expression": "",
            }

    def _handle_remember_command(self, content: str) -> Dict[str, Any]:
        """处理"记住"命令"""
        if not content:
            return {
                "text": "请告诉我要记住什么内容",
                "motion": "idle",
                "expression": "",
            }

        try:
            self.memory_manager.add_long_term_memory(
                content=content, importance=1.0, tags=["explicitly_remembered"]
            )
            return {
                "text": f"已记住: {content}",
                "motion": "Scene1",
                "expression": "shy",
            }
        except Exception as e:
            logger.error(f"[CommandHandler] 记住命令执行失败: {e}")
            return {"text": "记住失败了...", "motion": "idle", "expression": "angry"}

    def _handle_forget_command(self, content: str) -> Dict[str, Any]:
        """处理"忘记"命令"""
        if not content:
            return {
                "text": "请告诉我要忘记什么内容",
                "motion": "idle",
                "expression": "",
            }

        try:
            self.memory_manager.forget_memories(filters={"content": content})
            return {
                "text": f"已忘记: {content}",
                "motion": "idle",
                "expression": "angry",
            }
        except Exception as e:
            logger.error(f"[CommandHandler] 忘记命令执行失败: {e}")
            return {"text": "忘记失败了...", "motion": "idle", "expression": "angry"}

    def _handle_list_memories_command(self, filters: str) -> Dict[str, Any]:
        """处理"列出记忆"命令"""
        try:
            memories = self.memory_manager.list_long_term_memories()
            if not memories:
                return {"text": "没有找到记忆", "motion": "idle", "expression": ""}

            memory_list = "记忆列表：\n"
            for i, memory in enumerate(memories[:5]):
                memory_list += f"{i+1}. {memory.content[:50]}...\n"

            if len(memories) > 5:
                memory_list += f"... 共 {len(memories)} 条记忆"

            return {"text": memory_list, "motion": "idle", "expression": ""}
        except Exception as e:
            logger.error(f"[CommandHandler] 列出记忆命令执行失败: {e}")
            return {
                "text": "列出记忆失败了...",
                "motion": "idle",
                "expression": "angry",
            }

    def _handle_clear_command(self) -> Dict[str, Any]:
        """处理"清空"命令"""
        try:
            short_term_memories = self.memory_manager.list_short_term_memories()
            for memory in short_term_memories:
                self.memory_manager.short_term_store.delete_memory(memory.id)

            return {"text": "已清空对话历史", "motion": "idle", "expression": ""}
        except Exception as e:
            logger.error(f"[CommandHandler] 清空命令执行失败: {e}")
            return {"text": "清空失败了...", "motion": "idle", "expression": "angry"}
