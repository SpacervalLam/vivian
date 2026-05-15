"""语音识别管理模块。"""

import asyncio
import logging
from typing import Callable, Optional
from winsdk.windows.media.speechrecognition import SpeechRecognizer, SpeechContinuousRecognitionSession, SpeechRecognitionResultStatus

logger = logging.getLogger(__name__)

class SpeechRecognitionManager:
    def __init__(self, 
                 partial_result_callback: Optional[Callable[[str], None]] = None,
                 final_result_callback: Optional[Callable[[str], None]] = None):
        
        self._recognizer = None
        self._continuous_session = None
        
        self._partial_callback = partial_result_callback
        self._final_callback = final_result_callback
        
        self._user_requested_stop = False
        self._is_running = False
        
        self._available = True

    async def _ensure_initialized(self):
        if self._recognizer:
            return

        try:
            self._recognizer = SpeechRecognizer()
            await self._recognizer.compile_constraints_async()
            
            self._recognizer.add_hypothesis_generated(self._on_hypothesis)
            self._continuous_session = self._recognizer.continuous_recognition_session
            self._continuous_session.add_result_generated(self._on_result)
            self._continuous_session.add_completed(self._on_completed)

            logger.debug("WinRT 语音引擎初始化完成")
        except Exception as e:
            logger.error(f"WinRT 初始化失败: {e}")
            self._available = False
            return

    async def start_recognition(self):
        self._user_requested_stop = False
        
        if not self._available:
            logger.warning("语音识别不可用，已跳过启动")
            return False
        
        await self._ensure_initialized()
        
        if not self._available:
            logger.warning("语音识别初始化失败，无法启动")
            return False
        
        if self._is_running:
            return True

        if not self._continuous_session:
            logger.error("语音识别会话未初始化")
            return False

        try:
            await self._continuous_session.start_async()
            self._is_running = True
            return True
        except Exception as e:
            if "0x80045509" in str(e):
                 self._is_running = True
                 return True
            logger.error(f"启动失败: {e}")
            return False

    async def stop_recognition(self):
        self._user_requested_stop = True
        self._is_running = False
        
        if self._continuous_session:
            try:
                await self._continuous_session.stop_async()
            except Exception as e:
                logger.warning(f"停止时出错 (可忽略): {e}")
        return True

    def _on_hypothesis(self, sender, args):
        if self._partial_callback:
            text = args.hypothesis.text
            self._partial_callback(text)

    def _on_result(self, sender, args):
        if args.result.status == SpeechRecognitionResultStatus.SUCCESS:
            text = args.result.text
            if self._final_callback and text:
                self._final_callback(text)

    def _on_completed(self, sender, args):
        logger.info(f"语音会话结束，原因: {args.status}")
        self._is_running = False
        
        if not self._user_requested_stop and self._available:
            logger.warning("检测到非正常结束（可能是超时），正在尝试自动重启...")
            import threading
            def restart_task():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.start_recognition())
                except Exception as e:
                    logger.error(f"自动重启语音识别失败: {e}")
            
            t = threading.Thread(target=restart_task, daemon=True)
            t.start()
    
    def is_available(self):
        return self._available
