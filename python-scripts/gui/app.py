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
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QTreeWidgetItem,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QLabel,
)

from library import database
from .toast import ToastWidget

if TYPE_CHECKING:
    from .frida_ops import AppInfo

_DEVICE_TYPE_ANDROID = "android"


class RefreshWorker(QThread):
    finished = Signal(list)

    def __init__(self, host_port: int) -> None:
        super().__init__()
        self.host_port = host_port

    def run(self) -> None:
        from .frida_ops import get_all_apps

        try:
            apps = get_all_apps(self.host_port)
        except Exception:
            apps = []
        self.finished.emit(apps)


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
        self._last_fingerprint = ""

        database.init_db()

        self.setWindowTitle("Frida Manager")
        self.resize(1100, 680)
        self.setMinimumSize(800, 480)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addWidget(self._build_info_panel())
        layout.addLayout(self._build_search_bar())
        layout.addLayout(self._build_action_bar())
        layout.addWidget(self._build_app_list())

        self._refresh_apps()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_apps)
        self._timer.start(5000)

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

    def _build_search_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        label = QLabel("搜索:")
        label.setStyleSheet("font-size: 13px;")
        bar.addWidget(label)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入包名或应用名搜索...")
        self._search_input.setStyleSheet("font-size: 13px;")
        self._search_input.textChanged.connect(self._on_search_changed)
        bar.addWidget(self._search_input)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet("font-size: 13px; padding: 4px 12px;")
        refresh_btn.clicked.connect(self._refresh_apps)
        bar.addWidget(refresh_btn)

        return bar

    def _build_action_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()

        self._kill_btn = QPushButton("Kill 选中进程")
        self._kill_btn.setStyleSheet(
            "color: #c62828; font-weight: bold; font-size: 13px; padding: 4px 12px;"
        )
        self._kill_btn.clicked.connect(self._kill_selected)
        bar.addWidget(self._kill_btn)

        self._spawn_btn = QPushButton("启动选中应用")
        self._spawn_btn.setStyleSheet(
            "color: #2e7d32; font-weight: bold; font-size: 13px; padding: 4px 12px;"
        )
        self._spawn_btn.clicked.connect(self._on_spawn_btn_clicked)
        bar.addWidget(self._spawn_btn)

        bar.addStretch()
        return bar

    def _build_app_list(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["#", "状态", "PID", "应用名", "包名", "脚本", "操作"])
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.setSortingEnabled(False)
        tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_context_menu)
        tree.installEventFilter(self)
        tree.itemSelectionChanged.connect(self._update_spawn_btn_label)

        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.resizeSection(3, 180)
        header.resizeSection(4, 220)

        self._tree = tree
        return tree

    def _update_spawn_btn_label(self) -> None:
        app = self._selected_app()
        if app and app.is_running:
            self._spawn_btn.setText("重启选中应用")
        else:
            self._spawn_btn.setText("启动选中应用")

    def eventFilter(self, obj, event):
        if hasattr(self, "_tree") and obj is self._tree and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._tree.hasFocus():
                    self._on_spawn_btn_clicked()
                    return True
        return super().eventFilter(obj, event)

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return

        col = self._tree.columnAt(pos.x())
        if col not in (2, 3, 4, 5):
            return

        text = item.text(col)
        if not text or text == "-":
            return

        menu = QMenu(self._tree)
        copy_action = QAction(f"复制: {text[:40]}{'…' if len(text) > 40 else ''}", menu)
        copy_action.triggered.connect(lambda: self._copy_text(text))
        menu.addAction(copy_action)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_text(text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _open_script_dialog(self, app_identifier: str, app_name: str) -> None:
        from .script_dialog import ScriptBindDialog

        dlg = ScriptBindDialog(self, self.device_id, app_identifier, app_name)
        dlg.exec()

    def _on_search_changed(self) -> None:
        self._render_apps(force=True)

    def _render_apps(self, force: bool = False) -> None:
        search = (
            self._search_input.text().lower()
            if hasattr(self, "_search_input")
            else ""
        )

        filtered = self._all_apps
        if search:
            filtered = [
                app
                for app in self._all_apps
                if search in app.name.lower() or search in app.identifier.lower()
            ]

        running = [a for a in filtered if a.is_running]
        stopped = [a for a in filtered if not a.is_running]
        ordered = running + stopped

        fingerprint = ",".join(
            f"{a.is_running}:{a.pid}:{a.name}:{a.identifier}" for a in ordered
        )
        if not force and fingerprint == self._last_fingerprint:
            return
        self._last_fingerprint = fingerprint

        script_counts = database.count_scripts_by_app(_DEVICE_TYPE_ANDROID)

        prev_id = ""
        selected = self._tree.selectedItems()
        if selected:
            prev_id = selected[0].data(0, Qt.ItemDataRole.UserRole) or ""

        vscroll = self._tree.verticalScrollBar()
        scroll_pos = vscroll.value()

        self._tree.clear()

        for idx, app in enumerate(ordered):
            status = "运行中" if app.is_running else "未运行"
            pid = str(app.pid) if app.is_running else "-"
            script_count = script_counts.get(app.identifier, 0)
            script_text = str(script_count) if script_count > 0 else "-"
            item = QTreeWidgetItem(
                [str(idx + 1), status, pid, app.name, app.identifier, script_text, ""]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, app.identifier)

            if app.is_running:
                item.setForeground(1, Qt.GlobalColor.darkGreen)
            else:
                item.setForeground(1, Qt.GlobalColor.gray)
                item.setForeground(2, Qt.GlobalColor.gray)

            if script_count > 0:
                item.setForeground(5, Qt.GlobalColor.darkGreen)
            else:
                item.setForeground(5, Qt.GlobalColor.gray)

            self._tree.addTopLevelItem(item)

            btn = QPushButton("⚙")
            btn.setFixedSize(28, 24)
            btn.setToolTip("配置脚本")
            identifier = app.identifier
            name = app.name
            btn.clicked.connect(
                lambda checked=False, _id=identifier, _n=name: self._open_script_dialog(_id, _n)
            )
            self._tree.setItemWidget(item, 6, btn)

            if app.identifier == prev_id:
                self._tree.setCurrentItem(item)

        vscroll.setValue(scroll_pos)

    def _refresh_apps(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = RefreshWorker(self.host_port)
        self._worker.finished.connect(self._update_apps)
        self._worker.start()

    def _update_apps(self, apps: list[AppInfo]) -> None:
        self._all_apps = apps
        self._render_apps()

    def _selected_app(self) -> AppInfo | None:
        selected = self._tree.selectedItems()
        if not selected:
            return None
        identifier = selected[0].data(0, Qt.ItemDataRole.UserRole) or ""
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

    def _do_kill(self, app: AppInfo) -> None:
        if not app.is_running or app.pid is None:
            return

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
        def _worker() -> None:
            from .frida_ops import spawn_app

            bindings = database.query_scripts(_DEVICE_TYPE_ANDROID, app.identifier)
            script_paths: list[str] | None = (
                [row["script_path"] for row in bindings] if bindings else None
            )

            proc, err = spawn_app(self.host_port, app.identifier, script_paths)
            if proc is None:
                msg = f"启动 {app.identifier} 失败"
                if err:
                    msg += f": {err}"
                QTimer.singleShot(0, lambda: ToastWidget.show_error(self, msg))
                return

            import time
            time.sleep(1)
            if proc.poll() is not None:
                stdout = proc.stdout.read() if proc.stdout else ""
                stderr = proc.stderr.read() if proc.stderr else ""
                detail = stderr or stdout or f"exit code {proc.returncode}"
                QTimer.singleShot(0, lambda: ToastWidget.show_error(
                    self, f"启动 {app.identifier} 失败: {detail.strip()}"
                ))
                return

            self._spawned_processes.append(proc)
            label = ", ".join(script_paths) if script_paths else "无脚本"
            QTimer.singleShot(0, lambda: ToastWidget.show_success(
                self, f"已启动 {app.identifier} ({label})"
            ))
            QTimer.singleShot(2000, self._refresh_apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_restart(self, app: AppInfo) -> None:
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
