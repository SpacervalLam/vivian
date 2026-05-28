"""日记浏览器窗口组件"""

import os
from datetime import datetime

from PyQt5.QtCore import Qt, QDate, QTimer
from PyQt5.QtGui import QColor, QIcon, QFont
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QListWidget, QListWidgetItem, QTextEdit, QLabel,
                            QPushButton, QFrame, QDateEdit, QMessageBox,
                            QDialog, QLineEdit, QFileDialog)

from loguru import logger
from core.diary_system import get_diary_system


MOOD_EMOJIS = {
    "happy": "☀️",
    "good": "😊",
    "neutral": "😐",
    "sad": "😢",
    "angry": "😠"
}

MOOD_COLORS = {
    "happy": "#FFCA28",
    "good": "#66BB6A",
    "neutral": "#9E9E9E",
    "sad": "#42A5F5",
    "angry": "#EF5350"
}


class DiaryWindow(QMainWindow):
    """日记浏览器窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._diary_system = get_diary_system()
        self._selected_entry = None
        
        self._init_ui()
        self._load_entries()
    
    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("薇薇安的日记本")
        self.setGeometry(100, 100, 800, 600)
        
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 左侧日记列表
        left_panel = QWidget()
        left_panel.setFixedWidth(250)
        left_layout = QVBoxLayout(left_panel)
        
        # 搜索和过滤区域
        search_layout = QHBoxLayout()
        
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索日记...")
        self._search_edit.textChanged.connect(self._filter_entries)
        search_layout.addWidget(self._search_edit)
        
        self._date_filter = QDateEdit()
        self._date_filter.setDisplayFormat("yyyy-MM-dd")
        self._date_filter.setDate(QDate.currentDate())
        self._date_filter.dateChanged.connect(self._filter_entries)
        search_layout.addWidget(self._date_filter)
        
        left_layout.addLayout(search_layout)
        
        # 日记列表
        self._entry_list = QListWidget()
        self._entry_list.setStyleSheet("""
            QListWidget {
                background-color: #1e232b;
                border: none;
                border-radius: 8px;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }
            QListWidget::item:hover {
                background-color: rgba(155, 89, 182, 0.2);
            }
            QListWidget::item:selected {
                background-color: rgba(155, 89, 182, 0.3);
            }
        """)
        self._entry_list.itemClicked.connect(self._on_entry_selected)
        left_layout.addWidget(self._entry_list)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.clicked.connect(self._load_entries)
        button_layout.addWidget(self._refresh_btn)
        
        self._export_btn = QPushButton("导出")
        self._export_btn.clicked.connect(self._export_diaries)
        button_layout.addWidget(self._export_btn)
        
        left_layout.addLayout(button_layout)
        
        main_layout.addWidget(left_panel)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet("background-color: rgba(255,255,255,0.1);")
        main_layout.addWidget(separator)
        
        # 右侧日记内容
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # 日记头部
        self._header_widget = QWidget()
        header_layout = QHBoxLayout(self._header_widget)
        
        self._date_label = QLabel("选择一篇日记")
        self._date_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        header_layout.addWidget(self._date_label)
        
        self._mood_icon = QLabel("📝")
        self._mood_icon.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(self._mood_icon)
        
        right_layout.addWidget(self._header_widget)
        
        # 日记统计
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.6);")
        right_layout.addWidget(self._stats_label)
        
        # 分隔线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("color: rgba(255,255,255,0.2);")
        right_layout.addWidget(separator2)
        
        # 日记内容
        self._content_edit = QTextEdit()
        self._content_edit.setReadOnly(True)
        self._content_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e232b;
                border: none;
                color: white;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        right_layout.addWidget(self._content_edit)
        
        # 关键事件
        self._events_label = QLabel("今日要事")
        self._events_label.setStyleSheet("font-size: 14px; font-weight: bold; color: rgba(255,255,255,0.8);")
        right_layout.addWidget(self._events_label)
        
        self._events_list = QListWidget()
        self._events_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(255,255,255,0.05);
                border: none;
                border-radius: 6px;
            }
            QListWidget::item {
                padding: 6px;
                color: rgba(255,255,255,0.7);
            }
        """)
        right_layout.addWidget(self._events_list)
        
        # 操作按钮
        action_layout = QHBoxLayout()
        
        self._edit_btn = QPushButton("编辑")
        self._edit_btn.clicked.connect(self._edit_entry)
        action_layout.addWidget(self._edit_btn)
        
        self._delete_btn = QPushButton("删除")
        self._delete_btn.clicked.connect(self._delete_entry)
        action_layout.addWidget(self._delete_btn)
        
        self._generate_btn = QPushButton("手动生成")
        self._generate_btn.clicked.connect(self._generate_diary)
        action_layout.addWidget(self._generate_btn)
        
        right_layout.addLayout(action_layout)
        
        main_layout.addWidget(right_panel)
    
    def _load_entries(self):
        """加载日记列表"""
        self._entry_list.clear()
        
        entries = self._diary_system.get_entries()
        
        if not entries:
            item = QListWidgetItem("暂无日记")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            item.setForeground(QColor(100, 100, 100))
            self._entry_list.addItem(item)
            return
        
        for entry in entries:
            mood_emoji = MOOD_EMOJIS.get(entry.mood_tag, "📝")
            item = QListWidgetItem(f"{entry.date} {mood_emoji}")
            item.setData(Qt.UserRole, entry.id)
            self._entry_list.addItem(item)
    
    def _filter_entries(self):
        """过滤日记列表"""
        search_text = self._search_edit.text().lower()
        filter_date = self._date_filter.date().toString("yyyy-MM-dd")
        
        for i in range(self._entry_list.count()):
            item = self._entry_list.item(i)
            entry_id = item.data(Qt.UserRole)
            
            if entry_id:
                entry = self._diary_system.get_entry(entry_id)
                if entry:
                    match = True
                    
                    if search_text and search_text not in entry.content.lower():
                        match = False
                    
                    if filter_date and entry.date != filter_date:
                        match = False
                    
                    item.setHidden(not match)
    
    def _on_entry_selected(self, item):
        """选择日记条目"""
        entry_id = item.data(Qt.UserRole)
        if not entry_id:
            return
        
        self._selected_entry = self._diary_system.get_entry(entry_id)
        if self._selected_entry:
            self._display_entry(self._selected_entry)
    
    def _display_entry(self, entry):
        """显示日记内容"""
        self._date_label.setText(f"{entry.date}")
        self._mood_icon.setText(MOOD_EMOJIS.get(entry.mood_tag, "📝"))
        
        stats = f"""触发方式: {entry.trigger_type} | 互动次数: {entry.interaction_count} | 字数: {entry.word_count}
生成时间: {datetime.fromtimestamp(entry.created_at).strftime('%Y-%m-%d %H:%M:%S')}"""
        self._stats_label.setText(stats)
        
        self._content_edit.setPlainText(entry.content)
        
        # 更新关键事件列表
        self._events_list.clear()
        if entry.key_events:
            for event in entry.key_events:
                self._events_list.addItem(event)
        else:
            self._events_list.addItem("暂无特别事件")
    
    def _edit_entry(self):
        """编辑日记"""
        if not self._selected_entry:
            QMessageBox.warning(self, "警告", "请先选择一篇日记")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑日记")
        dialog.setFixedSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(self._selected_entry.content)
        layout.addWidget(text_edit)
        
        button_layout = QHBoxLayout()
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(lambda: self._save_edit(dialog, text_edit.toPlainText()))
        button_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.close)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    def _save_edit(self, dialog, content):
        """保存编辑"""
        if self._diary_system.update_entry(self._selected_entry.id, content):
            QMessageBox.information(self, "提示", "日记已更新")
            self._display_entry(self._diary_system.get_entry(self._selected_entry.id))
        else:
            QMessageBox.warning(self, "警告", "更新失败")
        
        dialog.close()
    
    def _delete_entry(self):
        """删除日记"""
        if not self._selected_entry:
            QMessageBox.warning(self, "警告", "请先选择一篇日记")
            return
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这篇日记吗？此操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self._diary_system.delete_entry(self._selected_entry.id):
                QMessageBox.information(self, "提示", "日记已删除")
                self._load_entries()
                self._content_edit.clear()
                self._date_label.setText("选择一篇日记")
                self._mood_icon.setText("📝")
                self._stats_label.clear()
                self._events_list.clear()
                self._selected_entry = None
            else:
                QMessageBox.warning(self, "警告", "删除失败")
    
    def _generate_diary(self):
        """手动生成日记"""
        import asyncio
        
        async def generate():
            self._generate_btn.setEnabled(False)
            self._generate_btn.setText("生成中...")
            
            try:
                entry = await self._diary_system.try_generate_diary(trigger_type="manual")
                
                if entry:
                    QMessageBox.information(self, "提示", "日记生成成功")
                    self._load_entries()
                else:
                    QMessageBox.warning(self, "警告", "生成失败或条件不满足")
            except Exception as e:
                QMessageBox.warning(self, "警告", f"生成失败: {str(e)}")
            finally:
                self._generate_btn.setEnabled(True)
                self._generate_btn.setText("手动生成")
        
        asyncio.create_task(generate())
    
    def _export_diaries(self):
        """导出日记"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出日记",
            f"vivian_diary_{datetime.now().strftime('%Y%m%d')}.md",
            "Markdown文件 (*.md)"
        )
        
        if file_path:
            if self._diary_system.export_diaries(file_path):
                QMessageBox.information(self, "提示", f"日记已导出到\n{file_path}")
            else:
                QMessageBox.warning(self, "警告", "导出失败")