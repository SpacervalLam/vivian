"""右侧Dock组件"""

from PyQt5.QtCore import (
    QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal,
    QEasingCurve, QPoint, QEvent, QSize
)
from PyQt5.QtGui import (
    QColor, QCursor, QFont, QIcon, QPainter, QPainterPath, QPixmap
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QApplication,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QMessageBox
)

from loguru import logger
from utils.i18n import _


class EnhancedRightDock(QWidget):
    """右侧Dock组件"""
    
    settings_clicked = pyqtSignal()
    memory_clicked = pyqtSignal()
    quit_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        self.width = 96
        self.animation_duration = 320
        self.edge_threshold = 12
        self.hide_delay = 180
        
        self._init_ui()
        self._init_animations()
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._delayed_hide)
        
        self._initial_position()
        
        QApplication.instance().installEventFilter(self)
        
    def _init_ui(self):
        """初始化UI组件"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 22, 12, 22)
        layout.setSpacing(14)
        
        # 创建按钮
        self.settings_btn = self._create_button("⚙️", _("settings"))
        self.memory_btn = self._create_button("📋", _("memory_management"))
        self.quit_btn = self._create_button("🚪", _("quit"))
        
        # 连接信号
        self.settings_btn.clicked.connect(self.settings_clicked)
        self.memory_btn.clicked.connect(self.memory_clicked)
        self.quit_btn.clicked.connect(self._on_quit_clicked)
        
        # 添加按钮到布局
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.memory_btn)
        layout.addWidget(self.quit_btn)
        
        # 添加背景样式
        self._apply_style()
        
        # 添加阴影效果
        self._add_shadow()
        
        # 设置固定大小
        self.setFixedWidth(self.width)
        self.adjustSize()
        
    def _create_button(self, icon_text, tooltip):
        """创建按钮"""
        button = EnhancedButton(icon_text, tooltip)
        return button
        
    def _apply_style(self):
        """应用样式"""
        style = """
        QWidget {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(35, 40, 52, 0.97),
                stop:1 rgba(28, 32, 42, 0.95)
            );
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 20px;
        }
        """
        self.setStyleSheet(style)
        
    def _add_shadow(self):
        """添加阴影效果"""
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(28)
        self.shadow.setOffset(-8, 4)
        self.shadow.setColor(QColor(0, 0, 0, 110))
        self.setGraphicsEffect(self.shadow)
        
    def _init_animations(self):
        """初始化动画效果"""
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(self.animation_duration)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        
    def _initial_position(self):
        """设置初始位置"""
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right()
        y = screen.center().y() - self.height() // 2
        y = max(screen.top(), min(y, screen.bottom() - self.height()))
        self.setGeometry(x, y, self.width, self.height())
        
    def show_dock(self, animate=True):
        """显示Dock组件"""
        self.hide_timer.stop()
        
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right() - self.width
        y = screen.center().y() - self.height() // 2
        y = max(screen.top(), min(y, screen.bottom() - self.height()))
        
        if animate:
            self._play_show_animation(x, y)
        else:
            self.setGeometry(x, y, self.width, self.height())
            
        if not self.isVisible():
            self.show()
            
    def _play_show_animation(self, x, y):
        """播放显示动画"""
        current = self.geometry()
        self.animation.setStartValue(current)
        self.animation.setEndValue(QRect(x, y, self.width, self.height()))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()
        
    def hide_dock(self, animate=True):
        """隐藏Dock组件"""
        if not self.isVisible():
            return
            
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.right()
        y = self.y()
        
        if animate:
            self._play_hide_animation(x, y)
        else:
            self.setGeometry(x, y, self.width, self.height())
            
    def _play_hide_animation(self, x, y):
        """播放隐藏动画"""
        current = self.geometry()
        self.animation.setStartValue(current)
        self.animation.setEndValue(QRect(x, y, self.width, self.height()))
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.start()
        
    def _delayed_hide(self):
        """延迟隐藏"""
        self.hide_dock()
        
    def eventFilter(self, obj, event):
        """全局事件过滤器，监听鼠标移动"""
        if event.type() == QEvent.MouseMove:
            global_pos = event.globalPos()
            screen = QApplication.primaryScreen().availableGeometry()
            
            dist_from_right = screen.right() - global_pos.x()
            
            if dist_from_right <= self.edge_threshold:
                self.show_dock()
                self.hide_timer.stop()
            else:
                if not self.geometry().contains(global_pos):
                    self.hide_timer.start(self.hide_delay)
        
        return super().eventFilter(obj, event)
        
    def enterEvent(self, event):
        """鼠标进入Dock区域"""
        self.hide_timer.stop()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """鼠标离开Dock区域"""
        self.hide_timer.start(self.hide_delay)
        super().leaveEvent(event)
        
    def _on_quit_clicked(self):
        """处理退出按钮点击"""
        reply = QMessageBox.question(
            self, "确认退出", "确定要退出应用吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.quit_clicked.emit()
            
    def adjust_to_screen(self):
        """调整Dock位置以适应屏幕尺寸变化"""
        screen = QApplication.primaryScreen().availableGeometry()
        y = screen.center().y() - self.height() // 2
        y = max(screen.top(), min(y, screen.bottom() - self.height()))
        
        if self.isVisible():
            x = screen.right() - self.width
        else:
            x = screen.right()
            
        self.setGeometry(x, y, self.width, self.height())


class EnhancedButton(QPushButton):
    """增强版按钮"""
    
    def __init__(self, icon, tooltip, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 64)
        self.setToolTip(tooltip)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        self.icon_text = icon
        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        from PyQt5.QtWidgets import QVBoxLayout, QLabel
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        
        self.icon_label = QLabel(self.icon_text)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("""
            QLabel {
                font-size: 22px;
                background: transparent;
            }
        """)
        
        layout.addWidget(self.icon_label)
        
        self._set_style()
        
        self.effect = QGraphicsOpacityEffect()
        self.effect.setOpacity(1.0)
        self.setGraphicsEffect(self.effect)

    def _set_style(self):
        """设置按钮样式"""
        style = """
        QPushButton {
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 16px;
            color: white;
        }
        
        QPushButton:hover {
            background-color: rgba(255, 255, 255, 0.13);
            border: 1px solid rgba(0, 173, 181, 0.35);
        }
        
        QPushButton:pressed {
            background-color: rgba(0, 173, 181, 0.28);
            border: 1px solid rgba(0, 173, 181, 0.55);
        }
        """
        self.setStyleSheet(style)
