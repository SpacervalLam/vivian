import asyncio
import json
import os
from loguru import logger
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QCheckBox, QRadioButton, QButtonGroup, QGroupBox, QGridLayout, QSpinBox, QDoubleSpinBox,
    QMessageBox, QFrame, QWidget, QGraphicsDropShadowEffect,
    QScrollArea, QToolButton, QSizePolicy, QSpacerItem, QDesktopWidget
)
from PyQt5.QtCore import Qt, QPoint, QRect, QSize
from PyQt5.QtGui import QColor, QFont, QCursor, QIcon

from core.ai_manager import test_proxy_connectivity
from core.model_router import get_model_router, reload_model_router
from utils.config_manager import config_manager
from utils.i18n import _, available_languages, translator
from ui.styles import get_dracula_stylesheet, get_config_window_style

from ui.toast_notification import ToastNotification


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        event.ignore()


class ProviderConfigWidget(QWidget):
    def __init__(self, provider_name, provider_data, parent=None):
        super().__init__(parent)
        self.provider_name = provider_name
        self.provider_data = provider_data or {
            'base_url': '',
            'api_key': '',
            'model': ''
        }
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        name_label = QLabel(self.provider_name)
        name_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        name_label.setStyleSheet("color: #50fa7b;")
        header_layout.addWidget(name_label)
        header_layout.addStretch()
        
        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("▼")
        self.collapse_btn.setFont(QFont("Arial", 12))
        self.collapse_btn.setFixedSize(30, 30)
        self.collapse_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                color: #bd93f9;
                border: none;
            }
            QToolButton:hover {
                color: #ff79c6;
            }
        """)
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        header_layout.addWidget(self.collapse_btn)
        
        layout.addLayout(header_layout)
        
        self.content_widget = QWidget()
        content_layout = QGridLayout(self.content_widget)
        content_layout.setContentsMargins(20, 0, 0, 0)
        content_layout.setVerticalSpacing(15)
        content_layout.setHorizontalSpacing(20)
        
        base_url_label = QLabel(_("api_address"))
        base_url_label.setFont(QFont("Microsoft YaHei", 14))
        content_layout.addWidget(base_url_label, 0, 0)
        
        self.base_url_edit = QLineEdit(self.provider_data.get('base_url', ''))
        self.base_url_edit.setFont(QFont("Microsoft YaHei", 14))
        self.base_url_edit.setFixedHeight(28)
        self.base_url_edit.setPlaceholderText(_("api_address_placeholder"))
        content_layout.addWidget(self.base_url_edit, 0, 1)
        
        api_key_label = QLabel(_("api_key"))
        api_key_label.setFont(QFont("Microsoft YaHei", 14))
        content_layout.addWidget(api_key_label, 1, 0)
        
        self.api_key_edit = QLineEdit(self.provider_data.get('api_key', ''))
        self.api_key_edit.setFont(QFont("Microsoft YaHei", 14))
        self.api_key_edit.setFixedHeight(28)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        content_layout.addWidget(self.api_key_edit, 1, 1)
        
        model_label = QLabel(_("model_name"))
        model_label.setFont(QFont("Microsoft YaHei", 14))
        content_layout.addWidget(model_label, 2, 0)
        
        self.model_edit = QLineEdit(self.provider_data.get('model', ''))
        self.model_edit.setFont(QFont("Microsoft YaHei", 14))
        self.model_edit.setFixedHeight(28)
        self.model_edit.setPlaceholderText(_("model_name_placeholder"))
        content_layout.addWidget(self.model_edit, 2, 1)
        
        layout.addWidget(self.content_widget)
    
    def toggle_collapse(self):
        is_visible = self.content_widget.isVisible()
        self.content_widget.setVisible(not is_visible)
        self.collapse_btn.setText("▲" if is_visible else "▼")
    
    def get_data(self):
        return {
            'base_url': self.base_url_edit.text().strip(),
            'api_key': self.api_key_edit.text().strip(),
            'model': self.model_edit.text().strip()
        }


class AdvancedConfigWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(1100, 800)
        self.resize(1150, 850)
        
        self.m_flag = False
        self.m_Position = QPoint()
        
        self.load_config()
        self.provider_widgets = {}
        
        self.init_ui()
        self.apply_modern_style()
        self.center_window()
    
    def load_config(self):
        self.network_config = {
            'proxy_mode': config_manager.get("network.proxy_mode", "direct"),
            'proxy_url': config_manager.get("network.proxy_url", ""),
            'timeout': config_manager.get("network.timeout", 30.0)
        }
        
        self.providers = config_manager.get("providers", {})
        self.routing_matrix = config_manager.get("routing_matrix", {
            'chat': [],
            'reasoning': [],
            'diary': []
        })
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("MainFrame")
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.bg_frame.setGraphicsEffect(shadow)
        
        main_layout.addWidget(self.bg_frame)
        
        content_layout = QVBoxLayout(self.bg_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        self.title_bar = QWidget()
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(65)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(30, 0, 30, 0)
        
        title_label = QLabel(_("advanced_settings"))
        title_label.setObjectName("TitleLabel")
        title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(54, 54)
        close_btn.setFont(QFont("Arial", 35))
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_btn)
        content_layout.addWidget(self.title_bar)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("ScrollArea")
        
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(35, 25, 35, 25)
        body_layout.setSpacing(25)
        
        network_group = QGroupBox(_("network_proxy_settings"))
        network_group.setObjectName("ConfigGroup")
        network_layout = QGridLayout(network_group)
        network_layout.setVerticalSpacing(20)
        network_layout.setHorizontalSpacing(20)
        
        mode_label = QLabel(_("proxy_mode"))
        mode_label.setFont(QFont("Microsoft YaHei", 18))
        network_layout.addWidget(mode_label, 0, 0)
        
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(20)
        
        self.proxy_mode_group = QButtonGroup()
        
        self.direct_radio = QRadioButton(_("direct_mode"))
        self.direct_radio.setFont(QFont("Microsoft YaHei", 16))
        self.direct_radio.setChecked(self.network_config['proxy_mode'] == 'direct')
        self.proxy_mode_group.addButton(self.direct_radio)
        mode_layout.addWidget(self.direct_radio)
        
        self.system_radio = QRadioButton(_("system_proxy"))
        self.system_radio.setFont(QFont("Microsoft YaHei", 16))
        self.system_radio.setChecked(self.network_config['proxy_mode'] == 'system')
        self.proxy_mode_group.addButton(self.system_radio)
        mode_layout.addWidget(self.system_radio)
        
        self.custom_radio = QRadioButton(_("custom_proxy"))
        self.custom_radio.setFont(QFont("Microsoft YaHei", 16))
        self.custom_radio.setChecked(self.network_config['proxy_mode'] == 'custom')
        self.proxy_mode_group.addButton(self.custom_radio)
        mode_layout.addWidget(self.custom_radio)
        
        self.direct_radio.clicked.connect(lambda: self.set_proxy_mode('direct'))
        self.system_radio.clicked.connect(lambda: self.set_proxy_mode('system'))
        self.custom_radio.clicked.connect(lambda: self.set_proxy_mode('custom'))
        
        network_layout.addLayout(mode_layout, 0, 1)
        
        proxy_url_label = QLabel(_("proxy_address"))
        proxy_url_label.setFont(QFont("Microsoft YaHei", 18))
        network_layout.addWidget(proxy_url_label, 1, 0)
        
        url_layout = QHBoxLayout()
        url_layout.setSpacing(15)
        
        self.proxy_url_edit = QLineEdit(self.network_config['proxy_url'])
        self.proxy_url_edit.setFont(QFont("Microsoft YaHei", 18))
        self.proxy_url_edit.setFixedHeight(28)
        self.proxy_url_edit.setMinimumWidth(400)
        self.proxy_url_edit.setPlaceholderText(_("proxy_address_placeholder"))
        url_layout.addWidget(self.proxy_url_edit)
        
        self.test_btn = QPushButton(_("test_connectivity"))
        self.test_btn.setFont(QFont("Microsoft YaHei", 14))
        self.test_btn.setFixedHeight(28)
        self.test_btn.setFixedWidth(120)
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.clicked.connect(self.test_connectivity)
        url_layout.addWidget(self.test_btn)
        
        self.test_result_label = QLabel("")
        self.test_result_label.setFont(QFont("Microsoft YaHei", 14))
        url_layout.addWidget(self.test_result_label)
        
        network_layout.addLayout(url_layout, 1, 1)
        
        timeout_label = QLabel(_("timeout"))
        timeout_label.setFont(QFont("Microsoft YaHei", 18))
        network_layout.addWidget(timeout_label, 2, 0)
        
        self.timeout_spin = NoWheelDoubleSpinBox()
        self.timeout_spin.setFont(QFont("Microsoft YaHei", 18))
        self.timeout_spin.setFixedHeight(28)
        self.timeout_spin.setFixedWidth(120)
        self.timeout_spin.setRange(5.0, 120.0)
        self.timeout_spin.setSingleStep(1.0)
        self.timeout_spin.setValue(self.network_config['timeout'])
        network_layout.addWidget(self.timeout_spin, 2, 1)
        
        body_layout.addWidget(network_group)
        
        providers_group = QGroupBox(_("ai_model_providers"))
        providers_group.setObjectName("ConfigGroup")
        providers_layout = QVBoxLayout(providers_group)
        providers_layout.setSpacing(15)
        
        add_provider_layout = QHBoxLayout()
        add_provider_layout.setSpacing(15)
        
        self.new_provider_edit = QLineEdit()
        self.new_provider_edit.setFont(QFont("Microsoft YaHei", 14))
        self.new_provider_edit.setFixedHeight(28)
        self.new_provider_edit.setPlaceholderText(_("enter_provider_name"))
        add_provider_layout.addWidget(self.new_provider_edit)
        
        self.add_provider_btn = QPushButton(_("add_provider"))
        self.add_provider_btn.setFont(QFont("Microsoft YaHei", 14))
        self.add_provider_btn.setFixedHeight(28)
        self.add_provider_btn.setCursor(Qt.PointingHandCursor)
        self.add_provider_btn.clicked.connect(self.add_provider)
        add_provider_layout.addWidget(self.add_provider_btn)
        
        providers_layout.addLayout(add_provider_layout)
        
        self.providers_scroll = QScrollArea()
        self.providers_scroll.setWidgetResizable(True)
        self.providers_scroll.setMaximumHeight(350)
        
        self.providers_container = QWidget()
        self.providers_layout = QVBoxLayout(self.providers_container)
        self.providers_layout.setSpacing(15)
        
        for name, data in self.providers.items():
            self.add_provider_widget(name, data)
        
        self.providers_scroll.setWidget(self.providers_container)
        providers_layout.addWidget(self.providers_scroll)
        
        body_layout.addWidget(providers_group)
        
        routing_group = QGroupBox(_("ai_routing_matrix"))
        routing_group.setObjectName("ConfigGroup")
        routing_layout = QGridLayout(routing_group)
        routing_layout.setVerticalSpacing(20)
        routing_layout.setHorizontalSpacing(20)
        
        routing_layout.addWidget(QLabel(_("task_type")), 0, 0)
        routing_layout.addWidget(QLabel(_("primary_model")), 0, 1)
        routing_layout.addWidget(QLabel(_("fallback_model")), 0, 2)
        
        tasks = [
            (_("daily_chat"), "chat"),
            (_("tool_reasoning"), "reasoning"),
            (_("smart_diary"), "diary")
        ]
        
        self.routing_combo_boxes = {}
        
        for i, (label, task_type) in enumerate(tasks):
            task_label = QLabel(label)
            task_label.setFont(QFont("Microsoft YaHei", 16))
            routing_layout.addWidget(task_label, i+1, 0)
            
            primary_combo = NoWheelComboBox()
            primary_combo.setFont(QFont("Microsoft YaHei", 16))
            primary_combo.setFixedHeight(28)
            primary_combo.setMinimumWidth(300)
            self.update_provider_combo(primary_combo)
            routing_layout.addWidget(primary_combo, i+1, 1)
            self.routing_combo_boxes[f"{task_type}_primary"] = primary_combo
            
            fallback_combo = NoWheelComboBox()
            fallback_combo.setFont(QFont("Microsoft YaHei", 16))
            fallback_combo.setFixedHeight(28)
            fallback_combo.setMinimumWidth(300)
            fallback_combo.addItem(_("none"))
            self.update_provider_combo(fallback_combo)
            routing_layout.addWidget(fallback_combo, i+1, 2)
            self.routing_combo_boxes[f"{task_type}_fallback"] = fallback_combo
        
        self.fallback_check = QCheckBox(_("enable_fallback"))
        self.fallback_check.setFont(QFont("Microsoft YaHei", 16))
        self.fallback_check.setFixedHeight(82)
        self.fallback_check.setChecked(True)
        routing_layout.addWidget(self.fallback_check, 4, 0, 1, 3)
        
        body_layout.addWidget(routing_group)
        
        scroll_area.setWidget(body_widget)
        content_layout.addWidget(scroll_area)
        
        bottom_bar = QWidget()
        bottom_bar.setObjectName("BottomBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(35, 15, 35, 25)
        bottom_layout.setSpacing(20)
        
        self.save_btn = QPushButton(_("save_config"))
        self.save_btn.setObjectName("SaveBtn")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setMinimumHeight(32)
        self.save_btn.setMinimumWidth(100)
        self.save_btn.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        
        self.cancel_btn = QPushButton(_("cancel"))
        self.cancel_btn.setObjectName("CancelBtn")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.setFont(QFont("Microsoft YaHei", 13))
        
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addWidget(self.save_btn)
        content_layout.addWidget(bottom_bar)
    
    def set_proxy_mode(self, mode):
        self.network_config['proxy_mode'] = mode
        self.direct_radio.setChecked(mode == 'direct')
        self.system_radio.setChecked(mode == 'system')
        self.custom_radio.setChecked(mode == 'custom')
        self.proxy_url_edit.setEnabled(mode == 'custom')
        self.test_btn.setEnabled(mode == 'custom' and self.proxy_url_edit.text().strip())
    
    def update_provider_combo(self, combo):
        combo.clear()
        combo.addItem(_("select_option"))
        for name in self.providers.keys():
            combo.addItem(name)
    
    def add_provider(self):
        name = self.new_provider_edit.text().strip()
        if not name:
            QMessageBox.warning(self, _("warning"), _("enter_provider_name"))
            return
        
        if name in self.providers:
            QMessageBox.warning(self, _("warning"), _("provider_exists"))
            return
        
        self.providers[name] = {
            'base_url': '',
            'api_key': '',
            'model': ''
        }
        self.add_provider_widget(name, self.providers[name])
        self.update_all_routing_combos()
        self.new_provider_edit.clear()
    
    def add_provider_widget(self, name, data):
        widget = ProviderConfigWidget(name, data)
        self.provider_widgets[name] = widget
        self.providers_layout.addWidget(widget)
    
    def update_all_routing_combos(self):
        for combo_name, combo in self.routing_combo_boxes.items():
            current_text = combo.currentText()
            self.update_provider_combo(combo)
            if current_text and current_text != _("select_option") and current_text != _("none"):
                index = combo.findText(current_text)
                if index >= 0:
                    combo.setCurrentIndex(index)
    
    async def _test_connectivity(self):
        proxy_url = self.proxy_url_edit.text().strip()
        if not proxy_url:
            self.test_result_label.setText(_("enter_proxy_address"))
            self.test_result_label.setStyleSheet("color: #ff5555;")
            return
        
        self.test_btn.setEnabled(False)
        self.test_result_label.setText(_("testing"))
        self.test_result_label.setStyleSheet("color: #f1fa8c;")
        
        try:
            success, message = await test_proxy_connectivity(proxy_url)
            if success:
                self.test_result_label.setText(f"✓ {message}")
                self.test_result_label.setStyleSheet("color: #50fa7b;")
            else:
                self.test_result_label.setText(f"✗ {message}")
                self.test_result_label.setStyleSheet("color: #ff5555;")
        except Exception as e:
            self.test_result_label.setText(f"✗ {_('test_failed')}: {str(e)}")
            self.test_result_label.setStyleSheet("color: #ff5555;")
        
        self.test_btn.setEnabled(True)
    
    def test_connectivity(self):
        asyncio.create_task(self._test_connectivity())
    
    def apply_modern_style(self):
        style_sheet = get_dracula_stylesheet() + get_config_window_style()
        self.setStyleSheet(style_sheet)
    
    def save_config(self):
        try:
            self.network_config['proxy_url'] = self.proxy_url_edit.text().strip()
            self.network_config['timeout'] = self.timeout_spin.value()
            
            for name, widget in self.provider_widgets.items():
                self.providers[name] = widget.get_data()
            
            for task_type in ['chat', 'reasoning', 'diary']:
                primary = self.routing_combo_boxes[f"{task_type}_primary"].currentText()
                fallback = self.routing_combo_boxes[f"{task_type}_fallback"].currentText()
                
                self.routing_matrix[task_type] = []
                if primary and primary != _("select_option"):
                    self.routing_matrix[task_type].append(primary)
                if fallback and fallback != _("select_option") and fallback != _("none") and fallback != primary:
                    self.routing_matrix[task_type].append(fallback)
            
            config_manager.set_many({
                'network.proxy_mode': self.network_config['proxy_mode'],
                'network.proxy_url': self.network_config['proxy_url'],
                'network.timeout': self.network_config['timeout'],
                'providers': self.providers,
                'routing_matrix': self.routing_matrix,
                'enable_fallback': self.fallback_check.isChecked()
            })
            
            import asyncio
            asyncio.create_task(reload_model_router())
            
            ToastNotification.show_notification(_("config_saved"), self.parent() if self.parent() else self)
            self.close()
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            ToastNotification.show_notification(f"{_('save_failed')}: {str(e)}", self)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.y() < 75:
                self.m_flag = True
                self.m_Position = event.globalPos() - self.pos()
                event.accept()
                self.setCursor(QCursor(Qt.OpenHandCursor))
    
    def mouseMoveEvent(self, event):
        if Qt.LeftButton and self.m_flag:
            self.move(event.globalPos() - self.m_Position)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self.m_flag = False
        self.setCursor(QCursor(Qt.ArrowCursor))
    
    def center_window(self):
        desktop = QDesktopWidget().availableGeometry()
        window_rect = self.frameGeometry()
        center_point = desktop.center()
        window_rect.moveCenter(center_point)
        self.move(window_rect.topLeft())