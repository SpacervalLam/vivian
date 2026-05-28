"""桌面宠物主程序入口模块。"""

import json
import os
import sys
import time
import asyncio

import win32api
import win32con
import win32gui
from loguru import logger
from PyQt5.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt,
                          QTimer, pyqtSignal)
from PyQt5.QtGui import QBrush, QColor, QCursor, QFont, QIcon, QPainter, QPen, QConicalGradient
from PyQt5.QtWidgets import (QAction, QApplication, QGraphicsDropShadowEffect,
                             QInputDialog, QLabel, QMainWindow, QMenu,
                             QMessageBox, QPushButton, QSystemTrayIcon, 
                             QVBoxLayout, QWidget)

logger.remove()
if sys.stdout is not None:
    logger.add(
        sys.stdout,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {module} | {message}",
    )

class _StdoutSuppressor:
    def __init__(self):
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        self._devnull = open(os.devnull, 'w')

    def __enter__(self):
        sys.stdout = self._devnull
        sys.stderr = self._devnull
        return self

    def __exit__(self, *args):
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self._devnull.close()

with _StdoutSuppressor():
    import pygame
    import live2d.v3 as live2d

from PyQt5.QtCore import QThread, pyqtSignal, QThreadPool, QRunnable, QObject, pyqtSlot

import concurrent.futures
from functools import wraps
import threading

_ai_thread_pool = None
_ai_thread_pool_lock = threading.Lock()

def get_ai_thread_pool(max_workers=2):
    global _ai_thread_pool
    with _ai_thread_pool_lock:
        if _ai_thread_pool is None:
            _ai_thread_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="AIWorker"
            )
    return _ai_thread_pool

def ai_async(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            get_ai_thread_pool(),
            lambda: func(*args, **kwargs)
        )
    return wrapper

from core.ai_manager import AIManager
from core.brain import Brain
from core.pet_controller import PetController
from core.pet_status import get_pet_status_manager
from core.diary_system import get_diary_system
from engine.animation_manager import AnimationManager
from engine.expression_manager import ExpressionManager
from engine.resource_loader import ResourceLoader
from engine.state_machine import StateMachine
from sound_manager import SoundManager
from speech_recognition_manager import SpeechRecognitionManager
from ui.components.live2d_widget import Live2DWidget
from ui.components.enhanced_dock import EnhancedRightDock as RightDock
from ui.components.modern_input import MessageBubble, ModernInputDialog
from ui.config_window import AIConfigWindow
from ui.system_tray import SystemTray
from utils.config_manager import (AI_CONFIG, WINDOW_HEIGHT, WINDOW_TITLE,
                                  WINDOW_WIDTH, config_manager)
from utils.i18n import _, init_i18n


class AIWorkerSignals(QObject):
    """AIWorker信号类，用于跨线程通信"""
    response_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(Exception)
    thinking_signal = pyqtSignal(bool)  # 思考状态信号，True表示开始思考，False表示结束

class AIWorker(QRunnable):
    """后台工作者：采用单任务独立 Loop 隔离，彻底解决多线程 run_until_complete 冲突"""

    def __init__(self, brain, user_input):
        super().__init__()
        self.brain = brain
        self.user_input = user_input
        self.signals = AIWorkerSignals()
        self._is_cancelled = False
        self._chunk_buffer = []
        self._chunk_flush_threshold = 1
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        # 每次执行创建一个局部的、完全线程隔离的事件循环
        local_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(local_loop)
        try:
            # 发送开始思考信号
            self.signals.thinking_signal.emit(True)
            
            # 安全地在隔离环境内运行流式思考任务
            response_data = local_loop.run_until_complete(
                self.brain.athink(
                    self.user_input,
                    stream=True,
                    stream_callback=self._emit_stream_chunk,
                )
            )

            if self._is_cancelled:
                return

            # 刷新缓冲区中剩余的内容
            self._flush_buffer()

            if isinstance(response_data, dict):
                response_data = {"type": "final_response", **response_data}
            else:
                response_data = {
                    "type": "final_response",
                    "text": str(response_data),
                    "motion": "idle",
                    "expression": "smile",
                }

            self.signals.response_signal.emit(response_data)
        except Exception as e:
            logger.error(f"AIWorker 发生错误: {e}")
            self.signals.response_signal.emit(
                {
                    "type": "final_response",
                    "text": "脑子有点乱... (发生错误)",
                    "motion": "idle",
                    "expression": "angry",
                }
            )
        finally:
            # 发送结束思考信号
            self.signals.thinking_signal.emit(False)
            self.brain.is_thinking = False
            local_loop.close()  # 显式关闭，释放局部套接字及资源

    def _emit_stream_chunk(self, chunk):
        if chunk and not self._is_cancelled:
            logger.debug(f"[AIWorker._emit_stream_chunk] 接收到chunk，长度: {len(chunk)}, 当前buffer: {len(self._chunk_buffer)}")
            self._chunk_buffer.append(chunk)
            # 达到阈值时批量发送，减少信号传递开销
            if len(self._chunk_buffer) >= self._chunk_flush_threshold:
                self._flush_buffer()

    def _flush_buffer(self):
        if self._chunk_buffer:
            combined = ''.join(self._chunk_buffer)
            logger.debug(f"[AIWorker._flush_buffer] 发送stream_event，长度: {len(combined)}")
            self.signals.response_signal.emit({"type": "stream_event", "chunk": combined})
            self._chunk_buffer = []

    def cancel(self):
        """取消正在执行的任务"""
        self._is_cancelled = True

class AIRequestPrefetcher:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self._pending_input = ""
        self._prefetch_future = None
        self._prefetch_lock = asyncio.Lock()
        self._is_active = False
    
    def start_prefetch(self, partial_input):
        if not self._is_active:
            return
        
        self._pending_input = partial_input
        
        if self._prefetch_future and not self._prefetch_future.done():
            self._prefetch_future.cancel()
        
        loop = asyncio.new_event_loop()
        self._prefetch_future = loop.run_in_executor(
            get_ai_thread_pool(),
            self._prepare_prompt,
            partial_input
        )
    
    def _prepare_prompt(self, partial_input):
        import time
        time.sleep(0.1)
        return f"Prepared prompt for: {partial_input}"
    
    def get_prefetched_prompt(self):
        if self._prefetch_future and self._prefetch_future.done():
            try:
                return self._prefetch_future.result()
            except Exception:
                return None
        return None
    
    def stop(self):
        self._is_active = False
        if self._prefetch_future and not self._prefetch_future.done():
            self._prefetch_future.cancel()
    
    def start(self):
        self._is_active = True

ai_prefetcher = AIRequestPrefetcher()


from ui.toast_notification import ToastNotification


class AnimeBubble(QMainWindow):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.setText(text)

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_label = QLabel(text, self)

        self._setup_dynamic_properties()

        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.shadow = QGraphicsDropShadowEffect()
        self.text_label.setGraphicsEffect(self.shadow)

        layout.addWidget(self.text_label)

        self.anim_pos = None
        self.anim_opacity = None

        self.position_timer = QTimer(self)
        self.position_timer.setInterval(500)
        self.position_timer.timeout.connect(self._update_position)

        self.original_pos = None

        self._apply_dynamic_size()

        if self.parent_widget:
            self.parent_widget._original_resizeEvent = self.parent_widget.resizeEvent
            self.parent_widget.resizeEvent = self._on_parent_resize

    def _setup_dynamic_properties(self):
        self.width_ratio = 0.5 * 1.5
        self.font_ratio = 0.025 * 1.5
        self.padding_ratio = 0.015 * 1.5
        self.border_ratio = 0.005 * 1.5
        self.border_radius_ratio = 0.03 * 1.5
        self.shadow_ratio = 0.03 * 1.5

        self.min_width = int(150 * 1.5)
        self.max_width = int(350 * 1.5)
        self.min_font_size = int(10 * 1.5)
        self.max_font_size = int(20 * 1.5)
        self.min_padding = int(8 * 1.5)
        self.max_padding = int(20 * 1.5)
        self.min_border = int(1 * 1.5)
        self.max_border = int(3 * 1.5)
        self.min_border_radius = int(10 * 1.5)
        self.max_border_radius = int(25 * 1.5)
        self.min_shadow_blur = int(8 * 1.5)
        self.max_shadow_blur = int(25 * 1.5)

    def _calculate_dynamic_size(self):
        if not self.parent_widget:
            return {
                "width": 200,
                "font_size": 14,
                "padding": 12,
                "border": 2,
                "border_radius": 15,
                "shadow_blur": 15,
            }

        parent_width = self.parent_widget.width()
        parent_height = self.parent_widget.height()

        width = int(parent_width * self.width_ratio)
        font_size = int(parent_width * self.font_ratio)
        padding = int(parent_width * self.padding_ratio)
        border = int(parent_width * self.border_ratio)
        border_radius = int(parent_width * self.border_radius_ratio)
        shadow_blur = int(parent_width * self.shadow_ratio)

        width = max(self.min_width, min(self.max_width, width))
        font_size = max(self.min_font_size, min(self.max_font_size, font_size))
        padding = max(self.min_padding, min(self.max_padding, padding))
        border = max(self.min_border, min(self.max_border, border))
        border_radius = max(
            self.min_border_radius, min(self.max_border_radius, border_radius)
        )
        shadow_blur = max(self.min_shadow_blur, min(self.max_shadow_blur, shadow_blur))

        return {
            "width": width,
            "font_size": font_size,
            "padding": padding,
            "border": border,
            "border_radius": border_radius,
            "shadow_blur": shadow_blur,
        }

    def _apply_dynamic_size(self):
        dynamic_size = self._calculate_dynamic_size()

        self.text_label.setFixedWidth(dynamic_size["width"])

        style_sheet = f"""
            QLabel {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(189, 147, 249, 0.92),
                    stop: 0.35 rgba(139, 92, 252, 0.88),
                    stop: 0.65 rgba(168, 85, 247, 0.85),
                    stop: 1 rgba(192, 132, 252, 0.82)
                );
                border: 1px solid rgba(255, 255, 255, 0.35);
                border-radius: {dynamic_size['border_radius']}px;
                padding: {dynamic_size['padding']}px {int(dynamic_size['padding'] * 1.3)}px;
                color: rgba(255, 255, 255, 0.98);
                font-family: "Microsoft YaHei", "Segoe UI";
                font-size: {dynamic_size['font_size']}px;
                font-weight: 500;
                line-height: 1.6;
                
            }}
        """
        self.text_label.setStyleSheet(style_sheet)

        self.shadow.setBlurRadius(min(dynamic_size["shadow_blur"], 20))
        self.shadow.setColor(QColor(99, 40, 180, 60))
        shadow_offset = int(min(dynamic_size["shadow_blur"], 15) * 0.15)
        self.shadow.setOffset(max(shadow_offset, 0), max(shadow_offset * 2, 0))

        self.text_label.adjustSize()
        label_size = self.text_label.size()
        
        width = max(label_size.width(), 100)
        height = max(label_size.height(), 50)
        
        self.resize(width, height)

    def _on_parent_resize(self, event):
        if hasattr(self.parent_widget, "_original_resizeEvent"):
            self.parent_widget._original_resizeEvent(event)

        self._apply_dynamic_size()

        if self.isVisible():
            self._update_position()

    def setText(self, text):
        if hasattr(self, "text_label"):
            self.text_label.setText(text)
            self._apply_dynamic_size()
            if self.isVisible():
                self._update_position()

    def show(self):
        self.original_pos = self.pos()
        self.position_timer.start()
        super().show()
        self._fade_in()

    def hide(self):
        self.position_timer.stop()
        self._fade_out()

    def close(self):
        self.position_timer.stop()
        self._fade_out()

    def _fade_in(self):
        if (
            self.anim_opacity
            and self.anim_opacity.state() == QPropertyAnimation.Running
        ):
            self.anim_opacity.stop()

        self.anim_opacity = QPropertyAnimation(self, b"windowOpacity")
        self.anim_opacity.setDuration(300)
        self.anim_opacity.setStartValue(0.0)
        self.anim_opacity.setEndValue(1.0)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_opacity.start()

    def _fade_out(self):
        if (
            self.anim_opacity
            and self.anim_opacity.state() == QPropertyAnimation.Running
        ):
            self.anim_opacity.stop()

        self.anim_opacity = QPropertyAnimation(self, b"windowOpacity")
        self.anim_opacity.setDuration(300)
        self.anim_opacity.setStartValue(1.0)
        self.anim_opacity.setEndValue(0.0)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_opacity.finished.connect(super().close)
        self.anim_opacity.start()

    def _move_to(self, x, y, animate=True):
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        window_size = self.size()
        x = max(screen_geo.left(), min(x, screen_geo.right() - window_size.width()))
        y = max(screen_geo.top(), min(y, screen_geo.bottom() - window_size.height()))
        
        x = max(0, x)
        y = max(0, y)
        
        if animate:
            if self.anim_pos and self.anim_pos.state() == QPropertyAnimation.Running:
                self.anim_pos.stop()

            self.anim_pos = QPropertyAnimation(self, b"pos")
            self.anim_pos.setDuration(300)
            self.anim_pos.setStartValue(self.pos())
            self.anim_pos.setEndValue(QPoint(x, y))
            self.anim_pos.setEasingCurve(QEasingCurve.OutCubic)
            self.anim_pos.start()
        else:
            self.move(x, y)

    def _update_position(self):
        if not self.parent_widget or not self.isVisible():
            return

        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()

        pet_geo = self.parent_widget.geometry()
        pet_pos = self.parent_widget.pos()

        bubble_size = self.size()

        best_pos = self._calculate_best_position(
            screen_geo, pet_pos, pet_geo, bubble_size
        )

        if best_pos != self.pos():
            self._move_to(best_pos.x(), best_pos.y())

    def _calculate_best_position(self, screen_geo, pet_pos, pet_geo, bubble_size):
        candidate_positions = []

        x = pet_pos.x() + pet_geo.width() - 30
        y = pet_pos.y() + 50
        candidate_positions.append((x, y, "right_top"))

        x = pet_pos.x() - bubble_size.width() + 30
        y = pet_pos.y() + 50
        candidate_positions.append((x, y, "left_top"))

        x = pet_pos.x() + (pet_geo.width() - bubble_size.width()) // 2
        y = pet_pos.y() - bubble_size.height() - 10
        candidate_positions.append((x, y, "top_center"))

        x = pet_pos.x() + (pet_geo.width() - bubble_size.width()) // 2
        y = pet_pos.y() + pet_geo.height() + 10
        candidate_positions.append((x, y, "bottom_center"))

        x = pet_pos.x() + pet_geo.width() - 30
        y = pet_pos.y() + pet_geo.height() - bubble_size.height() - 50
        candidate_positions.append((x, y, "right_bottom"))

        x = pet_pos.x() - bubble_size.width() + 30
        y = pet_pos.y() + pet_geo.height() - bubble_size.height() - 50
        candidate_positions.append((x, y, "left_bottom"))

        for x, y, position_type in candidate_positions:
            bubble_rect = QRect(x, y, bubble_size.width(), bubble_size.height())

            if screen_geo.contains(bubble_rect):
                return QPoint(x, y)

        return self._fallback_position(screen_geo, bubble_size)

    def _fallback_position(self, screen_geo, bubble_size):
        x = screen_geo.center().x() - bubble_size.width() // 2
        y = screen_geo.center().y() - bubble_size.height() // 2

        x = max(screen_geo.left(), min(x, screen_geo.right() - bubble_size.width()))
        y = max(screen_geo.top(), min(y, screen_geo.bottom() - bubble_size.height()))

        return QPoint(x, y)

    def mousePressEvent(self, event):
        self.close()
        super().mousePressEvent(event)


class LoadingSpinner(QWidget):
    """旋转加载图标组件（可内置到父窗口）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(32, 32)
        self.move(10, 10)
        
        self._rotation = 0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(50)
        self._animation_timer.timeout.connect(self._update_rotation)
    
    def start(self):
        """开始旋转动画"""
        self._animation_timer.start()
        self.show()
    
    def stop(self):
        """停止旋转动画"""
        self._animation_timer.stop()
        self.hide()
    
    def _update_rotation(self):
        """更新旋转角度"""
        self._rotation += 10
        if self._rotation >= 360:
            self._rotation = 0
        self.update()
    
    def paintEvent(self, event):
        """绘制旋转加载图标"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        center = QPoint(self.width() // 2, self.height() // 2)
        radius = min(self.width(), self.height()) // 2 - 3
        
        painter.setPen(QPen(QColor(155, 89, 182, 50), 2))
        painter.drawEllipse(center, radius, radius)
        
        painter.save()
        painter.translate(center.x(), center.y())
        painter.rotate(self._rotation)
        
        gradient = QConicalGradient(0, 0, 0)
        gradient.setColorAt(0, QColor(155, 89, 182))
        gradient.setColorAt(0.7, QColor(155, 89, 182))
        gradient.setColorAt(1, QColor(155, 89, 182, 0))
        
        painter.setPen(QPen(QBrush(gradient), 2, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(-radius, -radius, radius * 2, radius * 2, 0, 270 * 16)
        
        painter.restore()


class DeskpetMainWindow(QMainWindow):
    ai_response_received = pyqtSignal(object)
    
    sig_speech_partial = pyqtSignal(str)
    sig_speech_final = pyqtSignal(str)
    sig_speech_started = pyqtSignal()
    sig_speech_stopped = pyqtSignal()
    sig_stream_event = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        self.current_bubble = None
        self.voice_base_text = "" 
        self.is_voice_recording = False
        self._has_streamed_content = False
        
        self._stream_buffer = ""
        self._stream_update_timer = None
        self._stream_update_interval = 30
        
        self._ui_update_queue = []
        self._ui_update_timer = None
        
        self._init_window_properties()
        self._init_signal_connections()
        self._init_ui_update_optimization()

    def _init_signal_connections(self):
        self.ai_response_received.connect(self._update_ui_with_ai_response)
        self.sig_speech_partial.connect(self._ui_on_partial_result)
        self.sig_speech_final.connect(self._ui_on_final_result)
        self.sig_speech_started.connect(self._ui_on_speech_started)
        self.sig_speech_stopped.connect(self._ui_on_speech_stopped)
        self.sig_stream_event.connect(self._ui_on_stream_event)
        
        # 思考状态计时器（备用）
        self._thinking_animation_timer = QTimer(self)
        self._thinking_animation_timer.setInterval(500)  # 每500ms更新一次
        self._thinking_dots_count = 0

    def _init_ui_update_optimization(self):
        self._stream_update_timer = QTimer(self)
        self._stream_update_timer.setSingleShot(True)
        self._stream_update_timer.setInterval(self._stream_update_interval)
        self._stream_update_timer.timeout.connect(self._flush_stream_buffer)
        
        self._ui_update_timer = QTimer(self)
        self._ui_update_timer.setSingleShot(True)
        self._ui_update_timer.setInterval(30)
        self._ui_update_timer.timeout.connect(self._process_ui_update_queue)

    def _queue_ui_update(self, update_func):
        self._ui_update_queue.append(update_func)
        if not self._ui_update_timer.isActive():
            self._ui_update_timer.start()

    def _process_ui_update_queue(self):
        while self._ui_update_queue:
            try:
                update_func = self._ui_update_queue.pop(0)
                update_func()
            except Exception as e:
                logger.error(f"处理UI更新队列失败: {e}")

    def _stream_update_direct(self, chunk):
        if not chunk:
            return
        
        self._has_streamed_content = True
        self._stream_buffer += chunk
        
        self._update_streaming_bubble(self._stream_buffer)
        
        if len(self._stream_buffer) > 50 and not self._stream_update_timer.isActive():
            self._stream_update_timer.start()
    
    def _reset_stream_state(self):
        self._stream_buffer = ""
        self._has_streamed_content = False

    def _extract_text_from_json_payload(self, payload: str) -> str:
        """从JSON负载中提取最合理的文本字段，避免直接显示原始JSON。"""
        try:
            import json
            data = json.loads(payload)
        except Exception:
            return ""

        def extract(obj):
            if isinstance(obj, dict):
                if isinstance(obj.get("text"), str) and obj.get("text").strip():
                    return obj.get("text").strip()
                if isinstance(obj.get("content"), str) and obj.get("content").strip():
                    return obj.get("content").strip()
                content = obj.get("content")
                if isinstance(content, list) and content:
                    for item in content:
                        if isinstance(item, dict):
                            text_value = extract(item)
                            if text_value:
                                return text_value
                        elif isinstance(item, str):
                            return item.strip()
                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        nested = extract(value)
                        if nested:
                            return nested
                return ""
            elif isinstance(obj, list):
                for item in obj:
                    text_value = extract(item)
                    if text_value:
                        return text_value
            return ""

        return extract(data)

    def _update_streaming_bubble(self, text):
        if not text:
            return
            
        if text.startswith('{') or text.startswith('['):
            extracted = self._extract_text_from_json_payload(text)
            if extracted:
                text = extracted
            else:
                logger.debug("[_update_streaming_bubble] JSON格式但无法提取text字段")
                return
            
        if hasattr(self, 'current_bubble') and self.current_bubble and self.current_bubble.isVisible():
            if hasattr(self.current_bubble, 'label') and hasattr(self.current_bubble, 'text'):
                self.current_bubble.text = text
                self.current_bubble.label.setText(text)
                self.current_bubble._calculate_size()
        else:
            text_length = len(text)
            duration_ms = max(5000, 5000 + (text_length // 50) * 1000)
            self._show_message_bubble(text, duration_ms=duration_ms)

    def _flush_stream_buffer(self):
        if self._stream_buffer:
            self._update_streaming_bubble(self._stream_buffer)

    def _init_window_properties(self):
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)

        self.live2d_widget = Live2DWidget(self)
        self.setCentralWidget(self.live2d_widget)

        self.drag_position = QPoint()
        self.is_dragging = False

        self._init_managers()
        self._init_system_tray()
        self._init_global_shortcut()

        self.auto_resize()

        self.message_bubble = None
        self.input_dialog = None
        self.child_windows = []
        self._last_ai_text = None
        self._last_ai_time = 0.0
        self._ai_response_signal_count = 0

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)

        self.current_bubble = None
        self.voice_base_text = ""

        self._init_right_dock()

    def _init_global_shortcut(self):
        try:
            import ctypes
            from ctypes import wintypes

            self.user32 = ctypes.windll.user32

            self.HOTKEY_ID_SHOW_INPUT = 101

            hwnd = int(self.winId())

            if self.user32.RegisterHotKey(
                hwnd, self.HOTKEY_ID_SHOW_INPUT, 0x0006, 0x41
            ):
                logger.info("全局热键 Ctrl+Shift+A 注册成功")
                self.hotkey_registered = True
            else:
                logger.error("无法注册全局热键 Ctrl+Shift+A")
                from PyQt5.QtGui import QKeySequence
                from PyQt5.QtWidgets import QShortcut

                self.shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
                self.shortcut.activated.connect(self._show_input_window)
                logger.info("已回退到使用 QShortcut 实现快捷键 Ctrl+Shift+A")
                self.hotkey_registered = False

            self._install_keyboard_hook()
        except Exception as e:
            logger.error(f"注册全局快捷键失败: {e}")
            from PyQt5.QtGui import QKeySequence
            from PyQt5.QtWidgets import QShortcut

            self.shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
            self.shortcut.activated.connect(self._show_input_window)
            logger.info("已回退到使用 QShortcut 实现快捷键 Ctrl+Shift+A")
            self.hotkey_registered = False

    def _install_keyboard_hook(self):
        try:
            import ctypes
            from ctypes import wintypes

            self.HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))

            self.ctrl_pressed = False
            self.shift_pressed = False
            self.a_pressed = False
            self.all_keys_pressed_time = 0
            self.voice_recognition_started = False

            from PyQt5.QtCore import QTimer
            self.hold_timer = QTimer(self)
            self.hold_timer.setSingleShot(True)
            self.hold_timer.setInterval(500)
            self.hold_timer.timeout.connect(self._on_hold_timeout)

            def keyboard_hook(nCode, wParam, lParam):
                if nCode >= 0:
                    keyboard_struct = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulonglong)).contents.value
                    vk_code = (keyboard_struct >> 16) & 0xFFFF

                    if vk_code == 162 or vk_code == 163:
                        if wParam == 256 or wParam == 260:
                            self.ctrl_pressed = True
                            self._check_all_keys_pressed()
                        elif wParam == 257 or wParam == 261:
                            self.ctrl_pressed = False
                            self._check_all_keys_released()
                    elif vk_code == 160 or vk_code == 161:
                        if wParam == 256 or wParam == 260:
                            self.shift_pressed = True
                            self._check_all_keys_pressed()
                        elif wParam == 257 or wParam == 261:
                            self.shift_pressed = False
                            self._check_all_keys_released()
                    elif vk_code == 65:
                        if wParam == 256 or wParam == 260:
                            self.a_pressed = True
                            self._check_all_keys_pressed()
                        elif wParam == 257 or wParam == 261:
                            self.a_pressed = False
                            self._check_all_keys_released()

                return self.user32.CallNextHookEx(self.hook_handle, nCode, wParam, lParam)

            self.keyboard_hook_func = self.HOOKPROC(keyboard_hook)

            self.hook_handle = self.user32.SetWindowsHookExA(13, self.keyboard_hook_func, None, 0)
            if self.hook_handle:
                logger.info("全局键盘钩子安装成功")
            else:
                logger.error("无法安装全局键盘钩子")
        except Exception as e:
            logger.error(f"安装全局键盘钩子失败: {e}")

    def _check_all_keys_pressed(self):
        if self.ctrl_pressed and self.shift_pressed and self.a_pressed:
            if not self.all_keys_pressed_time:
                import time
                self.all_keys_pressed_time = time.time()
                self.hold_timer.start()

    def _check_all_keys_released(self):
        if not (self.ctrl_pressed and self.shift_pressed and self.a_pressed):
            self.hold_timer.stop()
            self.all_keys_pressed_time = 0
            
            if self.voice_recognition_started:
                self._auto_send_voice_message()
                self.voice_recognition_started = False

    def _on_hold_timeout(self):
        import time
        if self.ctrl_pressed and self.shift_pressed and self.a_pressed:
            if time.time() - self.all_keys_pressed_time >= 0.5:
                self._auto_start_voice_recognition()

    def _auto_start_voice_recognition(self):
        self._show_input_window()
        
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._trigger_voice_button)

    def _trigger_voice_button(self):
        if hasattr(self, 'input_dialog') and self.input_dialog:
            for widget in self.input_dialog.findChildren(QPushButton):
                if widget.objectName() == "VoiceBtn":
                    widget.click()
                    self.voice_recognition_started = True
                    logger.info("自动启动语音识别")
                    break

    def _auto_send_voice_message(self):
        if hasattr(self, 'input_dialog') and self.input_dialog:
            for widget in self.input_dialog.findChildren(QPushButton):
                if widget.objectName() == "SendBtn":
                    widget.click()
                    logger.info("自动发送语音识别结果")
                    break

    def _init_managers(self):
        logger.debug("正在初始化 managers...")

        self._init_critical_managers()

        QTimer.singleShot(0, self._init_background_managers)

    def _init_critical_managers(self):
        logger.debug("正在初始化关键 managers...")

        try:
            self.resource_loader = ResourceLoader(
                os.path.dirname(os.path.abspath(__file__)), "Vivian"
            )
            self.resource_loader.load_critical()
            logger.debug("ResourceLoader(关键资源) 初始化完成")
        except Exception as e:
            logger.error(f"ResourceLoader 初始化失败: {e}")
            QMessageBox.critical(self, "错误", f"资源加载器初始化失败: {e}")
            sys.exit(1)

        try:
            self.expression_manager = ExpressionManager(self.resource_loader)
            self.expression_manager._main_window = self
            logger.debug("ExpressionManager 初始化完成")
        except Exception as e:
            logger.error(f"ExpressionManager 初始化失败: {e}")
            QMessageBox.critical(self, "错误", f"表情管理器初始化失败: {e}")
            sys.exit(1)

        try:
            self.animation_manager = AnimationManager(self.resource_loader)
            logger.debug("AnimationManager 初始化完成")
        except Exception as e:
            logger.error(f"AnimationManager 初始化失败: {e}")
            QMessageBox.critical(self, "错误", f"动画管理器初始化失败: {e}")
            sys.exit(1)

        try:
            self.state_machine = StateMachine(
                self.animation_manager, self.expression_manager, self.resource_loader
            )
            logger.debug("StateMachine 对象创建完成")
        except Exception as e:
            logger.error(f"StateMachine 初始化失败: {e}")
            QMessageBox.critical(self, "错误", f"状态机初始化失败: {e}")
            sys.exit(1)

        try:
            self.sound_manager = SoundManager({"enabled": False})
            logger.debug("SoundManager 初始化完成")
        except Exception as e:
            logger.error(f"SoundManager 初始化失败: {e}")
            QMessageBox.warning(self, "警告", f"声音管理器初始化失败: {e}")

        try:
            self.live2d_widget.set_managers(
                resource_loader=self.resource_loader,
                expression_manager=self.expression_manager,
                animation_manager=self.animation_manager,
                state_machine=self.state_machine,
                sound_manager=self.sound_manager,
            )

            if self.sound_manager.is_enabled():
                self.sound_manager.set_mouth_callback(self._on_tts_mouth_open)

            logger.debug("关键 managers 设置到widget完成")
        except Exception as e:
            logger.error(f"设置widget managers失败: {e}")
            QMessageBox.warning(self, "警告", f"设置部件管理器失败: {e}")

        try:
            self.pet_controller = PetController(self)
            logger.debug("PetController 初始化完成")
        except Exception as e:
            logger.error(f"PetController 初始化失败: {e}")
            QMessageBox.warning(self, "警告", f"宠物控制器初始化失败: {e}")

    def _init_background_managers(self):
        logger.debug("正在初始化后台 managers...")

        try:
            self.resource_loader.load_background()
            logger.debug("ResourceLoader(完整资源) 加载完成")
        except Exception as e:
            logger.error(f"ResourceLoader 完整资源加载失败: {e}")

        try:
            self.state_machine.start()
            logger.debug("StateMachine 启动完成")
        except Exception as e:
            logger.error(f"StateMachine 启动失败: {e}")

        ai_config = config_manager.get("ai")

        try:
            self.ai_manager = AIManager(ai_config)
            self._setup_idle_action_callback()
            logger.debug("AIManager 初始化完成")
        except Exception as e:
            logger.error(f"AIManager 初始化失败: {e}")
            QMessageBox.warning(self, "警告", f"AI管理器初始化失败: {e}")

        try:
            self.brain = Brain(self.ai_manager)

            self.brain.max_short_term_memory = config_manager.get(
                "memory.max_short_term_memory"
            )
            self.brain.memory_importance_threshold = config_manager.get(
                "memory.memory_importance_threshold"
            )

            logger.debug("Brain 初始化完成")
        except Exception as e:
            import traceback
            logger.error(f"Brain 初始化失败: {e}")
            logger.error(traceback.format_exc())
            QMessageBox.warning(self, "警告", f"AI大脑初始化失败: {e}")

        try:
            from core.scheduler import init_scheduler
            self.scheduler = init_scheduler(callback=self._on_scheduler_event)
            logger.debug("Scheduler 初始化完成")
        except Exception as e:
            logger.error(f"Scheduler 初始化失败: {e}")

        # 初始化心情状态系统
        try:
            self.pet_status_manager = get_pet_status_manager()
            self.pet_status_manager.set_callback(self._on_pet_status_change)
            logger.debug("PetStatusManager 初始化完成")
        except Exception as e:
            logger.error(f"PetStatusManager 初始化失败: {e}")

        # 初始化日记系统
        try:
            self.diary_system = get_diary_system()
            self.diary_system.set_dependencies(
                ai_manager=self.ai_manager,
                status_manager=self.pet_status_manager,
                memory_manager=self.brain.memory_manager if hasattr(self.brain, 'memory_manager') else None
            )
            self.diary_system.set_callback(self._on_diary_created)
            logger.debug("DiarySystem 初始化完成")
        except Exception as e:
            logger.error(f"DiarySystem 初始化失败: {e}")

        # 将状态管理器设置到AI管理器
        if hasattr(self, 'ai_manager') and hasattr(self, 'pet_status_manager'):
            self.ai_manager.set_status_manager(self.pet_status_manager)
            logger.debug("状态管理器已关联到AI管理器")

        logger.info("所有 managers 初始化完成")

    def _setup_idle_action_callback(self):
        """设置AI空闲动作回调"""
        import random
        
        def on_idle_action():
            try:
                if hasattr(self, 'expression_manager') and self.expression_manager:
                    expressions = ["shy", "eye_roll", "umbrella_close"]
                    expr = random.choice(expressions)
                    self.expression_manager.set_expression(expr, duration_ms=2000)
                    logger.debug(f"[IdleAction] Triggered expression: {expr}")
            except Exception as e:
                logger.debug(f"[IdleAction] Failed to trigger expression: {e}")
        
        if hasattr(self, 'ai_manager') and self.ai_manager:
            self.ai_manager.set_idle_action_callback(on_idle_action)

    def _on_tts_mouth_open(self, value: float):
        if hasattr(self.live2d_widget, "target_mouth_open"):
            self.live2d_widget.target_mouth_open = value

    def _on_pet_status_change(self, event_data):
        """处理宠物状态变化事件"""
        event_type = event_data.get("type")
        
        if event_type == "action":
            action = event_data.get("action")
            expression = event_data.get("expression")
            
            if expression and hasattr(self, 'expression_manager'):
                self.expression_manager.set_expression(expression, duration_ms=2000)
                logger.debug(f"[_on_pet_status_change] 设置表情: {expression}")
            
            if action:
                logger.debug(f"[_on_pet_status_change] 收到动作指令: {action}")

    def _on_diary_created(self, event_data):
        """处理日记创建事件"""
        event_type = event_data.get("type")
        
        if event_type == "diary_created":
            entry = event_data.get("entry")
            if entry:
                date = entry.get("date")
                logger.info(f"[_on_diary_created] 新日记已创建: {date}")
                ToastNotification.show_notification("📝 薇薇安写了一篇新日记！", self)

    def _on_scheduler_event(self, event_data: dict):
        event_type = event_data.get("type")
        
        if event_type == "reminder":
            message = event_data.get("message", "")
            if message:
                self.show_message_bubble(message)
                
        elif event_type == "tool_result":
            tool_name = event_data.get("tool_name", "")
            success = event_data.get("success", False)
            result = event_data.get("result", "")
            msg = f"定时任务执行完成: {tool_name}"
            if not success:
                msg += f" (失败: {result})"
            self.show_message_bubble(msg)

    def _init_context_menu(self):
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.context_menu = QMenu(self)

        self.show_action = QAction("显示", self)
        self.show_action.triggered.connect(self.show)

        self.hide_action = QAction("隐藏", self)
        self.hide_action.triggered.connect(self.hide)

        self.ai_toggle_action = QAction("AI 对话", self)
        self.ai_toggle_action.setCheckable(True)
        self.ai_toggle_action.setChecked(False)
        self.ai_toggle_action.triggered.connect(self._toggle_ai_dialog)

        self.sound_toggle_action = QAction("语音开关", self)
        self.sound_toggle_action.setCheckable(True)
        self.sound_toggle_action.setChecked(False)
        self.sound_toggle_action.triggered.connect(self._toggle_sound)

        self.clear_memories_action = QAction("清除所有记忆", self)
        self.clear_memories_action.triggered.connect(self._clear_all_memories)

        self.quit_action = QAction("退出", self)
        self.quit_action.triggered.connect(self.close)

        self.context_menu.addSeparator()
        self.context_menu.addAction(self.show_action)
        self.context_menu.addAction(self.hide_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.ai_toggle_action)
        self.context_menu.addAction(self.sound_toggle_action)
        self.context_menu.addAction(self.clear_memories_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.quit_action)

    def _init_system_tray(self):
        self.system_tray = SystemTray(self)

        self.system_tray.tray_menu.clear()
        
        self.tray_memory_visualization_action = QAction(_("memory_management"), self)
        self.tray_memory_visualization_action.triggered.connect(
            self._show_memory_visualization
        )
        self.system_tray.tray_menu.addAction(self.tray_memory_visualization_action)
        
        self.settings_action = QAction(_("settings"), self)
        self.settings_action.triggered.connect(self.system_tray.on_settings)
        self.system_tray.tray_menu.addAction(self.settings_action)
        
        self.quit_action = QAction(_("quit"), self)
        self.quit_action.triggered.connect(self.close)
        self.system_tray.tray_menu.addAction(self.quit_action)

        self.system_tray.show()
        
    def _init_right_dock(self):
        self.right_dock = RightDock(self)
        
        self.right_dock.settings_clicked.connect(self.system_tray.on_settings)
        self.right_dock.memory_clicked.connect(self._show_memory_visualization)
        self.right_dock.quit_clicked.connect(self.close)

    def _show_memory_visualization(self):
        from ui.memory_visualization_window import MemoryVisualizationWindow

        time_stamped_memory = None
        if hasattr(self.brain, 'chat_chain') and self.brain.chat_chain:
            time_stamped_memory = getattr(self.brain.chat_chain, 'time_stamped_memory', None)
            
        self.memory_visualization_window = MemoryVisualizationWindow(self.brain.memory_manager, time_stamped_memory)
        self.memory_visualization_window.show()
        self.child_windows.append(self.memory_visualization_window)

    def show_context_menu(self, pos):
        self.context_menu.exec_(self.mapToGlobal(pos))

    def auto_resize(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()

        base_height = screen_geometry.height() // 3
        base_width = int(base_height * 0.8)

        new_width = int(base_width * 0.7)
        new_height = int(base_height * 0.85)

        new_width = max(new_width, 250)
        new_height = max(new_height, 350)

        self.resize(new_width, new_height)

        self.move(
            screen_geometry.width() - new_width - 50,
            screen_geometry.height() - new_height - 50,
        )

    def nativeEvent(self, eventType, message):
        import ctypes
        from ctypes import wintypes

        WM_HOTKEY = 0x0312

        msg = wintypes.MSG.from_address(message.__int__())

        if msg.message == WM_HOTKEY:
            if (
                hasattr(self, "HOTKEY_ID_SHOW_INPUT")
                and msg.wParam == self.HOTKEY_ID_SHOW_INPUT
            ):
                self._show_input_window()
                return True, 0

        return super().nativeEvent(eventType, message)

    def mousePressEvent(self, event):
        if hasattr(self.live2d_widget, "is_asleep") and self.live2d_widget.is_asleep:
            self.live2d_widget.set_asleep(False)
            self.expression_manager.set_expression(
                "shy", duration_ms=3000
            )
            logger.info("薇薇安被点击唤醒了！")

        if event.button() == Qt.LeftButton:
            widget_pos = self.live2d_widget.mapFromParent(event.pos())
            is_in_model = self.live2d_widget.is_in_model_area(widget_pos)

            if is_in_model:
                clicked_area = self.live2d_widget.detect_interaction_area(widget_pos)
                self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                self.is_dragging = True
                
                if hasattr(self, 'brain') and hasattr(self.brain, 'local_proactive_service') and self.brain.local_proactive_service:
                    self.brain.local_proactive_service.on_drag_start()
                
                self.live2d_widget.handle_click(widget_pos)
                
                # 更新心情状态
                if hasattr(self, 'pet_status_manager'):
                    self.pet_status_manager.record_click()
            else:
                hwnd = win32gui.GetParent(self.winId()) if self.winId() else 0
                if hwnd:
                    original_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                    win32gui.SetWindowLong(
                        hwnd,
                        win32con.GWL_EXSTYLE,
                        original_style | win32con.WS_EX_TRANSPARENT,
                    )
                    win32gui.SendMessage(
                        hwnd,
                        win32con.WM_LBUTTONDOWN,
                        win32con.MK_LBUTTON,
                        win32api.MAKELONG(event.pos().x(), event.pos().y()),
                    )
                    win32gui.SendMessage(
                        hwnd,
                        win32con.WM_LBUTTONUP,
                        0,
                        win32api.MAKELONG(event.pos().x(), event.pos().y()),
                    )
                    win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, original_style)
        elif event.button() == Qt.RightButton:
            pass

    def mouseMoveEvent(self, event):
        if self.is_dragging and (event.buttons() & Qt.LeftButton):
            old_pos = self.pos()
            self.move(event.globalPos() - self.drag_position)
            new_pos = self.pos()
            
            if hasattr(self, 'brain') and hasattr(self.brain, 'local_proactive_service') and self.brain.local_proactive_service:
                distance = abs(new_pos.x() - old_pos.x()) + abs(new_pos.y() - old_pos.y())
                if distance > 0:
                    self.brain.local_proactive_service.on_drag_move(distance)
            
            if (
                not hasattr(self, "_drag_expression_set")
                or not self._drag_expression_set
            ):
                if self.expression_manager.get_current_expression() != "eye_roll":
                    self.expression_manager.set_expression("panic", duration_ms=None)
                self._drag_expression_set = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            
            if hasattr(self, 'brain') and hasattr(self.brain, 'local_proactive_service') and self.brain.local_proactive_service:
                self.brain.local_proactive_service.on_drag_end()
            
            if hasattr(self, "_drag_expression_set") and self._drag_expression_set:
                self.expression_manager.reset_expression()
                self._drag_expression_set = False
                
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "right_dock"):
            self.right_dock.adjust_to_screen()

    def _toggle_ai_dialog(self):
        if not hasattr(self, "_ai_dialog_open") or not self._ai_dialog_open:
            self._show_ai_dialog()

    def _clear_all_memories(self):
        from PyQt5.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "确认清除",
            "确定要清除所有记忆吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                self.brain.memory_manager.clear_all_memories()
                ToastNotification.show_notification("所有记忆已成功清除", self)
            except Exception as e:
                ToastNotification.show_notification(
                    f"清除记忆时发生错误: {str(e)}", self
                )

    def _show_input_window(self):
        from PyQt5.QtCore import (QEasingCurve, QPoint, QPropertyAnimation,
                                  QRect, Qt, pyqtSignal)
        from PyQt5.QtGui import QColor, QCursor, QFont, QKeyEvent, QKeySequence
        from PyQt5.QtWidgets import (QDialog, QFrame,
                                     QGraphicsDropShadowEffect, QHBoxLayout,
                                     QLineEdit, QPushButton, QShortcut,
                                     QVBoxLayout)

        if self.input_dialog and self.input_dialog.isVisible():
            self.input_dialog.activateWindow()
            self.input_dialog.raise_()
            return

        input_dialog = QDialog(None)
        input_dialog.setWindowTitle("与薇薇安对话")
        input_dialog.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        input_dialog.setAttribute(Qt.WA_TranslucentBackground, True)

        width = 500
        height = 80
        input_dialog.setFixedSize(width, height + 20)

        container = QFrame(input_dialog)
        container.setGeometry(10, 10, width - 20, height)

        style_sheet = """ 
            QFrame#Container { 
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                                      stop:0 rgba(23, 25, 35, 0.95), 
                                      stop:1 rgba(30, 35, 45, 0.90)); 
                border: 1px solid rgba(255, 255, 255, 0.15); 
                border-radius: 40px; 
            } 
            
            QLineEdit { 
                background: transparent; 
                border: none; 
                color: #FFFFFF;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif; 
                font-size: 18px;
                font-weight: 500;
                padding: 0 5px; 
                
                selection-background-color: #00ADB5;
                selection-color: #FFFFFF;
            } 
            
            QLineEdit::placeholder { 
                color: rgba(255, 255, 255, 0.4); 
                font-style: italic; 
            } 

            QPushButton#SendBtn { 
                background-color: transparent; 
                border: none; 
                border-radius: 20px; 
                color: rgba(255, 255, 255, 0.6); 
                font-weight: bold; 
                font-size: 20px; 
            } 
            QPushButton#SendBtn:hover { 
                background-color: rgba(255, 255, 255, 0.1); 
                color: #00ADB5;
            } 
            QPushButton#SendBtn:pressed {
                background-color: rgba(0, 173, 181, 0.2);
            }
            
            QPushButton#VoiceBtn {
                background-color: transparent;
                border: none;
                border-radius: 20px;
                color: rgba(255, 255, 255, 0.6);
                font-weight: bold;
                font-size: 20px;
            }
            QPushButton#VoiceBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: #00ADB5;
            }
            QPushButton#VoiceBtn:pressed {
                background-color: rgba(0, 173, 181, 0.2);
            }
            QPushButton#VoiceBtn.recording {
                color: #FF4757;
            }
        """
        container.setObjectName("Container")
        container.setStyleSheet(style_sheet)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(25, 5, 10, 5)
        layout.setSpacing(10)

        class CustomLineEdit(QLineEdit):
            def keyPressEvent(self, event):
                if event.key() == Qt.Key_Up:
                    self.setCursorPosition(0)
                elif event.key() == Qt.Key_Down:
                    self.setCursorPosition(len(self.text()))
                else:
                    super().keyPressEvent(event)

        ai_input = CustomLineEdit()
        ai_input.setPlaceholderText(_("say_something"))
        ai_input.setFixedHeight(40)
        layout.addWidget(ai_input)
        self.ai_input = ai_input

        voice_btn = QPushButton()
        voice_btn.setObjectName("VoiceBtn")
        voice_btn.setFixedSize(40, 40)
        voice_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.voice_btn = voice_btn
        
        from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPainterPath
        from PyQt5.QtCore import QSize, Qt
        
        def create_mic_icon(size=32, color=QColor(255, 255, 255)):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            p = QPainter(pixmap)
            p.setRenderHint(QPainter.Antialiasing)

            p.setPen(Qt.NoPen)
            p.setBrush(color)

            center_x = size // 2

            body_width = int(size * 0.28)
            body_height = int(size * 0.45)
            body_x = int(center_x - body_width / 2)
            body_y = int(size * 0.18)

            body_radius = body_width / 2

            body_path = QPainterPath()
            body_path.addRoundedRect(
                body_x,
                body_y,
                body_width,
                body_height,
                body_radius,
                body_radius
            )
            p.drawPath(body_path)

            stand_width = int(size * 0.55)
            stand_height = int(size * 0.35)
            stand_x = int(center_x - stand_width / 2)
            stand_y = int(body_y + body_height - size * 0.05)

            stand_path = QPainterPath()
            stand_path.moveTo(stand_x, stand_y)
            stand_path.arcTo(
                stand_x,
                stand_y,
                stand_width,
                stand_height,
                0,
                -180
            )

            p.drawPath(stand_path)

            stem_width = int(size * 0.08)
            stem_height = int(size * 0.15)
            stem_x = int(center_x - stem_width / 2)
            stem_y = int(stand_y + stand_height * 0.6)

            p.drawRoundedRect(
                stem_x,
                stem_y,
                stem_width,
                stem_height,
                stem_width / 2,
                stem_width / 2
            )

            base_width = int(size * 0.35)
            base_height = int(size * 0.07)
            base_x = int(center_x - base_width / 2)
            base_y = int(stem_y + stem_height + size * 0.02)

            p.drawRoundedRect(
                base_x,
                base_y,
                base_width,
                base_height,
                base_height / 2,
                base_height / 2
            )

            p.end()
            return pixmap
        
        mic_pixmap = create_mic_icon(32, QColor(255, 255, 255))
        voice_btn.setIcon(QIcon(mic_pixmap))
        voice_btn.setIconSize(QSize(20, 20))
        
        voice_btn.setStyleSheet("""
        QPushButton#VoiceBtn {
            background-color: transparent;
            border: none;
            border-radius: 20px;
            color: white;
        }
        
        QPushButton#VoiceBtn:hover {
            background-color: rgba(255, 255, 255, 0.1);
        }
        
        QPushButton#VoiceBtn:pressed {
            background-color: rgba(255, 255, 255, 0.2);
        }
        
        QPushButton#VoiceBtn.recording {
            background-color: rgba(46, 124, 246, 0.8);
            color: white;
        }
        
        QPushButton#VoiceBtn.recording:hover {
            background-color: rgba(46, 124, 246, 0.9);
        }
        """)
        
        layout.addWidget(voice_btn)

        send_btn = QPushButton("➤")
        send_btn.setObjectName("SendBtn")
        send_btn.setFixedSize(40, 40)
        send_btn.setCursor(QCursor(Qt.PointingHandCursor))
        layout.addWidget(send_btn)

        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        container.setGraphicsEffect(shadow)

        is_sending = False

        def send_message_debounced():
            nonlocal is_sending
            if is_sending:
                logger.debug("[send_message_debounced] already sending, ignoring")
                return

            is_sending = True
            logger.debug("[send_message_debounced] start sending")

            user_input = getattr(self, "_pending_user_input", "").strip()
            if not user_input:
                is_sending = False
                return

            if hasattr(self, 'brain') and hasattr(self.brain, 'local_proactive_service') and self.brain.local_proactive_service:
                self.brain.local_proactive_service.on_user_input()

            # 记录用户交互到心情状态系统
            if hasattr(self, 'pet_status_manager'):
                self.pet_status_manager.record_interaction(user_input)

            if hasattr(self, "_pending_user_input"):
                delattr(self, "_pending_user_input")

            send_btn.setEnabled(False)
            ai_input.setEnabled(False)

            anim_close = QPropertyAnimation(input_dialog, b"windowOpacity")
            anim_close.setDuration(200)
            anim_close.setStartValue(1.0)
            anim_close.setEndValue(0.0)

            def on_close_finished():
                input_dialog.close()
                send_btn.setEnabled(True)
                ai_input.setEnabled(True)

            anim_close.finished.connect(on_close_finished)
            anim_close.start()

            input_dialog.anim_close = anim_close

            if (
                hasattr(self.live2d_widget, "is_asleep")
                and self.live2d_widget.is_asleep
            ):
                self.live2d_widget.set_asleep(False)
                logger.info("薇薇安被消息唤醒了！")

            self._reset_stream_state()

            worker = AIWorker(self.brain, user_input)
            
            worker.signals.response_signal.connect(self._on_ai_response_from_worker)
            worker.signals.thinking_signal.connect(self._on_thinking_state_changed)
            
            if not hasattr(self, '_active_workers'):
                self._active_workers = []
                self._active_workers_lock = threading.Lock()
            with self._active_workers_lock:
                self._active_workers.append(worker)
            
            def cleanup_worker():
                with self._active_workers_lock:
                    if worker in self._active_workers:
                        self._active_workers.remove(worker)
            worker.signals.response_signal.connect(cleanup_worker)
            
            if not hasattr(self, '_ai_thread_pool'):
                self._ai_thread_pool = QThreadPool.globalInstance()
                self._ai_thread_pool.setMaxThreadCount(2)
            self._ai_thread_pool.start(worker)
            
            is_sending = False

        def send_message():
            user_input = ai_input.text().strip()
            if not user_input:
                return

            self._pending_user_input = user_input

            ai_input.setText("")

            logger.debug("[send_message] debounce timer started")
            try:
                self._debounce_timer.timeout.disconnect()
            except TypeError:
                pass
            self._debounce_timer.timeout.connect(send_message_debounced)
            self._debounce_timer.start()

        def close_dialog():
            anim_out = QPropertyAnimation(input_dialog, b"windowOpacity")
            anim_out.setDuration(150)
            anim_out.setStartValue(1.0)
            anim_out.setEndValue(0.0)
            anim_out.finished.connect(input_dialog.close)
            anim_out.start()
            input_dialog.anim_out = anim_out

        def on_dialog_closed():
            self.input_dialog = None

        ai_input.returnPressed.connect(send_message)
        send_btn.clicked.connect(send_message)

        esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), input_dialog)
        esc_shortcut.activated.connect(close_dialog)

        input_dialog.finished.connect(on_dialog_closed)
        input_dialog.destroyed.connect(on_dialog_closed)

        def thread_safe_partial(text):
            self.sig_speech_partial.emit(text)

        def thread_safe_final(text):
            self.sig_speech_final.emit(text)

        speech_manager = SpeechRecognitionManager(
            partial_result_callback=thread_safe_partial,
            final_result_callback=thread_safe_final
        )
        
        is_recording = False
        pulse_anim = None
        glow_effect = None
        
        def set_recording_state(recording: bool):
            nonlocal is_recording, pulse_anim, glow_effect
            is_recording = recording
            
            if recording:
                voice_btn.setProperty("class", "VoiceBtn recording")
                voice_btn.setStyleSheet("""
                QPushButton#VoiceBtn {
                    background-color: transparent;
                    border: none;
                    border-radius: 20px;
                    color: white;
                }
                
                QPushButton#VoiceBtn:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                }
                
                QPushButton#VoiceBtn:pressed {
                    background-color: rgba(255, 255, 255, 0.2);
                }
                
                QPushButton#VoiceBtn.recording {
                    background-color: rgba(46, 124, 246, 0.8);
                    color: white;
                }
                
                QPushButton#VoiceBtn.recording:hover {
                    background-color: rgba(46, 124, 246, 0.9);
                }
                """)
                
                self._start_btn_animation(voice_btn)
                logger.info("语音识别已启动")
            else:
                voice_btn.setProperty("class", "VoiceBtn")
                voice_btn.setStyleSheet("""
                QPushButton#VoiceBtn {
                    background-color: transparent;
                    border: none;
                    border-radius: 20px;
                    color: white;
                }
                
                QPushButton#VoiceBtn:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                }
                
                QPushButton#VoiceBtn:pressed {
                    background-color: rgba(255, 255, 255, 0.2);
                }
                
                QPushButton#VoiceBtn.recording {
                    background-color: rgba(46, 124, 246, 0.8);
                    color: white;
                }
                
                QPushButton#VoiceBtn.recording:hover {
                    background-color: rgba(46, 124, 246, 0.9);
                }
                """)
                
                self._stop_btn_animation(voice_btn)
                logger.info("语音识别已停止")
        
        import threading

        async def start_recognition():
            nonlocal is_recording
            current_txt = ai_input.text()
            if current_txt and not current_txt.endswith(" "):
                self.voice_base_text = current_txt + " "
            else:
                self.voice_base_text = current_txt

            try:
                success = await speech_manager.start_recognition()
                if success:
                    self.sig_speech_started.emit()
                else:
                    self.sig_speech_stopped.emit()
            except Exception as e:
                logger.error(f"启动语音识别失败: {e}")
                self.sig_speech_stopped.emit()

        async def stop_recognition():
            try:
                await speech_manager.stop_recognition()
                self.sig_speech_stopped.emit()
            except Exception as e:
                logger.error(f"停止语音识别失败: {e}")
            finally:
                set_recording_state(False)

        def _run_coroutine_in_thread(coro_func):
            def _target():
                try:
                    asyncio.run(coro_func())
                except Exception as e:
                    logger.exception(f"Recognition background thread exception: {e}")

            t = threading.Thread(target=_target, daemon=True)
            t.start()
            return t

        def toggle_recognition():
            nonlocal is_recording
            if is_recording:
                _run_coroutine_in_thread(stop_recognition)
            else:
                set_recording_state(True)
                self.sig_speech_started.emit()
                _run_coroutine_in_thread(start_recognition)

        voice_btn.clicked.connect(toggle_recognition)

        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()

        target_x = (screen_geo.width() - width) // 2
        target_y = (
            screen_geo.height() - height
        ) // 2 + 100

        input_dialog.move(target_x, target_y + 30)

        def on_focus_change(event):
            if event.gotFocus:
                shadow.setColor(QColor(0, 173, 181, 100))
                shadow.setBlurRadius(30)
            elif event.lostFocus:
                shadow.setColor(QColor(0, 0, 0, 80))
                shadow.setBlurRadius(20)

        def focus_in_event(e):
            QLineEdit.focusInEvent(ai_input, e)
            shadow.setColor(QColor(0, 173, 181, 120))
            shadow.setBlurRadius(35)

        def focus_out_event(e):
            QLineEdit.focusOutEvent(ai_input, e)
            shadow.setColor(QColor(0, 0, 0, 80))
            shadow.setBlurRadius(20)

        ai_input.focusInEvent = focus_in_event
        ai_input.focusOutEvent = focus_out_event

        self.input_dialog = input_dialog

        input_dialog.setWindowOpacity(0.0)

        anim_fade = QPropertyAnimation(input_dialog, b"windowOpacity")
        anim_fade.setDuration(300)
        anim_fade.setStartValue(0.0)
        anim_fade.setEndValue(1.0)
        anim_fade.setEasingCurve(QEasingCurve.OutCubic)

        anim_move = QPropertyAnimation(input_dialog, b"pos")
        anim_move.setDuration(300)
        anim_move.setStartValue(QPoint(target_x, target_y + 30))
        anim_move.setEndValue(QPoint(target_x, target_y))
        anim_move.setEasingCurve(QEasingCurve.OutCubic)

        input_dialog.show()

        anim_fade.start()
        anim_move.start()

        input_dialog.anim_fade = anim_fade
        input_dialog.anim_move = anim_move

        input_dialog.activateWindow()
        input_dialog.raise_()
        ai_input.setFocus()

    def _on_ai_response(self, ai_response):
        import time

        logger.debug(
            f"[_on_ai_response] received ai_response at {time.time()}, text: {ai_response.text[:20]}..."
        )
        logger.debug(f"[_on_ai_response] emitting ai_response_received signal")
        self.ai_response_received.emit(ai_response)
        logger.debug(f"[_on_ai_response] signal emitted")

    def _on_ai_response_from_worker(self, response_data):
        import time

        from core.types import AIResponse

        response_type = response_data.get("type")
        text = response_data.get("text", "")
        logger.info(
            f"[_on_ai_response_from_worker] type: {response_type}, text: {text[:30]}..."
        )

        if hasattr(self, 'brain') and hasattr(self.brain, 'local_proactive_service') and self.brain.local_proactive_service:
            self._queue_ui_update(lambda: (
                self.brain.local_proactive_service.on_ai_response(),
                self.brain.local_proactive_service.on_user_input_complete()
            ))

        if response_type == "stream_event":
            chunk = response_data.get("chunk", "")
            if chunk:
                logger.info(f"[_on_ai_response_from_worker] 处理流式事件，chunk长度: {len(chunk)}")
                self._stream_update_direct(chunk)
            return

        text = response_data.get("text", "Hmm... let me think...")
        logger.info(f"[_on_ai_response_from_worker] 处理最终响应，text长度: {len(text)}")
        
        # 解析AI响应中的心情状态命令
        if hasattr(self, 'pet_status_manager'):
            text, command_data = self.pet_status_manager.parse_llm_command(text)
            if command_data:
                self.pet_status_manager.apply_command(command_data)
                logger.debug(f"[_on_ai_response_from_worker] 已解析并应用命令: {command_data}")
        
        ai_response = AIResponse(
            text=text,
            motion=response_data.get("motion", "idle"),
            expression=response_data.get("expression", ""),
            emotion_score=0.0,
        )

        if "execution_result" in response_data:
            ai_response.execution_result = response_data["execution_result"]

        self._on_ai_response(ai_response)

    def _update_ui_with_ai_response(self, ai_response):
        import time

        has_streamed = getattr(self, '_has_streamed_content', False)
        
        if has_streamed:
            logger.debug("[_update_ui_with_ai_response] 已通过流式显示，更新现有气泡内容")
            self._has_streamed_content = False
            self._streaming_text = ""
        
        self._ai_response_signal_count += 1

        now = time.time()
        text = getattr(ai_response, "text", "") or ""
        if text and text == self._last_ai_text and (now - self._last_ai_time) < 0.8:
            logger.debug("[_update_ui_with_ai_response] 重复消息，忽略")
            return

        self._last_ai_text = text
        self._last_ai_time = now

        try:
            if hasattr(ai_response, "text") and ai_response.text:
                display_text = ai_response.text
                if display_text.startswith('{') or display_text.startswith('['):
                    extracted = self._extract_text_from_json_payload(display_text)
                    if extracted:
                        display_text = extracted

                if has_streamed:
                    if hasattr(self, 'current_bubble') and self.current_bubble:
                        self.current_bubble.label.setText(display_text)
                        self.current_bubble.adjustSize()
                    else:
                        logger.debug("[_update_ui_with_ai_response] 流式传输未创建气泡，创建新气泡")
                        self._show_message_bubble(display_text, duration_ms=5000)
                else:
                    if hasattr(self, "current_bubble") and self.current_bubble:
                        self.current_bubble.close()
                    self._show_message_bubble(display_text, duration_ms=5000)

            if hasattr(ai_response, "expression") and ai_response.expression:
                self.expression_manager.set_expression(
                    ai_response.expression, duration_ms=3000
                )

            if hasattr(ai_response, "motion") and ai_response.motion:
                supported_motions = ["sleep", "wink", "leisurely", "idle"]
                if ai_response.motion in supported_motions:
                    if ai_response.motion == "sleep":
                        if hasattr(self.live2d_widget, "target_eye_open"):
                            self.live2d_widget.target_eye_open = 0.0
                    elif ai_response.motion == "wink":
                        pass
                    elif ai_response.motion == "leisurely":
                        pass
                    elif ai_response.motion == "idle":
                        if hasattr(self.live2d_widget, "target_eye_open"):
                            self.live2d_widget.target_eye_open = 1.0
                    logger.debug(
                        f"[_update_ui_with_ai_response] motion handling finished"
                    )

            logger.debug(
                f"[_update_ui_with_ai_response] calling state_machine.notify_event('ai_response')"
            )
            self.state_machine.notify_event(
                "ai_response",
                {
                    "text": ai_response.text if hasattr(ai_response, "text") else "",
                    "motion": (
                        ai_response.motion if hasattr(ai_response, "motion") else "idle"
                    ),
                    "expression": (
                        ai_response.expression
                        if hasattr(ai_response, "expression")
                        else ""
                    ),
                    "emotion_score": (
                        ai_response.emotion_score
                        if hasattr(ai_response, "emotion_score")
                        else 0.0
                    ),
                },
            )
            logger.debug(
                f"[_update_ui_with_ai_response] state_machine.notify_event finished"
            )

            if (
                self.sound_manager.is_enabled()
                and hasattr(ai_response, "text")
                and ai_response.text
            ):
                logger.debug(
                    f"[_update_ui_with_ai_response] calling sound_manager.speak()"
                )
                self.sound_manager.speak(ai_response.text)
                logger.debug(
                    f"[_update_ui_with_ai_response] sound_manager.speak finished"
                )

            logger.debug(
                f"[_update_ui_with_ai_response] finished processing ai_response"
            )
        except Exception as e:
            logger.error(f"处理AI响应时出错: {e}")
            self._show_message_bubble("抱歉，处理响应时出现错误。", duration_ms=3000)
        finally:
            if (
                hasattr(ai_response, "execution_result")
                and ai_response.execution_result
            ):
                ToastNotification.show_notification(
                    f"执行结果: {ai_response.execution_result}", self
                )

    def _send_ai_message(self, input_dialog):
        logger.warning("_send_ai_message方法已过时，建议使用新的消息发送逻辑")
        pass

    def _ui_on_partial_result(self, text):
        if hasattr(self, '_speech_debounce_timer') and self._speech_debounce_timer.isActive():
            self._speech_debounce_timer.stop()
        
        def update_ui():
            base_text = self.voice_base_text
            if base_text and not base_text.endswith(' '):
                new_content = base_text + ' ' + text
            else:
                new_content = base_text + text
            
            if hasattr(self, 'ai_input') and self.ai_input and self.ai_input.isVisible():
                 self.ai_input.setText(new_content)
                 self.ai_input.setCursorPosition(len(new_content))
        
        if not hasattr(self, '_speech_debounce_timer'):
            from PyQt5.QtCore import QTimer
            self._speech_debounce_timer = QTimer(self)
            self._speech_debounce_timer.setSingleShot(True)
            self._speech_debounce_timer.setInterval(100)
        
        self._speech_debounce_timer.timeout.connect(update_ui)
        self._speech_debounce_timer.start()

    def _ui_on_stream_event(self, chunk):
        if not chunk:
            return

        self._has_streamed_content = True
        self._streaming_text = getattr(self, '_streaming_text', '') + chunk

        streaming_text = self._streaming_text.strip()

        if streaming_text.startswith('{') or streaming_text.startswith('['):
            if streaming_text.startswith('{'):
                open_brace, close_brace = '{', '}'
            else:
                open_brace, close_brace = '[', ']'

            open_count = streaming_text.count(open_brace)
            close_count = streaming_text.count(close_brace)

            if open_count == close_count and open_count > 0:
                display_text = self._extract_text_from_json_payload(streaming_text)
                if not display_text:
                    return
            else:
                return
        else:
            display_text = streaming_text

        if not hasattr(self, 'current_bubble') or self.current_bubble is None:
            self._show_message_bubble(display_text, duration_ms=20000)
        else:
            try:
                self.current_bubble.label.setText(display_text)
                self.current_bubble._calculate_size()
                self.current_bubble.adjustSize()
                pet_rect = self.frameGeometry()
                bubble_width = self.current_bubble.width()
                bubble_height = self.current_bubble.height()
                bubble_x = pet_rect.x() + pet_rect.width() - 25
                bubble_y = pet_rect.y() + 35
                screen_geometry = QApplication.screenAt(self.pos()).availableGeometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
                if bubble_x + bubble_width > screen_width:
                    bubble_x = pet_rect.x() - bubble_width + 25
                    if bubble_x < 0:
                        bubble_x = 0
                if bubble_y + bubble_height > screen_height:
                    bubble_y = pet_rect.y() + pet_rect.height() - bubble_height - 20
                    if bubble_y < 0:
                        bubble_y = 20
                bubble_x = max(0, min(bubble_x, screen_width - bubble_width))
                bubble_y = max(0, min(bubble_y, screen_height - bubble_height))
                self.current_bubble.move(bubble_x, bubble_y)
            except Exception:
                pass

    def _ui_on_final_result(self, text):
        if hasattr(self, '_speech_debounce_timer') and self._speech_debounce_timer.isActive():
            self._speech_debounce_timer.stop()
        
        if self.voice_base_text and not self.voice_base_text.endswith(' '):
            self.voice_base_text += ' ' + text
        else:
            self.voice_base_text += text
        
        if hasattr(self, 'ai_input') and self.ai_input:
            self.ai_input.setText(self.voice_base_text)
        
        if self.current_bubble:
            self.current_bubble.close()
            self.current_bubble = None

    def _ui_on_speech_started(self):
        self.is_voice_recording = True
        if hasattr(self, 'ai_input'):
            self.voice_base_text = self.ai_input.text()
            
        if hasattr(self, 'voice_btn'):
            from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPainterPath
            from PyQt5.QtCore import QSize, Qt
            
            def create_mic_icon(size=32, color=QColor(255, 255, 255)):
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.transparent)

                p = QPainter(pixmap)
                p.setRenderHint(QPainter.Antialiasing)

                p.setPen(Qt.NoPen)
                p.setBrush(color)

                center_x = size // 2

                body_width = int(size * 0.28)
                body_height = int(size * 0.45)
                body_x = int(center_x - body_width / 2)
                body_y = int(size * 0.18)

                body_radius = body_width / 2

                body_path = QPainterPath()
                body_path.addRoundedRect(
                    body_x,
                    body_y,
                    body_width,
                    body_height,
                    body_radius,
                    body_radius
                )
                p.drawPath(body_path)

                stand_width = int(size * 0.55)
                stand_height = int(size * 0.35)
                stand_x = int(center_x - stand_width / 2)
                stand_y = int(body_y + body_height - size * 0.05)

                stand_path = QPainterPath()
                stand_path.moveTo(stand_x, stand_y)
                stand_path.arcTo(
                    stand_x,
                    stand_y,
                    stand_width,
                    stand_height,
                    0,
                    -180
                )

                p.drawPath(stand_path)

                stem_width = int(size * 0.08)
                stem_height = int(size * 0.15)
                stem_x = int(center_x - stem_width / 2)
                stem_y = int(stand_y + stand_height * 0.6)

                p.drawRoundedRect(
                    stem_x,
                    stem_y,
                    stem_width,
                    stem_height,
                    stem_width / 2,
                    stem_width / 2
                )

                base_width = int(size * 0.35)
                base_height = int(size * 0.07)
                base_x = int(center_x - base_width / 2)
                base_y = int(stem_y + stem_height + size * 0.02)

                p.drawRoundedRect(
                    base_x,
                    base_y,
                    base_width,
                    base_height,
                    base_height / 2,
                    base_height / 2
                )

                p.end()
                return pixmap
            
            mic_pixmap = create_mic_icon(32, QColor(255, 255, 255))
            self.voice_btn.setIcon(QIcon(mic_pixmap))
            self.voice_btn.setIconSize(QSize(20, 20))
            
            self.voice_btn.setProperty("recording", "true")
            self.voice_btn.style().unpolish(self.voice_btn)
            self.voice_btn.style().polish(self.voice_btn)
            
            if hasattr(self, '_start_btn_animation'):
                try:
                    self._start_btn_animation(self.voice_btn)
                except Exception as e:
                    logger.warning(f"启动按钮动画失败: {e}")

    def _ui_on_speech_stopped(self):
        self.is_voice_recording = False
        if hasattr(self, 'voice_btn'):
            from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPainterPath
            from PyQt5.QtCore import QSize, Qt
            
            def create_mic_icon(size=32, color=QColor(255, 255, 255)):
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.transparent)

                p = QPainter(pixmap)
                p.setRenderHint(QPainter.Antialiasing)

                p.setPen(Qt.NoPen)
                p.setBrush(color)

                center_x = size // 2

                body_width = int(size * 0.28)
                body_height = int(size * 0.45)
                body_x = int(center_x - body_width / 2)
                body_y = int(size * 0.18)

                body_radius = body_width / 2

                body_path = QPainterPath()
                body_path.addRoundedRect(
                    body_x,
                    body_y,
                    body_width,
                    body_height,
                    body_radius,
                    body_radius
                )
                p.drawPath(body_path)

                stand_width = int(size * 0.55)
                stand_height = int(size * 0.35)
                stand_x = int(center_x - stand_width / 2)
                stand_y = int(body_y + body_height - size * 0.05)

                stand_path = QPainterPath()
                stand_path.moveTo(stand_x, stand_y)
                stand_path.arcTo(
                    stand_x,
                    stand_y,
                    stand_width,
                    stand_height,
                    0,
                    -180
                )

                p.drawPath(stand_path)

                # 中央支杆
                stem_width = int(size * 0.08)
                stem_height = int(size * 0.15)
                stem_x = int(center_x - stem_width / 2)
                stem_y = int(stand_y + stand_height * 0.6)

                p.drawRoundedRect(
                    stem_x,
                    stem_y,
                    stem_width,
                    stem_height,
                    stem_width / 2,
                    stem_width / 2
                )

                base_width = int(size * 0.35)
                base_height = int(size * 0.07)
                base_x = int(center_x - base_width / 2)
                base_y = int(stem_y + stem_height + size * 0.02)

                p.drawRoundedRect(
                    base_x,
                    base_y,
                    base_width,
                    base_height,
                    base_height / 2,
                    base_height / 2
                )

                p.end()
                return pixmap
            
            mic_pixmap = create_mic_icon(32, QColor(255, 255, 255))
            self.voice_btn.setIcon(QIcon(mic_pixmap))
            self.voice_btn.setIconSize(QSize(20, 20))
            
            self.voice_btn.setProperty("recording", "false")
            self.voice_btn.style().unpolish(self.voice_btn)
            self.voice_btn.style().polish(self.voice_btn)
            
            if hasattr(self, '_stop_btn_animation'):
                try:
                    self._stop_btn_animation(self.voice_btn)
                except Exception as e:
                    logger.warning(f"停止按钮动画失败: {e}")

    def _start_btn_animation(self, btn):
        try:
            effect = btn.graphicsEffect()
            if not effect or not isinstance(effect, QGraphicsDropShadowEffect):
                effect = QGraphicsDropShadowEffect(btn)
                effect.setColor(QColor(255, 71, 87, 200))
                effect.setOffset(0, 0)
                effect.setBlurRadius(10)
                btn.setGraphicsEffect(effect)
            else:
                effect.setColor(QColor(255, 71, 87, 200))
                effect.setBlurRadius(15)
        except Exception as e:
            logger.warning(f"设置按钮阴影效果失败: {e}")

    def _stop_btn_animation(self, btn):
        try:
            btn.setGraphicsEffect(None)
        except Exception as e:
            logger.warning(f"移除按钮阴影效果失败: {e}")

    def _show_message_bubble(self, text, duration_ms=None):
        if duration_ms is None:
            text_length = len(text)
            calculated_duration = max(3000, min(15000, 3000 + (text_length // 50) * 1000))
            duration_ms = calculated_duration
        
        logger.debug(
            f"[_show_message_bubble] called with text: {text[:20]}..., duration: {duration_ms}, text_length: {len(text)}"
        )

        if hasattr(self, "current_bubble") and self.current_bubble:
            self.current_bubble.close()

        self.current_bubble = MessageBubble(text, self)

        pet_rect = self.frameGeometry()
        pet_x = pet_rect.x()
        pet_y = pet_rect.y()
        pet_width = pet_rect.width()
        pet_height = pet_rect.height()
        
        screen = QApplication.screenAt(self.pos())
        if screen is not None:
            screen_geometry = screen.availableGeometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
        else:
            primary_screen = QApplication.primaryScreen()
            if primary_screen is not None:
                screen_geometry = primary_screen.availableGeometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
            else:
                screen_width = 1920
                screen_height = 1080
        
        bubble_width = self.current_bubble.width()
        bubble_height = self.current_bubble.height()
        
        bubble_x = pet_x + pet_width - 25
        bubble_y = pet_y + 35
        
        if bubble_x + bubble_width > screen_width:
            bubble_x = pet_x - bubble_width + 25
            if bubble_x < 0:
                bubble_x = pet_x + (pet_width - bubble_width) // 2
                if bubble_x < 0:
                    bubble_x = 0
        
        if bubble_y + bubble_height > screen_height:
            bubble_y = pet_y + pet_height - bubble_height - 20
            if bubble_y < 0:
                bubble_y = 20
        
        bubble_x = max(0, min(bubble_x, screen_width - bubble_width))
        bubble_y = max(0, min(bubble_y, screen_height - bubble_height))
        
        self.current_bubble.move(bubble_x, bubble_y)

        self.current_bubble.show()

        QTimer.singleShot(duration_ms, self.current_bubble.close)
        logger.debug(f"[_show_message_bubble] finished")

    def _on_thinking_state_changed(self, is_thinking):
        """处理思考状态变化"""
        if is_thinking:
            logger.info("[_on_thinking_state_changed] 开始思考")
            self._thinking_dots_count = 0
            self._show_thinking_bubble()
            self._thinking_animation_timer.start()
        else:
            logger.info("[_on_thinking_state_changed] 结束思考")
            self._thinking_animation_timer.stop()
            self._close_thinking_bubble()
    
    def _show_thinking_bubble(self):
        """显示思考动画（旋转加载图标，内置到主窗口）"""
        if hasattr(self, "_thinking_spinner") and self._thinking_spinner:
            self._thinking_spinner.stop()
            if self._thinking_spinner.parent() is not None:
                self._thinking_spinner.setParent(None)
        
        self._thinking_spinner = LoadingSpinner(self)
        self._thinking_spinner.raise_()
        self._thinking_spinner.start()
    
    def _close_thinking_bubble(self):
        """关闭思考动画"""
        if hasattr(self, "_thinking_spinner") and self._thinking_spinner:
            self._thinking_spinner.stop()
            self._thinking_spinner.setParent(None)
            self._thinking_spinner.deleteLater()
            self._thinking_spinner = None

    def _toggle_sound(self):
        enabled = self.sound_toggle_action.isChecked()
        self.sound_manager.set_enabled(enabled)
        self.tray_sound_action.setChecked(enabled)

    def _show_ai_config(self):
        config_window = AIConfigWindow(self, self.ai_manager)
        self.child_windows.append(config_window)
        config_window.exec_()
        if config_window in self.child_windows:
            self.child_windows.remove(config_window)

    def closeEvent(self, event):
        logger.info("开始关闭应用程序...")

        logger.info(f"开始关闭 {len(self.child_windows)} 个子窗口...")
        for window in self.child_windows[:]:
            try:
                if hasattr(window, "isVisible") and window.isVisible():
                    window.close()
                if window in self.child_windows:
                    self.child_windows.remove(window)
            except Exception as e:
                logger.error(f"关闭子窗口失败: {e}")
        logger.info("所有子窗口已关闭")

        if hasattr(self, "message_bubble") and self.message_bubble:
            try:
                self.message_bubble.close()
                self.message_bubble = None
            except Exception as e:
                logger.error(f"关闭消息气泡失败: {e}")

        if hasattr(self, "input_dialog") and self.input_dialog:
            try:
                self.input_dialog.close()
                self.input_dialog = None
            except Exception as e:
                logger.error(f"关闭输入窗口失败: {e}")

        logger.info("停止状态机...")
        self.state_machine.stop()

        logger.info("停止声音管理器...")
        self.sound_manager.stop()

        logger.info("保存用户数据和程序状态...")
        try:
            config_manager.set(
                "window.position", {"x": self.pos().x(), "y": self.pos().y()}
            )
            config_manager.set(
                "window.size",
                {"width": self.size().width(), "height": self.size().height()},
            )
            config_manager.save()
            logger.info("窗口配置已保存")
        except Exception as e:
            logger.error(f"保存数据失败: {e}")

        # 关闭心情状态管理器
        if hasattr(self, 'pet_status_manager'):
            try:
                self.pet_status_manager.shutdown()
                logger.info("PetStatusManager 已关闭")
            except Exception as e:
                logger.error(f"关闭PetStatusManager失败: {e}")

        logger.info("关闭全局HTTP连接池...")
        try:
            from core.ai_manager import close_global_sessions
            import asyncio
            # 创建临时事件循环来执行异步关闭操作
            loop = asyncio.new_event_loop()
            loop.run_until_complete(close_global_sessions())
            loop.close()
            logger.info("全局HTTP连接池已关闭")
        except Exception as e:
            logger.error(f"关闭HTTP连接池失败: {e}")

        logger.info("终止后台线程...")
        try:
            if hasattr(self, "ai_worker") and self.ai_worker.isRunning():
                self.ai_worker.terminate()
                self.ai_worker.wait()
                logger.info("AIWorker线程已终止")

            if hasattr(self, "brain"):
                if hasattr(self.brain, "dialogue_manager"):
                    try:
                        self.brain.dialogue_manager.save_history(max_entries=24)
                        logger.info("对话历史已保存")
                    except Exception as e:
                        logger.error(f"保存对话历史失败: {e}")
                if hasattr(self.brain, "memory_manager"):
                    pass
        except Exception as e:
            logger.error(f"终止后台线程失败: {e}")

        logger.info("隐藏系统托盘图标...")
        if hasattr(self, "system_tray"):
            self.system_tray.hide()

        logger.info("注销全局热键...")
        if hasattr(self, "hotkey_registered") and self.hotkey_registered:
            try:
                if hasattr(self, "user32") and hasattr(self, "HOTKEY_ID_SHOW_INPUT"):
                    hwnd = int(self.winId())
                    self.user32.UnregisterHotKey(hwnd, self.HOTKEY_ID_SHOW_INPUT)
                    logger.info("全局热键已注销")
            except Exception as e:
                logger.error(f"注销全局热键失败: {e}")

        logger.info("停止所有定时器...")
        for timer in self.findChildren(QTimer):
            timer.stop()

        logger.info("应用程序关闭完成")
        event.accept()

        QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setQuitOnLastWindowClosed(False)

    language = config_manager.get("base.language", "zh-CN")
    init_i18n(language)

    window = DeskpetMainWindow()
    window.show()
    sys.exit(app.exec_())
