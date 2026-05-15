import json
import time
from typing import Dict, List, Optional, Callable

import numpy as np


class MotionCurve:
    """动作曲线解析与播放"""

    def __init__(self, curve_data: dict):
        self.target = curve_data["Target"]
        self.parameter_id = curve_data["Id"]
        self.segments = curve_data["Segments"]
        self._parse_segments()

    def _parse_segments(self):
        self.keyframes = []
        data = self.segments

        i = 0
        while i < len(data):
            if i + 1 < len(data):
                start_time = data[i]
                start_value = data[i + 1]

                j = i + 2
                while j < len(data) and data[j] <= start_time:
                    j += 1

                if j + 1 < len(data):
                    end_time = data[j]
                    end_value = data[j + 1]
                    self.keyframes.append({
                        "start_time": start_time,
                        "start_value": start_value,
                        "end_time": end_time,
                        "end_value": end_value
                    })
                    i = j + 2
                else:
                    self.keyframes.append({
                        "start_time": start_time,
                        "start_value": start_value,
                        "end_time": start_time + 1.0,
                        "end_value": start_value
                    })
                    break
            else:
                break

    def get_value(self, time: float) -> float:
        """获取指定时间点的参数值"""
        if not self.keyframes:
            return 0.0

        for keyframe in self.keyframes:
            if keyframe["start_time"] <= time <= keyframe["end_time"]:
                t = (time - keyframe["start_time"]) / (keyframe["end_time"] - keyframe["start_time"])
                value = keyframe["start_value"] + t * (keyframe["end_value"] - keyframe["start_value"])
                return max(0.0, min(1.0, value / 10.0))

        return max(0.0, min(1.0, self.keyframes[-1]["end_value"] / 10.0))


class MotionPlayer:
    """动作播放器"""

    def __init__(self):
        self._curves: Dict[str, MotionCurve] = {}
        self._duration = 0.0
        self._start_time = 0.0
        self._is_playing = False
        self._is_looping = False
        self._on_end_callback: Optional[Callable] = None

    def load_motion(self, motion_path: str) -> bool:
        """加载动作文件，返回是否成功"""
        try:
            with open(motion_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._duration = data["Meta"].get("Duration", 0.0)

            self._curves = {}
            for curve_data in data.get("Curves", []):
                curve = MotionCurve(curve_data)
                self._curves[curve.parameter_id] = curve

            return True
        except Exception as e:
            from loguru import logger
            logger.error(f"[MotionPlayer] 加载动作失败: {e}")
            return False

    def play(self, loop: bool = False, on_end_callback: Optional[Callable] = None):
        """开始播放动作"""
        self._start_time = time.time()
        self._is_playing = True
        self._is_looping = loop
        self._on_end_callback = on_end_callback

    def stop(self):
        """停止播放"""
        self._is_playing = False

    def is_playing(self) -> bool:
        """是否正在播放"""
        return self._is_playing

    def get_current_values(self) -> Dict[str, float]:
        """获取当前时间点的所有参数值"""
        if not self._is_playing or not self._curves:
            return {}

        elapsed = time.time() - self._start_time

        if self._is_looping and self._duration > 0:
            elapsed = elapsed % self._duration

        if not self._is_looping and elapsed >= self._duration:
            self._is_playing = False
            if self._on_end_callback:
                self._on_end_callback()
            return {}

        values = {}
        for param_id, curve in self._curves.items():
            value = curve.get_value(elapsed)
            values[param_id] = value
            from loguru import logger
            logger.debug(f"[MotionPlayer] {param_id} = {value:.4f} (elapsed={elapsed:.4f})")

        return values

    def get_duration(self) -> float:
        """获取动作时长"""
        return self._duration
