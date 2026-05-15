"""Vivian UI 样式模块 - Dracula Dark Theme"""

# Dracula Dark Theme 配色方案
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


def get_dracula_stylesheet():
    """获取 Dracula Dark Theme 样式表"""
    return f"""
    /* 全局样式 */
    QWidget {{
        color: {COLORS['text_main']};
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        font-size: 18px;
    }}

    /* 工具提示 */
    QToolTip {{
        color: #ffffff;
        background-color: rgba(33, 37, 43, 180);
        border-left: 2px solid {COLORS['accent_pink']};
        padding-left: 8px;
    }}

    /* 主窗口背景 */
    QMainWindow {{
        background-color: {COLORS['bg_main']};
        border: none;
    }}

    /* LineEdit */
    QLineEdit {{
        background-color: {COLORS['bg_input']};
        border-radius: 5px;
        border: 2px solid {COLORS['bg_sidebar']};
        padding-left: 10px;
        selection-color: #ffffff;
        selection-background-color: {COLORS['accent_pink']};
    }}
    QLineEdit:hover {{
        border: 2px solid rgb(64, 71, 88);
    }}
    QLineEdit:focus {{
        border: 2px solid {COLORS['border_focus']};
    }}

    /* PlainTextEdit */
    QPlainTextEdit {{
        background-color: {COLORS['bg_input']};
        border-radius: 5px;
        padding: 10px;
        selection-color: #ffffff;
        selection-background-color: {COLORS['accent_pink']};
    }}

    /* PushButton */
    QPushButton {{
        border: 2px solid rgb(52, 59, 72);
        border-radius: 5px;
        background-color: rgb(52, 59, 72);
        color: {COLORS['text_main']};
        padding: 5px 12px;
    }}
    QPushButton:hover {{
        background-color: rgb(57, 65, 80);
        border: 2px solid rgb(61, 70, 86);
    }}
    QPushButton:pressed {{
        background-color: rgb(35, 40, 49);
        border: 2px solid rgb(43, 50, 61);
    }}
    QPushButton:disabled {{
        background-color: rgb(44, 49, 58);
        border-color: rgb(44, 49, 58);
        color: {COLORS['text_secondary']};
    }}

    /* GroupBox */
    QGroupBox {{
        border: 1px solid {COLORS['border']};
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 6px;
        background-color: {COLORS['bg_sidebar']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 4px;
        color: {COLORS['accent_purple']};
        font-weight: bold;
    }}

    /* ComboBox */
    QComboBox {{
        background-color: {COLORS['bg_input']};
        border-radius: 5px;
        border: 2px solid {COLORS['bg_sidebar']};
        padding: 5px;
        padding-left: 10px;
    }}
    QComboBox:hover {{
        border: 2px solid rgb(64, 71, 88);
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 25px;
        border-left-width: 3px;
        border-left-color: rgba(39, 44, 54, 150);
        border-left-style: solid;
        border-top-right-radius: 3px;
        border-bottom-right-radius: 3px;
        background-color: {COLORS['bg_card']};
    }}
    QComboBox QAbstractItemView {{
        color: {COLORS['accent_pink']};
        background-color: {COLORS['bg_sidebar']};
        padding: 10px;
        selection-background-color: rgb(39, 44, 54);
    }}

    /* CheckBox */
    QCheckBox::indicator {{
        border: 3px solid rgb(52, 59, 72);
        width: 15px;
        height: 15px;
        border-radius: 10px;
        background: {COLORS['bg_card']};
    }}
    QCheckBox::indicator:hover {{
        border: 3px solid rgb(58, 66, 81);
    }}
    QCheckBox::indicator:checked {{
        background-color: {COLORS['accent_purple']};
        border: 2px solid {COLORS['accent_purple']};
    }}

    /* SpinBox */
    QAbstractSpinBox, QDoubleSpinBox, QSpinBox {{
        background-color: {COLORS['bg_input']};
        border: 2px solid {COLORS['bg_sidebar']};
        border-radius: 4px;
        padding: 2px 6px;
    }}

    /* ScrollBar */
    QScrollBar:horizontal {{
        border: none;
        background: rgb(52, 59, 72);
        height: 8px;
        margin: 0px 21px 0 21px;
        border-radius: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {COLORS['accent_purple']};
        min-width: 25px;
        border-radius: 4px;
    }}
    QScrollBar:vertical {{
        border: none;
        background: rgb(52, 59, 72);
        width: 8px;
        margin: 21px 0 21px 0;
        border-radius: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLORS['accent_purple']};
        min-height: 25px;
        border-radius: 4px;
    }}

    /* Slider */
    QSlider::groove:horizontal {{
        border-radius: 5px;
        height: 10px;
        margin: 0px;
        background-color: rgb(52, 59, 72);
    }}
    QSlider::handle:horizontal {{
        background-color: {COLORS['accent_purple']};
        border: none;
        height: 10px;
        width: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    QSlider::groove:vertical {{
        border-radius: 5px;
        width: 10px;
        margin: 0px;
        background-color: rgb(52, 59, 72);
    }}
    QSlider::handle:vertical {{
        background-color: {COLORS['accent_purple']};
        border: none;
        height: 10px;
        width: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    """


def get_config_window_style():
    """获取配置窗口样式 - 优化版"""
    return f"""
    QDialog {{
        background-color: transparent;
    }}

    QFrame#MainFrame {{
        background-color: {COLORS['bg_main']};
        border-radius: 16px;
        border: 1px solid {COLORS['border']};
    }}

    QWidget#TitleBar {{
        background-color: {COLORS['bg_sidebar']};
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
        border-bottom: 1px solid {COLORS['border']};
    }}

    QLabel#TitleLabel {{
        color: {COLORS['text_main']};
        font-weight: bold;
        font-size: 18px;
    }}

    QPushButton#CloseBtn {{
        background-color: transparent;
        border: none;
        color: {COLORS['text_secondary']};
        font-size: 24px;
        font-weight: bold;
        border-radius: 12px;
        padding: 0;
    }}
    QPushButton#CloseBtn:hover {{
        color: {COLORS['accent_pink']};
        background-color: {COLORS['bg_card']};
    }}

    QScrollArea#ScrollArea {{
        background-color: transparent;
        border: none;
    }}

    QScrollArea#ScrollArea QWidget {{
        background-color: transparent;
    }}

    QGroupBox#ConfigGroup {{
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        margin-top: 15px;
        padding-top: 15px;
        padding-bottom: 20px;
        padding-left: 20px;
        padding-right: 20px;
        background-color: {COLORS['bg_sidebar']};
    }}

    QGroupBox#ConfigGroup::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        color: {COLORS['accent_purple']};
        font-weight: bold;
        font-size: 16px;
    }}

    QPushButton#SaveBtn {{
        background-color: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {COLORS['accent_purple']},
            stop: 1 rgb(160, 120, 220)
        );
        color: #ffffff;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        font-size: 14px;
        padding: 8px 24px;
        
    }}
    QPushButton#SaveBtn:hover {{
        background-color: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 rgb(195, 155, 255),
            stop: 1 rgb(170, 130, 230)
        );
        
    }}
    QPushButton#SaveBtn:pressed {{
        background-color: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 rgb(170, 130, 230),
            stop: 1 rgb(145, 105, 200)
        );
        
    }}

    QPushButton#CancelBtn {{
        background-color: {COLORS['bg_card']};
        color: {COLORS['text_main']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        font-size: 14px;
        padding: 8px 20px;
    }}
    QPushButton#CancelBtn:hover {{
        background-color: rgb(57, 65, 80);
        border-color: rgb(61, 70, 86);
    }}

    QLineEdit {{
        background-color: {COLORS['bg_input']};
        border-radius: 4px;
        border: 1px solid {COLORS['bg_sidebar']};
        padding: 2px 8px;
        selection-color: #ffffff;
        selection-background-color: {COLORS['accent_pink']};
        font-size: 14px;
        min-height: 28px;
    }}
    QLineEdit:hover {{
        border: 1px solid rgb(64, 71, 88);
    }}
    QLineEdit:focus {{
        border: 1px solid {COLORS['border_focus']};
    }}

    QComboBox {{
        background-color: {COLORS['bg_input']};
        border-radius: 4px;
        border: 1px solid {COLORS['bg_sidebar']};
        padding: 2px 8px;
        font-size: 14px;
        min-height: 28px;
    }}
    QComboBox:hover {{
        border: 2px solid rgb(64, 71, 88);
    }}
    QComboBox:focus {{
        border: 2px solid {COLORS['border_focus']};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 45px;
        border-left-width: 2px;
        border-left-color: rgba(39, 44, 54, 150);
        border-left-style: solid;
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
        background-color: {COLORS['bg_card']};
    }}
    QComboBox QAbstractItemView {{
        color: {COLORS['text_main']};
        background-color: {COLORS['bg_sidebar']};
        padding: 6px;
        selection-background-color: rgb(39, 44, 54);
        font-size: 14px;
    }}

    QCheckBox::indicator {{
        border: 2px solid rgb(52, 59, 72);
        width: 16px;
        height: 16px;
        border-radius: 10px;
        background: {COLORS['bg_card']};
    }}
    QCheckBox::indicator:hover {{
        border: 2px solid rgb(58, 66, 81);
    }}
    QCheckBox::indicator:checked {{
        background-color: {COLORS['accent_purple']};
        border: 2px solid {COLORS['accent_purple']};
    }}

    QAbstractSpinBox, QDoubleSpinBox, QSpinBox {{
        background-color: {COLORS['bg_input']};
        border: 1px solid {COLORS['bg_sidebar']};
        border-radius: 4px;
        padding: 0 8px;
        font-size: 14px;
        min-height: 28px;
    }}
    QAbstractSpinBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
        border: 2px solid {COLORS['border_focus']};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        width: 0px;
        height: 0px;
    }}
    """


def get_input_dialog_style():
    """获取输入对话框样式"""
    return f"""
    QFrame#MainContainer {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 rgba(33, 37, 43, 0.98),
            stop:1 rgba(40, 44, 52, 0.95)
        );
        border: 1px solid rgba(189, 147, 249, 0.3);
        border-radius: 50px;
    }}

    QLineEdit {{
        background: transparent;
        border: none;
        color: {COLORS['text_main']};
        font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
        font-size: 23px;
        font-weight: 500;
        padding: 13px 20px;
    }}

    QLineEdit::placeholder {{
        color: rgba(221, 221, 221, 0.4);
        font-style: italic;
    }}

    QPushButton {{
        background-color: rgba(189, 147, 249, 0.15);
        border: 1px solid rgba(189, 147, 249, 0.3);
        border-radius: 25px;
        color: {COLORS['text_main']};
    }}
    QPushButton:hover {{
        background-color: rgba(189, 147, 249, 0.25);
        border-color: rgba(189, 147, 249, 0.5);
    }}
    QPushButton:pressed {{
        background-color: rgba(255, 121, 198, 0.3);
        border-color: rgba(255, 121, 198, 0.5);
    }}
    """


def get_message_bubble_style():
    """获取消息气泡样式"""
    return f"""
    QFrame#BubbleContainer {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 rgba(189, 147, 249, 0.92),
            stop: 0.35 rgba(139, 92, 252, 0.88),
            stop: 0.65 rgba(168, 85, 247, 0.85),
            stop: 1 rgba(192, 132, 252, 0.82)
        );
        border: 1px solid rgba(255, 255, 255, 0.35);
        border-radius: 28px;
        
    }}

    QLabel {{
        color: rgba(255, 255, 255, 0.98);
        background: transparent;
        font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
        font-size: 21px;
        font-weight: 500;
        line-height: 1.7;
        
    }}

    QLabel::selection {{
        background-color: rgba(255, 255, 255, 0.3);
        color: white;
    }}

    QFrame#BubbleContainer:hover {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 rgba(139, 92, 252, 0.95),
            stop: 0.35 rgba(159, 92, 252, 0.92),
            stop: 0.65 rgba(188, 85, 247, 0.88),
            stop: 1 rgba(212, 132, 252, 0.85)
        );
        border-color: rgba(255, 255, 255, 0.45);
    }}
    """
