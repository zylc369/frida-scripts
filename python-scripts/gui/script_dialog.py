from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from library import database
from library.log import log
from .toast import ToastWidget

_DEVICE_TYPE_ANDROID = "android"


class ScriptBindDialog(QDialog):

    _TABLE_STYLESHEET = """
        QTableWidget {
            font-size: 13px;
            gridline-color: #ddd;
        }
        QTableWidget::item {
            padding: 4px;
        }
        QTableWidget::item:selected {
            background-color: #e3f2fd;
            color: #000;
        }
        QHeaderView::section {
            background-color: #f5f5f5;
            font-weight: bold;
            padding: 4px;
            border: 1px solid #ddd;
        }
    """

    def __init__(
        self,
        parent: QWidget,
        device_id: str,
        app_identity: str,
        app_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._device_id = device_id
        self._app_identity = app_identity
        self._app_name = app_name or app_identity

        self.setWindowTitle(f"配置脚本 - {self._app_name} ({self._app_identity})")
        self.resize(700, 500)
        self.setMinimumSize(500, 350)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(self._build_table())
        layout.addLayout(self._build_delete_row())
        layout.addLayout(self._build_add_row())

    def _build_table(self) -> QTableWidget:
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["序号", "添加时间", "脚本名", "脚本路径"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(self._TABLE_STYLESHEET)

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.setMouseTracking(True)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(2, 160)

        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return self._table

    def _build_delete_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._delete_btn = QPushButton("删除选中")
        self._delete_btn.setEnabled(False)
        self._delete_btn.setAutoDefault(False)
        self._delete_btn.setStyleSheet(
            "color: #c62828; font-weight: bold; font-size: 13px; padding: 4px 12px;"
        )
        self._delete_btn.clicked.connect(self._on_delete)
        row.addWidget(self._delete_btn)
        row.addStretch()
        return row

    def _build_add_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        label = QLabel("脚本路径:")
        label.setStyleSheet("font-size: 13px;")
        row.addWidget(label)

        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("输入脚本文件的完整路径...")
        self._add_input.setStyleSheet("font-size: 13px;")
        self._add_input.textChanged.connect(self._on_input_changed)
        self._add_input.returnPressed.connect(self._on_add)
        row.addWidget(self._add_input, stretch=1)

        self._add_btn = QPushButton("添加")
        self._add_btn.setEnabled(False)
        self._add_btn.setAutoDefault(False)
        self._add_btn.setStyleSheet("font-size: 13px; padding: 4px 12px;")
        self._add_btn.clicked.connect(self._on_add)
        row.addWidget(self._add_btn)

        return row

    def _on_input_changed(self, text: str) -> None:
        self._add_btn.setEnabled(bool(text.strip()))

    def _on_delete(self) -> None:
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            ToastWidget.show_error(self, "请先选中要删除的脚本")
            return
        row_idx = selected_rows[0].row()
        script_id_item = self._table.item(row_idx, 0)
        if script_id_item is None:
            return
        script_id = script_id_item.data(Qt.ItemDataRole.UserRole)
        if script_id is None:
            return
        log.info("删除脚本绑定: id=%d, app=%s", script_id, self._app_identity)
        database.delete_script(script_id)
        self._refresh_list()

    def _on_add(self) -> None:
        raw = self._add_input.text()
        script_path = raw.strip()
        if not script_path:
            ToastWidget.show_error(self, "脚本路径不能为空")
            return

        if database.check_duplicate(_DEVICE_TYPE_ANDROID, self._app_identity, script_path):
            log.warning("重复脚本绑定: app=%s, path=%s", self._app_identity, script_path)
            ToastWidget.show_error(self, "该脚本已绑定，不要重复添加")
            return

        log.info("添加脚本绑定: app=%s, path=%s", self._app_identity, script_path)
        database.add_script(
            device_type=_DEVICE_TYPE_ANDROID,
            device_id=self._device_id,
            app_identity=self._app_identity,
            script_path=script_path,
        )
        self._add_input.clear()
        self._refresh_list()

    def _refresh_list(self) -> None:
        rows = database.query_scripts(_DEVICE_TYPE_ANDROID, self._app_identity)
        log.debug("脚本列表刷新: app=%s, 绑定数=%d", self._app_identity, len(rows))
        self._table.setRowCount(len(rows))

        for i, row_data in enumerate(rows):
            seq = str(i + 1)
            seq_item = QTableWidgetItem(seq)
            seq_item.setData(Qt.ItemDataRole.UserRole, row_data["id"])
            seq_item.setToolTip(seq)
            seq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            create_time_ms = row_data["create_time"]
            create_time_str = datetime.datetime.fromtimestamp(
                create_time_ms / 1000.0
            ).strftime("%Y-%m-%d %H:%M:%S")

            script_name = Path(row_data["script_path"]).name
            script_path = row_data["script_path"]

            time_item = QTableWidgetItem(create_time_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            time_item.setToolTip(create_time_str)

            name_item = QTableWidgetItem(script_name)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_item.setToolTip(script_name)

            path_item = QTableWidgetItem(script_path)
            path_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            path_item.setToolTip(script_path)

            self._table.setItem(i, 0, seq_item)
            self._table.setItem(i, 1, time_item)
            self._table.setItem(i, 2, name_item)
            self._table.setItem(i, 3, path_item)

        self._delete_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        self._delete_btn.setEnabled(bool(self._table.selectionModel().selectedRows()))

    def _on_context_menu(self, pos) -> None:
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        item = self._table.itemAt(pos)
        if item is None:
            return
        text = item.text()
        if not text:
            return
        menu = QMenu(self._table)
        copy_action = QAction(f"复制: {text[:40]}{'…' if len(text) > 40 else ''}", menu)
        copy_action.triggered.connect(lambda: self._copy_text(text))
        menu.addAction(copy_action)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_text(text: str) -> None:
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
