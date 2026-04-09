"""Frida Management GUI — PySide6 (Qt) based interface."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidgetItem,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QLabel,
)

if TYPE_CHECKING:
    from .frida_ops import AppInfo


class RefreshWorker(QThread):
    """Background thread to fetch app list from frida-ps."""
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
    """Qt-based GUI for managing frida sessions on Android devices."""

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

        self.setWindowTitle("Frida Manager")
        self.resize(960, 680)
        self.setMinimumSize(720, 480)

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
        info.setFocusPolicy(Qt.NoFocus)
        info.setStyleSheet("background: #e3f2fd; color: #1a237e; border: none; padding: 6px; font-size: 13px;")
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
        self._kill_btn.setStyleSheet("color: #c62828; font-weight: bold; font-size: 13px; padding: 4px 12px;")
        self._kill_btn.clicked.connect(self._kill_selected)
        bar.addWidget(self._kill_btn)

        self._spawn_btn = QPushButton("启动选中应用")
        self._spawn_btn.setStyleSheet("color: #2e7d32; font-weight: bold; font-size: 13px; padding: 4px 12px;")
        self._spawn_btn.clicked.connect(self._spawn_selected)
        bar.addWidget(self._spawn_btn)

        bar.addStretch()
        return bar

    def _build_app_list(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["#", "状态", "PID", "应用名", "包名"])
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setSortingEnabled(False)
        tree.setFocusPolicy(Qt.StrongFocus)

        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.resizeSection(3, 220)

        self._tree = tree
        return tree

    def _on_search_changed(self) -> None:
        self._render_apps(force=True)

    def _render_apps(self, force: bool = False) -> None:
        search = self._search_input.text().lower() if hasattr(self, "_search_input") else ""

        filtered = self._all_apps
        if search:
            filtered = [
                app for app in self._all_apps
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

        prev_id = ""
        selected = self._tree.selectedItems()
        if selected:
            prev_id = selected[0].data(0, Qt.UserRole) or ""

        vscroll = self._tree.verticalScrollBar()
        scroll_pos = vscroll.value()

        self._tree.clear()

        for idx, app in enumerate(ordered):
            status = "运行中" if app.is_running else "未运行"
            pid = str(app.pid) if app.is_running else "-"
            item = QTreeWidgetItem([str(idx + 1), status, pid, app.name, app.identifier])
            item.setData(0, Qt.UserRole, app.identifier)

            if app.is_running:
                item.setForeground(1, Qt.darkGreen)
            else:
                item.setForeground(1, Qt.gray)
                item.setForeground(2, Qt.gray)

            self._tree.addTopLevelItem(item)

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

    def _kill_selected(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            return
        identifier = selected[0].data(0, Qt.UserRole) or ""
        app = next((a for a in self._all_apps if a.identifier == identifier), None)
        if app:
            self._do_kill(app)

    def _spawn_selected(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            return
        identifier = selected[0].data(0, Qt.UserRole) or ""
        app = next((a for a in self._all_apps if a.identifier == identifier), None)
        if app:
            self._do_spawn(app)

    def _do_kill(self, app: AppInfo) -> None:
        if not app.is_running or app.pid is None:
            return

        def _worker() -> None:
            from .frida_ops import kill_app

            success = kill_app(self.host_port, app.pid)
            if success:
                print(f"[Frida Manager] 已终止 {app.identifier} (PID {app.pid})")
            else:
                print(f"[Frida Manager] 终止 {app.identifier} 失败")
            QTimer.singleShot(0, self._refresh_apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _do_spawn(self, app: AppInfo) -> None:
        from .frida_ops import find_hook_scripts, spawn_app

        scripts = find_hook_scripts()
        script_arg = None
        if scripts:
            selected = self._show_script_dialog(scripts)
            if selected is None:
                return
            script_arg = str(selected) if selected != Path("__none__") else None

        proc = spawn_app(self.host_port, app.identifier, script_arg)
        if proc:
            self._spawned_processes.append(proc)
            label = script_arg or "无脚本"
            print(f"[Frida Manager] 已启动 {app.identifier} ({label})")
        else:
            print(f"[Frida Manager] 启动 {app.identifier} 失败")
        QTimer.singleShot(2000, self._refresh_apps)

    def _show_script_dialog(self, scripts: list[Path]) -> Path | None:
        items = [s.name for s in scripts] + ["无脚本 (直接启动)"]
        choice, ok = QTreeWidgetItem(), False

        dialog = QMessageBox(self)
        dialog.setWindowTitle("选择 Hook 脚本")
        dialog.setText("选择要加载的 Hook 脚本:")
        dialog.setStandardButtons(QMessageBox.Cancel)

        for i, script_name in enumerate(items):
            btn = dialog.addButton(script_name, QMessageBox.ActionRole)
            btn.setProperty("script_index", i)

        result = dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is None or result == QMessageBox.Cancel:
            return None

        idx = clicked.property("script_index")
        if idx is None:
            return None
        if idx >= len(scripts):
            return Path("__none__")
        return scripts[idx]

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
