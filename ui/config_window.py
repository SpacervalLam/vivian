import asyncio
import json
import os
from typing import Dict, List, Any
from loguru import logger
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QGridLayout, QSpinBox,
    QDoubleSpinBox, QMessageBox, QFrame, QWidget, QGraphicsDropShadowEffect,
    QScrollArea, QRadioButton, QButtonGroup, QToolButton, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QPoint, QRect, QSize
from PyQt5.QtGui import QColor, QFont, QCursor, QIcon
from PyQt5.QtWidgets import QDesktopWidget

from core.ai_manager import AIManager, test_proxy_connectivity
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


class ModelConfigWidget(QWidget):
    """独立模型配置组件，包含完整的 base_url、api_key、model 配置"""
    
    def __init__(self, model_data=None, parent=None):
        super().__init__(parent)
        self.model_data = model_data or {
            'name': '',
            'base_url': '',
            'api_key': '',
            'model': ''
        }
        self.init_ui()
    
    def init_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(12)
        layout.setHorizontalSpacing(15)
        
        # 模型名称
        name_label = QLabel(_("model_identifier"))
        name_label.setFont(QFont("Microsoft YaHei", 14))
        name_label.setStyleSheet("color: #6272a4;")
        layout.addWidget(name_label, 0, 0)
        
        self.name_edit = QLineEdit(self.model_data.get('name', ''))
        self.name_edit.setFont(QFont("Microsoft YaHei", 14))
        self.name_edit.setFixedHeight(32)
        self.name_edit.setPlaceholderText(_("model_name_placeholder"))
        layout.addWidget(self.name_edit, 0, 1)
        
        # API 地址
        base_url_label = QLabel(_("api_address"))
        base_url_label.setFont(QFont("Microsoft YaHei", 14))
        base_url_label.setStyleSheet("color: #6272a4;")
        layout.addWidget(base_url_label, 1, 0)
        
        self.base_url_edit = QLineEdit(self.model_data.get('base_url', ''))
        self.base_url_edit.setFont(QFont("Microsoft YaHei", 14))
        self.base_url_edit.setFixedHeight(32)
        self.base_url_edit.setPlaceholderText(_("api_address_placeholder"))
        layout.addWidget(self.base_url_edit, 1, 1)
        
        # API Key
        api_key_label = QLabel(_("api_key"))
        api_key_label.setFont(QFont("Microsoft YaHei", 14))
        api_key_label.setStyleSheet("color: #6272a4;")
        layout.addWidget(api_key_label, 2, 0)
        
        self.api_key_edit = QLineEdit(self.model_data.get('api_key', ''))
        self.api_key_edit.setFont(QFont("Microsoft YaHei", 14))
        self.api_key_edit.setFixedHeight(32)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.api_key_edit, 2, 1)
        
        # 模型名称
        model_label = QLabel(_("model_name"))
        model_label.setFont(QFont("Microsoft YaHei", 14))
        model_label.setStyleSheet("color: #6272a4;")
        layout.addWidget(model_label, 3, 0)
        
        self.model_edit = QLineEdit(self.model_data.get('model', ''))
        self.model_edit.setFont(QFont("Microsoft YaHei", 14))
        self.model_edit.setFixedHeight(32)
        self.model_edit.setPlaceholderText(_("model_name_placeholder"))
        layout.addWidget(self.model_edit, 3, 1)
    
    def get_data(self):
        return {
            'name': self.name_edit.text().strip(),
            'base_url': self.base_url_edit.text().strip(),
            'api_key': self.api_key_edit.text().strip(),
            'model': self.model_edit.text().strip()
        }


class CollapsibleGroupBox(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._is_collapsed = True
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.header = QFrame()
        self.header.setObjectName("CollapsibleHeader")
        self.header.setFixedHeight(50)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet("""
            QFrame#CollapsibleHeader {
                background: transparent;
                border-radius: 8px;
            }
            QFrame#CollapsibleHeader:hover {
                background: rgba(189, 147, 249, 0.08);
            }
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(15, 0, 15, 0)
        
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("▶")
        self.toggle_btn.setFont(QFont("Arial", 12))
        self.toggle_btn.setFixedSize(30, 30)
        self.toggle_btn.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.toggle_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                color: #bd93f9;
                border: none;
            }
        """)
        header_layout.addWidget(self.toggle_btn)
        
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        self.title_label.setStyleSheet("color: #f8f8f2;")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        layout.addWidget(self.header)
        
        self.content = QFrame()
        self.content.setObjectName("CollapsibleContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content.setVisible(False)
        layout.addWidget(self.content)
        
        self.header.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        if obj == self.header and event.type() == event.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.toggle()
                return True
        return super().eventFilter(obj, event)
    
    def toggle(self):
        self._is_collapsed = not self._is_collapsed
        self.content.setVisible(not self._is_collapsed)
        self.toggle_btn.setText("▼" if not self._is_collapsed else "▶")
    
    def setContentLayout(self, layout):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.content_layout.addLayout(layout)


class AIConfigWindow(QDialog):
    """
    现代轻科技风格 AI 配置模态框 - 优化版
    """
    
    def __init__(self, parent=None, ai_manager=None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        
        # 1. 基础窗口设置 - 增大窗口尺寸
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(1200, 900)
        self.resize(1250, 950)
        
        # 鼠标拖拽相关变量
        self.m_flag = False
        self.m_Position = QPoint()

        # 2. 初始化配置数据
        self.config = {
            'provider': config_manager.get("ai.provider", 'openai'),
            'api_key': config_manager.get("ai.api_key", ""),
            'endpoint': config_manager.get("ai.endpoint", ''),
            'model': config_manager.get("ai.model", ''),
            'temperature': config_manager.get("ai.temperature", 0.7),
            'max_tokens': config_manager.get("ai.max_tokens", 2000),
            'use_proxy': config_manager.get("ai.use_proxy", False),
            'proxy_type': config_manager.get("ai.proxy_type", 'http'),
            'proxy_host': config_manager.get("ai.proxy_host", '127.0.0.1'),
            'proxy_port': config_manager.get("ai.proxy_port", 7890),
            'proxy_auth': config_manager.get("ai.proxy_auth", False),
            'proxy_username': config_manager.get("ai.proxy_username", ''),
            'proxy_password': config_manager.get("ai.proxy_password", ''),
            'local_model_path': config_manager.get("ai.local_model_path", ''),
            'local_model_n_ctx': config_manager.get("ai.local_model_n_ctx", 2048),
            'local_model_n_threads': config_manager.get("ai.local_model_n_threads", 4),
            'local_model_n_gpu_layers': config_manager.get("ai.local_model_n_gpu_layers", 0),
            'enable_local_proactive': config_manager.get("ai.enable_local_proactive", True),
            'embedding_model_path': config_manager.get("memory.embedding_model_path", ''),
            'language': config_manager.get("base.language", "zh-CN")
        }
        
        for key, value in self.config.items():
            if value is None:
                self.config[key] = ''

        # 加载高级配置数据
        self.network_config = {
            'proxy_mode': config_manager.get("network.proxy_mode", "direct"),
            'proxy_url': config_manager.get("network.proxy_url", ""),
            'timeout': config_manager.get("network.timeout", 30.0)
        }
        
        providers = config_manager.get("providers", {})
        self.routing_matrix = self._migrate_routing_matrix(
            config_manager.get("routing_matrix", {
                'chat': [],
                'reasoning': [],
                'diary': []
            }),
            providers
        )
        self.enable_fallback = config_manager.get("enable_fallback", True)
        self.enable_routing_matrix = config_manager.get("enable_routing_matrix", False)
        
        self.routing_model_widgets = {}

        # 3. 构建 UI 和样式
        self.initUI()
        self.apply_modern_style()
        
        # 4. 初始化后的后续操作
        self._post_init()
    
    def _migrate_routing_matrix(self, matrix: Dict[str, Any], providers: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
        """将旧的路由矩阵格式（字符串列表）迁移到新格式（完整配置列表）"""
        providers = providers or {}
        migrated = {}
        
        for task_type, entries in matrix.items():
            migrated_entries = []
            for entry in entries:
                if isinstance(entry, str):
                    if entry in providers:
                        provider_config = providers[entry]
                        migrated_entries.append({
                            'name': entry,
                            'base_url': provider_config.get('base_url', ''),
                            'api_key': provider_config.get('api_key', ''),
                            'model': provider_config.get('model', '')
                        })
                elif isinstance(entry, dict):
                    migrated_entries.append(entry)
            
            migrated[task_type] = migrated_entries
        
        if not migrated and providers:
            default_provider = list(providers.keys())[0]
            default_config = providers[default_provider]
            default_entry = {
                'name': default_provider,
                'base_url': default_config.get('base_url', ''),
                'api_key': default_config.get('api_key', ''),
                'model': default_config.get('model', '')
            }
            migrated = {
                'chat': [default_entry],
                'reasoning': [default_entry],
                'diary': [default_entry]
            }
        
        return migrated
    
    def _post_init(self):
        """初始化后的后续操作"""
        self.update_proxy_ui_state()
        self.update_network_proxy_ui_state()
        self.center_window()

    def initUI(self):
        """构建界面布局"""
        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- 背景容器 ---
        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("MainFrame")
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.bg_frame.setGraphicsEffect(shadow)
        
        main_layout.addWidget(self.bg_frame)

        # --- 内容布局 ---
        content_layout = QVBoxLayout(self.bg_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 1. 自定义标题栏 - 更高更宽
        self.title_bar = QWidget()
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(65)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(30, 0, 30, 0)
        
        title_label = QLabel(_("settings"))
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

        # --- 核心设置组 ---
        basic_group = QGroupBox(_("basic_model_settings"))
        basic_group.setObjectName("ConfigGroup")
        basic_layout = QGridLayout(basic_group)
        basic_layout.setVerticalSpacing(20)
        basic_layout.setHorizontalSpacing(20)

        # 服务商
        provider_label = QLabel(_("service_provider"))
        provider_label.setFont(QFont("Microsoft YaHei", 18))
        basic_layout.addWidget(provider_label, 0, 0)
        
        self.provider_combo = NoWheelComboBox()
        self.provider_combo.setFont(QFont("Microsoft YaHei", 18))
        self.provider_combo.setFixedHeight(76)
        self.provider_combo.setMinimumWidth(525)
        self.provider_combo.addItems(['openai', 'doubao', 'gemini', 'anthropic', 'moonshot', 'deepseek', 'dashscope', 'ollama'])
        self.provider_combo.setCurrentText(self.config['provider'])
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        basic_layout.addWidget(self.provider_combo, 0, 1)

        # API Key
        api_key_label = QLabel(_("api_key"))
        api_key_label.setFont(QFont("Microsoft YaHei", 18))
        basic_layout.addWidget(api_key_label, 1, 0)
        
        self.api_key_edit = QLineEdit(self.config['api_key'])
        self.api_key_edit.setFont(QFont("Microsoft YaHei", 18))
        self.api_key_edit.setFixedHeight(28)
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("")
        basic_layout.addWidget(self.api_key_edit, 1, 1)

        # Endpoint
        endpoint_label = QLabel(_("endpoint"))
        endpoint_label.setFont(QFont("Microsoft YaHei", 18))
        basic_layout.addWidget(endpoint_label, 2, 0)
        
        self.endpoint_edit = QLineEdit(self.config['endpoint'])
        self.endpoint_edit.setFont(QFont("Microsoft YaHei", 18))
        self.endpoint_edit.setFixedHeight(28)
        self.endpoint_edit.setPlaceholderText("如：https://api.openai.com/v1")
        basic_layout.addWidget(self.endpoint_edit, 2, 1)

        # Model
        model_label = QLabel(_("model"))
        model_label.setFont(QFont("Microsoft YaHei", 18))
        basic_layout.addWidget(model_label, 3, 0)
        
        self.model_edit = QLineEdit(self.config['model'])
        self.model_edit.setFont(QFont("Microsoft YaHei", 18))
        self.model_edit.setFixedHeight(28)
        self.model_edit.setPlaceholderText("如：gpt-4o-mini")
        basic_layout.addWidget(self.model_edit, 3, 1)

        # 参数行 (Temp + Tokens)
        param_layout = QHBoxLayout()
        param_layout.setSpacing(30)
        
        temp_label = QLabel(_("temperature"))
        temp_label.setFont(QFont("Microsoft YaHei", 18))
        param_layout.addWidget(temp_label)
        
        self.temp_spin = NoWheelDoubleSpinBox()
        self.temp_spin.setFont(QFont("Microsoft YaHei", 18))
        self.temp_spin.setFixedHeight(28)
        self.temp_spin.setFixedWidth(120)
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(self.config['temperature'])
        param_layout.addWidget(self.temp_spin)
        
        tokens_label = QLabel(_("max_tokens"))
        tokens_label.setFont(QFont("Microsoft YaHei", 18))
        param_layout.addWidget(tokens_label)
        
        self.tokens_spin = NoWheelSpinBox()
        self.tokens_spin.setFont(QFont("Microsoft YaHei", 18))
        self.tokens_spin.setFixedHeight(28)
        self.tokens_spin.setFixedWidth(120)
        self.tokens_spin.setRange(100, 32000)
        self.tokens_spin.setSingleStep(100)
        self.tokens_spin.setValue(self.config['max_tokens'])
        param_layout.addWidget(self.tokens_spin)
        
        param_layout.addStretch()
        basic_layout.addLayout(param_layout, 5, 0, 1, 2)
        body_layout.addWidget(basic_group)

        # --- 本地模型设置组 ---        
        local_group = QGroupBox(_("local_model_settings"))
        local_group.setObjectName("ConfigGroup")
        local_layout = QGridLayout(local_group)
        local_layout.setVerticalSpacing(22)
        local_layout.setHorizontalSpacing(20)

        # 本地模型路径
        local_model_label = QLabel(_("local_model_path"))
        local_model_label.setFont(QFont("Microsoft YaHei", 18))
        local_layout.addWidget(local_model_label, 0, 0)
        
        self.local_model_path_edit = QLineEdit(self.config['local_model_path'])
        self.local_model_path_edit.setFont(QFont("Microsoft YaHei", 18))
        self.local_model_path_edit.setFixedHeight(28)
        self.local_model_path_edit.setPlaceholderText("如：D:\\models\\llama3.gguf")
        local_layout.addWidget(self.local_model_path_edit, 0, 1)

        # 嵌入模型路径
        embedding_label = QLabel(_("embedding_model_path"))
        embedding_label.setFont(QFont("Microsoft YaHei", 18))
        local_layout.addWidget(embedding_label, 4, 0)
        
        self.embedding_model_path_edit = QLineEdit(self.config['embedding_model_path'])
        self.embedding_model_path_edit.setFont(QFont("Microsoft YaHei", 18))
        self.embedding_model_path_edit.setFixedHeight(28)
        self.embedding_model_path_edit.setPlaceholderText("如：E:\\embedding\\all-MiniLM-L6-v2")
        self.embedding_model_path_edit.setToolTip("用于文本向量化的SentenceTransformer模型路径")
        local_layout.addWidget(self.embedding_model_path_edit, 4, 1)

        # 本地模型参数
        param_layout = QHBoxLayout()
        param_layout.setSpacing(25)
        
        ctx_label = QLabel(_("context_window"))
        ctx_label.setFont(QFont("Microsoft YaHei", 18))
        param_layout.addWidget(ctx_label)
        
        self.local_model_n_ctx_spin = NoWheelSpinBox()
        self.local_model_n_ctx_spin.setFont(QFont("Microsoft YaHei", 18))
        self.local_model_n_ctx_spin.setFixedHeight(28)
        self.local_model_n_ctx_spin.setFixedWidth(120)
        self.local_model_n_ctx_spin.setRange(512, 16384)
        self.local_model_n_ctx_spin.setSingleStep(512)
        self.local_model_n_ctx_spin.setValue(self.config['local_model_n_ctx'])
        param_layout.addWidget(self.local_model_n_ctx_spin)
        
        threads_label = QLabel(_("threads"))
        threads_label.setFont(QFont("Microsoft YaHei", 18))
        param_layout.addWidget(threads_label)
        
        self.local_model_n_threads_spin = NoWheelSpinBox()
        self.local_model_n_threads_spin.setFont(QFont("Microsoft YaHei", 18))
        self.local_model_n_threads_spin.setFixedHeight(28)
        self.local_model_n_threads_spin.setFixedWidth(100)
        self.local_model_n_threads_spin.setRange(1, 16)
        self.local_model_n_threads_spin.setSingleStep(1)
        self.local_model_n_threads_spin.setValue(self.config['local_model_n_threads'])
        param_layout.addWidget(self.local_model_n_threads_spin)
        
        gpu_label = QLabel(_("gpu_layers"))
        gpu_label.setFont(QFont("Microsoft YaHei", 18))
        param_layout.addWidget(gpu_label)
        
        self.local_model_n_gpu_layers_spin = NoWheelSpinBox()
        self.local_model_n_gpu_layers_spin.setFont(QFont("Microsoft YaHei", 18))
        self.local_model_n_gpu_layers_spin.setFixedHeight(28)
        self.local_model_n_gpu_layers_spin.setFixedWidth(100)
        self.local_model_n_gpu_layers_spin.setRange(0, 32)
        self.local_model_n_gpu_layers_spin.setSingleStep(1)
        self.local_model_n_gpu_layers_spin.setValue(self.config['local_model_n_gpu_layers'])
        param_layout.addWidget(self.local_model_n_gpu_layers_spin)
        
        param_layout.addStretch()
        local_layout.addLayout(param_layout, 1, 0, 1, 2)
        
        # 启用本地LLM主动互动选项
        self.enable_local_proactive_check = QCheckBox(_("enable_local_proactive"))
        self.enable_local_proactive_check.setFont(QFont("Microsoft YaHei", 18))
        self.enable_local_proactive_check.setFixedHeight(82)
        self.enable_local_proactive_check.setChecked(self.config['enable_local_proactive'])
        self.enable_local_proactive_check.setToolTip("启用后，将使用本地LLM实现整点问候、调戏回应、长期未交互问候等主动互动功能")
        local_layout.addWidget(self.enable_local_proactive_check, 2, 0, 1, 2)
        
        body_layout.addWidget(local_group)


        proxy_group = QGroupBox(_("network_connection"))
        proxy_group.setObjectName("ConfigGroup")
        proxy_layout = QGridLayout(proxy_group)
        proxy_layout.setVerticalSpacing(20)
        
        self.use_proxy_check = QCheckBox(_("enable_proxy_server"))
        self.use_proxy_check.setFont(QFont("Microsoft YaHei", 18))
        self.use_proxy_check.setFixedHeight(82)
        self.use_proxy_check.setChecked(self.config['use_proxy'])
        self.use_proxy_check.stateChanged.connect(self.update_proxy_ui_state)
        proxy_layout.addWidget(self.use_proxy_check, 0, 0, 1, 2)

        # 代理详情容器
        self.proxy_details_widget = QWidget()
        details_layout = QGridLayout(self.proxy_details_widget)
        details_layout.setContentsMargins(0, 12, 0, 0)
        details_layout.setSpacing(18)

        self.proxy_type_combo = NoWheelComboBox()
        self.proxy_type_combo.setFont(QFont("Microsoft YaHei", 18))
        self.proxy_type_combo.setFixedHeight(28)
        self.proxy_type_combo.setFixedWidth(195)
        self.proxy_type_combo.addItems(['http', 'socks5'])
        self.proxy_type_combo.setCurrentText(self.config['proxy_type'])
        
        self.proxy_host_edit = QLineEdit(self.config['proxy_host'])
        self.proxy_host_edit.setFont(QFont("Microsoft YaHei", 18))
        self.proxy_host_edit.setFixedHeight(28)
        self.proxy_host_edit.setFixedWidth(285)
        self.proxy_host_edit.setPlaceholderText("127.0.0.1")
        
        port_label = QLabel(_("proxy_port"))
        port_label.setFont(QFont("Microsoft YaHei", 18))
        
        self.proxy_port_spin = NoWheelSpinBox()
        self.proxy_port_spin.setFont(QFont("Microsoft YaHei", 18))
        self.proxy_port_spin.setFixedHeight(28)
        self.proxy_port_spin.setFixedWidth(100)
        self.proxy_port_spin.setRange(1, 65535)
        self.proxy_port_spin.setValue(self.config['proxy_port'] if self.config['proxy_port'] else 7890)

        type_label = QLabel(_("proxy_type"))
        type_label.setFont(QFont("Microsoft YaHei", 18))
        
        host_label = QLabel(_("proxy_host"))
        host_label.setFont(QFont("Microsoft YaHei", 18))

        details_layout.addWidget(type_label, 0, 0)
        details_layout.addWidget(self.proxy_type_combo, 0, 1)
        details_layout.addWidget(host_label, 0, 2)
        details_layout.addWidget(self.proxy_host_edit, 0, 3)
        details_layout.addWidget(port_label, 0, 4)
        details_layout.addWidget(self.proxy_port_spin, 0, 5)

        proxy_layout.addWidget(self.proxy_details_widget, 1, 0, 1, 2)
        body_layout.addWidget(proxy_group)

        # --- 语言设置组 ---
        language_group = QGroupBox(_("language_settings"))
        language_group.setObjectName("ConfigGroup")
        language_layout = QGridLayout(language_group)
        language_layout.setVerticalSpacing(20)
        language_layout.setHorizontalSpacing(20)

        # 语言选择
        lang_label = QLabel(_("language_settings"))
        lang_label.setFont(QFont("Microsoft YaHei", 18))
        language_layout.addWidget(lang_label, 0, 0)
        
        self.language_combo = NoWheelComboBox()
        self.language_combo.setFont(QFont("Microsoft YaHei", 18))
        self.language_combo.setFixedHeight(28)
        self.language_combo.setMinimumWidth(330)
        for code, name in available_languages.items():
            self.language_combo.addItem(name, code)
        
        current_lang = self.config.get('language', 'zh-CN')
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == current_lang:
                self.language_combo.setCurrentIndex(i)
                break
        language_layout.addWidget(self.language_combo, 0, 1)
        body_layout.addWidget(language_group)

        # --- 高级设置（可折叠）---
        advanced_group = CollapsibleGroupBox(_("advanced_settings"))
        advanced_layout = QVBoxLayout()
        advanced_layout.setSpacing(20)

        # 网络与代理设置
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
        
        self.network_proxy_url_edit = QLineEdit(self.network_config['proxy_url'])
        self.network_proxy_url_edit.setFont(QFont("Microsoft YaHei", 18))
        self.network_proxy_url_edit.setFixedHeight(28)
        self.network_proxy_url_edit.setMinimumWidth(400)
        self.network_proxy_url_edit.setPlaceholderText(_("proxy_address_placeholder"))
        url_layout.addWidget(self.network_proxy_url_edit)
        
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
        
        self.network_timeout_spin = NoWheelDoubleSpinBox()
        self.network_timeout_spin.setFont(QFont("Microsoft YaHei", 18))
        self.network_timeout_spin.setFixedHeight(28)
        self.network_timeout_spin.setFixedWidth(120)
        self.network_timeout_spin.setRange(5.0, 120.0)
        self.network_timeout_spin.setSingleStep(1.0)
        self.network_timeout_spin.setValue(self.network_config['timeout'])
        network_layout.addWidget(self.network_timeout_spin, 2, 1)
        
        advanced_layout.addWidget(network_group)

        # AI 模型路由矩阵
        routing_group = QGroupBox(_("ai_routing_matrix"))
        routing_group.setObjectName("ConfigGroup")
        routing_layout = QVBoxLayout(routing_group)
        routing_layout.setSpacing(15)
        
        # 启用模型矩阵开关
        self.enable_routing_check = QCheckBox(_("enable_routing_matrix"))
        self.enable_routing_check.setFont(QFont("Microsoft YaHei", 18))
        self.enable_routing_check.setFixedHeight(82)
        self.enable_routing_check.setChecked(self.enable_routing_matrix)
        routing_layout.addWidget(self.enable_routing_check)
        
        # 路由矩阵内容容器（根据开关显示/隐藏）
        self.routing_content_widget = QWidget()
        routing_content_layout = QVBoxLayout(self.routing_content_widget)
        routing_content_layout.setContentsMargins(0, 0, 0, 0)
        routing_content_layout.setSpacing(20)
        
        tasks = [
            (_("daily_chat"), "chat"),
            (_("tool_reasoning"), "reasoning"),
            (_("smart_diary"), "diary")
        ]
        
        for i, (label, task_type) in enumerate(tasks):
            task_group = QGroupBox(label)
            task_group.setObjectName("ConfigGroup")
            task_layout = QGridLayout(task_group)
            task_layout.setVerticalSpacing(15)
            task_layout.setHorizontalSpacing(20)
            
            # 首选模型
            primary_label = QLabel(_("primary_model"))
            primary_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
            primary_label.setStyleSheet("color: #bd93f9;")
            task_layout.addWidget(primary_label, 0, 0)
            
            primary_widget = ModelConfigWidget()
            task_layout.addWidget(primary_widget, 1, 0)
            self.routing_model_widgets[f"{task_type}_primary"] = primary_widget
            
            # 备用模型
            fallback_label = QLabel(_("fallback_model"))
            fallback_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
            fallback_label.setStyleSheet("color: #6272a4;")
            task_layout.addWidget(fallback_label, 2, 0)
            
            fallback_widget = ModelConfigWidget()
            task_layout.addWidget(fallback_widget, 3, 0)
            self.routing_model_widgets[f"{task_type}_fallback"] = fallback_widget
            
            routing_content_layout.addWidget(task_group)
        
        self.fallback_check = QCheckBox(_("enable_fallback"))
        self.fallback_check.setFont(QFont("Microsoft YaHei", 18))
        self.fallback_check.setFixedHeight(82)
        self.fallback_check.setChecked(self.enable_fallback)
        routing_content_layout.addWidget(self.fallback_check)
        
        routing_layout.addWidget(self.routing_content_widget)
        
        # 连接开关信号
        self.enable_routing_check.toggled.connect(self.routing_content_widget.setVisible)
        
        # 初始化显示状态
        self.routing_content_widget.setVisible(self.enable_routing_matrix)
        
        advanced_layout.addWidget(routing_group)

        advanced_group.setContentLayout(advanced_layout)
        body_layout.addWidget(advanced_group)

        # 初始化路由模型配置的初始值
        self.init_routing_combo_values()

        scroll_area.setWidget(body_widget)
        content_layout.addWidget(scroll_area)

        # 3. 底部按钮栏 - 更高更宽的按钮
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

    def apply_modern_style(self):
        """应用 Dracula Dark Theme CSS 样式表"""
        style_sheet = get_dracula_stylesheet() + get_config_window_style()
        self.setStyleSheet(style_sheet)

    def on_provider_changed(self, text):
        """提供商改变时自动填充默认值"""
        defaults = {
            'openai': {'endpoint': 'https://api.openai.com/v1/chat/completions', 'model': 'gpt-4o-mini'},
            'doubao': {'endpoint': 'https://ark.cn-beijing.volces.com/api/v3/responses', 'model': 'doubao-seed-2-0-lite-260428'},
            'gemini': {'endpoint': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent', 'model': 'gemini-pro'},
            'anthropic': {'endpoint': 'https://api.anthropic.com/v1/messages', 'model': 'claude-3-5-sonnet-20241022'},
            'moonshot': {'endpoint': 'https://api.moonshot.cn/v1/chat/completions', 'model': 'moonshot-v1-8k'},
            'deepseek': {'endpoint': 'https://api.deepseek.com/v1/chat/completions', 'model': 'deepseek-chat'},
            'dashscope': {'endpoint': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions', 'model': 'qwen-max'},
            'ollama': {'endpoint': 'http://localhost:11434/v1', 'model': 'llama3'}
        }
        
        current_endpoint = self.endpoint_edit.text()
        current_model = self.model_edit.text()
        
        all_default_endpoints = [defaults[prov]['endpoint'] for prov in defaults if prov in defaults]
        all_default_models = [defaults[prov]['model'] for prov in defaults if prov in defaults]
        
        if text in defaults:
            if not current_endpoint or current_endpoint in all_default_endpoints:
                self.endpoint_edit.setText(defaults[text]['endpoint'])
            
            if not current_model or current_model in all_default_models:
                self.model_edit.setText(defaults[text]['model'])
            
            self.endpoint_edit.setToolTip(f"默认地址: {defaults[text]['endpoint']}")

    def update_proxy_ui_state(self):
        """根据复选框状态显示/隐藏代理设置"""
        is_enabled = self.use_proxy_check.isChecked()
        self.proxy_details_widget.setVisible(is_enabled)

    def update_network_proxy_ui_state(self):
        """根据网络代理模式更新UI状态"""
        mode = self.network_config.get('proxy_mode', 'direct')
        self.network_proxy_url_edit.setEnabled(mode == 'custom')
        self.test_btn.setEnabled(mode == 'custom' and self.network_proxy_url_edit.text().strip())
        self.direct_radio.setChecked(mode == 'direct')
        self.system_radio.setChecked(mode == 'system')
        self.custom_radio.setChecked(mode == 'custom')

    def set_proxy_mode(self, mode):
        """设置网络代理模式"""
        self.network_config['proxy_mode'] = mode
        self.update_network_proxy_ui_state()

    def init_routing_combo_values(self):
        """初始化路由模型配置的初始值"""
        for task_type in ['chat', 'reasoning', 'diary']:
            entries = self.routing_matrix.get(task_type, [])
            if entries:
                primary_data = entries[0]
                primary_widget = self.routing_model_widgets.get(f"{task_type}_primary")
                if primary_widget:
                    primary_widget.name_edit.setText(primary_data.get('name', ''))
                    primary_widget.base_url_edit.setText(primary_data.get('base_url', ''))
                    primary_widget.api_key_edit.setText(primary_data.get('api_key', ''))
                    primary_widget.model_edit.setText(primary_data.get('model', ''))
                if len(entries) > 1:
                    fallback_data = entries[1]
                    fallback_widget = self.routing_model_widgets.get(f"{task_type}_fallback")
                    if fallback_widget:
                        fallback_widget.name_edit.setText(fallback_data.get('name', ''))
                        fallback_widget.base_url_edit.setText(fallback_data.get('base_url', ''))
                        fallback_widget.api_key_edit.setText(fallback_data.get('api_key', ''))
                        fallback_widget.model_edit.setText(fallback_data.get('model', ''))

    async def _test_connectivity(self):
        """测试代理连通性（异步）"""
        proxy_url = self.network_proxy_url_edit.text().strip()
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
        """测试代理连通性"""
        asyncio.create_task(self._test_connectivity())

    def _update_advanced_config_from_ui(self):
        """从UI读取高级配置"""
        self.network_config['proxy_url'] = self.network_proxy_url_edit.text().strip()
        self.network_config['timeout'] = self.network_timeout_spin.value()
        
        for task_type in ['chat', 'reasoning', 'diary']:
            primary_widget = self.routing_model_widgets.get(f"{task_type}_primary")
            fallback_widget = self.routing_model_widgets.get(f"{task_type}_fallback")
            
            self.routing_matrix[task_type] = []
            
            if primary_widget:
                primary_data = primary_widget.get_data()
                if primary_data.get('model') or primary_data.get('base_url'):
                    self.routing_matrix[task_type].append(primary_data)
            
            if fallback_widget:
                fallback_data = fallback_widget.get_data()
                if fallback_data.get('model') or fallback_data.get('base_url'):
                    self.routing_matrix[task_type].append(fallback_data)
        
        self.enable_fallback = self.fallback_check.isChecked()
        self.enable_routing_matrix = self.enable_routing_check.isChecked()

    def _update_config_from_ui(self):
        """从UI读取配置到字典"""
        self.config['provider'] = self.provider_combo.currentText()
        self.config['api_key'] = self.api_key_edit.text().strip()
        self.config['endpoint'] = self.endpoint_edit.text().strip()
        self.config['model'] = self.model_edit.text().strip()
        self.config['temperature'] = self.temp_spin.value()
        self.config['max_tokens'] = self.tokens_spin.value()
        
        self.config['local_model_path'] = self.local_model_path_edit.text().strip()
        self.config['local_model_n_ctx'] = self.local_model_n_ctx_spin.value()
        self.config['local_model_n_threads'] = self.local_model_n_threads_spin.value()
        self.config['local_model_n_gpu_layers'] = self.local_model_n_gpu_layers_spin.value()
        self.config['enable_local_proactive'] = self.enable_local_proactive_check.isChecked()
        
        self.config['embedding_model_path'] = self.embedding_model_path_edit.text().strip()
        
        self.config['use_proxy'] = self.use_proxy_check.isChecked()
        self.config['proxy_type'] = self.proxy_type_combo.currentText()
        self.config['proxy_host'] = self.proxy_host_edit.text().strip()
        self.config['proxy_port'] = self.proxy_port_spin.value()
        
        self.config['language'] = self.language_combo.currentData()

    def save_config(self):
        """保存配置到配置管理器"""
        logger.info(f"[AIConfigWindow] save_config 被调用")

        self._update_config_from_ui()
        self._update_advanced_config_from_ui()

        if not self.config['api_key'] and self.config['provider'] != 'ollama':
            QMessageBox.warning(self, _("warning"), _("api_key_empty"))
            return

        try:
            batch_data = {}
            for k, v in self.config.items():
                if k == 'language':
                    batch_data['base.language'] = v
                elif k == 'embedding_model_path':
                    batch_data['memory.embedding_model_path'] = v
                else:
                    batch_data[f"ai.{k}"] = v

            # 保存高级配置
            batch_data['network.proxy_mode'] = self.network_config['proxy_mode']
            batch_data['network.proxy_url'] = self.network_config['proxy_url']
            batch_data['network.timeout'] = self.network_config['timeout']
            batch_data['routing_matrix'] = self.routing_matrix
            batch_data['enable_fallback'] = self.enable_fallback
            batch_data['enable_routing_matrix'] = self.enable_routing_matrix

            config_manager.set_many(batch_data)

            if self.ai_manager:
                self.ai_manager.update_config(**self.config)
            
            # 如果有父窗口并且有 brain，重新加载主动交互配置
            if self.parent() and hasattr(self.parent(), 'brain') and hasattr(self.parent().brain, 'reload_proactive_config'):
                self.parent().brain.reload_proactive_config()

            if 'language' in self.config:
                translator.set_language(self.config['language'])

            if 'language' in self.config and self.parent() and hasattr(self.parent(), '_init_system_tray'):
                self.parent()._init_system_tray()

            # 重新加载模型路由
            asyncio.create_task(reload_model_router())

            ToastNotification.show_notification(_("config_saved"), self.parent() if self.parent() else self)
            self.close()

        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            ToastNotification.show_notification(_("save_failed", error=str(e)), self)

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
        """窗口居中显示"""
        desktop = QDesktopWidget().availableGeometry()
        window_rect = self.frameGeometry()
        center_point = desktop.center()
        window_rect.moveCenter(center_point)
        self.move(window_rect.topLeft())
