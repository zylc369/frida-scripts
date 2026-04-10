"""Frida CLI operations: list apps, kill processes, spawn apps."""

import subprocess
from dataclasses import dataclass


@dataclass
class AppInfo:
    pid: int | None
    name: str
    identifier: str
    is_running: bool


def _run_frida_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a frida CLI command with standard safety settings."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def get_running_apps(host_port: int) -> list[AppInfo]:
    """List running processes via ``frida-ps -H``.

    Output format::

        PID  Name
        ----  ----
        1234  Gmail

    Running apps lack a package identifier, so *identifier* is set to *name*.
    """
    proc = _run_frida_cmd(["frida-ps", "-H", f"127.0.0.1:{host_port}"])
    apps: list[AppInfo] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if not parts:
            continue
        if parts[0] == "PID" or parts[0].startswith("----"):
            continue
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        name = parts[1].strip()
        apps.append(AppInfo(pid=pid, name=name, identifier=name, is_running=True))
    return apps


def get_installed_apps(host_port: int) -> list[AppInfo]:
    """List installed applications via ``frida-ps -H … -ai``.

    Output format::

        PID  Name             Identifier
        ----  ---------------  -----------------------
        1234  Gmail            com.google.android.gm
         -    Calculator       com.android.calculator2
    """
    proc = _run_frida_cmd(["frida-ps", "-H", f"127.0.0.1:{host_port}", "-ai"])
    apps: list[AppInfo] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if not parts or parts[0] == "PID" or parts[0].startswith("----"):
            continue
        if len(parts) < 3:
            continue
        pid_str = parts[0]
        if pid_str == "-":
            pid = None
            is_running = False
        else:
            try:
                pid = int(pid_str)
                is_running = True
            except ValueError:
                continue
        identifier = parts[-1]
        name = " ".join(parts[1:-1])
        apps.append(AppInfo(pid=pid, name=name, identifier=identifier, is_running=is_running))
    return apps


def get_all_apps(host_port: int) -> list[AppInfo]:
    """Return installed + running apps, deduplicated by *identifier*.

    Running apps appear first, then non-running.  Within each group apps are
    sorted alphabetically by name.
    """
    installed = get_installed_apps(host_port)
    running = get_running_apps(host_port)

    installed_by_id: dict[str, AppInfo] = {app.identifier: app for app in installed}
    name_to_identifier: dict[str, str] = {app.name: app.identifier for app in installed}

    seen_identifiers: set[str] = set()
    merged: list[AppInfo] = []

    for app in running:
        identifier = name_to_identifier.get(app.name, app.name)
        if identifier in installed_by_id:
            installed_app = installed_by_id[identifier]
            merged.append(AppInfo(
                pid=app.pid,
                name=installed_app.name,
                identifier=installed_app.identifier,
                is_running=True,
            ))
        else:
            merged.append(app)
        seen_identifiers.add(identifier)

    for app in installed:
        if app.identifier not in seen_identifiers:
            merged.append(app)
            seen_identifiers.add(app.identifier)

    merged.sort(key=lambda a: (not a.is_running, -(a.pid or 0), a.name.lower()))
    return merged


def kill_app(host_port: int, pid: int) -> bool:
    """Kill a process via ``frida-kill -H … <pid>``.

    Returns ``True`` if the command exited with code 0.
    """
    proc = _run_frida_cmd(["frida-kill", "-H", f"127.0.0.1:{host_port}", str(pid)])
    return proc.returncode == 0


def build_spawn_cmd(
    host_port: int,
    package: str,
    script_paths: list[str] | None = None,
) -> list[str]:
    cmd = [
        "frida",
        "-H", f"127.0.0.1:{host_port}",
        "-f", package,
    ]
    if script_paths:
        for sp in script_paths:
            cmd.extend(["-l", sp])
    cmd.append("--no-pause")
    return cmd


def spawn_app(
    host_port: int,
    package: str,
    script_paths: list[str] | None = None,
) -> tuple[subprocess.Popen | None, str | None]:
    cmd = build_spawn_cmd(host_port, package, script_paths)
    try:
        return subprocess.Popen(cmd), None
    except OSError as exc:
        return None, str(exc)
