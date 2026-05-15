from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (QApplication, QGraphicsDropShadowEffect, QLabel,
                             QVBoxLayout, QWidget)


class ToastNotification(QWidget):
    """Toast通知组件"""

    def __init__(self, text, parent=None, notification_type="info"):
        super().__init__(parent)
        self.text = text
        self.notification_type = notification_type

        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setFixedSize(320, 80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 15, 10)

        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("""
            color: rgb(221, 221, 221); 
            font-size: 16px; 
            font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            background: transparent;
            font-weight: 500;
        """)
        layout.addWidget(self.text_label)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(99, 40, 180, 80))
        self.setGraphicsEffect(shadow)

        self._init_position_and_show()

    def paintEvent(self, event):
        """绘制圆角卡片"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_brush = QBrush(QColor(40, 44, 52, 245))
        border_pen = QPen(QColor(44, 49, 58))
        border_pen.setWidth(1)

        painter.setBrush(bg_brush)
        painter.setPen(border_pen)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = 12
        painter.drawRoundedRect(rect, radius, radius)

        type_colors = {
            "info": QColor(189, 147, 249),
            "success": QColor(103, 194, 58),
            "warning": QColor(255, 184, 108),
            "error": QColor(245, 108, 108),
        }
        accent_color = type_colors.get(self.notification_type, type_colors["info"])

        painter.setBrush(QBrush(accent_color))
        painter.setPen(Qt.NoPen)

        bar_width = 5

        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QPainterPath

        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        painter.setClipPath(path)

        painter.drawRect(rect.x(), rect.y(), bar_width, rect.height())

    def _init_position_and_show(self):
        """计算位置并启动动画"""
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()

        margin_right = 20
        margin_bottom = 60

        target_x = screen_geometry.width() - self.width() - margin_right
        target_y = screen_geometry.height() - self.height() - margin_bottom

        start_pos = QPoint(target_x, target_y + 30)
        end_pos = QPoint(target_x, target_y)

        self.move(start_pos)
        self.setWindowOpacity(0.0)
        self.show()

        self.entry_anim = QPropertyAnimation(self, b"pos")
        self.entry_anim.setDuration(500)
        self.entry_anim.setStartValue(start_pos)
        self.entry_anim.setEndValue(end_pos)
        self.entry_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(400)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)

        self.entry_anim.start()
        self.fade_in.start()

        QTimer.singleShot(3000, self._exit_smoothly)

    def _exit_smoothly(self):
        """退出动画"""
        current_pos = self.pos()
        exit_pos = QPoint(current_pos.x() + 40, current_pos.y())

        self.exit_anim = QPropertyAnimation(self, b"pos")
        self.exit_anim.setDuration(500)
        self.exit_anim.setStartValue(current_pos)
        self.exit_anim.setEndValue(exit_pos)
        self.exit_anim.setEasingCurve(QEasingCurve.InCubic)

        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(400)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)

        self.exit_anim.finished.connect(self.close)

        self.exit_anim.start()
        self.fade_out.start()

    @staticmethod
    def show_notification(text, parent=None, notification_type="info"):
        """显示Toast通知"""
        toast = ToastNotification(text, parent, notification_type)
        return toast
