"""日记浏览器窗口组件 - 现代电子日记风格"""

from datetime import datetime

from PyQt5.QtCore import Qt, QDate, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QBrush, QPen, QLinearGradient
from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, 
                            QListWidget, QListWidgetItem, QTextEdit, QLabel,
                            QFrame, QDateEdit, QLineEdit, QGraphicsDropShadowEffect,
                            QPushButton, QGridLayout, QScrollArea, QSizePolicy)

from core.diary_system import get_diary_system
from utils.i18n import tr


class ModernCalendar(QWidget):
    """完全自定义的现代化日历组件"""
    
    date_selected = pyqtSignal(QDate)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_date = QDate.currentDate()
        self._selected_date = QDate.currentDate()
        self._today = QDate.currentDate()
        self._setup_ui()
        self._update_calendar()
    
    def _setup_ui(self):
        self.setFixedSize(420, 500)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 容器卡片
        self._card = QFrame()
        self._card.setObjectName("CalendarCard")
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)
        
        # 头部：年月显示和导航
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        self._prev_btn = QPushButton("‹")
        self._prev_btn.setFixedSize(40, 40)
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.clicked.connect(self._prev_month)
        header_layout.addWidget(self._prev_btn)
        
        self._month_label = QLabel()
        self._month_label.setAlignment(Qt.AlignCenter)
        self._month_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_main']};
                font-size: 22px;
                font-weight: 700;
            }}
        """)
        header_layout.addWidget(self._month_label, stretch=1)
        
        self._next_btn = QPushButton("›")
        self._next_btn.setFixedSize(40, 40)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.clicked.connect(self._next_month)
        header_layout.addWidget(self._next_btn)
        
        card_layout.addLayout(header_layout)
        
        # 星期标题
        week_layout = QGridLayout()
        week_layout.setHorizontalSpacing(4)
        week_layout.setVerticalSpacing(4)
        
        weekdays = [tr("weekday.sun"), tr("weekday.mon"), tr("weekday.tue"), 
                   tr("weekday.wed"), tr("weekday.thu"), tr("weekday.fri"), 
                   tr("weekday.sat")]
        
        for col, day in enumerate(weekdays):
            label = QLabel(day[:1])
            label.setAlignment(Qt.AlignCenter)
            label.setFixedHeight(36)
            if col == 0 or col == 6:
                label.setStyleSheet(f"color: {COLORS['accent_pink']}; font-size: 16px; font-weight: 600;")
            else:
                label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 16px; font-weight: 600;")
            week_layout.addWidget(label, 0, col)
        
        # 日期网格
        self._date_container = QWidget()
        self._date_grid = QGridLayout(self._date_container)
        self._date_grid.setHorizontalSpacing(4)
        self._date_grid.setVerticalSpacing(4)
        self._date_grid.setContentsMargins(0, 0, 0, 0)
        
        card_layout.addLayout(week_layout)
        card_layout.addWidget(self._date_container)
        
        main_layout.addWidget(self._card)
        
        self._setup_styles()
    
    def _setup_styles(self):
        self._card.setStyleSheet(f"""
            QFrame#CalendarCard {{
                background-color: {COLORS['bg_card']};
                border: 2px solid {COLORS['border']};
                border-radius: 24px;
            }}
            QPushButton {{
                background-color: {COLORS['bg_input']};
                border: 2px solid {COLORS['border']};
                border-radius: 14px;
                color: {COLORS['text_main']};
                font-size: 28px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(157, 78, 221, 0.15);
                border-color: {COLORS['accent_purple']};
            }}
        """)
    
    def _update_month_label(self):
        lang = tr("weekday")
        if lang == "Week":
            month_str = self._current_date.toString("MMMM yyyy")
        else:
            month_str = f"{self._current_date.year()} 年 {self._current_date.month()} 月"
        self._month_label.setText(month_str)
    
    def _update_calendar(self):
        self._update_month_label()
        
        # 清除旧的日期按钮
        for i in reversed(range(self._date_grid.count())):
            self._date_grid.itemAt(i).widget().setParent(None)
        
        # 获取当月第一天和总天数
        first_day = QDate(self._current_date.year(), self._current_date.month(), 1)
        days_in_month = self._current_date.daysInMonth()
        start_col = first_day.dayOfWeek() % 7  # 0=周日
        
        # 日期按钮样式模板
        day_btn_style_base = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 18px;
                color: {COLORS['text_main']};
                font-size: 18px;
                font-weight: 500;
                min-height: 56px;
                min-width: 52px;
            }}
            QPushButton:hover {{
                background-color: rgba(157, 78, 221, 0.2);
            }}
        """
        
        today_style = f"""
            QPushButton {{
                background-color: transparent;
                border: 3px solid {COLORS['accent_purple']};
                border-radius: 24px;
                color: {COLORS['accent_purple']};
                font-size: 18px;
                font-weight: 700;
                min-height: 56px;
                min-width: 52px;
            }}
            QPushButton:hover {{
                background-color: rgba(157, 78, 221, 0.2);
            }}
        """
        
        selected_style = f"""
            QPushButton {{
                background-color: {COLORS['accent_purple']};
                border: none;
                border-radius: 18px;
                color: white;
                font-size: 18px;
                font-weight: 700;
                min-height: 52px;
                min-width: 52px;
            }}
        """
        
        other_month_style = f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 18px;
                color: {COLORS['text_muted']};
                font-size: 18px;
                font-weight: 400;
                min-height: 52px;
                min-width: 52px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.05);
            }}
        """
        
        # 填充日期
        row = 0
        for day in range(1, days_in_month + 1):
            col = (start_col + day - 1) % 7
            row = (start_col + day - 1) // 7
            
            date = QDate(self._current_date.year(), self._current_date.month(), day)
            btn = QPushButton(str(day))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            # 设置样式
            if date == self._selected_date:
                btn.setStyleSheet(selected_style)
            elif date == self._today:
                btn.setStyleSheet(today_style)
            else:
                btn.setStyleSheet(day_btn_style_base)
            
            btn.clicked.connect(lambda checked, d=date: self._select_date(d))
            self._date_grid.addWidget(btn, row + 1, col)
        
        # 填充上个月和下个月的日期（可选显示）
        # 上个月的日期
        prev_month = self._current_date.addMonths(-1)
        prev_days = prev_month.daysInMonth()
        for col in range(start_col):
            day = prev_days - (start_col - col - 1)
            date = QDate(prev_month.year(), prev_month.month(), day)
            btn = QPushButton(str(day))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(other_month_style)
            btn.clicked.connect(lambda checked, d=date: self._select_date(d))
            self._date_grid.addWidget(btn, 1, col)
        
        # 下个月的日期
        next_month = self._current_date.addMonths(1)
        last_day = QDate(self._current_date.year(), self._current_date.month(), days_in_month)
        end_col = (start_col + days_in_month - 1) % 7
        next_day = 1
        for col in range(end_col + 1, 7):
            date = QDate(next_month.year(), next_month.month(), next_day)
            btn = QPushButton(str(next_day))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(other_month_style)
            btn.clicked.connect(lambda checked, d=date: self._select_date(d))
            self._date_grid.addWidget(btn, row + 1, col)
            next_day += 1
    
    def _select_date(self, date):
        self._selected_date = date
        self._current_date = QDate(date.year(), date.month(), 1)
        self._update_calendar()
        self.date_selected.emit(date)
    
    def _prev_month(self):
        self._current_date = self._current_date.addMonths(-1)
        self._update_calendar()
    
    def _next_month(self):
        self._current_date = self._current_date.addMonths(1)
        self._update_calendar()
    
    def selected_date(self):
        return self._selected_date
    
    def set_selected_date(self, date):
        self._selected_date = date
        self._current_date = QDate(date.year(), date.month(), 1)
        self._update_calendar()


class DatePickerButton(QPushButton):
    """自定义日期选择按钮，点击弹出日历"""
    
    date_changed = pyqtSignal(QDate)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_date = QDate.currentDate()
        self._calendar_popup = None
        self._setup_ui()
    
    def _setup_ui(self):
        self.setFixedHeight(60)
        self.setCursor(Qt.PointingHandCursor)
        self._update_display()
        self.clicked.connect(self._toggle_calendar)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_input']};
                border: 2px solid {COLORS['border']};
                border-radius: 16px;
                color: {COLORS['text_main']};
                font-size: 22px;
                padding: 14px 20px;
                text-align: left;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent_purple']};
                background-color: rgba(157, 78, 221, 0.05);
            }}
        """)
    
    def _update_display(self):
        lang = tr("weekday")
        if lang == "Week":
            date_str = self._selected_date.toString("MM / dd / yyyy")
        else:
            date_str = f"{self._selected_date.year()} / {self._selected_date.month():02d} / {self._selected_date.day():02d}"
        self.setText(f"📅  {date_str}")
    
    def _toggle_calendar(self):
        if self._calendar_popup and self._calendar_popup.isVisible():
            self._calendar_popup.close()
            self._calendar_popup = None
        else:
            self._show_calendar()
    
    def _show_calendar(self):
        # 关闭之前的日历
        if self._calendar_popup:
            self._calendar_popup.close()
        
        # 创建日历弹层
        self._calendar_popup = QFrame(self.window())
        self._calendar_popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self._calendar_popup.setAttribute(Qt.WA_TranslucentBackground)
        
        # 添加阴影
        shadow = QGraphicsDropShadowEffect(self._calendar_popup)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 8)
        self._calendar_popup.setGraphicsEffect(shadow)
        
        # 日历布局
        popup_layout = QVBoxLayout(self._calendar_popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        
        calendar = ModernCalendar()
        calendar.set_selected_date(self._selected_date)
        calendar.date_selected.connect(self._on_date_selected)
        popup_layout.addWidget(calendar)
        
        # 计算位置
        btn_rect = self.geometry()
        global_pos = self.mapTo(self.window(), btn_rect.bottomLeft())
        popup_x = global_pos.x()
        popup_y = global_pos.y() + 8
        
        # 确保不超出屏幕
        screen_width = self.window().screen().availableGeometry().width()
        if popup_x + 420 > screen_width:
            popup_x = screen_width - 420 - 20
        
        self._calendar_popup.move(popup_x, popup_y)
        self._calendar_popup.show()
    
    def _on_date_selected(self, date):
        self._selected_date = date
        self._update_display()
        self.date_changed.emit(date)
        if self._calendar_popup:
            self._calendar_popup.close()
            self._calendar_popup = None
    
    def date(self):
        return self._selected_date
    
    def set_date(self, date):
        self._selected_date = date
        self._update_display()


# 现代电子日记高级奢华配色方案
COLORS = {
    'bg_main': '#12121a',          # 主背景（极深曜石黑）
    'bg_sidebar': '#1a1a26',       # 侧边栏（优雅深海蓝）
    'bg_card': '#1e1e2f',          # 文本大卡片
    'bg_card_hover': '#252538',    # 卡片悬停状态
    'bg_item': '#252538',          # 列表元素未选中状态
    'bg_input': '#161622',         # 输入框背景
    'accent_purple': '#9d4edd',    # 赛博高光紫
    'accent_pink': '#ff007f',      # 霓虹粉
    'accent_green': '#00f5d4',     # 荧光绿
    'accent_yellow': '#fee440',    # 明朗黄
    'text_main': '#ffffff',        # 主文本
    'text_secondary': '#94a3b8',   # 次要说明文本
    'text_muted': '#475569',       # 暗色提示文本
    'border': '#2d2d44',           # 边框线
}


class DiaryWindow(QDialog):
    """日记浏览器窗口 - 现代电子日记风格"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._diary_system = get_diary_system()
        self._selected_entry = None
        self._is_dragging = False
        self._drag_position = QPoint()
        
        # 初始化心情配置（支持国际化）
        self._init_mood_config()
        
        self._init_ui()
        self._load_entries()
    
    def _init_mood_config(self):
        """初始化心情配置（支持国际化）"""
        self._mood_config = {
            "happy": {"emoji": "☀️", "label": tr("diary.mood.happy"), "color": COLORS['accent_yellow']},
            "good": {"emoji": "😊", "label": tr("diary.mood.good"), "color": COLORS['accent_green']},
            "neutral": {"emoji": "😌", "label": tr("diary.mood.neutral"), "color": COLORS['text_secondary']},
            "sad": {"emoji": "😢", "label": tr("diary.mood.sad"), "color": "#3a86ff"},
            "angry": {"emoji": "😤", "label": tr("diary.mood.angry"), "color": COLORS['accent_pink']}
        }
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(2100, 1200)
        self.resize(2300, 1400)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 精致弥散阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(35)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 8)
        
        self._main_frame = QFrame()
        self._main_frame.setObjectName("MainWindow")
        self._main_frame.setGraphicsEffect(shadow)
        
        self._inner_layout = QHBoxLayout(self._main_frame)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(0)
        
        self._init_sidebar()
        self._init_content_area()
        
        main_layout.addWidget(self._main_frame)
        self.setStyleSheet(self._get_stylesheet())
    
    def _get_stylesheet(self):
        """生成样式表（适配大尺寸窗口）"""
        return f"""
QWidget {{
    font-family: 'Segoe UI', 'Microsoft YaHei', -apple-system, sans-serif;
    font-size: 22px;
    color: {COLORS['text_main']};
}}

#MainWindow {{
    background-color: {COLORS['bg_main']};
    border-radius: 24px;
    border: 2px solid {COLORS['border']};
}}

#Sidebar {{
    background-color: {COLORS['bg_sidebar']};
    border-top-left-radius: 24px;
    border-bottom-left-radius: 24px;
    border-right: 2px solid {COLORS['border']};
}}

#ContentArea {{
    background-color: {COLORS['bg_main']};
    border-top-right-radius: 24px;
    border-bottom-right-radius: 24px;
}}

#TitleLabel {{
    font-size: 36px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {COLORS['text_main']};
}}

QLineEdit {{
    background-color: {COLORS['bg_input']};
    border: 2px solid {COLORS['border']};
    border-radius: 16px;
    padding: 18px 22px;
    color: {COLORS['text_main']};
    font-size: 22px;
}}

QLineEdit:focus {{
    border-color: {COLORS['accent_purple']};
}}

QDateEdit {{
    background-color: {COLORS['bg_input']};
    border: 2px solid {COLORS['border']};
    border-radius: 16px;
    padding: 14px 18px;
    color: {COLORS['text_main']};
    font-size: 22px;
}}

QDateEdit:focus {{
    border-color: {COLORS['accent_purple']};
}}

QListWidget {{
    background-color: transparent;
    border: none;
}}

QListWidget::item {{
    background-color: transparent;
    border: none;
    padding: 0px;
    margin-bottom: 12px;
}}

QTextEdit {{
    background-color: transparent;
    border: none;
    color: {COLORS['text_main']};
    font-size: 28px;
    line-height: 2.0;
}}

/* 极简扁平化滚动条定制 */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 12px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.15);
    min-height: 40px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 0.3);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

.QFrame#DiaryCard {{
    background-color: {COLORS['bg_card']};
    border-radius: 24px;
    border: 2px solid {COLORS['border']};
}}

.QFrame#EventCard {{
    background-color: rgba(157, 78, 221, 0.06);
    border: 2px solid rgba(157, 78, 221, 0.15);
    border-radius: 20px;
}}

QLabel#DateTitle {{
    font-size: 42px;
    font-weight: 700;
    color: {COLORS['text_main']};
}}

QLabel#MoodBadge {{
    font-size: 24px;
    font-weight: 600;
    padding: 10px 24px;
    border-radius: 24px;
}}

QLabel#StatsLabel {{
    font-size: 24px;
    color: {COLORS['text_secondary']};
}}

QLabel#EventTitle {{
    font-size: 26px;
    font-weight: 700;
    color: {COLORS['accent_purple']};
}}

QPushButton#CloseBtn {{
    background-color: transparent;
    border: none;
    color: {COLORS['text_muted']};
    font-size: 28px;
    font-weight: 300;
    border-radius: 10px;
    width: 44px;
    height: 44px;
    padding: 0;
}}

QPushButton#CloseBtn:hover {{
    color: {COLORS['text_main']};
    background-color: rgba(255, 255, 255, 0.08);
}}

QPushButton#CloseBtn:pressed {{
    background-color: rgba(255, 255, 255, 0.12);
}}

QCheckBox {{
    width: 28px;
    height: 28px;
}}

QCheckBox::indicator {{
    width: 28px;
    height: 28px;
    border-radius: 8px;
    border: 2px solid {COLORS['border']};
    background-color: {COLORS['bg_input']};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS['accent_purple']};
    border-color: {COLORS['accent_purple']};
}}
"""
    
    def _init_sidebar(self):
        """初始化左侧边栏"""
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(500)  # 显著加宽侧边栏
        
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(32, 36, 32, 32)
        sidebar_layout.setSpacing(28)
        
        # 顶栏头部
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_label = QLabel("📔")
        icon_label.setStyleSheet("font-size: 42px; margin-right: 8px;")
        header_layout.addWidget(icon_label)
        
        title_label = QLabel(tr("diary.title"))
        title_label.setObjectName("TitleLabel")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseBtn")
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        
        header_frame.mousePressEvent = self._on_title_bar_press
        header_frame.mouseMoveEvent = self._on_title_bar_move
        header_frame.mouseReleaseEvent = self._on_title_bar_release
        sidebar_layout.addWidget(header_frame)
        
        # 搜索与过滤卡片
        filter_widget = QWidget()
        filter_layout = QVBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(16)
        
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(f"🔍  {tr('diary.search_placeholder')}")
        self._search_edit.textChanged.connect(self._filter_entries)
        self._search_edit.setFixedWidth(400)
        filter_layout.addWidget(self._search_edit)
        
        date_row = QHBoxLayout()
        date_row.setSpacing(12)
        
        self._date_filter = DatePickerButton()
        self._date_filter.date_changed.connect(self._filter_entries)
        self._date_filter.setMinimumWidth(400)
        self._date_filter.setMaximumWidth(400)
        date_row.addWidget(self._date_filter)
        date_row.addStretch()
        
        filter_layout.addLayout(date_row)
        sidebar_layout.addWidget(filter_widget)
        
        # 分类小标题
        list_header = QHBoxLayout()
        list_title = QLabel(tr("diary.all_records"))
        list_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {COLORS['text_secondary']}; text-transform: uppercase; letter-spacing: 2px;")
        list_header.addWidget(list_title)
        
        self._entry_count_label = QLabel(f"{len(self._diary_system.get_entries())}")
        self._entry_count_label.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {COLORS['accent_purple']}; background: rgba(157, 78, 221, 0.15); padding: 4px 12px; border-radius: 16px;")
        list_header.addWidget(self._entry_count_label)
        list_header.addStretch()
        sidebar_layout.addLayout(list_header)
        
        # 日记列表容器
        self._entry_list = QListWidget()
        self._entry_list.setSpacing(8)
        self._entry_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._entry_list.itemClicked.connect(self._on_entry_selected)
        sidebar_layout.addWidget(self._entry_list)
        
        self._inner_layout.addWidget(sidebar)
    
    def _init_content_area(self):
        """初始化右侧内容区"""
        content_area = QFrame()
        content_area.setObjectName("ContentArea")
        
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)
        
        # 空状态
        empty_state = QWidget()
        empty_layout = QVBoxLayout(empty_state)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(12)
        empty_layout.setAlignment(Qt.AlignCenter)
        
        empty_icon = QLabel("☕")
        empty_icon.setStyleSheet("font-size: 60px;")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)
        
        empty_title = QLabel(tr("diary.empty_title"))
        empty_title.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {COLORS['text_secondary']};")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        
        empty_desc = QLabel(tr("diary.empty_desc"))
        empty_desc.setStyleSheet(f"font-size: 18px; color: {COLORS['text_muted']};")
        empty_desc.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_desc)
        
        self._empty_state = empty_state
        content_layout.addWidget(empty_state, 0)
        
        # 核心日记展示大卡片
        self._diary_card = QFrame()
        self._diary_card.setObjectName("DiaryCard")
        self._diary_card.hide()
        
        card_layout = QVBoxLayout(self._diary_card)
        card_layout.setContentsMargins(42, 42, 42, 42)
        card_layout.setSpacing(30)
        
        # 头部：日期、星期与情绪胶囊标签
        header_section = QFrame()
        header_layout = QVBoxLayout(header_section)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        
        date_mood_layout = QHBoxLayout()
        self._date_title = QLabel("")
        self._date_title.setObjectName("DateTitle")
        date_mood_layout.addWidget(self._date_title)
        
        date_mood_layout.addSpacing(24)
        
        self._mood_badge = QLabel("")
        self._mood_badge.setObjectName("MoodBadge")
        self._mood_badge.setAlignment(Qt.AlignCenter)
        date_mood_layout.addWidget(self._mood_badge)
        date_mood_layout.addStretch()
        header_layout.addLayout(date_mood_layout)
        
        # 数据流统计行
        self._stats_label = QLabel("")
        self._stats_label.setObjectName("StatsLabel")
        header_layout.addWidget(self._stats_label)
        card_layout.addWidget(header_section)
        
        # 微光渐变隔离线
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 2px; border: none;")
        card_layout.addWidget(divider)
        
        # 深度沉浸式文本阅读器
        self._content_edit = QTextEdit()
        self._content_edit.setReadOnly(True)
        card_layout.addWidget(self._content_edit, stretch=1)
        
        # 底部：今日要事模块
        self._events_section = QFrame()
        self._events_section.setObjectName("EventCard")
        
        events_layout = QVBoxLayout(self._events_section)
        events_layout.setContentsMargins(28, 24, 28, 24)
        events_layout.setSpacing(18)
        
        events_title = QLabel(f"🎯  {tr('diary.events_title')}")
        events_title.setObjectName("EventTitle")
        events_layout.addWidget(events_title)
        
        self._events_list = QListWidget()
        self._events_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
            }}
            QListWidget::item {{
                padding: 8px 0px;
                color: {COLORS['text_secondary']};
                font-size: 24px;
            }}
            QListWidget QScrollBar:vertical {{
                width: 0px;
            }}
        """)
        self._events_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._events_section.setMaximumHeight(280)
        events_layout.addWidget(self._events_list)
        
        card_layout.addWidget(self._events_section)
        content_layout.addWidget(self._diary_card)
        self._inner_layout.addWidget(content_area)
    
    def _load_entries(self):
        """安全加载并高质量渲染日记卡片列表"""
        self._entry_list.clear()
        entries = self._diary_system.get_entries()
        
        if not entries:
            item = QListWidgetItem(f"  {tr('diary.no_records')}")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            item.setForeground(QColor(COLORS['text_muted']))
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(420, 80))
            self._entry_list.addItem(item)
            return
        
        for entry in entries:
            mood = self._mood_config.get(entry.mood_tag, self._mood_config["neutral"])
            date_obj = datetime.strptime(entry.date, "%Y-%m-%d")
            # 根据语言环境格式化日期
            lang = tr("weekday")
            if lang == "Week":
                # 英文模式
                date_str = date_obj.strftime("%m/%d")
            else:
                # 中文模式
                date_str = f"{date_obj.month:02d}月{date_obj.day:02d}日"
            
            item = QListWidgetItem()
            
            item_widget = QWidget()
            item_widget.setObjectName("ItemWidget")
            item_widget.setStyleSheet(f"""
                QWidget#ItemWidget {{
                    background-color: rgba(255, 255, 255, 0.02);
                    border: 2px solid {COLORS['border']};
                    border-radius: 18px;
                }}
                QWidget#ItemWidget:hover {{
                    background-color: rgba(157, 78, 221, 0.08);
                    border-color: rgba(157, 78, 221, 0.4);
                }}
            """)
            
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(20, 18, 20, 18)
            item_layout.setSpacing(18)
            
            # 心情图标
            mood_label = QLabel(mood["emoji"])
            mood_label.setStyleSheet("font-size: 34px; background: rgba(255,255,255,0.04); padding: 10px; border-radius: 16px;")
            item_layout.addWidget(mood_label, alignment=Qt.AlignVCenter)
            
            # 中间核心信息区
            content_vbox = QVBoxLayout()
            content_vbox.setSpacing(6)
            content_vbox.setContentsMargins(0, 0, 0, 0)
            
            date_label = QLabel(date_str)
            date_label.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {COLORS['text_main']};")
            content_vbox.addWidget(date_label)
            
            clean_content = entry.content.replace('\n', ' ').strip()
            preview = clean_content[:20] + "..." if len(clean_content) > 20 else clean_content
            preview_label = QLabel(preview)
            preview_label.setStyleSheet(f"font-size: 20px; color: {COLORS['text_secondary']};")
            content_vbox.addWidget(preview_label)
            
            item_layout.addLayout(content_vbox, stretch=1)
            
            item.setSizeHint(QSize(420, 120))
            
            self._entry_list.addItem(item)
            self._entry_list.setItemWidget(item, item_widget)
            item.setData(Qt.UserRole, entry.id)
        
        self._entry_list.setStyleSheet(f"""
            QListWidget::item:selected QWidget#ItemWidget {{
                background-color: rgba(157, 78, 221, 0.16) !important;
                border-color: {COLORS['accent_purple']} !important;
            }}
        """)
    
    def _filter_entries(self):
        """过滤日记列表（搜索）+ 日期定位"""
        search_text = self._search_edit.text().lower()
        filter_date = self._date_filter.date().toString("yyyy-MM-dd")
        target_row = -1
        
        for i in range(self._entry_list.count()):
            item = self._entry_list.item(i)
            entry_id = item.data(Qt.UserRole)
            
            if entry_id:
                entry = self._diary_system.get_entry(entry_id)
                if entry:
                    # 搜索文本过滤
                    if search_text and search_text not in entry.content.lower():
                        item.setHidden(True)
                    else:
                        item.setHidden(False)
                        # 记录目标日期的行号（用于滚动定位）
                        if filter_date and entry.date == filter_date:
                            target_row = i
        
        # 日期定位：滚动到目标日期的日记项
        if target_row >= 0:
            self._entry_list.scrollToItem(self._entry_list.item(target_row), QListWidget.PositionAtTop)
    
    def _on_entry_selected(self, item):
        """选择日记条目"""
        entry_id = item.data(Qt.UserRole)
        if not entry_id:
            return
        
        self._selected_entry = self._diary_system.get_entry(entry_id)
        if self._selected_entry:
            self._empty_state.hide()
            self._diary_card.show()
            self._display_entry(self._selected_entry)
    
    def _display_entry(self, entry):
        """将加载到的核心内容优雅映射到主渲染画布上"""
        date_obj = datetime.strptime(entry.date, "%Y-%m-%d")
        weekdays = [tr("weekday.mon"), tr("weekday.tue"), tr("weekday.wed"), 
                    tr("weekday.thu"), tr("weekday.fri"), tr("weekday.sat"), tr("weekday.sun")]
        weekday = weekdays[date_obj.weekday()]
        
        # 根据语言环境格式化日期
        lang = tr("weekday")
        if lang == "Week":
            # 英文模式
            month_name = date_obj.strftime("%B")
            date_str = f"{month_name} {date_obj.day}, {date_obj.year} · {weekday}"
        else:
            # 中文模式
            date_str = f"{date_obj.year} 年 {date_obj.month} 月 {date_obj.day} 日 · {tr('weekday')}{weekday}"
        
        self._date_title.setText(date_str)
        
        mood = self._mood_config.get(entry.mood_tag, self._mood_config["neutral"])
        self._mood_badge.setText(f"{mood['emoji']} {mood['label']}")
        self._mood_badge.setStyleSheet(f"""
            QLabel#MoodBadge {{
                color: {mood['color']};
                background: transparent;
                border: none;
                padding: 0;
            }}
        """)
        
        stats = tr("diary.stats_format", word_count=entry.word_count)
        self._stats_label.setText(stats)
        
        self._content_edit.setPlainText(entry.content)
        
        self._events_list.clear()
        if entry.key_events:
            for event in entry.key_events:
                self._events_list.addItem(f"•  {event}")
        else:
            self._events_list.addItem(f"•  {tr('diary.no_events')}")
    
    def _on_title_bar_press(self, event):
        """标题栏按下事件"""
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def _on_title_bar_move(self, event):
        """标题栏移动事件"""
        if self._is_dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_position)
            event.accept()
    
    def _on_title_bar_release(self, event):
        """标题栏释放事件"""
        self._is_dragging = False
