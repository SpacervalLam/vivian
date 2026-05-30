"""桌宠状态面板组件 - 现代半透明小窗口"""

import time
from datetime import datetime

from PyQt5.QtCore import QTimer, Qt, QPoint, QRect, QSize, QPropertyAnimation, pyqtProperty
from PyQt5.QtGui import QColor, QPainter, QFont, QPen, QLinearGradient, QBrush
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QProgressBar, QFrame, QPushButton, QApplication, QGraphicsOpacityEffect)

from loguru import logger


# 现代化半透明配色方案
COLORS = {
    'bg_start': QColor(20, 20, 35, 220),     # 背景渐变开始
    'bg_end': QColor(30, 30, 50, 230),       # 背景渐变结束
    'border': QColor(155, 89, 182, 80),      # 边框色（半透明紫）
    'text_main': QColor(255, 255, 255, 240), # 主文字
    'text_secondary': QColor(200, 200, 220, 200), # 次要文字
    'text_muted': QColor(150, 150, 180, 180),    # 暗色文字
    'accent_purple': QColor(155, 89, 182),      # 主题紫
    'accent_pink': QColor(255, 0, 127),         # 霓虹粉
    'accent_green': QColor(0, 245, 212),        # 荧光绿
    'accent_yellow': QColor(254, 228, 64),      # 明朗黄
    'accent_blue': QColor(58, 134, 255),        # 晴空蓝
    'progress_bg': QColor(255, 255, 255, 25),   # 进度条背景
}


class StatusPanel(QWidget):
    """桌宠状态面板 - 定位在桌宠附近的半透明小窗口"""
    
    MOOD_COLORS = {
        "happy": COLORS['accent_yellow'],
        "excited": COLORS['accent_pink'],
        "tired": QColor(158, 158, 158),
        "sleepy": QColor(189, 189, 189),
        "bored": QColor(121, 85, 72),
        "sad": COLORS['accent_blue'],
        "angry": QColor(211, 47, 47),
        "neutral": COLORS['accent_green']
    }
    
    MOOD_ICONS = {
        "happy": "☀️",
        "excited": "🥰",
        "tired": "😫",
        "sleepy": "😴",
        "bored": "😒",
        "sad": "😢",
        "angry": "😠",
        "neutral": "😊"
    }
    
    MOOD_LABELS = {
        "happy": "开心",
        "excited": "兴奋",
        "tired": "疲惫",
        "sleepy": "困倦",
        "bored": "无聊",
        "sad": "难过",
        "angry": "生气",
        "neutral": "平静"
    }
    
    def __init__(self, parent=None, pet_pos=None):
        super().__init__(parent)
        self._status_manager = None
        self._pet_pos = pet_pos
        self._panel_size = QSize(280, 140)
        self._margin = 20
        self._is_visible = False
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide_panel)
        self._auto_hide_delay = 8000  # 8秒后自动隐藏
        
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(500)
        self._update_timer.timeout.connect(self._update_status)
        
        # 透明度动画效果
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(300)
        
        self._init_ui()
        self._update_timer.start()
        
        # 尝试自动获取状态管理器 - 修复函数名
        try:
            from core.pet_status import get_pet_status_manager
            self._status_manager = get_pet_status_manager()
            logger.info("[StatusPanel] 状态管理器已获取")
        except Exception as e:
            logger.warning(f"[StatusPanel] 获取状态管理器失败: {e}")
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self.setFixedSize(self._panel_size)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(8)
        
        # 心情状态区域（直接放在主布局中）
        # 愉悦度
        self._happiness_bar = StatusBar("愉悦", COLORS['accent_yellow'])
        main_layout.addWidget(self._happiness_bar)
        
        # 精力值
        self._energy_bar = StatusBar("精力", COLORS['accent_green'])
        main_layout.addWidget(self._energy_bar)
        
        # 亲密度
        self._intimacy_bar = StatusBar("亲密", COLORS['accent_pink'])
        main_layout.addWidget(self._intimacy_bar)
        
        # 无聊度
        self._boredom_bar = StatusBar("无聊", COLORS['accent_blue'])
        main_layout.addWidget(self._boredom_bar)
        
        self.setLayout(main_layout)
    
    def paintEvent(self, event):
        """绘制背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制渐变背景
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, COLORS['bg_start'])
        gradient.setColorAt(1, COLORS['bg_end'])
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 14, 14)
        
        # 绘制边框
        pen = QPen(COLORS['border'], 1.5)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect(), 14, 14)
        
        # 绘制顶部发光效果
        glow_gradient = QLinearGradient(0, 0, 0, 30)
        glow_gradient.setColorAt(0, QColor(155, 89, 182, 40))
        glow_gradient.setColorAt(1, QColor(155, 89, 182, 0))
        painter.setBrush(QBrush(glow_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), 30, 14, 14)
    
    def set_status_manager(self, status_manager):
        """设置状态管理器"""
        self._status_manager = status_manager
        logger.info("[StatusPanel] 状态管理器已设置")
    
    def set_pet_position(self, pos):
        """设置桌宠位置"""
        self._pet_pos = pos
    
    def _calculate_position(self):
        """智能计算面板位置"""
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        if not self._pet_pos:
            # 如果没有桌宠位置，显示在屏幕中央
            x = (screen_geo.width() - self.width()) // 2
            y = (screen_geo.height() - self.height()) // 2
            return QPoint(x, y)
        
        pet_rect = QRect(self._pet_pos, QSize(150, 350))  # 假设桌宠大小
        panel_w, panel_h = self.width(), self.height()
        margin = self._margin
        
        # 尝试的位置顺序：右上 → 左上 → 右下 → 左下
        positions = [
            # 右上角
            QPoint(pet_rect.right() + margin, pet_rect.top()),
            # 左上角
            QPoint(pet_rect.left() - panel_w - margin, pet_rect.top()),
            # 右下角
            QPoint(pet_rect.right() + margin, pet_rect.bottom() - panel_h),
            # 左下角
            QPoint(pet_rect.left() - panel_w - margin, pet_rect.bottom() - panel_h),
        ]
        
        # 检查每个位置是否在屏幕内
        for pos in positions:
            panel_rect = QRect(pos, QSize(panel_w, panel_h))
            if screen_geo.contains(panel_rect):
                return pos
        
        # 如果所有角落都不行，显示在屏幕中央
        x = (screen_geo.width() - panel_w) // 2
        y = (screen_geo.height() - panel_h) // 2
        return QPoint(x, y)
    
    def show_panel(self, pet_pos=None):
        """显示面板"""
        if self._is_visible:
            self.hide_panel()
            return
        
        if pet_pos:
            self._pet_pos = pet_pos
        
        pos = self._calculate_position()
        self.move(pos)
        
        # 显示并启动渐入动画
        self.show()
        self._is_visible = True
        self.raise_()
        self.activateWindow()
        
        # 渐入动画
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
        
        # 启动自动隐藏计时器
        self._auto_hide_timer.start(self._auto_hide_delay)
        logger.info(f"[StatusPanel] 面板已显示，将在{self._auto_hide_delay/1000}秒后自动隐藏")
    
    def hide_panel(self):
        """隐藏面板"""
        if not self._is_visible:
            return
        
        self._auto_hide_timer.stop()
        
        # 渐出动画
        self._fade_animation.stop()
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_fade_out_finished)
        self._fade_animation.start()
        
        logger.info("[StatusPanel] 面板正在隐藏...")
    
    def _on_fade_out_finished(self):
        """渐出动画完成后隐藏"""
        self.hide()
        self._is_visible = False
        self._fade_animation.finished.disconnect(self._on_fade_out_finished)
        logger.info("[StatusPanel] 面板已隐藏")
    
    def toggle_panel(self, pet_pos=None):
        """切换面板显示/隐藏"""
        if self._is_visible:
            self.hide_panel()
        else:
            self.show_panel(pet_pos)
    
    def is_visible(self):
        """检查面板是否可见"""
        return self._is_visible
    
    def _update_status(self):
        """更新状态显示"""
        if not self._status_manager:
            return
        
        try:
            status = self._status_manager.get_status_for_frontend()
            
            # 更新状态条
            mood = status["mood"]
            
            happiness = mood.get("happiness", 50)
            energy = mood.get("energy", 50)
            intimacy = mood.get("intimacy", 50)
            boredom = mood.get("boredom", 0)
            
            self._happiness_bar.setValue(happiness)
            self._energy_bar.setValue(energy)
            self._intimacy_bar.setValue(intimacy)
            self._boredom_bar.setValue(boredom)
            
        except Exception as e:
            logger.error(f"[StatusPanel] 更新状态失败: {e}")


class StatusBar(QWidget):
    """状态进度条组件"""
    
    def __init__(self, label, color):
        super().__init__()
        self._label = label
        self._color = color
        self._value = 50
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # 标签
        label = QLabel(self._label)
        label.setStyleSheet(f"""
            font-size: 12px; 
            color: {COLORS['text_secondary'].name()};
            font-weight: 500;
        """)
        label.setFixedWidth(48)
        layout.addWidget(label)
        
        # 进度条
        self._progress = QProgressBar()
        self._progress.setFixedHeight(10)
        self._progress.setRange(0, 100)
        self._progress.setValue(50)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['progress_bg'].name()};
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {self._color.name()};
                border-radius: 5px;
            }}
        """)
        layout.addWidget(self._progress, 1)
        
        # 数值
        self._value_label = QLabel("50")
        self._value_label.setStyleSheet(f"""
            font-size: 12px; 
            color: {COLORS['text_muted'].name()};
            font-weight: 600;
        """)
        self._value_label.setFixedWidth(36)
        self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self._value_label)
        
        self.setLayout(layout)
    
    def setValue(self, value):
        """设置值"""
        self._value = max(0, min(100, value))
        self._progress.setValue(int(self._value))
        self._value_label.setText(str(int(self._value)))
        
        # 根据数值调整颜色
        if self._value >= 70:
            text_color = COLORS['accent_green']
        elif self._value >= 40:
            text_color = COLORS['accent_yellow']
        else:
            text_color = QColor(239, 83, 80)
        
        self._value_label.setStyleSheet(f"""
            font-size: 11px; 
            color: {text_color.name()};
            font-weight: 600;
        """)
