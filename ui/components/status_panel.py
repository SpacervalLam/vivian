"""桌宠状态面板组件"""

import time
from datetime import datetime

from PyQt5.QtCore import QTimer, Qt, QPoint
from PyQt5.QtGui import QColor, QPainter, QFont, QPen
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QProgressBar, QFrame, QPushButton)

from loguru import logger


class StatusPanel(QWidget):
    """桌宠状态面板"""
    
    MOOD_COLORS = {
        "happy": QColor(255, 193, 7),
        "excited": QColor(255, 152, 0),
        "tired": QColor(158, 158, 158),
        "sleepy": QColor(189, 189, 189),
        "bored": QColor(121, 85, 72),
        "sad": QColor(66, 133, 244),
        "angry": QColor(211, 47, 47),
        "neutral": QColor(102, 187, 106)
    }
    
    MOOD_ICONS = {
        "happy": "😊",
        "excited": "🥰",
        "tired": "😫",
        "sleepy": "😴",
        "bored": "😒",
        "sad": "😢",
        "angry": "😠",
        "neutral": "😊"
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._status_manager = None
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(1000)
        self._update_timer.timeout.connect(self._update_status)
        
        self._init_ui()
        self._update_timer.start()
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setFixedSize(280, 320)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 状态标题区域
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignCenter)
        
        self._state_icon_label = QLabel("😊")
        self._state_icon_label.setStyleSheet("font-size: 32px;")
        self._state_label = QLabel("状态")
        self._state_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        
        title_layout.addWidget(self._state_icon_label)
        title_layout.addWidget(self._state_label)
        main_layout.addLayout(title_layout)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: rgba(255,255,255,0.3);")
        main_layout.addWidget(separator)
        
        # 心情状态区域
        mood_layout = QVBoxLayout()
        mood_layout.setSpacing(8)
        
        # 愉悦度
        self._happiness_bar = StatusBar("愉悦度", "😄")
        mood_layout.addWidget(self._happiness_bar)
        
        # 精力值
        self._energy_bar = StatusBar("精力值", "⚡")
        mood_layout.addWidget(self._energy_bar)
        
        # 亲密度
        self._intimacy_bar = StatusBar("亲密度", "💗")
        mood_layout.addWidget(self._intimacy_bar)
        
        # 无聊度
        self._boredom_bar = StatusBar("无聊度", "😴")
        mood_layout.addWidget(self._boredom_bar)
        
        main_layout.addLayout(mood_layout)
        
        # 分隔线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("color: rgba(255,255,255,0.3);")
        main_layout.addWidget(separator2)
        
        # 统计信息
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(5)
        
        self._days_label = QLabel("连续陪伴: 0 天")
        self._days_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.8);")
        stats_layout.addWidget(self._days_label)
        
        self._last_interaction_label = QLabel("最后互动: 刚刚")
        self._last_interaction_label.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.6);")
        stats_layout.addWidget(self._last_interaction_label)
        
        main_layout.addLayout(stats_layout)
        
        self.setLayout(main_layout)
    
    def paintEvent(self, event):
        """绘制背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制渐变背景
        gradient = QPainter()
        painter.setBrush(QColor(30, 35, 45))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 15, 15)
        
        # 添加边框
        pen = QPen(QColor(255, 255, 255, 30), 1)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect(), 15, 15)
        
        super().paintEvent(event)
    
    def set_status_manager(self, status_manager):
        """设置状态管理器"""
        self._status_manager = status_manager
        logger.info("[StatusPanel] 状态管理器已设置")
    
    def _update_status(self):
        """更新状态显示"""
        if not self._status_manager:
            return
        
        try:
            status = self._status_manager.get_status_for_frontend()
            
            # 更新状态图标和标签
            self._state_icon_label.setText(self.MOOD_ICONS.get(status["state"], "😊"))
            self._state_label.setText(status["state_label"])
            
            # 更新状态条
            mood = status["mood"]
            self._happiness_bar.setValue(mood.get("happiness", 0))
            self._energy_bar.setValue(mood.get("energy", 0))
            self._intimacy_bar.setValue(mood.get("intimacy", 0))
            self._boredom_bar.setValue(mood.get("boredom", 0))
            
            # 更新统计信息
            self._days_label.setText(f"连续陪伴: {status['consecutive_days']} 天")
            
            # 更新最后互动时间
            last_time = status["last_interaction_time"]
            now = time.time()
            diff = now - last_time
            
            if diff < 60:
                last_str = "刚刚"
            elif diff < 3600:
                last_str = f"{int(diff // 60)} 分钟前"
            elif diff < 86400:
                last_str = f"{int(diff // 3600)} 小时前"
            else:
                last_str = f"{int(diff // 86400)} 天前"
            
            self._last_interaction_label.setText(f"最后互动: {last_str}")
            
        except Exception as e:
            logger.error(f"[StatusPanel] 更新状态失败: {e}")
    
    def show_panel(self, parent_pos):
        """显示面板"""
        x = parent_pos.x() - self.width() - 20
        y = parent_pos.y()
        self.move(x, y)
        self.show()


class StatusBar(QWidget):
    """状态进度条组件"""
    
    def __init__(self, label, icon):
        super().__init__()
        self._label = label
        self._icon = icon
        self._value = 0
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 图标
        icon_label = QLabel(self._icon)
        icon_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_label)
        
        # 标签
        label = QLabel(self._label)
        label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.8); width: 50px;")
        layout.addWidget(label)
        
        # 进度条
        self._progress = QProgressBar()
        self._progress.setFixedHeight(12)
        self._progress.setRange(0, 100)
        self._progress.setValue(50)
        self._progress.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255,255,255,0.1);
                border-radius: 6px;
                text-align: right;
                padding-right: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #66BB6A, stop:1 #43A047);
                border-radius: 6px;
            }
        """)
        layout.addWidget(self._progress)
        
        # 数值
        self._value_label = QLabel("50")
        self._value_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.6); width: 30px;")
        layout.addWidget(self._value_label)
        
        self.setLayout(layout)
    
    def setValue(self, value):
        """设置值"""
        self._value = max(0, min(100, value))
        self._progress.setValue(self._value)
        self._value_label.setText(str(self._value))
        
        # 根据数值调整颜色
        if self._value >= 70:
            color = "#66BB6A"
        elif self._value >= 40:
            color = "#FFA726"
        else:
            color = "#EF5350"
        
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255,255,255,0.1);
                border-radius: 6px;
                text-align: right;
                padding-right: 5px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 {color}, stop:1 {color});
                border-radius: 6px;
            }}
        """)