"""
多模态交互模块 - VoiceManager

核心功能：
1. ASR 语音识别 - 使用腾讯云ASR服务
2. TTS 语音合成 - 使用HTTP API服务
3. 音频播放 - 使用pygame或pyttsx3

灵感来源：memoryos-agent的tencent_asr.py和tts.py
"""

import base64
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np
import requests

try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    wave = None
    PYAUDIO_AVAILABLE = False

import os
import sys

# 抑制 pygame 的启动 banner
class _Suppressor:
    def __init__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        self._devnull = open(os.devnull, 'w')
    def __enter__(self):
        sys.stdout = sys.stderr = self._devnull
        return self
    def __exit__(self, *args):
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr
        self._devnull.close()

with _Suppressor():
    try:
        import pygame
        PYGAME_AVAILABLE = True
    except ImportError:
        pygame = None
        PYGAME_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    PYTTSX3_AVAILABLE = False

from loguru import logger
from utils.config_manager import config_manager


class VoiceManager:
    """语音管理器 - 整合ASR语音识别和TTS语音合成"""

    def __init__(self):
        """初始化语音管理器"""
        self._load_config()
        self._init_directories()
        self._tts_engine = None
        self._asr_client = None
        logger.debug("VoiceManager 初始化完成")

    def _load_config(self):
        """加载配置"""
        voice_config = config_manager.get("voice", {})
        
        self.enable_asr = voice_config.get("enable_asr", False)
        self.enable_tts = voice_config.get("enable_tts", True)
        self.tts_engine = voice_config.get("tts_engine", "pyttsx3")
        self.asr_engine = voice_config.get("asr_engine", "tencent")
        
        self.tencent_asr_secret_id = voice_config.get("tencent_asr_secret_id", "")
        self.tencent_asr_secret_key = voice_config.get("tencent_asr_secret_key", "")
        self.tencent_asr_engine = voice_config.get("tencent_asr_engine", "16k_zh")
        self.tencent_asr_hotwords = voice_config.get("tencent_asr_hotwords", "")
        self.tencent_asr_max_record_seconds = voice_config.get("tencent_asr_max_record_seconds", 30)
        
        self.remote_tts_url = voice_config.get("remote_tts_url", "")
        self.remote_tts_reference_id = voice_config.get("remote_tts_reference_id", "")
        
        self.audio_output_dir = Path(voice_config.get("audio_output_dir", "temp/audio"))

        self.chunk = 1024
        self.audio_format = pyaudio.paInt16 if PYAUDIO_AVAILABLE else None
        self.channels = 1
        self.rate = 16000
        self.silence_threshold = 500.0
        self.silence_duration = 1.2

    def _init_directories(self):
        """初始化目录"""
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)

    def _init_tts_engine(self):
        """初始化TTS引擎"""
        if self.tts_engine == "pyttsx3" and PYTTSX3_AVAILABLE:
            try:
                self._tts_engine = pyttsx3.init()
                voices = self._tts_engine.getProperty('voices')
                for voice in voices:
                    if 'Chinese' in voice.language or 'zh' in voice.language.lower():
                        self._tts_engine.setProperty('voice', voice.id)
                        break
                self._tts_engine.setProperty('rate', 150)
                logger.debug("pyttsx3 TTS引擎初始化完成")
            except Exception as e:
                logger.error(f"初始化pyttsx3失败: {e}")
                self._tts_engine = None

    def _init_asr_client(self):
        """初始化ASR客户端"""
        if self.asr_engine == "tencent":
            try:
                from tencentcloud.asr.v20190614 import asr_client, models
                from tencentcloud.common import credential
                from tencentcloud.common.profile.client_profile import ClientProfile
                from tencentcloud.common.profile.http_profile import HttpProfile
                
                cred = credential.Credential(
                    self.tencent_asr_secret_id, 
                    self.tencent_asr_secret_key
                )
                http_profile = HttpProfile()
                http_profile.endpoint = "asr.tencentcloudapi.com"
                
                client_profile = ClientProfile()
                client_profile.httpProfile = http_profile
                self._asr_client = asr_client.AsrClient(cred, "", client_profile)
                logger.debug("腾讯云ASR客户端初始化完成")
            except ImportError:
                logger.warning("未安装腾讯云SDK，ASR功能不可用")
            except Exception as e:
                logger.error(f"初始化腾讯云ASR客户端失败: {e}")

    def record_audio(self, max_seconds: int = None) -> Optional[Path]:
        """
        录音并保存为临时wav文件
        
        Args:
            max_seconds: 最大录音时长，默认使用配置值
        
        Returns:
            录音文件路径，失败返回None
        """
        if not PYAUDIO_AVAILABLE:
            logger.warning("未安装pyaudio，无法录音")
            return None

        max_seconds = max_seconds or self.tencent_asr_max_record_seconds
        filename = self.audio_output_dir / f"voice_input_{int(time.time() * 1000)}.wav"
        
        logger.info(f"🎙️ 开始录音（最长 {max_seconds} 秒）")

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
        )

        frames = []
        start_time = time.time()
        last_voice_time = start_time
        speech_started = False

        try:
            while True:
                data = stream.read(self.chunk, exception_on_overflow=False)
                frames.append(data)

                now = time.time()
                if now - start_time > max_seconds:
                    logger.info(f"⏱️ 已达到最大录音时长 {max_seconds} 秒")
                    break

                if self.audio_format is not None:
                    samples = np.frombuffer(data, dtype=np.int16)
                    if samples.size > 0:
                        level = float(np.mean(np.abs(samples)))
                        if level > self.silence_threshold:
                            if not speech_started:
                                speech_started = True
                                logger.info("🎙️ 检测到语音")
                            last_voice_time = now
                        elif speech_started and now - last_voice_time >= self.silence_duration:
                            logger.info("⏹️ 检测到持续静音，自动结束录音")
                            break
        except KeyboardInterrupt:
            logger.info("录音被中断")
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

        with wave.open(str(filename), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(audio.get_sample_size(self.audio_format))
            wf.setframerate(self.rate)
            wf.writeframes(b"".join(frames))

        if not speech_started:
            filename.unlink(missing_ok=True)
            logger.warning("未检测到语音输入")
            return None

        return filename

    def recognize_audio(self, audio_path: Path) -> Optional[str]:
        """
        识别音频文件中的语音
        
        Args:
            audio_path: 音频文件路径
        
        Returns:
            识别结果文本，失败返回None
        """
        if not self.enable_asr:
            logger.warning("ASR功能已禁用")
            return None

        if not audio_path or not audio_path.exists():
            logger.error("音频文件不存在")
            return None

        if self.asr_engine == "tencent":
            return self._recognize_tencent(audio_path)
        else:
            logger.error(f"不支持的ASR引擎: {self.asr_engine}")
            return None

    def _recognize_tencent(self, audio_path: Path) -> Optional[str]:
        """使用腾讯云ASR识别语音"""
        if not (self.tencent_asr_secret_id and self.tencent_asr_secret_key):
            logger.warning("未配置腾讯云ASR密钥")
            return None

        if self._asr_client is None:
            self._init_asr_client()

        try:
            from tencentcloud.asr.v20190614 import models

            base64_wav = base64.b64encode(audio_path.read_bytes())
            params = {
                "EngSerViceType": self.tencent_asr_engine,
                "SourceType": 1,
                "VoiceFormat": "wav",
                "Data": base64_wav.decode(),
            }

            if self.tencent_asr_hotwords:
                params["HotwordList"] = self.tencent_asr_hotwords

            req = models.SentenceRecognitionRequest()
            req.from_json_string(json.dumps(params))
            
            resp = self._asr_client.SentenceRecognition(req)
            message = json.loads(resp.to_json_string())
            result = message.get("Result")
            
            if result:
                logger.info(f"🎙️ 语音识别成功: {result[:30]}...")
            return result
        except Exception as e:
            logger.error(f"腾讯云ASR调用失败: {e}")
            return None

    def transcribe(self, max_seconds: int = None) -> Optional[str]:
        """
        录音并识别（完整流程）
        
        Args:
            max_seconds: 最大录音时长
        
        Returns:
            识别结果文本，失败返回None
        """
        t0 = time.time()
        
        audio_path = self.record_audio(max_seconds=max_seconds)
        if not audio_path:
            return None
        
        try:
            t1 = time.time()
            result = self.recognize_audio(audio_path)
            t2 = time.time()
            
            logger.info(f"⏱️ 录音耗时: {t1 - t0:.2f} 秒")
            logger.info(f"⏱️ 识别耗时: {t2 - t1:.2f} 秒")
            logger.info(f"⏱️ 总耗时: {t2 - t0:.2f} 秒")
            
            return result
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    def synthesize(self, text: str) -> Optional[Path]:
        """
        将文本合成为音频文件
        
        Args:
            text: 需要合成的文本
        
        Returns:
            音频文件路径，失败返回None
        """
        if not self.enable_tts:
            logger.debug("TTS功能已禁用")
            return None

        cleaned_text = self._strip_action_text(text)
        if not cleaned_text:
            logger.debug("文本仅包含动作提示，跳过合成")
            return None

        if self.tts_engine == "pyttsx3":
            return self._synthesize_pyttsx3(cleaned_text)
        elif self.tts_engine == "remote":
            return self._synthesize_remote(cleaned_text)
        else:
            logger.error(f"不支持的TTS引擎: {self.tts_engine}")
            return None

    def _strip_action_text(self, text: str) -> str:
        """去除动作提示文本"""
        cleaned = re.sub(r"[（(][^）)]*[）)]", "", text)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        return cleaned.strip()

    def _synthesize_pyttsx3(self, text: str) -> Optional[Path]:
        """使用pyttsx3合成语音"""
        if not PYTTSX3_AVAILABLE:
            logger.warning("未安装pyttsx3")
            return None

        if self._tts_engine is None:
            self._init_tts_engine()

        if self._tts_engine is None:
            return None

        try:
            filename = self.audio_output_dir / f"tts_{int(time.time() * 1000)}.wav"
            self._tts_engine.save_to_file(text, str(filename))
            self._tts_engine.runAndWait()
            logger.info(f"🔊 pyttsx3合成成功")
            return filename
        except Exception as e:
            logger.error(f"pyttsx3合成失败: {e}")
            return None

    def _synthesize_remote(self, text: str) -> Optional[Path]:
        """使用远程API合成语音"""
        if not self.remote_tts_url:
            logger.warning("未配置远程TTS URL")
            return None

        try:
            headers = {"accept": "*/*", "Content-Type": "application/json"}
            payload = {
                "text": text,
                "chunk_length": 200,
                "format": "mp3",
                "references": [],
                "reference_id": self.remote_tts_reference_id,
                "seed": None,
                "use_memory_cache": "on",
                "normalize": True,
                "streaming": False,
                "max_new_tokens": 1024,
                "top_p": 0.8,
                "repetition_penalty": 1.1,
                "temperature": 0.8,
            }

            response = requests.post(
                self.remote_tts_url, 
                headers=headers, 
                json=payload, 
                timeout=60
            )

            if response.status_code == 200:
                filename = self.audio_output_dir / f"tts_{int(time.time() * 1000)}.mp3"
                filename.write_bytes(response.content)
                logger.info(f"🔊 远程TTS合成成功")
                return filename
            else:
                logger.error(f"远程TTS失败: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"远程TTS请求失败: {e}")
            return None

    def play_audio(self, audio_path: Path, auto_cleanup: bool = True):
        """
        播放音频文件
        
        Args:
            audio_path: 音频文件路径
            auto_cleanup: 是否自动删除文件
        """
        if not audio_path or not audio_path.exists():
            logger.error("音频文件不存在")
            return

        if PYGAME_AVAILABLE:
            self._play_pygame(audio_path, auto_cleanup)
        else:
            self._play_simple(audio_path, auto_cleanup)

    def _play_pygame(self, audio_path: Path, auto_cleanup: bool):
        """使用pygame播放音频"""
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"pygame播放失败: {e}")
        finally:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            
            if auto_cleanup:
                try:
                    audio_path.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"清理音频文件失败: {e}")

    def _play_simple(self, audio_path: Path, auto_cleanup: bool):
        """使用简单方式播放音频"""
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(str(audio_path), winsound.SND_FILENAME)
            except Exception as e:
                logger.error(f"播放失败: {e}")
        else:
            logger.warning("无法播放音频，请安装pygame")
        
        if auto_cleanup:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    def speak(self, text: str, auto_play: bool = True) -> Optional[Path]:
        """
        文本转语音并播放（完整流程）
        
        Args:
            text: 需要合成的文本
            auto_play: 是否自动播放
        
        Returns:
            音频文件路径，失败返回None
        """
        t0 = time.time()
        audio_file = self.synthesize(text)
        t1 = time.time()
        
        if audio_file:
            logger.info(f"⏱️ TTS合成耗时: {t1 - t0:.2f} 秒")
            
            if auto_play:
                t2 = time.time()
                self.play_audio(audio_file)
                t3 = time.time()
                logger.info(f"⏱️ 播放耗时: {t3 - t2:.2f} 秒")
            
            return audio_file
        
        return None

    def is_asr_available(self) -> bool:
        """检查ASR是否可用"""
        return self.enable_asr and PYAUDIO_AVAILABLE and (
            (self.asr_engine == "tencent" and 
             self.tencent_asr_secret_id and 
             self.tencent_asr_secret_key)
        )

    def is_tts_available(self) -> bool:
        """检查TTS是否可用"""
        if not self.enable_tts:
            return False
        
        if self.tts_engine == "pyttsx3":
            return PYTTSX3_AVAILABLE
        elif self.tts_engine == "remote":
            return bool(self.remote_tts_url)
        
        return False


# 全局语音管理器实例
_voice_manager = None


def get_voice_manager() -> VoiceManager:
    """获取全局语音管理器实例"""
    global _voice_manager
    if _voice_manager is None:
        _voice_manager = VoiceManager()
    return _voice_manager