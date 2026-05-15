"""声音管理模块，提供TTS语音合成功能。"""

import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional
from loguru import logger

try:
    import pyttsx3

    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False


try:
    import win32com.client

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class TTSEngine(Enum):
    NONE = "none"
    PYTTSX3 = "pyttsx3"
    SAPI5 = "sapi5"


class SoundManager:
    DEFAULT_RATE = 150
    DEFAULT_VOLUME = 1.0

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._enabled = self.config.get("enabled", False)
        self._engine_type = self._detect_engine()
        self._engine = None
        self._mouth_callback: Optional[Callable[[float], None]] = None
        self._is_speaking = False
        self._speech_thread: Optional[threading.Thread] = None

        self._rate = self.config.get("rate", self.DEFAULT_RATE)
        self._volume = self.config.get("volume", self.DEFAULT_VOLUME)
        self._voice_id = self.config.get("voice_id", None)

        if self._enabled:
            self._init_engine()

    def _detect_engine(self) -> TTSEngine:
        if not self._enabled:
            return TTSEngine.NONE

        if PYTTSX3_AVAILABLE:
            return TTSEngine.PYTTSX3
        elif WIN32_AVAILABLE:
            return TTSEngine.SAPI5
        else:
            logger.warning("[SoundManager] 未找到可用的 TTS 引擎，将禁用语音功能")
            self._enabled = False
            return TTSEngine.NONE

    def _init_engine(self):
        if self._engine_type == TTSEngine.PYTTSX3:
            self._init_pyttsx3()
        elif self._engine_type == TTSEngine.SAPI5:
            self._init_sapi5()

    def _init_pyttsx3(self):
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)

            if self._voice_id:
                voices = self._engine.getProperty("voices")
                for voice in voices:
                    if self._voice_id in voice.id:
                        self._engine.setProperty("voice", voice.id)
                        break

            self._engine.connect("started-utterance", self._on_speech_start)
            self._engine.connect("finished-utterance", self._on_speech_end)
            self._engine.connect("error", self._on_speech_error)

            logger.debug("[SoundManager] pyttsx3 引擎已初始化")
        except Exception as e:
            logger.warning(f"[SoundManager] pyttsx3 初始化失败: {e}")
            self._engine_type = TTSEngine.NONE

    def _init_sapi5(self):
        try:
            self._engine = win32com.client.Dispatch("SAPI.SpVoice")
            self._engine.Rate = int(self._rate / 10) - 2
            self._engine.Volume = int(self._volume * 100)

            if self._voice_id:
                voices = self._engine.GetVoices()
                for voice in voices:
                    if self._voice_id in voice.GetAttribute("Name"):
                        self._engine.Voice = voice
                        break

            logger.debug("[SoundManager] SAPI5 引擎已初始化")
        except Exception as e:
            logger.warning(f"[SoundManager] SAPI5 初始化失败: {e}")
            self._engine_type = TTSEngine.NONE

    def speak(self, text: str, block: bool = False) -> bool:
        if not self._enabled or not text:
            return False

        if self._is_speaking:
            logger.debug("[SoundManager] 正在说话中，跳过新的语音请求")
            return False

        if block:
            self._speak_sync(text)
        else:
            self._speech_thread = threading.Thread(
                target=self._speak_sync, args=(text,)
            )
            self._speech_thread.start()

        return True

    def _speak_sync(self, text: str):
        self._is_speaking = True

        if self._engine_type == TTSEngine.PYTTSX3:
            self._speak_pyttsx3(text)
        elif self._engine_type == TTSEngine.SAPI5:
            self._speak_sapi5(text)

        self._is_speaking = False

    def _speak_pyttsx3(self, text: str):
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as e:
            logger.warning(f"[SoundManager] pyttsx3 语音播放失败: {e}")

    def _speak_sapi5(self, text: str):
        try:
            self._engine.Speak(text)
            while self._is_speaking and self._engine.Status.RunningState == 1:
                time.sleep(0.05)
        except Exception as e:
            logger.warning(f"[SoundManager] SAPI5 语音播放失败: {e}")

    def _on_speech_start(self, name):
        logger.debug(f"[SoundManager] 开始语音: {name}")
        self._start_lip_sync()

    def _on_speech_end(self, name, completed):
        logger.debug(f"[SoundManager] 语音结束: {name}, 完成: {completed}")
        self._stop_lip_sync()

    def _on_speech_error(self, name, exception):
        logger.warning(f"[SoundManager] 语音错误: {name}, {exception}")
        self._stop_lip_sync()

    def _start_lip_sync(self):
        if self._mouth_callback:
            self._lip_sync_active = True
            self._lip_sync_thread = threading.Thread(target=self._lip_sync_loop)
            self._lip_sync_thread.start()

    def _stop_lip_sync(self):
        self._lip_sync_active = False
        if self._mouth_callback:
            self._mouth_callback(0.0)

    def _lip_sync_loop(self):
        import random

        while self._lip_sync_active and self._is_speaking:
            if self._mouth_callback:
                mouth_value = random.uniform(0.1, 0.4)
                self._mouth_callback(mouth_value)
            time.sleep(0.05 + random.uniform(0, 0.05))

    def set_mouth_callback(self, callback: Callable[[float], None]):
        self._mouth_callback = callback

    def stop(self):
        self._lip_sync_active = False
        if self._engine_type == TTSEngine.PYTTSX3 and self._engine:
            try:
                self._engine.stop()
            except:
                pass
        self._is_speaking = False

    def is_speaking(self) -> bool:
        return self._is_speaking

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        if enabled != self._enabled:
            self._enabled = enabled
            if enabled:
                self._engine_type = self._detect_engine()
                if self._engine_type != TTSEngine.NONE:
                    self._init_engine()
            else:
                self.stop()
                self._engine = None

    def get_voices(self) -> list:
        if not self._enabled:
            return []

        voices = []
        if self._engine_type == TTSEngine.PYTTSX3 and self._engine:
            try:
                for voice in self._engine.getProperty("voices"):
                    voices.append(
                        {
                            "id": voice.id,
                            "name": voice.name,
                            "languages": voice.languages,
                            "gender": voice.gender,
                        }
                    )
            except:
                pass
        elif self._engine_type == TTSEngine.SAPI5 and self._engine:
            try:
                for voice in self._engine.GetVoices():
                    voices.append({"id": voice.Id, "name": voice.GetAttribute("Name")})
            except:
                pass

        return voices

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "engine": self._engine_type.value if self._engine_type else "none",
            "is_speaking": self._is_speaking,
            "rate": self._rate,
            "volume": self._volume,
        }

    def update_config(self, **kwargs):
        for key, value in kwargs.items():
            if key in ["rate", "volume", "voice_id"]:
                self.config[key] = value
                setattr(self, key, value)

        if self._engine:
            if self._engine_type == TTSEngine.PYTTSX3:
                if "rate" in kwargs:
                    self._engine.setProperty("rate", self._rate)
                if "volume" in kwargs:
                    self._engine.setProperty("volume", self._volume)

        logger.debug(f"[SoundManager] 配置已更新: {kwargs}")
