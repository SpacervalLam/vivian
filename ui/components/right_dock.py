from PyQt5.QtCore import (QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal,
                          QEasingCurve, QPoint, QEvent)
from PyQt5.QtGui import QColor, QCursor, QFont, QIcon
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QApplication,
                             QGraphicsDropShadowEffect, QMessageBox)

from utils.i18n import _


class RightDock(QWidget):
    """右侧Dock组件"""
    
    settings_clicked = pyqtSignal()
    memory_clicked = pyqtSignal()
    quit_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        self.width = 80
        self.animation_duration = 300
        self.edge_threshold = 10
        self.hide_delay = 100
        
        self._init_ui()
        self._init_animation()
        
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_dock)
        
        self.hide_dock(animate=False)
        
        QApplication.instance().installEventFilter(self)
    
    def _init_ui(self):
        """初始化UI组件"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)
        layout.setSpacing(15)
        
        self.settings_btn = self._create_button(_("settings"))
        self.memory_btn = self._create_button(_("memory_management"))
        self.quit_btn = self._create_button(_("quit"))
        
        self.settings_btn.clicked.connect(self.settings_clicked)
        self.memory_btn.clicked.connect(self.memory_clicked)
        self.quit_btn.clicked.connect(self._on_quit_clicked)
        
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.memory_btn)
        layout.addWidget(self.quit_btn)
        
        self.setStyleSheet("""
        QWidget {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                                      stop:0 rgba(30, 35, 45, 0.95), 
                                      stop:1 rgba(23, 25, 35, 0.90));
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 15px;
        }
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(-5)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)
        
        self.setFixedWidth(self.width)
        self.adjustSize()
    
    def _create_button(self, text):
        """
        创建带有现代化样式的按钮
        """
        button = QPushButton(text, self)
        button.setFixedSize(self.width - 20, 50)
        button.setCursor(QCursor(Qt.PointingHandCursor))
        
        # 现代化按钮样式
        style = """
        QPushButton {
            background-color: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            color: white;
            font-family: "Microsoft YaHei", "Segoe UI";
            font-size: 14px;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: rgba(255, 255, 255, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.3);
        }
        QPushButton:pressed {
            background-color: rgba(255, 255, 255, 0.3);
        }
        """
        button.setStyleSheet(style)
        
        return button
    
    def _init_animation(self):
        """初始化动画效果"""
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(self.animation_duration)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
    
    def show_dock(self, animate=True):
        """显示Dock组件"""
        self.hide_timer.stop()
        
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        x = screen_geo.right() - self.width
        y = screen_geo.center().y() - self.height() // 2
        
        y = max(screen_geo.top(), min(y, screen_geo.bottom() - self.height()))
        
        if animate:
            current_rect = self.geometry()
            
            self.animation.setStartValue(current_rect)
            self.animation.setEndValue(QRect(x, y, self.width, self.height()))
            self.animation.start()
        else:
            self.setGeometry(x, y, self.width, self.height())
        
        if not self.isVisible():
            self.show()
    
    def hide_dock(self, animate=True):
        """隐藏Dock组件"""
        if not self.isVisible():
            return
        
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        x = screen_geo.right()
        y = self.y()
        
        if animate:
            current_rect = self.geometry()
            
            self.animation.setStartValue(current_rect)
            self.animation.setEndValue(QRect(x, y, self.width, self.height()))
            self.animation.start()
        else:
            self.setGeometry(x, y, self.width, self.height())
    
    def eventFilter(self, obj, event):
        """
        全局事件过滤器，监听鼠标移动
        """
        if event.type() == QEvent.MouseMove:
            # 获取鼠标位置
            global_pos = event.globalPos()
            
            # 获取屏幕尺寸
            screen = QApplication.primaryScreen()
            screen_geo = screen.availableGeometry()
            
            # 检查鼠标是否在屏幕最右侧边缘
            if screen_geo.right() - global_pos.x() <= self.edge_threshold:
                # 鼠标在屏幕右侧边缘，显示Dock
                self.show_dock()
                # 取消隐藏定时器
                self.hide_timer.stop()
            else:
                # 鼠标不在屏幕右侧边缘，检查是否在Dock区域内
                if not self.geometry().contains(global_pos):
                    # 鼠标不在Dock区域内，启动隐藏定时器
                    self.hide_timer.start(self.hide_delay)
        
        return super().eventFilter(obj, event)
    
    def enterEvent(self, event):
        """
        鼠标进入Dock区域
        """
        # 取消隐藏定时器
        self.hide_timer.stop()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """
        鼠标离开Dock区域
        """
        # 启动隐藏定时器
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
        screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        y = screen_geo.center().y() - self.height() // 2
        y = max(screen_geo.top(), min(y, screen_geo.bottom() - self.height()))
        
        if self.isVisible():
            x = screen_geo.right() - self.width
        else:
            x = screen_geo.right()
        
        self.setGeometry(x, y, self.width, self.height())
