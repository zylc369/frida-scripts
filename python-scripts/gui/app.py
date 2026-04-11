"""Frida Management GUI — PySide6 (Qt) based interface."""

from __future__ import annotations

import subprocess
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
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

from library import database
from library.log import log
from .app_table_model import AppTableModel, AppIdRole
from .gear_button_delegate import GearButtonDelegate
from .toast import ToastWidget

if TYPE_CHECKING:
    from .frida_ops import AppInfo

_DEVICE_TYPE_ANDROID = "android"


class RefreshWorker(QThread):
    finished = Signal(list, dict)

    def __init__(self, host_port: int) -> None:
        super().__init__()
        self.host_port = host_port

    def run(self) -> None:
        from .frida_ops import get_all_apps

        try:
            apps = get_all_apps(self.host_port)
        except Exception:
            apps = []
        script_counts = database.count_scripts_by_app(_DEVICE_TYPE_ANDROID)
        self.finished.emit(apps, script_counts)


class _InitWorker(QThread):
    finished = Signal(list, dict)

    def __init__(self, host_port: int) -> None:
        super().__init__()
        self.host_port = host_port

    def run(self) -> None:
        from .frida_ops import get_all_apps

        database.init_db()

        try:
            apps = get_all_apps(self.host_port)
        except Exception:
            apps = []
        script_counts = database.count_scripts_by_app(_DEVICE_TYPE_ANDROID)
        self.finished.emit(apps, script_counts)


class FridaManagerWindow(QMainWindow):

    def __init__(
        self,
        device_id: str,
        host_port: int,
        android_port: int,
        frida_server_path: str,
    ) -> None:
        super().__init__()
        self.device_id = device_id
        self.host_port = host_port
        self.android_port = android_port
        self.frida_server_path = frida_server_path
        self._all_apps: list[AppInfo] = []
        self._spawned_processes: list[subprocess.Popen] = []
        self._worker: RefreshWorker | None = None
        self._db_ready = False

        log.info("GUI 初始化: device_id=%s, host_port=%d, android_port=%d",
                 device_id, host_port, android_port)

        self.setWindowTitle("Frida Manager")
        self.resize(1100, 680)
        self.setMinimumSize(800, 480)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addWidget(self._build_info_panel())
        self._toolbar = self._build_toolbar_widget()
        layout.addWidget(self._toolbar)
        layout.addWidget(self._build_app_stack())

        self._toolbar.setEnabled(False)
        self._toolbar.hide()
        self._start_background_init()

    def _build_info_panel(self) -> QLineEdit:
        info = QLineEdit(
            f"设备ID: {self.device_id}    "
            f"Android端口: {self.android_port}    "
            f"主机端口: {self.host_port}    "
            f"Frida路径: {self.frida_server_path}",
        )
        info.setReadOnly(True)
        info.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        info.setStyleSheet(
            "background: #e3f2fd; color: #1a237e; border: none; "
            "padding: 6px; font-size: 13px;"
        )
        return info

    def _build_toolbar_widget(self) -> QWidget:
        widget = QWidget()
        bar = QHBoxLayout(widget)
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
        return widget

    def _build_app_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_loading_page())
        self._stack.addWidget(self._build_app_table())
        return self._stack

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        loading_label = QLabel("正在加载应用列表，请稍候…")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_label.setStyleSheet(
            "color: #546e7a; font-size: 16px; padding: 40px;"
        )
        layout.addWidget(loading_label)
        return page

    def _start_background_init(self) -> None:
        self._init_worker = _InitWorker(self.host_port)
        self._init_worker.finished.connect(self._on_init_done)
        self._init_worker.start()

    def _on_init_done(self, apps: list[AppInfo], script_counts: dict[str, int]) -> None:
        self._db_ready = True
        self._all_apps = apps
        self._stack.setCurrentIndex(1)
        self._toolbar.setEnabled(True)
        self._toolbar.show()
        self._apply_model_update(apps, script_counts)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_apps)
        self._timer.start(5000)

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

    def _update_spawn_btn_label(self) -> None:
        app = self._selected_app()
        if app and app.is_running:
            self._spawn_btn.setText("重启选中应用")
        else:
            self._spawn_btn.setText("启动选中应用")

    def eventFilter(self, obj, event):
        if hasattr(self, "_table") and obj is self._table and event.type() == QEvent.Type.KeyPress:
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
        copy_action = QAction(f"复制: {text[:40]}{'…' if len(text) > 40 else ''}", menu)
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

        log.info("打开脚本配置对话框: %s (%s)", app_name, app_identifier)
        dlg = ScriptBindDialog(self, self.device_id, app_identifier, app_name)
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

    def _apply_model_update(self, apps: list[AppInfo], script_counts: dict[str, int]) -> None:
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

    def _refresh_apps(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = RefreshWorker(self.host_port)
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
        from .frida_ops import build_spawn_cmd

        app = self._selected_app()
        if not app:
            ToastWidget.show_error(self, "请先选中一个应用")
            return

        bindings = database.query_scripts(_DEVICE_TYPE_ANDROID, app.identifier)
        script_paths = [row["script_path"] for row in bindings] if bindings else None
        cmd = build_spawn_cmd(self.host_port, app.identifier, script_paths)
        cmd_str = " ".join(cmd)

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(cmd_str)
        log.info("启动命令已复制到剪贴板: %s", cmd_str)
        ToastWidget.show_success(self, f"已复制: {cmd_str}")

    def _do_kill(self, app: AppInfo) -> None:
        if not app.is_running or app.pid is None:
            return

        log.info("Kill 请求: %s (PID=%d)", app.identifier, app.pid)

        def _worker() -> None:
            from .frida_ops import kill_app

            success = kill_app(self.host_port, app.pid)
            if success:
                QTimer.singleShot(0, lambda: ToastWidget.show_success(
                    self, f"已终止 {app.identifier} (PID {app.pid})"
                ))
            else:
                QTimer.singleShot(0, lambda: ToastWidget.show_error(
                    self, f"终止 {app.identifier} 失败"
                ))
            QTimer.singleShot(0, self._refresh_apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_spawn(self, app: AppInfo) -> None:
        log.info("启动应用请求: %s (当前状态: %s)", app.identifier,
                 f"运行中 PID={app.pid}" if app.is_running else "未运行")

        def _worker() -> None:
            from .frida_ops import spawn_app

            bindings = database.query_scripts(_DEVICE_TYPE_ANDROID, app.identifier)
            script_paths: list[str] | None = (
                [row["script_path"] for row in bindings] if bindings else None
            )

            log.info("启动应用 %s, 绑定脚本数: %d, 脚本列表: %s",
                     app.identifier,
                     len(bindings) if bindings else 0,
                     script_paths or [])

            proc, err = spawn_app(self.host_port, app.identifier, script_paths)
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
                log.error("frida 进程异常退出: %s, stderr=%s", detail.strip(), stderr.strip())
                QTimer.singleShot(0, lambda: ToastWidget.show_error(
                    self, f"启动 {app.identifier} 失败: {detail.strip()}"
                ))
                return

            self._spawned_processes.append(proc)
            label = ", ".join(script_paths) if script_paths else "无脚本"
            log.info("应用启动成功: %s (%s)", app.identifier, label)
            QTimer.singleShot(0, lambda: ToastWidget.show_success(
                self, f"已启动 {app.identifier} ({label})"
            ))
            QTimer.singleShot(2000, self._refresh_apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_restart(self, app: AppInfo) -> None:
        log.info("重启应用请求: %s (PID=%d)", app.identifier, app.pid)

        def _worker() -> None:
            from .frida_ops import kill_app

            success = kill_app(self.host_port, app.pid)
            if not success:
                QTimer.singleShot(0, lambda: ToastWidget.show_error(
                    self, f"重启失败: 终止 {app.identifier} 失败"
                ))
                return
            QTimer.singleShot(1000, lambda: self._do_spawn(app))

        threading.Thread(target=_worker, daemon=True).start()

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._cleanup_spawned()
        super().closeEvent(event)

    def _cleanup_spawned(self) -> None:
        for proc in self._spawned_processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._spawned_processes.clear()


def launch_gui(
    device_id: str,
    host_port: int,
    android_port: int,
    frida_server_path: str,
) -> None:
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    window = FridaManagerWindow(
        device_id=device_id,
        host_port=host_port,
        android_port=android_port,
        frida_server_path=frida_server_path,
    )
    window.show()
    app.exec()
