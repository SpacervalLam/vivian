import json
import os
from loguru import logger
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QGridLayout, QSpinBox,
    QDoubleSpinBox, QMessageBox, QFrame, QWidget, QGraphicsDropShadowEffect,
    QScrollArea
)
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QColor, QFont, QCursor
from PyQt5.QtWidgets import QDesktopWidget

from core.ai_manager import AIManager
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

        # 3. 构建 UI 和样式
        self.initUI()
        self.apply_modern_style()
        self.update_proxy_ui_state()
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
