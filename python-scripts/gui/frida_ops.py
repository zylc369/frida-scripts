"""Frida CLI operations: list apps, kill processes, spawn apps."""

import subprocess
from dataclasses import dataclass

from library.log import log


@dataclass
class AppInfo:
    pid: int | None
    name: str
    identifier: str
    is_running: bool


def _run_frida_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    log.debug("执行命令: %s", " ".join(args))
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        log.warning("命令失败 (exit %d): %s\nstderr: %s", result.returncode, " ".join(args), result.stderr.strip())
    return result


def get_running_apps(host_port: int) -> list[AppInfo]:
    log.info("获取运行中应用列表 (host_port=%d)", host_port)
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
    log.info("运行中应用数量: %d", len(apps))
    return apps


def get_installed_apps(host_port: int) -> list[AppInfo]:
    log.info("获取已安装应用列表 (host_port=%d)", host_port)
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
    log.info("已安装应用数量: %d", len(apps))
    return apps


def get_all_apps(host_port: int) -> list[AppInfo]:
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
    log.info("合并后应用总数: %d (运行中: %d, 未运行: %d)",
             len(merged),
             sum(1 for a in merged if a.is_running),
             sum(1 for a in merged if not a.is_running))
    return merged


def kill_app(host_port: int, pid: int) -> bool:
    log.info("正在终止进程 PID=%d (host_port=%d)", pid, host_port)
    proc = _run_frida_cmd(["frida-kill", "-H", f"127.0.0.1:{host_port}", str(pid)])
    success = proc.returncode == 0
    if success:
        log.info("进程 PID=%d 已终止", pid)
    else:
        log.error("终止进程 PID=%d 失败", pid)
    return success


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
    log.info("构建启动命令: %s (脚本: %s)", package, script_paths or "无")
    return cmd


def spawn_app(
    host_port: int,
    package: str,
    script_paths: list[str] | None = None,
) -> tuple[subprocess.Popen | None, str | None]:
    cmd = build_spawn_cmd(host_port, package, script_paths)
    log.info("启动应用: %s, 命令: %s", package, " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log.info("frida 进程已启动, PID=%d, 目标应用=%s", proc.pid, package)
        return proc, None
    except OSError as exc:
        log.error("启动 frida 进程失败: %s", exc)
        return None, str(exc)
