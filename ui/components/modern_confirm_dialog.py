"""现代化确认对话框组件"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSpacerItem, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize


class ModernConfirmDialog(QDialog):
    """确认对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(360)

        self._result = False

    @staticmethod
    def confirm(
        parent=None,
        title="确认",
        message="确定要执行此操作吗？",
        confirm_text="确定",
        cancel_text="取消",
        icon_type="question"
    ):
        """
        显示确认对话框
        
        Args:
            parent: 父窗口
            title: 标题
            message: 消息内容
            confirm_text: 确认按钮文本
            cancel_text: 取消按钮文本
            icon_type: 图标类型

        Returns:
            bool: 用户是否确认
        """
        dialog = ModernConfirmDialog(parent)
        dialog._setup_ui(title, message, confirm_text, cancel_text, icon_type)
        dialog.exec_()
        return dialog._result

    def _setup_ui(self, title, message, confirm_text, cancel_text, icon_type):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        content_frame = QFrame()
        content_frame.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 16px;
                border: 1px solid #E8E8E8;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            }
        """)
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(20)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                color: #333333;
                font-size: 18px;
                font-weight: 600;
            }
        """)
        title_label.setAlignment(Qt.AlignCenter)

        icon_pixmap = self._get_icon_pixmap(icon_type)

        message_label = QLabel(message)
        message_label.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        if cancel_text:
            cancel_btn = QPushButton(cancel_text)
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background-color: #F5F5F5;
                    color: #666666;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 24px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #EEEEEE;
                }
                QPushButton:pressed {
                    background-color: #E0E0E0;
                }
            """)
            cancel_btn.clicked.connect(self._on_cancel)
            button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton(confirm_text)
        confirm_color = self._get_confirm_color(icon_type)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {confirm_color};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                opacity: 0.8;
            }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        button_layout.addWidget(confirm_btn)

        content_layout.addWidget(title_label)
        content_layout.addWidget(message_label)
        content_layout.addLayout(button_layout)

        layout.addWidget(content_frame)

    def _get_icon_pixmap(self, icon_type):
        """获取图标"""
        try:
            icon_paths = {
                "question": ":/icons/question.png",
                "success": ":/icons/success.png",
                "error": ":/icons/error.png",
                "warning": ":/icons/warning.png",
            }
            if icon_type in icon_paths:
                return QPixmap(icon_paths[icon_type]).scaled(48, 48, Qt.KeepAspectRatio)
        except Exception:
            pass
        return None

    def _get_confirm_color(self, icon_type):
        """获取确认按钮颜色"""
        colors = {
            "question": "#4A90D9",
            "success": "#52C41A",
            "error": "#FF4D4F",
            "warning": "#FAAD14",
        }
        return colors.get(icon_type, "#4A90D9")

    def _on_confirm(self):
        self._result = True
        self.close()

    def _on_cancel(self):
        self._result = False
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.m_drag = True
            self.m_drag_pos = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if Qt.LeftButton and self.m_drag:
            self.move(event.globalPos() - self.m_drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.m_drag = False