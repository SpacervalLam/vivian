import os
import sys

from PyQt5.QtCore import QPoint, QRect, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QCursor, QFont, QIcon, QPainter, QPen
from PyQt5.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QMainWindow,
                             QProgressBar, QPushButton, QScrollArea,
                             QSizePolicy, QSpacerItem, QSplitter,
                             QStackedWidget, QStyleFactory, QTabWidget,
                             QTextEdit, QVBoxLayout, QWidget)
from loguru import logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.i18n import _

from ui.components.memory_item_delegate import MemoryItemDelegate


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

MODERN_STYLE = f"""
QWidget {{
    font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
    font-size: 18px;
    color: {COLORS['text_main']};
    outline: none;
}}

#MainContent {{
    background-color: {COLORS['bg_main']};
    border-radius: 16px;
    padding: 14px;
}}

.WhiteCard {{
    background-color: {COLORS['bg_sidebar']};
    border-radius: 12px;
    border: 1px solid {COLORS['border']};
    padding: 20px;
    margin: 8px;
}}

#TitleBar {{
    background-color: transparent;
    border-bottom: 1px solid {COLORS['border']};
}}

#TitleLabel {{
    font-size: 26px;
    font-weight: bold;
    color: {COLORS['text_main']};
}}

QPushButton {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    color: {COLORS['text_main']};
    padding: 12px 24px;
    font-weight: 500;
    font-size: 18px;
    min-height: 45px;
    margin: 6px;
}}

QPushButton:hover {{
    color: {COLORS['accent_purple']};
    border-color: {COLORS['accent_purple']};
    background-color: rgba(189, 147, 249, 0.1);
}}

QPushButton:pressed {{
    background-color: {COLORS['accent_purple']};
    color: #FFFFFF;
    border-color: {COLORS['accent_purple']};
}}

QPushButton#DangerBtn {{
    color: #F56C6C;
    border-color: rgba(245, 108, 108, 0.3);
    background-color: rgba(245, 108, 108, 0.1);
    font-size: 18px;
}}

QPushButton#DangerBtn:hover {{
    background-color: #F56C6C;
    color: #FFFFFF;
    border-color: #F56C6C;
}}

QPushButton#PrimaryBtn {{
    background-color: {COLORS['accent_purple']};
    color: #FFFFFF;
    border: none;
    font-size: 18px;
}}

QPushButton#PrimaryBtn:hover {{
    background-color: rgb(195, 155, 255);
}}

#CloseButton {{
    background-color: transparent;
    color: {COLORS['text_secondary']};
    font-size: 31px;
    font-weight: bold;
    border: none;
    border-radius: 15px;
    min-height: 30px;
    min-width: 30px;
    padding: 0;
    margin: 0;
    vertical-align: middle;
    text-align: center;
}}

#CloseButton:hover {{
    background-color: rgba(245, 108, 108, 0.2);
    color: #F56C6C;
}}

#CloseButton:pressed {{
    background-color: #F56C6C;
    color: white;
}}

QTabWidget {{
    margin: 8px;
}}

QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    background: {COLORS['bg_input']};
    border-radius: 10px;
    top: -1px; 
    padding: 12px;
}}

QTabBar::tab {{
    background: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    color: {COLORS['text_secondary']};
    padding: 12px 20px;
    margin-right: 4px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    font-size: 18px;
    min-width: 120px;
}}

QTabBar::tab:selected {{
    background: {COLORS['bg_input']};
    color: {COLORS['accent_purple']};
    border-bottom-color: {COLORS['bg_input']};
    font-weight: bold;
}}

QTabBar::tab:hover {{
    color: {COLORS['accent_purple']};
}}

QScrollBar:vertical {{
    border: none;
    background: {COLORS['bg_card']};
    width: 10px;
    margin: 6px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['accent_purple']};
    min-height: 36px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgb(200, 160, 255);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QListWidget, QTableWidget, QTreeWidget {{
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 8px;
    background: {COLORS['bg_input']};
    color: {COLORS['text_main']};
}}

QLabel {{
    margin: 4px;
}}

QFrame[frameShape="HLine"], QFrame[frameShape="VLine"] {{
    background-color: {COLORS['border']};
    margin: 12px 0;
}}

QGroupBox {{
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 12px;
    margin: 6px;
    background-color: {COLORS['bg_sidebar']};
}}

QGroupBox::title {{
    color: {COLORS['accent_purple']};
    font-weight: bold;
    padding: 0 8px;
    top: -12px;
}}

QLineEdit {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 12px;
    background: {COLORS['bg_input']};
    font-size: 18px;
    color: {COLORS['text_main']};
    margin: 6px;
}}

QLineEdit:focus {{
    border-color: {COLORS['accent_purple']};
    outline: none;
}}

QComboBox {{
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 12px;
    background: {COLORS['bg_input']};
    font-size: 18px;
    color: {COLORS['text_main']};
    margin: 6px;
}}

QComboBox:focus {{
    border-color: {COLORS['accent_purple']};
    outline: none;
}}
"""


class MemoryDataLoader(QThread):
    """异步加载记忆数据的线程"""

    data_loaded = pyqtSignal(dict)
    loading_progress = pyqtSignal(int)

    def __init__(self, memory_manager, time_stamped_memory=None, max_items=50):
        super().__init__()
        self.memory_manager = memory_manager
        self.time_stamped_memory = time_stamped_memory
        self.max_items = max_items

    def run(self):
        try:
            if not self.memory_manager:
                return
            self.loading_progress.emit(10)

            all_short_term = (
                self.memory_manager.list_short_term_memories()
                if hasattr(self.memory_manager, "list_short_term_memories")
                else []
            )
            self.loading_progress.emit(30)

            all_long_term = (
                self.memory_manager.list_long_term_memories()
                if hasattr(self.memory_manager, "list_long_term_memories")
                else []
            )
            self.loading_progress.emit(50)

            all_long_term_preferences = []
            if self.time_stamped_memory and hasattr(self.time_stamped_memory, "long_term_preferences"):
                for pref in self.time_stamped_memory.long_term_preferences:
                    memory_dict = {
                        "id": f"pref_{pref.extracted_at.timestamp()}",
                        "content": pref.content,
                        "created_at": pref.extracted_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "memory_type": "长期偏好",
                        "importance": pref.confidence,
                        "source": "preference",
                        "tags": ["preference"],
                        "emotion": "",
                    }
                    all_long_term_preferences.append(memory_dict)
            self.loading_progress.emit(70)

            all_memories = all_short_term + all_long_term + all_long_term_preferences

            self.loading_progress.emit(90)

            data = {
                "memories": all_memories,
                "short_term": all_short_term,
                "mid_term": [],
                "long_term": all_long_term,
                "long_term_preferences": all_long_term_preferences,
            }

            self.data_loaded.emit(data)
            self.loading_progress.emit(100)

        except Exception as e:
            logger.error(f"数据加载错误: {e}")


class MemoryDetailPanel(QFrame):
    """记忆详细档案面板"""

    def __init__(self):
        super().__init__()
        self.setProperty("class", "WhiteCard")
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(18)

        self.info_container = QWidget()
        self.info_layout = QVBoxLayout(self.info_container)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(15)
        self.main_layout.addWidget(self.info_container)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        self.main_layout.addWidget(line)

        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setPlaceholderText(_("select_memory_to_view_details"))
        self.content_display.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {COLORS['border']};
                background-color: {COLORS['bg_input']};
                border-radius: 8px;
                padding: 15px;
                font-size: 19px;
                color: {COLORS['text_main']};
                line-height: 1.6;
            }}
            QTextEdit::placeholder {{
                color: {COLORS['text_secondary']};
            }}
        """)
        self.main_layout.addWidget(self.content_display)

    def update_display(self, memory):
        """刷新显示的数据"""
        while self.info_layout.count():
            child = self.info_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if isinstance(memory, dict):
            data = memory
            memory_id = data.get("id", "N/A")
            source = data.get("source", "chat")
            importance = data.get("importance", 0.5)
            heat = data.get("heat", 0.0)
            created_at = data.get("created_at", "")
            tags = data.get("tags", [])
            content = data.get("content", "")
            memory_type = data.get("memory_type", "未知")
            emotion = data.get("emotion", "")
        else:
            data = memory.__dict__
            memory_id = memory.id
            source = memory.source or "chat"
            importance = memory.importance
            heat = getattr(memory, "heat", 0.0)
            created_at = memory.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(memory, "created_at") else ""
            tags = memory.tags if hasattr(memory, "tags") else []
            content = memory.content if hasattr(memory, "content") else ""
            if content.startswith("User: "):
                content = content[6:]
            elif content.startswith("AI: "):
                content = content[4:]
            emotion = memory.emotion if hasattr(memory, "emotion") else ""
            
            class_name = memory.__class__.__name__
            if class_name == "ShortTermMemory":
                memory_type = "短期记忆"
            elif class_name == "MidTermMemory":
                memory_type = "中期记忆"
            elif class_name == "LongTermMemory":
                memory_type = "长期记忆"
            else:
                memory_type = "未知"

        if memory_type == "短期记忆":
            type_color = "#3498db"
        elif memory_type == "中期记忆":
            type_color = "#f39c12"
        else:
            type_color = "#2ecc71"

        if importance > 0.7:
            importance_color = "#e74c3c"
        elif importance > 0.3:
            importance_color = "#f39c12"
        else:
            importance_color = "#2ecc71"

        stars = "★" * int(importance * 5)

        params = [
            ("记忆 ID:", memory_id),
            ("来源渠道:", source.upper()),
            ("记忆类型:", memory_type),
        ]
        
        if memory_type != "短期记忆":
            params.append(("重要程度:", f"{stars} {importance*100:.0f}%"))
        
        if heat > 0:
            params.append(("热度值:", f"{heat:.2f}"))
            
        params.extend([
            ("记录时间:", created_at),
            ("情绪标签:", emotion if emotion else "无"),
            ("标签:", ", ".join(tags) if tags else "无"),
        ])

        for k, v in params:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 8, 0, 8)

            key_label = QLabel(k)
            key_label.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 18px; font-weight: normal;"
            )

            value_label = QLabel(str(v))

            if k == "记忆类型":
                value_label.setStyleSheet(
                    f"color: {type_color}; font-size: 18px; font-weight: 600;"
                )
            elif k == "重要程度":
                value_label.setStyleSheet(
                    f"color: {importance_color}; font-size: 18px; font-weight: 600;"
                )
            else:
                value_label.setStyleSheet(
                    f"color: {COLORS['text_main']}; font-size: 18px; font-weight: 600;"
                )

            value_label.setAlignment(Qt.AlignRight)

            row_layout.addWidget(key_label)
            row_layout.addStretch()
            row_layout.addWidget(value_label)

            self.info_layout.addWidget(row_widget)

        self.content_display.setPlainText(content)


class ModernMemoryWindow(QMainWindow):
    """现代轻科技风格的记忆管理窗口"""

    def __init__(self, memory_manager, time_stamped_memory=None):
        super().__init__()
        self.memory_manager = memory_manager
        self.time_stamped_memory = time_stamped_memory
        self.setWindowTitle(_("vivian_memory_core"))
        self.resize(int(1400 * 1.2), int(980 * 1.2))

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.m_drag = False
        self.m_DragPosition = QPoint()

        self.init_ui()

        self.data_loader = MemoryDataLoader(self.memory_manager, self.time_stamped_memory)
        self.data_loader.data_loaded.connect(self.update_ui_data)
        self.data_loader.loading_progress.connect(self.update_progress)

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.load_memory_data)
        self.update_timer.start(30000)

        self.load_memory_data()

    def init_ui(self):
        """初始化现代UI结构"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)

        self.content_container = QFrame()
        self.content_container.setObjectName("MainContent")
        self.content_container.setStyleSheet(MODERN_STYLE)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 5)
        self.content_container.setGraphicsEffect(shadow)

        main_layout.addWidget(self.content_container)

        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.create_title_bar(content_layout)
        self.create_main_content(content_layout)

    def create_title_bar(self, parent_layout):
        """创建自定义标题栏"""
        title_bar = QFrame()
        title_bar.setObjectName("TitleBar")
        title_bar.setFixedHeight(70)

        hbox = QHBoxLayout(title_bar)
        hbox.setContentsMargins(28, 0, 20, 0)

        title_label = QLabel(_("memory_core"))
        title_label.setObjectName("TitleLabel")
        hbox.addWidget(title_label)

        hbox.addStretch()

        self.close_btn = QPushButton("×", self)
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        
        self.close_btn.setToolTip(_("close_window") if "_" in globals() else "关闭")
        
        self.close_btn.clicked.connect(self.close)
        
        hbox.addWidget(self.close_btn)
        hbox.setAlignment(self.close_btn, Qt.AlignVCenter)

        parent_layout.addWidget(title_bar)

    def create_main_content(self, parent_layout):
        """创建主要内容区域"""
        self.main_splitter = QSplitter(Qt.Horizontal)

        self.left_container = QFrame()
        self.left_container.setProperty("class", "WhiteCard")
        left_layout = QVBoxLayout(self.left_container)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(12)

        list_header = QLabel(_("memory_index"))
        list_header.setStyleSheet(
            f"font-weight: bold; font-size: 23px; color: {COLORS['text_main']}; margin-bottom: 8px;"
        )
        left_layout.addWidget(list_header)

        stats_container = QFrame()
        stats_container.setStyleSheet("background: transparent;")
        stats_layout = QHBoxLayout(stats_container)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(15)

        self.total_count_label = QLabel(_("total_memories").format(count=0))
        self.total_count_label.setStyleSheet(
            f"font-weight: bold; color: {COLORS['text_main']}; font-size: 18px;"
        )
        stats_layout.addWidget(self.total_count_label)

        self.short_term_label = QLabel("短期: 0")
        self.short_term_label.setStyleSheet("color: #3498db; font-size: 18px;")
        stats_layout.addWidget(self.short_term_label)

        self.mid_term_label = QLabel("中期: 0")
        self.mid_term_label.setStyleSheet("color: #f39c12; font-size: 18px;")
        stats_layout.addWidget(self.mid_term_label)

        self.long_term_label = QLabel("长期: 0")
        self.long_term_label.setStyleSheet("color: #2ecc71; font-size: 18px;")
        stats_layout.addWidget(self.long_term_label)

        stats_layout.addStretch()
        left_layout.addWidget(stats_container)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(
            f"QTabBar::tab {{ font-size: 18px; padding: 12px 18px; min-width: 130px; }}"
        )

        self.short_term_list = MemoryItemDelegate(self.memory_manager)
        self.mid_term_list = MemoryItemDelegate(self.memory_manager)
        self.long_term_list = MemoryItemDelegate(self.memory_manager)

        self.tab_widget.addTab(self.short_term_list, "短期记忆")
        self.tab_widget.addTab(self.mid_term_list, "中期记忆")
        self.tab_widget.addTab(self.long_term_list, "长期记忆")

        left_layout.addWidget(self.tab_widget)

        self.right_container = QFrame()
        self.right_container.setProperty("class", "WhiteCard")
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(20, 20, 20, 20)
        self.right_layout.setSpacing(15)

        self.view_title = QLabel(_("memory_details"))
        self.view_title.setStyleSheet(
            f"font-weight: bold; color: {COLORS['accent_purple']}; font-size: 23px;"
        )
        self.right_layout.addWidget(self.view_title)

        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ border: none; background: {COLORS['bg_card']}; border-radius: 3px; }} QProgressBar::chunk {{ background-color: {COLORS['accent_purple']}; border-radius: 3px; }}"
        )
        progress_layout.addWidget(self.progress_bar, 1)
        self.right_layout.addLayout(progress_layout)

        self.detail_view = MemoryDetailPanel()
        self.detail_view.setMinimumHeight(500)
        self.right_layout.addWidget(self.detail_view)

        action_bar = QHBoxLayout()
        action_bar.addStretch()

        self.clear_btn = QPushButton(_("forget_all_memories"))
        self.clear_btn.setObjectName("DangerBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.on_clear_all_memories)
        self.clear_btn.setMinimumWidth(200)
        self.clear_btn.setMinimumHeight(45)

        action_bar.addWidget(self.clear_btn)

        self.right_layout.addLayout(action_bar)

        self.main_splitter.addWidget(self.left_container)
        self.main_splitter.addWidget(self.right_container)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 6)

        parent_layout.addWidget(self.main_splitter)

    def load_memory_data(self):
        """开始加载数据"""
        if not self.data_loader.isRunning():
            self.progress_bar.setValue(0)
            self.data_loader.start()

    def update_progress(self, val):
        self.progress_bar.setValue(val)

    def update_ui_data(self, data):
        """数据加载完成的回调"""
        self.progress_bar.setValue(100)

        if "short_term" in data:
            short_term_memories = data["short_term"]
            self.short_term_list.update_data(short_term_memories)
            self.short_term_label.setText(f"短期: {len(short_term_memories)}")

        if "mid_term" in data:
            mid_term_memories = data["mid_term"]
            self.mid_term_list.update_data(mid_term_memories)
            self.mid_term_label.setText(f"中期: {len(mid_term_memories)}")

        if "long_term" in data:
            long_term_memories = data["long_term"]
            
            if "long_term_preferences" in data:
                long_term_memories = long_term_memories + data["long_term_preferences"]
            
            self.long_term_list.update_data(long_term_memories)
            self.long_term_label.setText(f"长期: {len(long_term_memories)}")

        if "memories" in data:
            total = len(data["memories"])
            self.total_count_label.setText(_("total_memories").format(count=total))

    def show_detail_mode(self):
        """保留此方法以兼容 memory_item_delegate 的调用"""
        pass

    def on_clear_all_memories(self):
        from ui.components.modern_confirm_dialog import ModernConfirmDialog
        from utils.i18n import _
        
        reply = ModernConfirmDialog.confirm(
            self,
            title=_("confirm_format"),
            message=_("confirm_clear_memories"),
            confirm_text=_("yes"),
            cancel_text=_("cancel"),
            icon_type="error"
        )

        if reply:
            try:
                if self.memory_manager:
                    self.memory_manager.clear_all_memories()
                self.load_memory_data()
                ModernConfirmDialog.confirm(
                    self,
                    title=_("reset_success"),
                    message=_("brain_formatted"),
                    confirm_text=_("ok"),
                    cancel_text="",
                    icon_type="success"
                )
            except Exception as e:
                ModernConfirmDialog.confirm(
                    self,
                    title=_("error"),
                    message=_("clear_failed", error=str(e)),
                    confirm_text=_("ok"),
                    cancel_text="",
                    icon_type="error"
                )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.y() < 80:
                self.m_drag = True
                self.m_DragPosition = event.globalPos() - self.pos()
                event.accept()

    def mouseMoveEvent(self, event):
        if Qt.LeftButton and self.m_drag:
            self.move(event.globalPos() - self.m_DragPosition)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.m_drag = False

    def closeEvent(self, event):
        self.update_timer.stop()
        if self.data_loader.isRunning():
            self.data_loader.quit()
            self.data_loader.wait()
        event.accept()


MemoryVisualizationWindow = ModernMemoryWindow

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = ModernMemoryWindow()
    window.show()
    sys.exit(app.exec_())
