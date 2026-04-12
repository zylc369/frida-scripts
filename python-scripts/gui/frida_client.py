"""FridaClient: per-device frida operations and lifecycle management."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from library import adb
from library import install_record
from library import port as port_mod
from library.errors import BwFridaError, ErrorCode
from library.log import log
from library.random_name import generate_random_name

if TYPE_CHECKING:
    pass

_FRIDA_APP_LOG_DIR = Path("~/bw-frida").expanduser()


class FridaServerError(BwFridaError):
    def __init__(self, message: str, error_code: ErrorCode) -> None:
        super().__init__(message, error_code)


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
        log.warning(
            "命令失败 (exit %d): %s\nstderr: %s",
            result.returncode,
            " ".join(args),
            result.stderr.strip(),
        )
    return result


class FridaClient:
    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self._host_port: int | None = None
        self._android_port: int | None = None
        self._frida_install_path: str | None = None
        self._process: subprocess.Popen | None = None
        self._frida_pid: int | None = None
        self._spawned_processes: list[subprocess.Popen] = []

    @property
    def host_port(self) -> int | None:
        return self._host_port

    @property
    def android_port(self) -> int | None:
        return self._android_port

    @property
    def frida_install_path(self) -> str | None:
        return self._frida_install_path

    @property
    def frida_pid(self) -> int | None:
        return self._frida_pid

    @property
    def is_server_running(self) -> bool:
        return self._host_port is not None

    @property
    def app_log_path(self) -> str:
        return str(_FRIDA_APP_LOG_DIR / f"frida-{self.device_id}-app.log")

    def install_server(self, upgrade: bool = False) -> None:
        from library.frida_server_downloader import prepare_frida_server

        record = install_record.get_device_record(self.device_id)
        if record is not None and not upgrade:
            install_path = record.get("installPath")
            if install_path and adb.check_path_exists(self.device_id, install_path):
                log.info(
                    "设备 %s 已安装 frida-server: %s", self.device_id, install_path
                )
                self._frida_install_path = install_path
                return
            else:
                log.warning("安装记录失效，将重新安装: %s", self.device_id)
                install_record.delete_device_record(self.device_id)

        source_path = prepare_frida_server(upgrade=upgrade)
        if source_path is None:
            msg = f"无法获取 frida-server 二进制文件 (设备: {self.device_id})"
            log.error(msg)
            raise FridaServerError(msg, ErrorCode.SERVER_NOT_INSTALLED)

        devices = adb.get_devices()
        if self.device_id not in devices:
            msg = f"设备 {self.device_id} 未连接"
            log.error(msg)
            raise FridaServerError(msg, ErrorCode.DEVICE_NOT_CONNECTED)

        dir_name = generate_random_name()
        file_name = generate_random_name()
        install_dir = f"/data/local/tmp/{dir_name}"
        install_path = f"{install_dir}/{file_name}"
        log.info("安装路径 (设备 %s): %s", self.device_id, install_path)
        adb.mkdir_p(self.device_id, install_dir)
        adb.push_file(self.device_id, str(source_path), install_path)
        adb.adb_shell(self.device_id, f"chmod 755 {install_path}")
        install_record.update_device_record(
            self.device_id,
            sourcePath=str(source_path),
            installPath=install_path,
        )
        log.info("frida-server 安装成功 (设备 %s): %s", self.device_id, install_path)
        self._frida_install_path = install_path

    def start_server(self) -> None:
        record = install_record.get_device_record(self.device_id)
        if record is None:
            msg = f"未找到设备 {self.device_id} 的安装记录，请先安装"
            log.error(msg)
            raise FridaServerError(msg, ErrorCode.INSTALL_RECORD_INVALID)

        install_path = record.get("installPath")
        if not install_path:
            msg = f"安装记录缺少 installPath (设备: {self.device_id})"
            log.error(msg)
            raise FridaServerError(msg, ErrorCode.INSTALL_RECORD_INVALID)

        if not adb.check_path_exists(self.device_id, install_path):
            msg = f"frida-server 在设备 {self.device_id} 上不存在: {install_path}"
            log.error(msg)
            raise FridaServerError(msg, ErrorCode.SERVER_NOT_INSTALLED)

        android_port = port_mod.find_free_android_port(self.device_id)
        log.info("使用 Android 端口 (设备 %s): %d", self.device_id, android_port)
        frida_process = adb.run_frida_server_bg(
            self.device_id, install_path, android_port
        )
        host_port = port_mod.find_free_host_port()
        log.info("使用主机端口 (设备 %s): %d", self.device_id, host_port)
        adb.forward_port(self.device_id, host_port, android_port)
        install_record.update_device_record(
            self.device_id,
            hostTcpPort=host_port,
            androidTcpPort=android_port,
        )
        log.info(
            "frida-server 已启动 (设备 %s): 主机端口 %d -> Android 端口 %d",
            self.device_id,
            host_port,
            android_port,
        )
        self._host_port = host_port
        self._android_port = android_port
        self._frida_install_path = install_path
        self._process = frida_process
        self._frida_pid = self._query_remote_pid(install_path)

    def stop_server(self) -> None:
        self._cleanup_remote_server()
        self._cleanup_port_forward()
        self._cleanup_process()

    def cleanup(self) -> None:
        self.stop_server()
        self._cleanup_spawned_processes()

    def _query_remote_pid(self, install_path: str) -> int | None:
        time.sleep(1)
        basename = Path(install_path).name
        result = adb.adb_shell(
            self.device_id, f"su -c 'pidof {basename}'"
        )
        pid_str = result.stdout.strip()
        if pid_str:
            pid = int(pid_str.split()[0])
            log.info("frida-server 远程 PID (设备 %s): %d", self.device_id, pid)
            return pid
        log.warning("未能获取远程 PID (设备 %s)", self.device_id)
        return None

    def _cleanup_remote_server(self) -> None:
        if not self._frida_install_path:
            return
        basename = Path(self._frida_install_path).name
        log.info("正在终止远程 frida-server (设备 %s): %s", self.device_id, basename)
        try:
            adb.adb_shell(self.device_id, f"su -c 'pkill -9 -f {basename}'")
        except Exception as e:
            log.warning(
                "终止远程 frida-server 失败 (设备 %s，可能已断联): %s",
                self.device_id,
                e,
            )
        self._frida_pid = None
        self._frida_install_path = None

    def _cleanup_port_forward(self) -> None:
        if self._host_port is None:
            return
        log.info(
            "清理端口转发 (设备 %s): host_port=%d", self.device_id, self._host_port
        )
        try:
            adb.remove_forward(self.device_id, self._host_port)
        except Exception as e:
            log.warning(
                "清理端口转发失败 (设备 %s，可能已断联): %s", self.device_id, e
            )
        try:
            install_record.update_device_record(
                self.device_id, hostTcpPort=None, androidTcpPort=None
            )
        except Exception as e:
            log.warning("更新安装记录失败 (设备 %s): %s", self.device_id, e)
        self._host_port = None
        self._android_port = None

    def _cleanup_process(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def _cleanup_spawned_processes(self) -> None:
        for proc in self._spawned_processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._spawned_processes.clear()

    def get_running_apps(self) -> list[AppInfo]:
        if self._host_port is None:
            return []
        log.info("获取运行中应用列表 (设备 %s)", self.device_id)
        proc = _run_frida_cmd(["frida-ps", "-H", f"127.0.0.1:{self._host_port}"])
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
        log.info("运行中应用数量 (设备 %s): %d", self.device_id, len(apps))
        return apps

    def get_installed_apps(self) -> list[AppInfo]:
        if self._host_port is None:
            return []
        log.info("获取已安装应用列表 (设备 %s)", self.device_id)
        proc = _run_frida_cmd(
            ["frida-ps", "-H", f"127.0.0.1:{self._host_port}", "-ai"]
        )
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
            apps.append(
                AppInfo(pid=pid, name=name, identifier=identifier, is_running=is_running)
            )
        log.info("已安装应用数量 (设备 %s): %d", self.device_id, len(apps))
        return apps

    def get_all_apps(self) -> list[AppInfo]:
        installed = self.get_installed_apps()
        running = self.get_running_apps()

        installed_by_id: dict[str, AppInfo] = {
            app.identifier: app for app in installed
        }
        name_to_identifier: dict[str, str] = {
            app.name: app.identifier for app in installed
        }

        seen_identifiers: set[str] = set()
        merged: list[AppInfo] = []

        for app in running:
            identifier = name_to_identifier.get(app.name, app.name)
            if identifier in installed_by_id:
                installed_app = installed_by_id[identifier]
                merged.append(
                    AppInfo(
                        pid=app.pid,
                        name=installed_app.name,
                        identifier=installed_app.identifier,
                        is_running=True,
                    )
                )
            else:
                merged.append(app)
            seen_identifiers.add(identifier)

        for app in installed:
            if app.identifier not in seen_identifiers:
                merged.append(app)
                seen_identifiers.add(app.identifier)

        merged.sort(key=lambda a: (not a.is_running, -(a.pid or 0), a.name.lower()))
        log.info(
            "合并后应用总数 (设备 %s): %d (运行中: %d, 未运行: %d)",
            self.device_id,
            len(merged),
            sum(1 for a in merged if a.is_running),
            sum(1 for a in merged if not a.is_running),
        )
        return merged

    def kill_app(self, pid: int) -> bool:
        if self._host_port is None:
            log.error("frida-server 未运行，无法 kill (设备 %s)", self.device_id)
            return False
        log.info(
            "正在终止进程 PID=%d (设备 %s, host_port=%d)",
            pid,
            self.device_id,
            self._host_port,
        )
        proc = _run_frida_cmd(
            ["frida-kill", "-H", f"127.0.0.1:{self._host_port}", str(pid)]
        )
        success = proc.returncode == 0
        if success:
            log.info("进程 PID=%d 已终止 (设备 %s)", pid, self.device_id)
        else:
            log.error("终止进程 PID=%d 失败 (设备 %s)", pid, self.device_id)
        return success

    def build_spawn_cmd(
        self,
        package: str,
        script_paths: list[str] | None = None,
    ) -> list[str]:
        if self._host_port is None:
            raise FridaServerError(
                f"frida-server 未运行，无法构建命令 (设备 {self.device_id})",
                ErrorCode.SERVER_NOT_RUNNING,
            )
        cmd = [
            "frida",
            "-H",
            f"127.0.0.1:{self._host_port}",
            "-f",
            package,
        ]
        if script_paths:
            for sp in script_paths:
                cmd.extend(["-l", sp])
        cmd.extend(["-o", self.app_log_path])
        log.info(
            "构建启动命令 (设备 %s): %s (脚本: %s)",
            self.device_id,
            package,
            script_paths or "无",
        )
        return cmd

    def spawn_app(
        self,
        package: str,
        script_paths: list[str] | None = None,
    ) -> tuple[subprocess.Popen | None, str | None]:
        cmd = self.build_spawn_cmd(package, script_paths)
        log.info(
            "启动应用 (设备 %s): %s, 命令: %s",
            self.device_id,
            package,
            " ".join(cmd),
        )
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            log.info(
                "frida 进程已启动 (设备 %s): PID=%d, 目标应用=%s",
                self.device_id,
                proc.pid,
                package,
            )
            return proc, None
        except OSError as exc:
            msg = f"启动 frida 进程失败 (设备 {self.device_id}): {exc}"
            log.error(msg)
            return None, str(exc)
