"""WinRT语音识别管理模块。"""

import asyncio
from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger

try:
    from winsdk.windows.media.speechrecognition import SpeechRecognizer
    WINSDK_AVAILABLE = True
except ImportError as e:
    logger.warning(f"无法导入 winsdk 模块: {e}")
    WINSDK_AVAILABLE = False

class WinRTSpeechManager(QObject):
    partial_signal = pyqtSignal(str)
    final_signal = pyqtSignal(str)

    def __init__(self, language=None):
        super().__init__()
        self.recognizer = None
        self._running = False

    async def start(self):
        if not WINSDK_AVAILABLE:
            logger.warning("winsdk 模块不可用，无法启动语音识别")
            return

        if self._running:
            return
        self._running = True

        try:
            self.recognizer = SpeechRecognizer()
            await self.recognizer.compile_constraints_async()

            def on_hypothesis(sender, args):
                try:
                    txt = getattr(args, "hypothesis", None)
                    if txt is None:
                        txt = getattr(args, "hypothesis", None)
                    text = getattr(args.hypothesis, "text", "") if getattr(args, "hypothesis", None) is not None else ""
                except Exception:
                    text = ""
                if text:
                    self.partial_signal.emit(text)

            def on_result(sender, args):
                try:
                    res = getattr(args, "result", None)
                    text = getattr(res, "text", "") if res is not None else ""
                except Exception:
                    text = ""
                if text:
                    self.final_signal.emit(text)

            try:
                self.recognizer.add_hypothesis_generated(on_hypothesis)
                self.recognizer.continuous_recognition_session.add_result_generated(on_result)
                logger.debug("WinRT 语音事件监听已成功绑定")
            except AttributeError as e:
                logger.error(f"API 映射错误，请检查 winsdk 版本: {e}")
            except Exception as e:
                logger.error(f"注册事件失败: {e}")

            await self.recognizer.continuous_recognition_session.start_async()
            logger.info("语音识别已启动")
        except Exception as e:
            logger.error(f"启动语音识别失败: {e}")
            self._running = False
            self.recognizer = None

    async def stop(self):
        if not self._running:
            return
        try:
            await self.recognizer.continuous_recognition_session.stop_async()
            logger.info("语音识别已停止")
        except Exception as e:
            logger.error(f"停止语音识别失败: {e}")
        self._running = False
        self.recognizer = None
