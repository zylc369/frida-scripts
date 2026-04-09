"""Frida Management GUI — tkinter-based graphical interface for managing frida sessions."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from tkinter import (
    BOTH,
    LEFT,
    RIGHT,
    W,
    Entry,
    Frame,
    Label,
    StringVar,
    Tk,
    Toplevel,
)
from tkinter.ttk import Button as TtkButton
from tkinter.ttk import Style, Treeview
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .frida_ops import AppInfo


class FridaManagerWindow:
    """tkinter-based GUI for managing frida sessions on Android devices."""

    def __init__(
        self,
        device_id: str,
        host_port: int,
        android_port: int,
        frida_server_path: str,
    ) -> None:
        self.device_id = device_id
        self.host_port = host_port
        self.android_port = android_port
        self.frida_server_path = frida_server_path
        self._all_apps: list[AppInfo] = []
        self._spawned_processes: list[subprocess.Popen] = []
        self._search_var: StringVar | None = None
        self._root: Tk | None = None
        self._tree: Treeview | None = None
        self._app_map: dict[str, AppInfo] = {}

    def run(self) -> None:
        root = Tk()
        root.title("Frida Manager")
        root.geometry("960x680")
        root.minsize(720, 480)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root = root

        self._setup_style(root)
        self._build_info_panel(root)
        self._build_search_bar(root)
        self._build_app_list(root)

        self._refresh_apps()
        self._schedule_refresh(root)

        root.mainloop()
        self._cleanup_spawned()

    def _setup_style(self, root: Tk) -> None:
        style = Style(root)
        style.theme_use("default")
        style.configure("Kill.TButton", foreground="#c62828", font=("Helvetica", 9, "bold"))
        style.configure("Spawn.TButton", foreground="#2e7d32", font=("Helvetica", 9, "bold"))
        style.configure("Refresh.TButton", font=("Helvetica", 10))
        style.configure("Treeview", rowheight=26, font=("Helvetica", 9))
        style.configure("Treeview.Heading", font=("Helvetica", 9, "bold"))

    def _build_info_panel(self, parent: Tk) -> None:
        panel = Frame(parent, padx=12, pady=4)
        panel.pack(fill="x", padx=8, pady=(8, 0))

        info_text = (
            f"设备ID: {self.device_id}    "
            f"Android端口: {self.android_port}    "
            f"主机端口: {self.host_port}    "
            f"Frida路径: {self.frida_server_path}"
        )
        entry = Entry(panel, font=("Helvetica", 10), bd=0, relief="flat")
        entry.insert(0, info_text)
        entry.configure(state="readonly")
        entry.pack(fill="x")

    def _build_search_bar(self, parent: Tk) -> None:
        bar = Frame(parent, padx=8, pady=6)
        bar.pack(fill="x")

        Label(bar, text="搜索:", font=("Helvetica", 10)).pack(side=LEFT, padx=(0, 6))

        self._search_var = StringVar()
        self._search_var.trace_add("write", lambda *_: self._render_apps())
        Entry(
            bar,
            textvariable=self._search_var,
            font=("Helvetica", 10),
            width=60,
        ).pack(side=LEFT, fill="x", expand=True)

        TtkButton(
            bar,
            text="刷新",
            command=self._refresh_apps,
            style="Refresh.TButton",
        ).pack(side=RIGHT, padx=(6, 0))

    def _build_app_list(self, parent: Tk) -> None:
        container = Frame(parent)
        container.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        btn_bar = Frame(container)
        btn_bar.pack(fill="x", pady=(4, 2))

        TtkButton(btn_bar, text="Kill 选中进程", style="Kill.TButton",
                  command=self._kill_selected).pack(side=LEFT, padx=(0, 6))
        TtkButton(btn_bar, text="启动选中应用", style="Spawn.TButton",
                  command=self._spawn_selected).pack(side=LEFT)

        columns = ("status", "pid", "name", "identifier")
        tree = Treeview(
            container,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        tree.heading("status", text="状态")
        tree.heading("pid", text="PID")
        tree.heading("name", text="应用名")
        tree.heading("identifier", text="包名")
        tree.column("status", width=80, anchor=W)
        tree.column("pid", width=70, anchor=W)
        tree.column("name", width=220, anchor=W)
        tree.column("identifier", width=360, anchor=W)

        scrollbar_style = Style(parent)
        scrollbar_style.configure("Vertical.TScrollbar")

        tree.configure(yscrollcommand=lambda *a: None)
        from tkinter.ttk import Scrollbar as TtkScrollbar
        vsb = TtkScrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        vsb.pack(side=RIGHT, fill="y")
        tree.pack(fill=BOTH, expand=True)

        tree.bind("<Double-1>", self._on_double_click)

        self._tree = tree

    def _on_double_click(self, event) -> None:
        if self._tree is None:
            return
        selection = self._tree.selection()
        if not selection:
            return
        iid = selection[0]
        app = self._app_map.get(iid)
        if app is None:
            return
        if app.is_running:
            self._do_kill(app)
        else:
            self._do_spawn(app)

    def _kill_selected(self) -> None:
        if self._tree is None:
            return
        selection = self._tree.selection()
        if not selection:
            return
        app = self._app_map.get(selection[0])
        if app:
            self._do_kill(app)

    def _spawn_selected(self) -> None:
        if self._tree is None:
            return
        selection = self._tree.selection()
        if not selection:
            return
        app = self._app_map.get(selection[0])
        if app:
            self._do_spawn(app)

    def _render_apps(self) -> None:
        if self._tree is None:
            return

        self._tree.delete(*self._tree.get_children())
        self._app_map.clear()

        search = (self._search_var.get() if self._search_var else "").lower()

        filtered = self._all_apps
        if search:
            filtered = [
                app for app in self._all_apps
                if search in app.name.lower() or search in app.identifier.lower()
            ]

        running = [a for a in filtered if a.is_running]
        stopped = [a for a in filtered if not a.is_running]
        ordered = running + stopped

        for idx, app in enumerate(ordered):
            if app.is_running:
                status = "运行中"
                pid = str(app.pid)
                tag = "running"
            else:
                status = "未运行"
                pid = "-"
                tag = "stopped"

            iid = str(idx)
            self._tree.insert("", "end", iid=iid, values=(status, pid, app.name, app.identifier), tags=(tag,))
            self._app_map[iid] = app

        self._tree.tag_configure("running", foreground="#2e7d32")
        self._tree.tag_configure("stopped", foreground="#9e9e9e")

    def _refresh_apps(self) -> None:
        def _worker() -> None:
            from .frida_ops import get_all_apps

            apps = get_all_apps(self.host_port)
            if self._root is None:
                return
            self._root.after(0, self._update_apps, apps)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_apps(self, apps: list[AppInfo]) -> None:
        self._all_apps = apps
        self._render_apps()

    def _schedule_refresh(self, root: Tk) -> None:
        self._refresh_apps()
        root.after(5000, lambda: self._schedule_refresh(root))

    def _do_kill(self, app: AppInfo) -> None:
        if not app.is_running or app.pid is None:
            return

        from .frida_ops import kill_app

        success = kill_app(self.host_port, app.pid)
        if success:
            print(f"[Frida Manager] 已终止 {app.identifier} (PID {app.pid})")
        else:
            print(f"[Frida Manager] 终止 {app.identifier} 失败")
        self._refresh_apps()

    def _do_spawn(self, app: AppInfo) -> None:
        from .frida_ops import find_hook_scripts, spawn_app

        scripts = find_hook_scripts()
        if scripts:
            selected = self._show_script_dialog(scripts)
            if selected is None:
                return
            script_arg = str(selected) if selected != Path("__none__") else None
        else:
            script_arg = None

        proc = spawn_app(self.host_port, app.identifier, script_arg)
        if proc:
            self._spawned_processes.append(proc)
            label = script_arg or "无脚本"
            print(f"[Frida Manager] 已启动 {app.identifier} ({label})")
        else:
            print(f"[Frida Manager] 启动 {app.identifier} 失败")
        if self._root:
            self._root.after(2000, self._refresh_apps)

    def _show_script_dialog(self, scripts: list[Path]) -> Path | None:
        result: list[Path | None] = [None]

        dialog = Toplevel(self._root)
        dialog.title("选择 Hook 脚本")
        dialog.geometry("480x360")
        dialog.transient(self._root)
        dialog.grab_set()

        Label(
            dialog,
            text="选择要加载的 Hook 脚本:",
            font=("Helvetica", 11, "bold"),
        ).pack(pady=(12, 8))

        btn_frame = Frame(dialog)
        btn_frame.pack(fill=BOTH, expand=True, padx=16)

        def on_select(val: Path | None) -> None:
            result[0] = val
            dialog.destroy()

        for script in scripts:
            TtkButton(
                btn_frame,
                text=script.name,
                command=lambda s=script: on_select(s),
            ).pack(fill="x", pady=2)

        TtkButton(
            btn_frame,
            text="无脚本 (直接启动)",
            command=lambda: on_select(Path("__none__")),
        ).pack(fill="x", pady=(8, 2))

        TtkButton(
            btn_frame,
            text="取消",
            command=lambda: on_select(None),
        ).pack(fill="x", pady=2)

        dialog.protocol("WM_DELETE_WINDOW", lambda: on_select(None))
        dialog.wait_window()
        return result[0]

    def _on_close(self) -> None:
        self._cleanup_spawned()
        if self._root:
            self._root.destroy()

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
    window = FridaManagerWindow(
        device_id=device_id,
        host_port=host_port,
        android_port=android_port,
        frida_server_path=frida_server_path,
    )
    window.run()
