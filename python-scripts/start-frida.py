#!/usr/bin/env python3
"""一键启动 Android 上的 frida-server"""

import argparse
import atexit
import lzma
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from library import config
from library import adb
from library import install_record
from library import port as port_mod
from library.log import log
from library.random_name import generate_random_name


@dataclass
class FridaStartupConfig:
    serial: str
    upgrade: bool
    gui: bool = False


class FridaStartupClient:
    def __init__(self, config: FridaStartupConfig) -> None:
        self._config: FridaStartupConfig = config
        self._host_port: int | None = None
        self._android_port: int | None = None
        self._frida_install_path: str | None = None
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        log.info("===== 开始启动 frida-server =====")
        source_path = self._prepare_server()
        if source_path is not None:
            self._install_to_device(source_path)
        self._run_server()
        atexit.register(self._cleanup)
        log.info("===== frida-server 启动完成 =====")
        log.info("连接信息: 127.0.0.1:%d", self._host_port)

        if self._config.gui:
            self._launch_gui()
        else:
            self._register_signal_handlers()
            log.info("按 Ctrl+C 停止 frida-server")
            self._wait()

    # --- step1: download ---
    def _prepare_server(self) -> Path | None:
        skip, record = self._check_install_record()
        if skip:
            return None

        local = self._find_local_download()
        if local is not None:
            return local
        archive = self._download_frida_server()
        return self._extract_archive(archive)

    def _check_install_record(self) -> tuple[bool, dict | None]:
        record = install_record.get_device_record(self._config.serial)
        if record is None:
            return False, None

        if self._config.upgrade:
            log.info("--upgrade 指定，跳过安装记录检查，将重新下载")
            return False, None

        install_path = record.get("installPath")
        if not install_path:
            log.warning("安装记录缺少 installPath，删除失效记录")
            install_record.delete_device_record(self._config.serial)
            return False, None

        if adb.check_path_exists(self._config.serial, install_path):
            log.info("frida-server 已安装于设备: %s", install_path)
            return True, record
        else:
            log.warning("安装记录中的路径在设备上不存在，删除失效记录: %s", install_path)
            install_record.delete_device_record(self._config.serial)
            return False, None

    def _find_local_download(self) -> Path | None:
        if not config.FRIDA_DOWNLOAD_DIR.exists():
            log.info(f"下载目录不存在，意味着 frida-server 还未下载: {config.FRIDA_DOWNLOAD_DIR}")
            return None

        candidates = []
        for path in config.FRIDA_DOWNLOAD_DIR.glob(config.FRIDA_SERVER_BINARY_GLOB):
            if path.is_file() and not path.name.endswith((".xz", ".gz", ".bz2")):
                candidates.append(path)

        if not candidates:
            log.info(f"没有找到本地下载的 frida-server: {config.FRIDA_DOWNLOAD_DIR}")
            return None

        candidates.sort(key=lambda p: p.stat().st_ctime, reverse=True)
        chosen = candidates[0]
        log.info("找到本地已下载的 frida-server: %s", chosen)
        return chosen

    def _download_frida_server(self) -> Path:
        config.FRIDA_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        log.info("正在下载 frida-server...")
        result = subprocess.run(
            [
                "bunx", "@zylc369/bw-gh-release-fetch",
                "https://github.com/frida/frida",
                "frida-server-*-android-arm64.*",
                "-o", str(config.FRIDA_DOWNLOAD_DIR),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log.error("下载 frida-server 失败:\nstdout: %s\nstderr: %s", result.stdout, result.stderr)
            sys.exit(1)

        output = result.stdout.strip()
        downloaded_files = set()
        for line in output.splitlines():
            line = line.strip()
            if config.FRIDA_DOWNLOAD_DIR.name in line or "frida-server" in line:
                for potential_path in line.split():
                    p = Path(potential_path.strip())
                    if p.exists() and "frida-server" in p.name:
                        downloaded_files.add(p)

        if not downloaded_files:
            for path in config.FRIDA_DOWNLOAD_DIR.glob("frida-server-*-android-arm64.*"):
                if path.is_file() and path.name.endswith((".xz", ".gz", ".bz2", ".tar")):
                    downloaded_files.add(path)

        if len(downloaded_files) == 0:
            log.error("下载完成但未找到下载的文件")
            sys.exit(1)

        if len(downloaded_files) > 1:
            log.error(
                "下载了多个文件，预期只下载一个。下载的文件: %s",
                ", ".join(str(f) for f in downloaded_files),
            )
            sys.exit(1)

        archive_path = next(iter(downloaded_files))
        log.info("下载完成: %s", archive_path)
        return archive_path

    def _extract_archive(self, archive_path: Path) -> Path:
        log.info("正在解压: %s", archive_path)
        output_path = config.FRIDA_DOWNLOAD_DIR / archive_path.stem
        try:
            with lzma.open(archive_path, "rb") as f_in, open(output_path, "wb") as f_out:
                while chunk := f_in.read(1024 * 1024):
                    f_out.write(chunk)
        except Exception as e:
            log.error("解压失败: %s", e)
            sys.exit(1)

        extracted = self._find_local_download()
        if extracted is None:
            log.error("解压完成但未找到 frida-server 二进制文件")
            sys.exit(1)
        log.info("解压成功: %s", extracted)
        return extracted

    # --- step2: install ---
    def _install_to_device(self, source_path: Path) -> str:
        devices = adb.get_devices()
        if self._config.serial not in devices:
            log.error("设备 %s 未连接", self._config.serial)
            sys.exit(1)
        dir_name = generate_random_name()
        file_name = generate_random_name()
        install_dir = f"{config.ADB_INSTALL_ROOT}/{dir_name}"
        install_path = f"{install_dir}/{file_name}"
        log.info("安装路径: %s", install_path)
        adb.mkdir_p(self._config.serial, install_dir)
        adb.push_file(self._config.serial, str(source_path), install_path)
        adb.adb_shell(self._config.serial, f"chmod 755 {install_path}")
        install_record.update_device_record(
            self._config.serial,
            sourcePath=str(source_path),
            installPath=install_path,
        )
        log.info("frida-server 安装成功: %s", install_path)
        return install_path

    # --- step3: run ---
    def _run_server(self) -> None:
        record = install_record.get_device_record(self._config.serial)
        if record is None:
            log.error("未找到设备 %s 的安装记录", self._config.serial)
            sys.exit(1)
        install_path = record.get("installPath")
        if not install_path:
            log.error("安装记录缺少 installPath")
            sys.exit(1)
        if not adb.check_path_exists(self._config.serial, install_path):
            log.error("frida-server 在设备上不存在: %s", install_path)
            sys.exit(1)
        android_port = port_mod.find_free_android_port(self._config.serial)
        log.info("使用 Android 端口: %d", android_port)
        frida_process = adb.run_frida_server_bg(self._config.serial, install_path, android_port)
        host_port = port_mod.find_free_host_port()
        log.info("使用主机端口: %d", host_port)
        adb.forward_port(self._config.serial, host_port, android_port)
        install_record.update_device_record(
            self._config.serial,
            hostTcpPort=host_port,
            androidTcpPort=android_port,
        )
        log.info("frida-server 已启动")
        log.info("主机端口 %d -> Android 端口 %d (设备: %s)", host_port, android_port, self._config.serial)
        self._host_port = host_port
        self._android_port = android_port
        self._frida_install_path = install_path
        self._process = frida_process

    # --- cleanup ---
    def _register_signal_handlers(self) -> None:
        def signal_handler(signum, frame):
            log.info("收到终止信号，正在清理...")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _cleanup(self) -> None:
        # 1. Kill remote frida-server and all its child processes on Android
        if self._config.serial and self._frida_install_path:
            basename = Path(self._frida_install_path).name
            log.info("正在终止远程 frida-server 进程: %s", basename)
            adb.adb_shell(self._config.serial, f"su -c 'pkill -9 -f {basename}'")

        # 2. Remove port forwarding (once only)
        if self._host_port is not None:
            log.info("要清理端口。serial: %s，host_port=%d", self._config.serial, self._host_port)
            if self._config.serial:
                adb.remove_forward(self._config.serial, self._host_port)
            install_record.update_device_record(
                self._config.serial,
                hostTcpPort=None,
                androidTcpPort=None,
            )
            self._host_port = None

        # 3. Kill local adb shell process (once only)
        if self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
            self._process = None

    def _launch_gui(self) -> None:
        from gui.app import launch_gui

        assert self._host_port is not None
        assert self._android_port is not None

        log.info("正在启动 GUI 模式...")
        launch_gui(
            device_id=self._config.serial,
            host_port=self._host_port,
            android_port=self._android_port,
            frida_server_path=self._frida_install_path or "unknown",
        )
        self._cleanup()

    def _wait(self) -> None:
        assert self._process is not None
        try:
            self._process.wait()
        except KeyboardInterrupt:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="一键启动 Android 上的 frida-server"
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="强制重新下载 frida-server",
    )
    parser.add_argument(
        "-s",
        dest="serial",
        metavar="SERIAL",
        help="使用指定 serial 的设备 (覆盖 $ANDROID_SERIAL)",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="启动 frida-server 后打开 GUI 管理界面",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client_config = FridaStartupConfig(
        serial=adb.resolve_device(args.serial),
        upgrade=args.upgrade,
        gui=args.gui,
    )
    FridaStartupClient(client_config).start()


if __name__ == "__main__":
    main()
