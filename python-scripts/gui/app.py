"""Frida Management GUI — tkinter-based graphical interface for managing frida sessions."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    W,
    Button,
    Canvas,
    Entry,
    Frame,
    Label,
    Scrollbar,
    StringVar,
    Tk,
    Toplevel,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .frida_ops import AppInfo


_BG = "#f5f5f5"
_HEADER_BG = "#e3f2fd"
_RUNNING_FG = "#2e7d32"
_STOPPED_FG = "#9e9e9e"
_ROW_EVEN = "#ffffff"
_ROW_ODD = "#f0f0f0"


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
        self._scroll_frame: Frame | None = None
        self._canvas: Canvas | None = None

    def run(self) -> None:
        root = Tk()
        root.title("Frida Manager")
        root.geometry("960x680")
        root.minsize(720, 480)
        root.configure(bg=_BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root = root

        self._build_info_panel(root)
        self._build_search_bar(root)
        self._build_app_list(root)

        self._refresh_apps()
        self._schedule_refresh(root)

        root.mainloop()
        self._cleanup_spawned()

    def _build_info_panel(self, parent: Tk) -> None:
        panel = Frame(parent, bg=_HEADER_BG, padx=12, pady=8)
        panel.pack(fill="x", padx=8, pady=(8, 0))

        fields = [
            ("设备ID", self.device_id),
            ("Android端口", str(self.android_port)),
            ("主机端口", str(self.host_port)),
            ("Frida路径", self.frida_server_path),
        ]
        for label_text, value_text in fields:
            row = Frame(panel, bg=_HEADER_BG)
            row.pack(fill="x", pady=1)
            Label(
                row, text=label_text + ": ", bg=_HEADER_BG, fg="#1a237e",
                font=("Helvetica", 10, "bold"), anchor=W,
            ).pack(side=LEFT)
            entry = Entry(
                row, font=("Helvetica", 10), readonlybackground=_HEADER_BG,
                fg="#1a237e", bd=0, relief="flat",
            )
            entry.insert(0, value_text)
            entry.configure(state="readonly")
            entry.pack(side=LEFT, fill="x", expand=True)

    def _build_search_bar(self, parent: Tk) -> None:
        bar = Frame(parent, bg=_BG, padx=8, pady=6)
        bar.pack(fill="x")

        Label(bar, text="搜索:", bg=_BG, font=("Helvetica", 10)).pack(side=LEFT, padx=(0, 6))

        self._search_var = StringVar()
        self._search_var.trace_add("write", lambda *_: self._render_apps())
        search_entry = Entry(
            bar,
            textvariable=self._search_var,
            font=("Helvetica", 10),
            width=60,
        )
        search_entry.pack(side=LEFT, fill="x", expand=True)

        Button(
            bar,
            text="刷新",
            command=self._refresh_apps,
            font=("Helvetica", 10),
            padx=12,
        ).pack(side=RIGHT, padx=(6, 0))

    def _build_app_list(self, parent: Tk) -> None:
        header = Frame(parent, bg="#e0e0e0", padx=8, pady=4)
        header.pack(fill="x", padx=8, pady=(4, 0))

        columns = [
            ("状态", 10),
            ("PID", 8),
            ("应用名", 22),
            ("包名", 36),
            ("操作", 12),
        ]
        for text, width in columns:
            Label(
                header,
                text=text,
                bg="#e0e0e0",
                fg="#424242",
                font=("Helvetica", 9, "bold"),
                width=width,
                anchor=W,
            ).pack(side=LEFT)

        list_frame = Frame(parent, bg=_BG)
        list_frame.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        canvas = Canvas(list_frame, bg=_BG, highlightthickness=0)
        scrollbar = Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self._scroll_frame = Frame(canvas, bg=_BG)
        self._canvas = canvas

        self._scroll_frame.bind(
            "<Configure>",
            lambda _: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill="y")
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        import platform
        if platform.system() == "Darwin":
            canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta, "units"))
        else:
            canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    def _render_apps(self) -> None:
        if self._scroll_frame is None:
            return

        for widget in self._scroll_frame.winfo_children():
            widget.destroy()

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

        for i, app in enumerate(ordered):
            row_bg = _ROW_EVEN if i % 2 == 0 else _ROW_ODD
            row = Frame(self._scroll_frame, bg=row_bg, padx=8, pady=3)
            row.pack(fill="x")

            if app.is_running:
                status_text = "运行中"
                status_fg = _RUNNING_FG
                pid_text = str(app.pid)
            else:
                status_text = "未运行"
                status_fg = _STOPPED_FG
                pid_text = "-"

            Label(
                row, text=status_text, bg=row_bg, fg=status_fg,
                font=("Helvetica", 9), width=10, anchor=W,
            ).pack(side=LEFT)
            Label(
                row, text=pid_text, bg=row_bg, fg="#424242",
                font=("Helvetica", 9), width=8, anchor=W,
            ).pack(side=LEFT)
            Label(
                row, text=app.name, bg=row_bg, fg="#212121",
                font=("Helvetica", 9), width=22, anchor=W,
            ).pack(side=LEFT)
            Label(
                row, text=app.identifier, bg=row_bg, fg="#616161",
                font=("Helvetica", 9), width=36, anchor=W,
            ).pack(side=LEFT)

            if app.is_running:
                Button(
                    row,
                    text="Kill",
                    font=("Helvetica", 9, "bold"),
                    padx=8,
                    command=lambda a=app: self._do_kill(a),
                ).pack(side=LEFT, padx=(4, 0))
            else:
                Button(
                    row,
                    text="启动",
                    font=("Helvetica", 9, "bold"),
                    padx=8,
                    command=lambda a=app: self._do_spawn(a),
                ).pack(side=LEFT, padx=(4, 0))

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
        dialog.configure(bg=_BG)
        dialog.transient(self._root)
        dialog.grab_set()

        Label(
            dialog,
            text="选择要加载的 Hook 脚本:",
            bg=_BG,
            font=("Helvetica", 11, "bold"),
        ).pack(pady=(12, 8))

        btn_frame = Frame(dialog, bg=_BG)
        btn_frame.pack(fill=BOTH, expand=True, padx=16)

        def on_select(val: Path | None) -> None:
            result[0] = val
            dialog.destroy()

        for script in scripts:
            Button(
                btn_frame,
                text=script.name,
                font=("Helvetica", 10),
                padx=12,
                pady=4,
                command=lambda s=script: on_select(s),
            ).pack(fill="x", pady=2)

        Button(
            btn_frame,
            text="无脚本 (直接启动)",
            font=("Helvetica", 10),
            padx=12,
            pady=4,
            command=lambda: on_select(Path("__none__")),
        ).pack(fill="x", pady=(8, 2))

        Button(
            btn_frame,
            text="取消",
            font=("Helvetica", 10),
            padx=12,
            pady=4,
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
