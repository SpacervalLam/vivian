"""
优化版的输入对话框 - 提供更美观、更流畅的用户体验
包含Dracula Dark Theme风格、平滑动画、更好的视觉反馈
"""

from PyQt5.QtCore import (
    QPropertyAnimation, QEasingCurve, QPoint, QRect, Qt,
    QTimer, pyqtSignal, QSize
)
from PyQt5.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QIcon, QPixmap, QFontMetrics, QLinearGradient, QTransform
from PyQt5.QtWidgets import (
    QDialog, QFrame, QPushButton, QLineEdit, QHBoxLayout,
    QVBoxLayout, QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)

from loguru import logger
from ui.styles import get_input_dialog_style


class ModernInputDialog(QDialog):
    """现代化输入对话框 - Glassmorphism风格"""
    
    # 发送信号
    send_message = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("与薇薇安对话")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        
        # 设置尺寸
        self.width = 600
        self.height = 100
        self.setFixedSize(self.width, self.height + 30)  # 预留阴影空间
        
        # 初始化UI
        self._init_ui()
        self._init_animations()
        
    def _init_ui(self):
        """初始化界面"""
        # 创建主容器
        self.container = QFrame(self)
        self.container.setObjectName("MainContainer")
        self.container.setGeometry(15, 15, self.width - 30, self.height)
        
        # 设置样式
        self._apply_style()
        
        # 创建布局
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(20, 10, 15, 10)
        layout.setSpacing(15)
        
        # 输入框
        self.input_field = CustomLineEdit()
        layout.addWidget(self.input_field)
        
        # 语音按钮
        self.voice_btn = AnimatedButton(icon_type="mic")
        layout.addWidget(self.voice_btn)
        
        # 发送按钮
        self.send_btn = AnimatedButton(icon_type="send")
        layout.addWidget(self.send_btn)
        
        # 添加阴影效果
        self._add_shadow()
        
    def _apply_style(self):
        """应用样式"""
        self.container.setStyleSheet(get_input_dialog_style())
        
    def _add_shadow(self):
        """添加阴影效果"""
        self.shadow = QGraphicsDropShadowEffect(self.container)
        self.shadow.setBlurRadius(30)
        self.shadow.setOffset(0, 6)
        self.shadow.setColor(QColor(0, 0, 0, 120))
        self.container.setGraphicsEffect(self.shadow)
        
    def _init_animations(self):
        """初始化动画"""
        # 按钮动画
        self.input_field.focus_in.connect(lambda: self._highlight_container(True))
        self.input_field.focus_out.connect(lambda: self._highlight_container(False))
        
        # 按钮点击动画
        self.send_btn.clicked.connect(self._on_send)
        self.voice_btn.clicked.connect(self._on_voice_click)
        
    def _highlight_container(self, has_focus):
        """高亮容器"""
        if has_focus:
            self.shadow.setColor(QColor(0, 173, 181, 140))
            self.shadow.setBlurRadius(40)
        else:
            self.shadow.setColor(QColor(0, 0, 0, 120))
            self.shadow.setBlurRadius(30)
    
    def _on_send(self):
        """发送按钮点击"""
        text = self.input_field.text().strip()
        if text:
            self.send_message.emit(text)
            self.input_field.clear()
    
    def _on_voice_click(self):
        """语音按钮点击"""
        logger.debug("语音按钮点击")
        pass
    
    def show(self):
        """显示对话框（带动画）"""
        screen = self.parent().screen().geometry()
        x = (screen.width() - self.width) // 2
        y = (screen.height() - self.height) // 2 + 150
        
        self.move(x, y + 40)
        super().show()
        
        # 播放入场动画
        self._play_enter_animation(x, y)
        
    def _play_enter_animation(self, target_x, target_y):
        """播放入场动画"""
        self.setWindowOpacity(0)
        
        # 透明度动画
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # 位移动画
        self.move_anim = QPropertyAnimation(self, b"pos")
        self.move_anim.setDuration(300)
        self.move_anim.setStartValue(QPoint(target_x, target_y + 40))
        self.move_anim.setEndValue(QPoint(target_x, target_y))
        self.move_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        self.fade_anim.start()
        self.move_anim.start()
        
        # 自动聚焦
        QTimer.singleShot(150, self.input_field.setFocus)
        
    def keyPressEvent(self, event):
        """键盘事件处理"""
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Return and event.modifiers() == Qt.NoModifier:
            self._on_send()
        else:
            super().keyPressEvent(event)


class CustomLineEdit(QLineEdit):
    """自定义输入框 - 带有焦点动画"""
    
    focus_in = pyqtSignal()
    focus_out = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("说点什么吧...")
        
    def focusInEvent(self, event):
        """获得焦点"""
        super().focusInEvent(event)
        self.focus_in.emit()
        
    def focusOutEvent(self, event):
        """失去焦点"""
        super().focusOutEvent(event)
        self.focus_out.emit()


class AnimatedButton(QPushButton):
    """带动画效果的按钮"""
    
    def __init__(self, icon_type="send", parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedSize(50, 50)
        self.setObjectName(f"AnimatedBtn_{icon_type}")
        
        # 设置图标
        self._set_icon()
        
        # 设置样式
        self._set_style()
        
        # 初始化动画效果
        self.effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.effect)
        
    def _set_icon(self):
        """设置图标"""
        if self.icon_type == "send":
            pixmap = self._create_arrow_icon()
        else:
            pixmap = self._create_mic_icon()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(24, 24))
        
    def _create_arrow_icon(self):
        """创建箭头图标"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        
        color = QColor(255, 255, 255, 230)
        p.setBrush(color)
        
        path = QPainterPath()
        path.moveTo(8, 16)
        path.lineTo(16, 8)
        path.lineTo(16, 12)
        path.lineTo(24, 12)
        path.lineTo(24, 20)
        path.lineTo(16, 20)
        path.lineTo(16, 24)
        path.lineTo(8, 16)
        
        p.drawPath(path)
        p.end()
        return pixmap
        
    def _create_mic_icon(self):
        """创建麦克风图标"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        
        color = QColor(255, 255, 255, 230)
        p.setBrush(color)
        
        center = 16
        
        body_w = 8
        body_h = 14
        body_x = center - body_w / 2
        body_y = 5
        
        path = QPainterPath()
        path.addRoundedRect(body_x, body_y, body_w, body_h, 4, 4)
        
        stand_w = 16
        stand_h = 10
        stand_x = center - stand_w / 2
        stand_y = body_y + body_h - 2
        
        path.arcMoveTo(stand_x, stand_y, stand_w, stand_h, 0)
        path.arcTo(stand_x, stand_y, stand_w, stand_h, 0, -180)
        
        stem_w = 2
        stem_h = 5
        stem_x = center - stem_w / 2
        stem_y = stand_y + stand_h * 0.55
        
        path.addRoundedRect(stem_x, stem_y, stem_w, stem_h, 1, 1)
        
        base_w = 10
        base_h = 3
        base_x = center - base_w / 2
        base_y = stem_y + stem_h + 1
        
        path.addRoundedRect(base_x, base_y, base_w, base_h, 1.5, 1.5)
        
        p.drawPath(path)
        p.end()
        return pixmap
        
    def _set_style(self):
        """设置样式"""
        style = """
        QPushButton {
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 25px;
        }
        
        QPushButton:hover {
            background-color: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.18);
        }
        
        QPushButton:pressed {
            background-color: rgba(0, 173, 181, 0.3);
            border: 1px solid rgba(0, 173, 181, 0.4);
        }
        """
        self.setStyleSheet(style)


class MessageBubble(QDialog):
    """消息气泡"""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._init_ui()

    def _init_ui(self):
        """初始化界面 - 优化组件层级"""
        from PyQt5.QtWidgets import QLabel

        self.container = QFrame(self)
        self.container.setObjectName("BubbleContainer")

        self.label = QLabel(self.text, self.container)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setAttribute(Qt.WA_TranslucentBackground, True)

        font = QFont("SF Pro Display", 15, QFont.Medium)
        font.setFamily("SF Pro Display, PingFang SC, Microsoft YaHei UI, Segoe UI, sans-serif")
        font.setLetterSpacing(QFont.PercentageSpacing, 102)
        self.label.setFont(font)

        self._set_style()
        self._calculate_size()
        self._add_shadow()

    def _calculate_size(self):
        """自适应尺寸计算 - 优化留白比例与最大宽度限制"""
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        screen = None

        if self.parent() is not None and hasattr(self.parent(), "screen"):
            try:
                screen = self.parent().screen()
            except Exception:
                screen = None
        if screen is None and app is not None:
            screen = app.primaryScreen()

        screen_width = 1920
        if screen is not None:
            screen_width = screen.availableGeometry().width()

        max_content_width = int(min(580, screen_width * 0.4))
        min_content_width = 120

        padding_x = 28
        padding_y = 14
        edge_margin = 12

        metrics = QFontMetrics(self.label.font())
        text_width = max_content_width - 2 * padding_x
        
        # 使用更精确的文本高度计算方法
        text_rect = metrics.boundingRect(
            0,
            0,
            text_width,
            0,
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop,
            self.text,
        )

        content_width = min(max(text_rect.width(), min_content_width), text_width)
        content_height = text_rect.height()

        # 精确计算最小高度：只包含一行文字+固定上下留白
        min_content_height = metrics.height()
        content_height = max(content_height, min_content_height)

        self.label.setFixedWidth(content_width)
        self.label.setFixedHeight(content_height)  # 使用固定高度确保留白正确

        # 固定留白，不随内容高度变化
        self.container.setFixedSize(
            content_width + 2 * padding_x,
            content_height + 2 * padding_y
        )
        self.setFixedSize(
            self.container.width() + 2 * edge_margin,
            self.container.height() + 2 * edge_margin
        )

        self.container.move(edge_margin, edge_margin)
        self.label.move(padding_x, padding_y)

    def _set_style(self):
        """应用 Dracula Dark Theme 样式"""
        from ui.styles import get_message_bubble_style
        self.container.setStyleSheet(get_message_bubble_style())

    def _add_shadow(self):
        """添加阴影效果"""
        self.shadow = QGraphicsDropShadowEffect(self.container)
        self.shadow.setBlurRadius(28)
        self.shadow.setOffset(0, 10)
        self.shadow.setColor(QColor(99, 40, 180, 60))
        
        self.inner_shadow = QGraphicsDropShadowEffect()
        self.inner_shadow.setBlurRadius(12)
        self.inner_shadow.setOffset(0, 4)
        self.inner_shadow.setColor(QColor(0, 0, 0, 25))
        
        self.container.setGraphicsEffect(self.shadow)

    def paintEvent(self, event):
        """绘制气泡尾巴装饰"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        tail_width = 20
        tail_height = 14
        tail_x = self.container.width() // 2 - tail_width // 2 + 12
        tail_y = self.container.height() + 2
        
        gradient = QLinearGradient(tail_x, tail_y, tail_x, tail_y + tail_height)
        gradient.setColorAt(0, QColor(168, 85, 247, 217))  # 0.85 * 255 = 217
        gradient.setColorAt(1, QColor(192, 132, 252, 153))  # 0.6 * 255 = 153
        
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        
        path = QPainterPath()
        path.moveTo(tail_x, tail_y)
        path.lineTo(tail_x + tail_width // 2, tail_y + tail_height)
        path.lineTo(tail_x + tail_width, tail_y)
        path.closeSubpath()
        
        painter.drawPath(path)
        
        shadow_painter = QPainter(self)
        shadow_painter.setRenderHint(QPainter.Antialiasing)
        shadow_painter.setBrush(QColor(99, 40, 180, 30))
        shadow_painter.setPen(Qt.NoPen)
        
        shadow_path = QPainterPath()
        shadow_path.moveTo(tail_x + 2, tail_y + 2)
        shadow_path.lineTo(tail_x + tail_width // 2, tail_y + tail_height + 3)
        shadow_path.lineTo(tail_x + tail_width - 2, tail_y + 2)
        shadow_path.closeSubpath()
        
        shadow_painter.drawPath(shadow_path)
        
        super().paintEvent(event)

    def show(self):
        """显示气泡"""
        self.setWindowOpacity(0)
        super().show()
        self._play_enter_animation()

    def _play_enter_animation(self):
        """入场动画优化 - 淡入效果"""
        self.setWindowOpacity(0)
        
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(350)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuart)
        self.fade_anim.start()

    def close(self):
        """关闭动画优化 - 淡出效果"""
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(250)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InOutCubic)

        self.fade_out.finished.connect(super().close)
        self.fade_out.start()

    def mousePressEvent(self, event):
        """点击关闭气泡"""
        QTimer.singleShot(100, self.close)
        super().mousePressEvent(event)
