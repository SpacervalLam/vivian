import os
import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon

from utils.i18n import _


class SystemTray(QSystemTrayIcon):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window

        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        icon_path = os.path.join(base_dir, "icon.ico")

        self.setIcon(QIcon(icon_path))
        self.setToolTip(_("vivian"))

        self.init_tray_menu()
        self.activated.connect(self.on_tray_activated)

    def init_tray_menu(self):
        """初始化托盘菜单"""
        self.tray_menu = QMenu()
        self.setContextMenu(self.tray_menu)
        
        # 记忆管理菜单
        self.memory_action = QAction(_("memory_management"), self)
        self.memory_action.triggered.connect(self.on_memory)
        self.tray_menu.addAction(self.memory_action)
        
        # 日记本菜单
        self.diary_action = QAction(_("diary"), self)
        self.diary_action.triggered.connect(self.on_diary)
        self.tray_menu.addAction(self.diary_action)
        
        # 分隔线
        self.tray_menu.addSeparator()
        
        # 设置菜单
        self.settings_action = QAction(_("settings"), self)
        self.settings_action.triggered.connect(self.on_settings)
        self.tray_menu.addAction(self.settings_action)
        
        # 分隔线
        self.tray_menu.addSeparator()
        
        # 退出菜单
        self.quit_action = QAction(_("quit"), self)
        self.quit_action.triggered.connect(self.on_quit)
        self.tray_menu.addAction(self.quit_action)

    def on_memory(self):
        """打开记忆管理窗口"""
        if hasattr(self.main_window, '_show_memory_visualization'):
            self.main_window._show_memory_visualization()

    def on_diary(self):
        """打开日记本窗口"""
        from ui.diary_window import DiaryWindow
        
        self.diary_window = DiaryWindow(parent=self.main_window)
        self.diary_window.show()

    def on_settings(self):
        """打开配置窗口"""
        from ui.config_window import AIConfigWindow

        self.config_window = AIConfigWindow(parent=self.main_window)
        self.config_window.show()

    def on_advanced_settings(self):
        """打开高级配置窗口"""
        from ui.advanced_config_window import AdvancedConfigWindow

        self.advanced_config_window = AdvancedConfigWindow(parent=self.main_window)
        self.advanced_config_window.show()

    def on_quit(self):
        """退出应用"""
        if hasattr(self.main_window, 'close'):
            self.main_window.close()

    def on_tray_activated(self, reason):
        """处理托盘图标激活事件"""
        if reason == QSystemTrayIcon.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self.main_window.show()
        elif reason == QSystemTrayIcon.Context:
            pass
