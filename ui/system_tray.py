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

    def on_settings(self):
        """打开配置窗口"""
        from ui.config_window import AIConfigWindow

        self.config_window = AIConfigWindow(parent=self.main_window)
        self.config_window.show()

    def on_tray_activated(self, reason):
        """处理托盘图标激活事件"""
        if reason == QSystemTrayIcon.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self.main_window.show()
        elif reason == QSystemTrayIcon.Context:
            pass
