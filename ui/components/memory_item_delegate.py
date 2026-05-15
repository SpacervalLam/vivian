import os
import sys

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMenu, QMessageBox, QPushButton, QTextEdit, QVBoxLayout,
                             QWidget)

# 导入翻译函数
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.i18n import _

# 导入ToastNotification类
from ui.toast_notification import ToastNotification

# 将项目根目录添加到Python路径
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)




COLORS = {
    'bg_main': 'rgb(40, 44, 52)',
    'bg_sidebar': 'rgb(33, 37, 43)',
    'bg_card': 'rgb(44, 49, 58)',
    'bg_input': 'rgb(27, 29, 35)',
    'accent_purple': 'rgb(189, 147, 249)',
    'accent_pink': 'rgb(255, 121, 198)',
    'text_main': 'rgb(221, 221, 221)',
    'text_secondary': 'rgb(113, 126, 149)',
    'border': 'rgb(44, 49, 58)',
    'border_focus': 'rgb(91, 101, 124)',
}


class MemoryItemDelegate(QWidget):
    """
    记忆详情渲染器组件
    展示记忆详细内容，支持回放、删除和加星操作
    """

    def __init__(self, memory_manager=None):
        super().__init__()
        self.memory_manager = memory_manager
        self.init_ui()

        # 记忆数据
        self.memories = []

        # 当前选中的记忆
        self.current_memory = None

    def init_ui(self):
        """
        初始化UI
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            0, 0, 0, 0
        )

        # 搜索和筛选栏
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(5, 5, 5, 5)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_("search_memory_content"))
        self.search_edit.textChanged.connect(self.filter_memories)
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                color: {COLORS['text_main']};
                font-size: 17px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['accent_purple']};
            }}
            QLineEdit::placeholder {{
                color: {COLORS['text_secondary']};
            }}
        """)
        filter_layout.addWidget(self.search_edit)

        # 重要性筛选
        self.importance_filter = QComboBox()
        self.importance_filter.addItems(
            [_("all_importance"), _("high_importance"), _("medium_importance"), _("low_importance")]
        )
        self.importance_filter.currentTextChanged.connect(self.filter_memories)
        self.importance_filter.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                color: {COLORS['text_main']};
                font-size: 17px;
                min-width: 120px;
            }}
            QComboBox:focus {{
                border-color: {COLORS['accent_purple']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS['bg_sidebar']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
            }}
        """)
        filter_layout.addWidget(self.importance_filter)

        layout.addLayout(filter_layout)

        # 记忆列表
        self.memory_list = QListWidget()
        self.memory_list.setFrameShape(QListWidget.NoFrame)
        self.memory_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)

        # 列表样式：深色主题
        self.memory_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                outline: none;
            }}
            QListWidget::item {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                margin-bottom: 10px;
                margin-right: 5px;
            }}
            QListWidget::item:hover {{
                background-color: rgb(57, 65, 80);
                border-color: {COLORS['border_focus']};
            }}
            QListWidget::item:selected {{
                background-color: rgba(189, 147, 249, 0.15);
                border-color: {COLORS['accent_purple']};
            }}
        """)

        # 连接点击事件
        self.memory_list.itemClicked.connect(self.on_memory_selected)
        self.memory_list.itemClicked.connect(self._on_item_clicked)

        # 设置右键菜单
        self.memory_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.memory_list.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.memory_list, 1)

        # 操作按钮组
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(5, 5, 5, 5)

        # 删除按钮
        self.delete_button = QPushButton(_("delete_memory"))
        self.delete_button.clicked.connect(self.on_delete_memory)
        self.delete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_main']};
                padding: 8px 16px;
                font-size: 17px;
            }}
            QPushButton:hover {{
                background-color: rgb(57, 65, 80);
                border-color: {COLORS['border_focus']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['bg_input']};
            }}
        """)
        action_layout.addWidget(self.delete_button)

        # 刷新按钮
        self.refresh_button = QPushButton(_("refresh"))
        self.refresh_button.clicked.connect(self.update_memory_list)
        self.refresh_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                color: {COLORS['text_main']};
                padding: 8px 16px;
                font-size: 17px;
            }}
            QPushButton:hover {{
                background-color: rgb(57, 65, 80);
                border-color: {COLORS['border_focus']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['bg_input']};
            }}
        """)
        action_layout.addWidget(self.refresh_button)

        action_layout.addStretch()
        layout.addLayout(action_layout)

    def init_property_labels(self):
        """初始化属性标签"""
        # 创建属性标签
        properties = [
            (f"{_('memory_id')}:", "id_label"),
            (f"{_('memory_type')}:", "type_label"),
            (f"{_('importance')}:", "importance_label"),
            ("创建时间:", "created_label"),
            ("更新时间:", "updated_label"),
            (f"{_('source_channel')}:", "source_label"),
            (f"{_('tags')}:", "tags_label"),
            ("令牌数:", "token_label"),
        ]

        # 存储标签引用
        self.property_labels = {}

        for i, (label_text, label_name) in enumerate(properties):
            # 属性名称标签
            name_label = QLabel(label_text)
            name_label.setFont(QFont("Arial", 9, QFont.Bold))
            self.properties_grid.addWidget(name_label, i, 0)

            value_label = QLabel("-")
            value_label.setWordWrap(True)
            self.property_labels[label_name] = value_label
            self.properties_grid.addWidget(value_label, i, 1)

    def update_data(self, memories):
        """更新记忆数据"""
        self.memories = memories
        self.update_memory_list()

    def update_memory_list(self, search_text=""):
        """
        更新记忆列表
        """
        # 清空列表
        self.memory_list.clear()

        # 添加记忆项
        for memory in self.memories:
            self._add_memory_item(memory, search_text)

    def _add_memory_item(self, memory, search_text=""):
        """
        添加单个记忆项到列表
        支持对象格式和字典格式的记忆数据
        """
        item = QListWidgetItem()

        is_dict = isinstance(memory, dict)
        
        if is_dict:
            memory_class_name = memory.get("memory_type", "LongTermMemory")
            if memory_class_name == "长期偏好":
                memory_type = _("long_term_memory")
            else:
                memory_type = _("long_term_memory")
        else:
            memory_class_name = memory.__class__.__name__
            memory_type = (
                _("short_term_memory") if memory_class_name == "ShortTermMemory" else _("long_term_memory")
            )

        if is_dict:
            role = memory.get("role", "user")
            content = memory.get("content", "")
        else:
            role = getattr(memory, "role", "user")
            content = memory.content
            
        color_bar_color = "#2ecc71" if role == "user" else COLORS['accent_purple']

        if content.startswith("User: "):
            content = content[6:]
        elif content.startswith("AI: "):
            content = content[4:]
        
        # 处理摘要，用紫色标出搜索关键词
        if len(content) > 100:
            summary = content[:100] + "..."
        else:
            summary = content
        
        if search_text:
            search_text_lower = search_text.lower()
            content_lower = summary.lower()
            result = ""
            i = 0
            while i < len(summary):
                if content_lower[i:i+len(search_text_lower)] == search_text_lower:
                    result += f"<span style='color: {COLORS['accent_pink']}; font-weight: bold;'>{summary[i:i+len(search_text_lower)]}</span>"
                    i += len(search_text_lower)
                else:
                    result += summary[i]
                    i += 1
            summary = result

        item_widget = QWidget()
        item_widget.setStyleSheet(f"background-color: {COLORS['bg_card']}; border-radius: 8px;")
        
        main_layout = QHBoxLayout(item_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧颜色条
        color_bar = QWidget()
        color_bar.setStyleSheet(f"background-color: {color_bar_color}; border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
        color_bar.setFixedWidth(4)
        main_layout.addWidget(color_bar)

        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {COLORS['bg_card']}; border-top-right-radius: 8px; border-bottom-right-radius: 8px;")
        item_layout = QVBoxLayout(content_widget)
        item_layout.setContentsMargins(12, 12, 12, 12)
        item_layout.setSpacing(6)

        top_row = QHBoxLayout()

        is_short_term = (not is_dict and memory_class_name == "ShortTermMemory")
        
        if not is_short_term:
            if is_dict:
                importance = memory.get("importance", 0.5)
            else:
                importance = memory.importance
            importance_color = self._get_importance_color(importance)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {importance_color}; font-size: 16px;")
            top_row.addWidget(dot)

        type_lbl = QLabel(memory_type.upper())
        type_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 16px; font-weight: bold;")
        top_row.addWidget(type_lbl)

        top_row.addStretch()

        if is_dict:
            time_str = memory.get("created_at", "")
            if not time_str:
                time_str = "未知时间"
            elif len(time_str) > 16:
                time_str = time_str[:16]
        else:
            if hasattr(memory, "created_at") and memory.created_at:
                time_str = memory.created_at.strftime("%Y-%m-%d %H:%M")
            else:
                time_str = "未知时间"
                
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 16px;")
        top_row.addWidget(time_lbl)

        item_layout.addLayout(top_row)

        content_label = QLabel()
        content_label.setWordWrap(False)
        content_label.setStyleSheet(f"font-size: 18px; line-height: 22px; color: {COLORS['text_main']};")
        
        if search_text:
            content_label.setTextFormat(Qt.RichText)
            content_label.setText(summary)
        else:
            font = QFont("Microsoft YaHei", 18)
            fm = QFontMetrics(font)
            max_width = 600
            elided_text = fm.elidedText(summary, Qt.ElideRight, max_width)
            content_label.setText(elided_text)
        
        item_layout.addWidget(content_label)

        main_layout.addWidget(content_widget)
        main_layout.setStretchFactor(content_widget, 1)

        fixed_height = 95
        item.setSizeHint(QSize(0, fixed_height))
        self.memory_list.addItem(item)
        self.memory_list.setItemWidget(item, item_widget)

        item.setData(Qt.UserRole, memory)

    def _on_item_clicked(self, item):
        """当列表项被点击时调用"""
        memory_data = item.data(Qt.UserRole)
        window = self.window()
        if hasattr(window, "show_detail_mode") and hasattr(window, "detail_view"):
            window.detail_view.update_display(memory_data)
            window.show_detail_mode()

    def on_memory_selected(self, item):
        """处理记忆选中事件"""
        memory = item.data(Qt.UserRole)
        self.current_memory = memory

        self.update_memory_details(memory)

    def update_memory_details(self, memory):
        """更新记忆详细信息"""
        pass

    def _get_importance_color(self, importance):
        """根据重要性获取颜色"""
        if importance > 0.7:
            return "#e74c3c"
        elif importance > 0.3:
            return "#f39c12"
        else:
            return "#2ecc71"

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.memory_list.itemAt(pos)
        if not item:
            return

        self.current_memory = item.data(Qt.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['bg_sidebar']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QMenu::item {{
                padding: 10px 30px;
                font-size: 17px;
                color: {COLORS['text_main']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['bg_card']};
                color: {COLORS['accent_purple']};
            }}
        """)

        delete_action = menu.addAction(_("delete_memory"))
        delete_action.triggered.connect(self.on_delete_memory)

        menu.exec_(self.memory_list.mapToGlobal(pos))

    def on_delete_memory(self):
        """
        处理删除操作
        """
        if not self.current_memory:
            from ui.components.modern_confirm_dialog import ModernConfirmDialog
            ModernConfirmDialog.confirm(
                self,
                title=_("warning"),
                message=_("please_select_memory"),
                confirm_text=_("ok"),
                cancel_text="",
                icon_type="warning"
            )
            return

        memory_type = (
            "short_term"
            if self.current_memory.__class__.__name__ == "ShortTermMemory"
            else "long_term"
        )

        try:
            # 获取存储对象并删除
            if memory_type == "short_term":
                self.memory_manager.short_term_store.delete_memory(
                    self.current_memory.id
                )
            else:
                self.memory_manager.long_term_store.delete_memory(self.current_memory.id)
                if hasattr(self.memory_manager, "chroma_store"):
                    self.memory_manager.chroma_store.delete_memory(
                        self.current_memory.id
                    )

            self.memories = [
                mem for mem in self.memories if mem.id != self.current_memory.id
            ]

            self.update_memory_list()

            ToastNotification.show_notification(_("delete_success"), self, "success")
        except Exception as e:
            ToastNotification.show_notification(
                _("delete_failed", error=str(e)), self, "error"
            )

    def reset_property_labels(self):
        """重置属性标签"""
        pass

    def filter_memories(self):
        """筛选记忆"""
        search_text = self.search_edit.text().lower()
        importance_filter = self.importance_filter.currentText()

        self.memory_list.clear()

        for memory in self.memories:
            is_dict = isinstance(memory, dict)
            
            if is_dict:
                content = memory.get("content", "")
                memory_class_name = memory.get("memory_type", "LongTermMemory")
                importance = memory.get("importance", 0.5)
            else:
                content = memory.content
                memory_class_name = memory.__class__.__name__
                importance = memory.importance if hasattr(memory, "importance") else 0.5
            
            if search_text and search_text not in content.lower():
                continue

            is_short_term = (not is_dict and memory_class_name == "ShortTermMemory")
            if not is_short_term:
                if importance_filter == _("high_importance") and importance <= 0.7:
                    continue
                elif importance_filter == _("medium_importance") and (
                    importance < 0.3 or importance > 0.7
                ):
                    continue
                elif importance_filter == _("low_importance") and importance >= 0.3:
                    continue

            self._add_memory_item(memory, search_text)
