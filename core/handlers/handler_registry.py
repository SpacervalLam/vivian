"""
Message handler registry and dispatcher.
"""

from typing import List

from .handler_base import MessageHandler, UIOutputMessageHandler


class MessageDispatcher:
    def __init__(self, handlers: List[MessageHandler]) -> None:
        if not handlers:
            raise ValueError("至少需要一个 handler")
        self._handlers = list(handlers)
    
    def init_handlers(self) -> None:
        for h in self._handlers:
            h.init()
    
    def dispatch(self, message) -> None:
        for h in self._handlers:
            if h.can_handle(message):
                h.pre_process(message)
                h.handle(message)
                h.post_process(message)
                return
        raise RuntimeError(f"无 handler 匹配消息: {message}")


class UIOutputMessageDispatcher:
    def __init__(self, handlers: List[UIOutputMessageHandler]) -> None:
        if not handlers:
            raise ValueError("至少需要一个 UI handler")
        self._handlers = list(handlers)
    
    def init_handlers(self) -> None:
        for h in self._handlers:
            h.init()
    
    def dispatch(self, message) -> None:
        for h in self._handlers:
            if h.can_handle(message):
                h.pre_process(message)
                h.handle(message)
                h.post_process(message)
                return
        raise RuntimeError(f"无 UI handler 匹配消息")


def default_tts_handler_chain() -> MessageDispatcher:
    from core.plugins.plugin_host import get_plugin_tts_handlers
    from .tts_message_handler import get_tts_handlers
    
    chain = list(get_plugin_tts_handlers()) + list(get_tts_handlers())
    return MessageDispatcher(chain)


def default_ui_output_handler_chain() -> UIOutputMessageDispatcher:
    from core.plugins.plugin_host import get_plugin_ui_handlers
    from .ui_message_handler import get_ui_output_handlers
    
    chain = list(get_plugin_ui_handlers()) + list(get_ui_output_handlers())
    return UIOutputMessageDispatcher(chain)