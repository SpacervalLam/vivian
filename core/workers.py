"""
Worker threads for processing LLM, TTS, and UI tasks.
"""

from queue import Queue
from typing import Optional

from PySide6.QtCore import QThread

from .runtime.app_runtime import get_app_runtime, try_get_app_runtime


class BaseWorker(QThread):
    """Base class for all worker threads."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
    
    def stop(self):
        """Stop the worker thread."""
        self.running = False
        if not self.wait(3000):
            self.terminate()
            self.wait()


class LLMWorker(BaseWorker):
    """Worker for processing LLM requests."""
    
    def __init__(self, input_queue: Queue, output_queue: Queue, parent=None):
        super().__init__(parent)
        self.input_queue = input_queue
        self.output_queue = output_queue
    
    def run(self):
        while self.running:
            try:
                message = self.input_queue.get()
                if message is None:
                    break
                
                rt = get_app_runtime()
                response = rt.llm_manager.chat(message.text, stream=True)
                
                for chunk in response:
                    self.output_queue.put(chunk)
                
                self.input_queue.task_done()
            except Exception as e:
                print(f"LLMWorker error: {e}")
                self.input_queue.task_done()


class TTSWorker(BaseWorker):
    """Worker for processing TTS requests."""
    
    def __init__(self, input_queue: Queue, output_queue: Queue, parent=None):
        super().__init__(parent)
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.tts_message_dispatcher = None
    
    def run(self):
        from core.handlers import default_tts_handler_chain
        
        self.tts_message_dispatcher = default_tts_handler_chain()
        self.tts_message_dispatcher.init_handlers()
        
        while self.running:
            try:
                message = self.input_queue.get()
                if message is None:
                    break
                
                self.tts_message_dispatcher.dispatch(message)
            except Exception as e:
                print(f"TTSWorker error: {e}")


class UIWorker(BaseWorker):
    """Worker for processing UI updates."""
    
    def __init__(self, input_queue: Queue, parent=None):
        super().__init__(parent)
        self.input_queue = input_queue
        self.ui_out_dispatcher = None
    
    def run(self):
        from core.handlers import default_ui_output_handler_chain
        
        self.ui_out_dispatcher = default_ui_output_handler_chain()
        self.ui_out_dispatcher.init_handlers()
        
        while self.running:
            try:
                message = self.input_queue.get()
                if message is None:
                    break
                
                self.ui_out_dispatcher.dispatch(message)
                self.input_queue.task_done()
            except Exception as e:
                print(f"UIWorker error: {e}")
                self.input_queue.task_done()