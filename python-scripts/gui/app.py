"""Frida Management GUI — PySide6 (Qt) based multi-device interface."""

from __future__ import annotations

import random
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableView,
    QStyledItemDelegate,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
)

from library import adb
from library import database
from library.log import log
from .app_table_model import AppTableModel, AppIdRole
from .frida_client import AppInfo, FridaServerError
from .frida_client_manager import FridaClientManager
from .gear_button_delegate import GearButtonDelegate
from .toast import ToastWidget

if TYPE_CHECKING:
    from .frida_client import FridaClient

_DEVICE_TYPE_ANDROID = "android"


class _DetectDevicesWorker(QThread):
    finished = Signal(list)

    def run(self) -> None:
        devices = adb.get_devices()
        self.finished.emit(devices)


class _StartFridaWorker(QThread):
    finished = Signal(str, bool, str)

    def __init__(self, device_id: str, upgrade: bool = False) -> None:
        super().__init__()
        self._device_id = device_id
        self._upgrade = upgrade

    def run(self) -> None:
        manager = FridaClientManager()
        try:
            manager.start_frida_for_device(self._device_id, upgrade=self._upgrade)
            self.finished.emit(self._device_id, True, "")
        except (FridaServerError, Exception) as e:
            log.error("启动 frida-server 失败 (设备 %s): %s", self._device_id, e)
            self.finished.emit(self._device_id, False, str(e))


class RefreshWorker(QThread):
    finished = Signal(list, dict)

    def __init__(self, client: FridaClient) -> None:
        super().__init__()
        self._client = client

    def run(self) -> None:
        try:
            apps = self._client.get_all_apps()
        except Exception:
            apps = []
        script_counts = database.count_scripts_by_app(_DEVICE_TYPE_ANDROID)
        self.finished.emit(apps, script_counts)


class _InitWorker(QThread):
    finished = Signal(list, dict)

    def __init__(self, client: FridaClient) -> None:
        super().__init__()
        self._client = client

    def run(self) -> None:
        database.init_db()
        try:
            apps = self._client.get_all_apps()
        except Exception:
            apps = []
        script_counts = database.count_scripts_by_app(_DEVICE_TYPE_ANDROID)
        self.finished.emit(apps, script_counts)


class FridaManagerWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self._manager = FridaClientManager()
        self._current_device_id: str | None = None
        self._all_apps: list[AppInfo] = []
        self._worker: RefreshWorker | None = None
        self._start_worker: _StartFridaWorker | None = None
        self._db_ready = False
        self._timer: QTimer | None = None

        self.setWindowTitle("Frida Manager")
        self.resize(1100, 720)
        self.setMinimumSize(800, 480)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        layout.addWidget(self._build_device_panel())
        layout.addWidget(self._build_toolbar_widget())
        self._toolbar_widget.setEnabled(False)
        self._toolbar_widget.hide()
        layout.addWidget(self._build_app_stack(), stretch=1)

        self._detect_devices()

    def _build_device_panel(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(8)

        device_label = QLabel("设备:")
        device_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(device_label)

        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(220)
        view = QListView()
        self._device_combo.setView(view)
        _arrow_svg = str(Path(__file__).resolve().parent.parent / "assets" / "chevron-down.svg")
        self._device_combo.setStyleSheet(
            "QComboBox {"
            "  font-size: 13px; padding: 5px 28px 5px 12px;"
            "  border: 1px solid #cfd8dc; border-radius: 6px;"
            "  background: #ffffff; color: #37474f;"
            "  min-height: 28px;"
            "}"
            "QComboBox:hover { border-color: #90caf9; }"
            "QComboBox:focus { border-color: #42a5f5; }"
            "QComboBox::drop-down {"
            "  subcontrol-origin: padding; subcontrol-position: center right;"
            "  width: 24px; border: none; border-left: 1px solid #e0e0e0;"
            "}"
            "QComboBox::down-arrow {"
            f"  image: url({_arrow_svg});"
            "  width: 12px; height: 12px;"
            "}"
            "QComboBox QAbstractItemView {"
            "  font-size: 13px; background: #ffffff;"
            "  border: 1px solid #e0e0e0; border-radius: 8px;"
            "  padding: 6px 0; outline: none;"
            "  selection-background-color: #e3f2fd;"
            "  selection-color: #1565c0;"
            "}"
            "QComboBox QAbstractItemView::item {"
            "  height: 32px; padding: 0 14px; color: #37474f;"
            "}"
            "QComboBox QAbstractItemView::item:hover {"
            "  background: #e3f2fd; color: #1565c0;"
            "}"
        )
        self._device_combo.currentTextChanged.connect(self._on_device_selected)
        layout.addWidget(self._device_combo)

        self._refresh_devices_btn = QPushButton("⟳ 刷新设备")
        self._refresh_devices_btn.setStyleSheet(
            "QPushButton { color: #1565c0; font-weight: bold; font-size: 13px; "
            "padding: 4px 12px; border: 1px solid #90caf9; border-radius: 4px; "
            "background: #e3f2fd; }"
            "QPushButton:hover { background: #bbdefb; }"
            "QPushButton:pressed { background: #90caf9; }"
        )
        self._refresh_devices_btn.clicked.connect(self._detect_devices)
        layout.addWidget(self._refresh_devices_btn)

        self._restart_adb_btn = QPushButton("↻ 重启ADB")
        self._restart_adb_btn.setStyleSheet(
            "QPushButton { color: #e65100; font-weight: bold; font-size: 13px; "
            "padding: 4px 12px; border: 1px solid #ffcc80; border-radius: 4px; "
            "background: #fff3e0; }"
            "QPushButton:hover { background: #ffe0b2; }"
            "QPushButton:pressed { background: #ffcc80; }"
        )
        self._restart_adb_btn.clicked.connect(self._on_restart_adb_clicked)
        layout.addWidget(self._restart_adb_btn)

        self._status_label = QLabel("● 未连接")
        self._status_label.setStyleSheet("font-size: 13px; color: #9e9e9e;")
        layout.addWidget(self._status_label)

        self._start_frida_btn = QPushButton("启动 Frida Server")
        self._start_frida_btn.setStyleSheet(
            "QPushButton { color: #2e7d32; font-weight: bold; font-size: 13px; "
            "padding: 4px 14px; border: 1px solid #a5d6a7; border-radius: 4px; "
            "background: #f1f8e9; }"
            "QPushButton:hover { background: #dcedc8; }"
            "QPushButton:pressed { background: #c5e1a5; }"
        )
        self._start_frida_btn.clicked.connect(self._on_start_frida_clicked)
        self._start_frida_btn.hide()
        layout.addWidget(self._start_frida_btn)

        self._stop_frida_btn = QPushButton("停止 Frida Server")
        self._stop_frida_btn.setStyleSheet(
            "QPushButton { color: #c62828; font-weight: bold; font-size: 13px; "
            "padding: 4px 14px; border: 1px solid #ef9a9a; border-radius: 4px; "
            "background: #fce4ec; }"
            "QPushButton:hover { background: #ffcdd2; }"
            "QPushButton:pressed { background: #ef9a9a; }"
        )
        self._stop_frida_btn.clicked.connect(self._on_stop_frida_clicked)
        self._stop_frida_btn.hide()
        layout.addWidget(self._stop_frida_btn)

        layout.addStretch()
        return panel

    def _build_toolbar_widget(self) -> QWidget:
        self._toolbar_widget = QWidget()
        bar = QHBoxLayout(self._toolbar_widget)
        bar.setContentsMargins(0, 0, 0, 0)

        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("font-size: 15px;")
        bar.addWidget(search_icon)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入包名或应用名搜索...")
        self._search_input.setStyleSheet(
            "QLineEdit {"
            "  font-size: 13px; padding: 6px 10px;"
            "  border: 1px solid #bbdefb; border-radius: 4px;"
            "  background: #fafafa;"
            "}"
            "QLineEdit:focus { border-color: #42a5f5; background: #fff; }"
        )
        self._search_input.textChanged.connect(self._on_search_changed)
        bar.addWidget(self._search_input)

        refresh_btn = QPushButton("⟳ 刷新")
        refresh_btn.setStyleSheet(
            "QPushButton {"
            "  color: #1565c0; font-weight: bold; font-size: 13px; padding: 6px 14px;"
            "  border: 1px solid #90caf9; border-radius: 4px;"
            "  background: #e3f2fd;"
            "}"
            "QPushButton:hover { background: #bbdefb; }"
            "QPushButton:pressed { background: #90caf9; }"
        )
        refresh_btn.clicked.connect(self._refresh_apps)
        bar.addWidget(refresh_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #cfd8dc;")
        bar.addWidget(sep)

        self._kill_btn = QPushButton("Kill 选中进程")
        self._kill_btn.setStyleSheet(
            "QPushButton {"
            "  color: #c62828; font-weight: bold; font-size: 13px; padding: 4px 12px;"
            "  border: 1px solid #ef9a9a; border-radius: 4px;"
            "  background: #fce4ec;"
            "}"
            "QPushButton:hover { background: #ffcdd2; }"
            "QPushButton:pressed { background: #ef9a9a; }"
        )
        self._kill_btn.clicked.connect(self._kill_selected)
        bar.addWidget(self._kill_btn)

        spawn_widget = QWidget()
        spawn_layout = QHBoxLayout(spawn_widget)
        spawn_layout.setContentsMargins(0, 0, 0, 0)
        spawn_layout.setSpacing(0)

        self._spawn_btn = QPushButton("启动选中应用")
        self._spawn_btn.setStyleSheet(
            "QPushButton {"
            "  color: #2e7d32; font-weight: bold; font-size: 13px;"
            "  padding: 4px 12px;"
            "  border: 1px solid #a5d6a7;"
            "  border-right: 1px solid #c8e6c9;"
            "  border-top-right-radius: 0;"
            "  border-bottom-right-radius: 0;"
            "  background: #f1f8e9;"
            "}"
            "QPushButton:hover { background: #dcedc8; }"
            "QPushButton:pressed { background: #c5e1a5; }"
        )
        self._spawn_btn.clicked.connect(self._on_spawn_btn_clicked)
        spawn_layout.addWidget(self._spawn_btn)

        self._copy_cmd_btn = QPushButton("📋")
        self._copy_cmd_btn.setFixedSize(30, self._spawn_btn.sizeHint().height() or 28)
        self._copy_cmd_btn.setToolTip("复制启动命令到剪贴板")
        self._copy_cmd_btn.setStyleSheet(
            "QPushButton {"
            "  color: #2e7d32; font-size: 13px;"
            "  padding: 4px 2px;"
            "  border: 1px solid #a5d6a7;"
            "  border-left: 1px solid #c8e6c9;"
            "  border-top-left-radius: 0;"
            "  border-bottom-left-radius: 0;"
            "  background: #f1f8e9;"
            "}"
            "QPushButton:hover { background: #dcedc8; }"
            "QPushButton:pressed { background: #c5e1a5; }"
        )
        self._copy_cmd_btn.clicked.connect(self._copy_spawn_cmd)
        spawn_layout.addWidget(self._copy_cmd_btn)

        bar.addWidget(spawn_widget)
        bar.addStretch()
        return self._toolbar_widget

    def _build_app_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_loading_page())
        self._stack.addWidget(self._build_error_page())
        self._stack.addWidget(self._build_start_frida_page())
        self._stack.addWidget(self._build_app_table())
        return self._stack

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label = QLabel("正在检测设备，请稍候…")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(
            "color: #546e7a; font-size: 16px; padding: 40px;"
        )
        layout.addWidget(self._loading_label)
        return page

    def _build_error_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._error_label = QLabel("未检测到 Android 设备")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setStyleSheet(
            "color: #c62828; font-size: 16px; padding: 20px;"
        )
        layout.addWidget(self._error_label)

        self._retry_btn = QPushButton("重试")
        self._retry_btn.setStyleSheet(
            "QPushButton { color: #1565c0; font-weight: bold; font-size: 14px; "
            "padding: 8px 24px; border: 1px solid #90caf9; border-radius: 4px; "
            "background: #e3f2fd; }"
            "QPushButton:hover { background: #bbdefb; }"
        )
        self._retry_btn.clicked.connect(self._detect_devices)
        layout.addWidget(self._retry_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return page

    def _build_start_frida_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._start_prompt_label = QLabel("当前设备未启动 Frida Server")
        self._start_prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._start_prompt_label.setStyleSheet(
            "color: #f57f17; font-size: 16px; padding: 20px;"
        )
        layout.addWidget(self._start_prompt_label)

        self._start_page_btn = QPushButton("启动 Frida Server")
        self._start_page_btn.setStyleSheet(
            "QPushButton { color: #2e7d32; font-weight: bold; font-size: 14px; "
            "padding: 8px 24px; border: 1px solid #a5d6a7; border-radius: 4px; "
            "background: #f1f8e9; }"
            "QPushButton:hover { background: #dcedc8; }"
        )
        self._start_page_btn.clicked.connect(self._on_start_frida_clicked)
        layout.addWidget(self._start_page_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return page

    def _build_app_table(self) -> QTableView:
        self._model = AppTableModel()

        self._gear_delegate = GearButtonDelegate()
        self._gear_delegate.gear_clicked.connect(self._on_gear_clicked)

        table = QTableView()
        table.setModel(self._model)
        table.setItemDelegateForColumn(6, self._gear_delegate)
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSortingEnabled(False)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_context_menu)
        table.installEventFilter(self)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.verticalHeader().setDefaultSectionSize(30)
        table.setStyleSheet(
            "QTableView {"
            "  font-size: 13px;"
            "  border: 1px solid #e0e0e0;"
            "  border-radius: 4px;"
            "}"
            "QTableView::item { padding: 3px 4px; }"
            "QTableView::item:selected {"
            "  background: #1565c0;"
            "  color: #ffffff;"
            "}"
            "QTableView::item:hover { background: #f5f5f5; }"
            "QTableView::item:selected:hover { background: #1976d2; }"
            "QHeaderView::section {"
            "  background: #eceff1;"
            "  color: #37474f;"
            "  font-size: 14px;"
            "  font-weight: bold;"
            "  padding: 6px 8px;"
            "  border: none;"
            "  border-bottom: 2px solid #b0bec5;"
            "}"
        )

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.resizeSection(3, 180)
        header.resizeSection(4, 220)

        self._table = table
        table.selectionModel().selectionChanged.connect(self._update_spawn_btn_label)
        return table

    def _detect_devices(self) -> None:
        self._set_ui_state_detecting()
        self._device_combo.setEnabled(False)
        self._refresh_devices_btn.setEnabled(False)
        worker = _DetectDevicesWorker()
        worker.finished.connect(self._on_devices_detected)
        worker.start()
        self._detect_worker = worker

    def _on_devices_detected(self, devices: list[str]) -> None:
        self._device_combo.setEnabled(True)
        self._refresh_devices_btn.setEnabled(True)

        if not devices:
            self._set_ui_state_no_devices()
            return

        self._populate_device_combo(devices)

        previous = self._current_device_id
        target = previous if previous and previous in devices else devices[0]

        self._device_combo.setCurrentText(target)
        self._on_device_selected(target)

    def _populate_device_combo(self, devices: list[str]) -> None:
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        for d in devices:
            active = self._manager.is_device_active(d)
            label = f"{d}  (Frida 运行中)" if active else d
            self._device_combo.addItem(label, d)
        self._device_combo.blockSignals(False)

    def _on_device_selected(self, text: str) -> None:
        device_id = self._device_combo.currentData()
        if not device_id:
            return
        self._current_device_id = device_id
        log.info("切换到设备: %s", device_id)

        client = self._manager.get_client(device_id)
        if client is not None and client.is_server_running:
            self._set_ui_state_connected(client)
        else:
            self._set_ui_state_not_started()

    def _on_restart_adb_clicked(self) -> None:
        self._restart_adb_btn.setEnabled(False)
        self._restart_adb_btn.setText("重启中...")

        def _worker() -> None:
            try:
                adb.restart_adb_server()
                QTimer.singleShot(0, lambda: ToastWidget.show_success(self, "ADB Server 已重启"))
            except adb.AdbError as e:
                log.error("重启 ADB Server 失败: %s", e)
                QTimer.singleShot(0, lambda: ToastWidget.show_error(self, f"重启 ADB 失败: {e.message}"))
            finally:
                QTimer.singleShot(0, self._on_adb_restarted)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_adb_restarted(self) -> None:
        self._restart_adb_btn.setEnabled(True)
        self._restart_adb_btn.setText("↻ 重启ADB")
        self._detect_devices()

    def _on_start_frida_clicked(self) -> None:
        device_id = self._current_device_id
        if not device_id:
            ToastWidget.show_error(self, "请先选择一个设备")
            return
        self._start_frida_for_device(device_id)

    def _on_stop_frida_clicked(self) -> None:
        device_id = self._current_device_id
        if not device_id:
            return
        log.info("停止 Frida Server (设备 %s)", device_id)

        def _worker() -> None:
            self._manager.close_client(device_id)
            QTimer.singleShot(0, lambda: self._on_frida_stopped(device_id))

        threading.Thread(target=_worker, daemon=True).start()
        self._stop_frida_btn.setEnabled(False)
        self._stop_frida_btn.setText("正在停止...")

    def _on_frida_stopped(self, device_id: str) -> None:
        self._update_device_combo_status(device_id)
        if device_id == self._current_device_id:
            self._set_ui_state_not_started()
        self._stop_frida_btn.setEnabled(True)
        self._stop_frida_btn.setText("停止 Frida Server")
        ToastWidget.show_success(self, f"设备 {device_id} 的 Frida Server 已停止")

    def _start_frida_for_device(self, device_id: str, upgrade: bool = False) -> None:
        self._loading_label.setText(f"正在为设备 {device_id} 启动 Frida Server…")
        self._stack.setCurrentIndex(0)
        self._device_combo.setEnabled(False)
        self._refresh_devices_btn.setEnabled(False)
        self._start_frida_btn.hide()

        self._start_worker = _StartFridaWorker(device_id, upgrade)
        self._start_worker.finished.connect(self._on_frida_start_result)
        self._start_worker.start()

    def _on_frida_start_result(
        self, device_id: str, success: bool, error_msg: str
    ) -> None:
        self._device_combo.setEnabled(True)
        self._refresh_devices_btn.setEnabled(True)
        self._update_device_combo_status(device_id)

        if success:
            log.info("Frida Server 启动成功 (设备 %s)", device_id)
            if device_id == self._current_device_id:
                client = self._manager.get_client(device_id)
                if client:
                    self._set_ui_state_connected(client)
            ToastWidget.show_success(self, f"设备 {device_id} Frida Server 启动成功")
        else:
            log.error(
                "Frida Server 启动失败 (设备 %s): %s", device_id, error_msg
            )
            if device_id == self._current_device_id:
                self._set_ui_state_start_failed(error_msg)
            ToastWidget.show_error(
                self, f"设备 {device_id} Frida Server 启动失败: {error_msg}"
            )

    def _set_ui_state_detecting(self) -> None:
        self._loading_label.setText("正在检测设备，请稍候…")
        self._stack.setCurrentIndex(0)
        self._toolbar_widget.setEnabled(False)
        self._toolbar_widget.hide()
        self._start_frida_btn.hide()
        self._stop_frida_btn.hide()
        self._status_label.setText("● 检测中…")
        self._status_label.setStyleSheet("font-size: 13px; color: #9e9e9e;")

    def _set_ui_state_no_devices(self) -> None:
        self._stack.setCurrentIndex(1)
        self._toolbar_widget.setEnabled(False)
        self._toolbar_widget.hide()
        self._start_frida_btn.hide()
        self._stop_frida_btn.hide()
        self._status_label.setText("● 未连接")
        self._status_label.setStyleSheet("font-size: 13px; color: #c62828;")

    def _set_ui_state_not_started(self) -> None:
        self._stack.setCurrentIndex(2)
        self._toolbar_widget.setEnabled(False)
        self._toolbar_widget.hide()
        self._start_frida_btn.show()
        self._stop_frida_btn.hide()
        self._status_label.setText("● 未启动")
        self._status_label.setStyleSheet("font-size: 13px; color: #f57f17;")

    def _set_ui_state_start_failed(self, error_msg: str) -> None:
        self._start_prompt_label.setText(
            f"Frida Server 启动失败: {error_msg}"
        )
        self._start_prompt_label.setStyleSheet(
            "color: #c62828; font-size: 14px; padding: 20px;"
        )
        self._stack.setCurrentIndex(2)
        self._toolbar_widget.setEnabled(False)
        self._toolbar_widget.hide()
        self._start_frida_btn.show()
        self._stop_frida_btn.hide()
        self._status_label.setText("● 启动失败")
        self._status_label.setStyleSheet("font-size: 13px; color: #c62828;")

    def _set_ui_state_connected(self, client: FridaClient) -> None:
        self._toolbar_widget.setEnabled(True)
        self._toolbar_widget.show()
        self._start_frida_btn.hide()
        self._stop_frida_btn.show()

        pid_text = str(client.frida_pid) if client.frida_pid else "未知"
        self._status_label.setText(
            f"● 已连接  (PID: {pid_text}  |  端口: {client.host_port})"
        )
        self._status_label.setStyleSheet("font-size: 13px; color: #2e7d32;")

        self._start_prompt_label.setText("当前设备未启动 Frida Server")
        self._start_prompt_label.setStyleSheet(
            "color: #f57f17; font-size: 16px; padding: 20px;"
        )

        if self._db_ready:
            self._refresh_apps()
        else:
            self._start_background_init(client)

    def _update_device_combo_status(self, device_id: str) -> None:
        self._device_combo.blockSignals(True)
        for i in range(self._device_combo.count()):
            if self._device_combo.itemData(i) == device_id:
                active = self._manager.is_device_active(device_id)
                label = f"{device_id}  (Frida 运行中)" if active else device_id
                self._device_combo.setItemText(i, label)
                break
        self._device_combo.blockSignals(False)

    def _start_background_init(self, client: FridaClient) -> None:
        self._init_worker = _InitWorker(client)
        self._init_worker.finished.connect(self._on_init_done)
        self._init_worker.start()

    def _on_init_done(self, apps: list[AppInfo], script_counts: dict[str, int]) -> None:
        self._db_ready = True
        self._stack.setCurrentIndex(3)
        self._apply_model_update(apps, script_counts)
        if self._timer is not None:
            self._timer.stop()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_apps)
        self._timer.start(5000)

    def _update_spawn_btn_label(self) -> None:
        app = self._selected_app()
        if app and app.is_running:
            self._spawn_btn.setText("重启选中应用")
        else:
            self._spawn_btn.setText("启动选中应用")

    def eventFilter(self, obj, event):
        if (
            hasattr(self, "_table")
            and obj is self._table
            and event.type() == QEvent.Type.KeyPress
        ):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._table.hasFocus():
                    self._on_spawn_btn_clicked()
                    return True
        return super().eventFilter(obj, event)

    def _on_context_menu(self, pos) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return

        col = index.column()
        if col not in (2, 3, 4, 5):
            return

        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text or text == "-":
            return

        menu = QMenu(self._table)
        copy_action = QAction(
            f"复制: {text[:40]}{'…' if len(text) > 40 else ''}", menu
        )
        copy_action.triggered.connect(lambda: self._copy_text(text))
        menu.addAction(copy_action)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_text(text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _open_script_dialog(self, app_identifier: str, app_name: str) -> None:
        from .script_dialog import ScriptBindDialog

        device_id = self._current_device_id or ""
        log.info("打开脚本配置对话框: %s (%s), 设备: %s", app_name, app_identifier, device_id)
        dlg = ScriptBindDialog(self, device_id, app_identifier, app_name)
        dlg.exec()
        self._refresh_apps()

    def _on_gear_clicked(self, index) -> None:
        identifier = index.data(AppIdRole) or ""
        app = next(
            (a for a in self._all_apps if a.identifier == identifier), None
        )
        name = app.name if app else ""
        self._open_script_dialog(identifier, name)

    def _on_search_changed(self) -> None:
        self._model.set_search(self._search_input.text())

    def _apply_model_update(
        self, apps: list[AppInfo], script_counts: dict[str, int]
    ) -> None:
        prev_id = ""
        rows = self._table.selectionModel().selectedRows()
        if rows:
            prev_id = rows[0].data(AppIdRole) or ""

        scroll_pos = self._table.verticalScrollBar().value()

        self._model.set_data(apps, script_counts)

        if prev_id:
            for row in range(self._model.rowCount()):
                index = self._model.index(row, 0)
                if index.data(AppIdRole) == prev_id:
                    self._table.selectRow(row)
                    break

        self._table.verticalScrollBar().setValue(scroll_pos)

    def _get_current_client(self) -> FridaClient | None:
        if not self._current_device_id:
            return None
        return self._manager.get_client(self._current_device_id)

    def _refresh_apps(self) -> None:
        client = self._get_current_client()
        if client is None or not client.is_server_running:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = RefreshWorker(client)
        self._worker.finished.connect(self._update_apps)
        self._worker.start()

    def _update_apps(self, apps: list[AppInfo], script_counts: dict[str, int]) -> None:
        running_count = sum(1 for a in apps if a.is_running)
        log.debug("应用列表更新: 总计 %d 个应用, %d 个运行中", len(apps), running_count)
        self._all_apps = apps
        self._apply_model_update(apps, script_counts)

    def _selected_app(self) -> AppInfo | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        identifier = rows[0].data(AppIdRole) or ""
        return next(
            (a for a in self._all_apps if a.identifier == identifier), None
        )

    def _kill_selected(self) -> None:
        app = self._selected_app()
        if app:
            self._do_kill(app)

    def _on_spawn_btn_clicked(self) -> None:
        app = self._selected_app()
        if not app:
            return
        if app.is_running:
            self._do_restart(app)
        else:
            self._do_spawn(app)

    def _copy_spawn_cmd(self) -> None:
        client = self._get_current_client()
        if client is None:
            ToastWidget.show_error(self, "Frida Server 未运行")
            return

        app = self._selected_app()
        if not app:
            ToastWidget.show_error(self, "请先选中一个应用")
            return

        bindings = database.query_scripts(_DEVICE_TYPE_ANDROID, app.identifier)
        script_paths = (
            [row["script_path"] for row in bindings] if bindings else None
        )
        cmd = client.build_spawn_cmd(app.identifier, script_paths)
        cmd_str = " ".join(cmd)

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(cmd_str)
        log.info("启动命令已复制到剪贴板: %s", cmd_str)
        ToastWidget.show_success(self, f"已复制: {cmd_str}")

    def _do_kill(self, app: AppInfo) -> None:
        if not app.is_running or app.pid is None:
            return
        client = self._get_current_client()
        if client is None:
            return

        log.info("Kill 请求: %s (PID=%d, 设备 %s)", app.identifier, app.pid, self._current_device_id)

        def _worker() -> None:
            success = client.kill_app(app.pid)
            if success:
                QTimer.singleShot(
                    0,
                    lambda: ToastWidget.show_success(
                        self, f"已终止 {app.identifier} (PID {app.pid})"
                    ),
                )
            else:
                QTimer.singleShot(
                    0,
                    lambda: ToastWidget.show_error(
                        self, f"终止 {app.identifier} 失败"
                    ),
                )
            QTimer.singleShot(0, self._refresh_apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_spawn(self, app: AppInfo) -> None:
        client = self._get_current_client()
        if client is None:
            ToastWidget.show_error(self, "Frida Server 未运行")
            return

        log.info(
            "启动应用请求 (设备 %s): %s (当前状态: %s)",
            self._current_device_id,
            app.identifier,
            f"运行中 PID={app.pid}" if app.is_running else "未运行",
        )

        def _worker() -> None:
            bindings = database.query_scripts(_DEVICE_TYPE_ANDROID, app.identifier)
            script_paths: list[str] | None = (
                [row["script_path"] for row in bindings] if bindings else None
            )

            log.info(
                "启动应用 %s (设备 %s), 绑定脚本数: %d, 脚本列表: %s",
                app.identifier,
                self._current_device_id,
                len(bindings) if bindings else 0,
                script_paths or [],
            )

            proc, err = client.spawn_app(app.identifier, script_paths)
            if proc is None:
                msg = f"启动 {app.identifier} 失败"
                if err:
                    msg += f": {err}"
                log.error("启动失败: %s", msg)
                QTimer.singleShot(0, lambda: ToastWidget.show_error(self, msg))
                return

            import time

            time.sleep(1)
            if proc.poll() is not None:
                stdout = proc.stdout.read() if proc.stdout else ""
                stderr = proc.stderr.read() if proc.stderr else ""
                detail = stderr or stdout or f"exit code {proc.returncode}"
                log.error(
                    "frida 进程异常退出: %s, stderr=%s",
                    detail.strip(),
                    stderr.strip(),
                )
                QTimer.singleShot(
                    0,
                    lambda: ToastWidget.show_error(
                        self,
                        f"启动 {app.identifier} 失败: {detail.strip()}",
                    ),
                )
                return

            label = ", ".join(script_paths) if script_paths else "无脚本"
            log.info(
                "应用启动成功 (设备 %s): %s (%s)",
                self._current_device_id,
                app.identifier,
                label,
            )
            QTimer.singleShot(
                0,
                lambda: ToastWidget.show_success(
                    self, f"已启动 {app.identifier} ({label})"
                ),
            )
            QTimer.singleShot(2000, self._refresh_apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_restart(self, app: AppInfo) -> None:
        client = self._get_current_client()
        if client is None:
            return

        log.info(
            "重启应用请求 (设备 %s): %s (PID=%d)",
            self._current_device_id,
            app.identifier,
            app.pid,
        )

        def _worker() -> None:
            success = client.kill_app(app.pid)
            if not success:
                QTimer.singleShot(
                    0,
                    lambda: ToastWidget.show_error(
                        self, f"重启失败: 终止 {app.identifier} 失败"
                    ),
                )
                return
            QTimer.singleShot(1000, lambda: self._do_spawn(app))

        threading.Thread(target=_worker, daemon=True).start()

    def closeEvent(self, event) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._stop_workers()
        self._manager.close_all()
        super().closeEvent(event)

    def _stop_workers(self) -> None:
        for attr in ("_worker", "_init_worker", "_start_worker", "_detect_worker"):
            worker = getattr(self, attr, None)
            if worker is not None and hasattr(worker, "isRunning") and worker.isRunning():
                worker.quit()
                worker.wait(3000)


def launch_gui() -> None:
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication.instance() or QApplication(sys.argv)

    icon_dir = Path(__file__).resolve().parent.parent / "assets" / "icon"
    icons = list(icon_dir.glob("*.png")) if icon_dir.is_dir() else []
    if icons:
        if isinstance(app, QApplication):
            app.setWindowIcon(QIcon(str(random.choice(icons))))

    window = FridaManagerWindow()
    window.show()
    app.exec()
