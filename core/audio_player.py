"""
音频播放器模块 - AudioPlayer

提供跨平台的音频播放功能，支持多种音频格式
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from loguru import logger


class AudioPlayer:
    """
    音频播放器 - 跨平台音频播放支持
    
    支持的平台:
    - Windows: winsound, powershell
    - macOS: afplay
    - Linux: aplay, paplay, ffplay
    """

    def __init__(self):
        """初始化音频播放器"""
        self._player = self._detect_player()
        logger.debug(f"音频播放器初始化完成，使用: {self._player}")

    def _detect_player(self) -> str:
        """检测可用的音频播放器"""
        if sys.platform == "win32":
            return "winsound"
        
        elif sys.platform == "darwin":
            return "afplay"
        
        elif sys.platform.startswith("linux"):
            if self._command_exists("paplay"):
                return "paplay"
            elif self._command_exists("aplay"):
                return "aplay"
            elif self._command_exists("ffplay"):
                return "ffplay"
            else:
                return "aplay"
        
        return "unknown"

    def _command_exists(self, cmd: str) -> bool:
        """检查命令是否存在"""
        try:
            subprocess.run(
                ["which", cmd] if sys.platform != "win32" else ["where", cmd],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def play(self, audio_path: Path, block: bool = True) -> bool:
        """
        播放音频文件
        
        Args:
            audio_path: 音频文件路径
            block: 是否阻塞播放（等待播放完成）
        
        Returns:
            是否播放成功
        """
        if not audio_path or not audio_path.exists():
            logger.error(f"音频文件不存在: {audio_path}")
            return False

        try:
            if self._player == "winsound":
                return self._play_winsound(audio_path)
            elif self._player == "afplay":
                return self._play_afplay(audio_path, block)
            elif self._player == "paplay":
                return self._play_paplay(audio_path, block)
            elif self._player == "aplay":
                return self._play_aplay(audio_path, block)
            elif self._player == "ffplay":
                return self._play_ffplay(audio_path, block)
            else:
                return self._play_fallback(audio_path, block)
        except Exception as e:
            logger.error(f"播放音频失败: {e}")
            return False

    def _play_winsound(self, audio_path: Path) -> bool:
        """使用winsound播放（Windows）"""
        try:
            import winsound
            winsound.PlaySound(str(audio_path), winsound.SND_FILENAME)
            return True
        except Exception as e:
            logger.error(f"winsound播放失败: {e}")
            return False

    def _play_afplay(self, audio_path: Path, block: bool) -> bool:
        """使用afplay播放（macOS）"""
        try:
            process = subprocess.Popen(
                ["afplay", str(audio_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if block:
                process.wait()
            
            return process.returncode == 0
        except Exception as e:
            logger.error(f"afplay播放失败: {e}")
            return False

    def _play_paplay(self, audio_path: Path, block: bool) -> bool:
        """使用paplay播放（PulseAudio）"""
        try:
            process = subprocess.Popen(
                ["paplay", str(audio_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if block:
                process.wait()
            
            return process.returncode == 0
        except Exception as e:
            logger.error(f"paplay播放失败: {e}")
            return False

    def _play_aplay(self, audio_path: Path, block: bool) -> bool:
        """使用aplay播放（ALSA）"""
        try:
            process = subprocess.Popen(
                ["aplay", str(audio_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if block:
                process.wait()
            
            return process.returncode == 0
        except Exception as e:
            logger.error(f"aplay播放失败: {e}")
            return False

    def _play_ffplay(self, audio_path: Path, block: bool) -> bool:
        """使用ffplay播放"""
        try:
            process = subprocess.Popen(
                ["ffplay", "-autoexit", "-nodisp", str(audio_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if block:
                process.wait()
            
            return process.returncode == 0
        except Exception as e:
            logger.error(f"ffplay播放失败: {e}")
            return False

    def _play_fallback(self, audio_path: Path, block: bool) -> bool:
        """回退播放方式"""
        try:
            if sys.platform == "win32":
                os.startfile(str(audio_path))
                return True
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.run([opener, str(audio_path)], check=True)
                return True
        except Exception as e:
            logger.error(f"回退播放失败: {e}")
            return False

    def play_bytes(self, audio_bytes: bytes, format: str = "wav") -> bool:
        """
        播放音频字节数据
        
        Args:
            audio_bytes: 音频字节数据
            format: 音频格式（wav, mp3等）
        
        Returns:
            是否播放成功
        """
        try:
            with tempfile.NamedTemporaryFile(
                suffix=f".{format}", 
                delete=False
            ) as f:
                f.write(audio_bytes)
                temp_path = Path(f.name)
            
            try:
                return self.play(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"播放音频字节失败: {e}")
            return False


# 全局音频播放器实例
_audio_player = None


def get_audio_player() -> AudioPlayer:
    """获取全局音频播放器实例"""
    global _audio_player
    if _audio_player is None:
        _audio_player = AudioPlayer()
    return _audio_player