#!/usr/bin/env python3
"""一键启动 Android 上的 frida-server"""

import argparse
import atexit
import signal
import subprocess
import sys
import tarfile
from pathlib import Path

from library import config
from library import adb
from library import install_record
from library import port as port_mod
from library.log import log
from library.random_name import generate_random_name

SCRIPT_DIR = Path(__file__).resolve().parent


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
    return parser.parse_args()


def step1_download_frida_server(serial: str, upgrade: bool) -> Path | None:
    skip, record = _check_install_record(serial, upgrade)
    if skip:
        return None

    local = _find_local_download()
    if local is not None:
        return local
    archive = _download_frida_server()
    return _extract_archive(archive)
def _check_install_record(serial: str, upgrade: bool) -> tuple[bool, dict | None]:
    record = install_record.get_device_record(serial)
    if record is None:
        return False, None

    if upgrade:
        log.info("--upgrade 指定，跳过安装记录检查，将重新下载")
        return False, None

    install_path = record.get("installPath")
    if not install_path:
        log.warning("安装记录缺少 installPath，删除失效记录")
        install_record.delete_device_record(serial)
        return False, None

    if adb.check_path_exists(serial, install_path):
        log.info("frida-server 已安装于设备: %s", install_path)
        return True, record
    else:
        log.warning("安装记录中的路径在设备上不存在，删除失效记录: %s", install_path)
        install_record.delete_device_record(serial)
        return False, None


def _find_local_download() -> Path | None:
    if not config.FRIDA_DOWNLOAD_DIR.exists():
        return None

    candidates = []
    for path in config.FRIDA_DOWNLOAD_DIR.glob(config.FRIDA_SERVER_BINARY_GLOB):
        if path.is_file() and not path.name.endswith((".xz", ".gz", ".bz2")):
            candidates.append(path)

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.stat().st_ctime, reverse=True)
    chosen = candidates[0]
    log.info("找到本地已下载的 frida-server: %s", chosen)
    return chosen
def _download_frida_server() -> Path:
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
    downloaded_files = []
    for line in output.splitlines():
        line = line.strip()
        if config.FRIDA_DOWNLOAD_DIR.name in line or "frida-server" in line:
            for potential_path in line.split():
                p = Path(potential_path.strip())
                if p.exists() and "frida-server" in p.name:
                    downloaded_files.append(p)

    if not downloaded_files:
        for path in config.FRIDA_DOWNLOAD_DIR.glob("frida-server-*-android-arm64.*"):
            if path.is_file() and path.name.endswith((".xz", ".gz", ".bz2", ".tar")):
                downloaded_files.append(path)

    if len(downloaded_files) == 0:
        log.error("下载完成但未找到下载的文件")
        sys.exit(1)

    if len(downloaded_files) > 1:
        log.error(
            "下载了多个文件，预期只下载一个。下载的文件: %s",
            ", ".join(str(f) for f in downloaded_files),
        )
        sys.exit(1)

    archive_path = downloaded_files[0]
    log.info("下载完成: %s", archive_path)
    return archive_path
def _extract_archive(archive_path: Path) -> Path:
    log.info("正在解压: %s", archive_path)
    try:
        with tarfile.open(archive_path, "r") as tar:
            tar.extractall(path=str(config.FRIDA_DOWNLOAD_DIR))
    except Exception as e:
        log.error("解压失败: %s", e)
        sys.exit(1)

    extracted = _find_local_download()
    if extracted is None:
        log.error("解压完成但未找到 frida-server 二进制文件")
        sys.exit(1)
    log.info("解压成功: %s", extracted)
    return extracted
def step2_install_to_device(serial: str, source_path: Path) -> str:
    devices = adb.get_devices()
    if serial not in devices:
        log.error("设备 %s 未连接", serial)
        sys.exit(1)
    dir_name = generate_random_name()
    file_name = generate_random_name()
    install_dir = f"{config.ADB_INSTALL_ROOT}/{dir_name}"
    install_path = f"{install_dir}/{file_name}"
    log.info("安装路径: %s", install_path)
    adb.mkdir_p(serial, install_dir)
    adb.push_file(serial, str(source_path), install_path)
    adb.adb_shell(serial, f"chmod 755 {install_path}")
    install_record.update_device_record(
        serial,
        sourcePath=str(source_path),
        installPath=install_path,
    )
    log.info("frida-server 安装成功: %s", install_path)
    return install_path
def step3_run_frida_server(serial: str) -> tuple[int, int, subprocess.Popen]:
    record = install_record.get_device_record(serial)
    if record is None:
        log.error("未找到设备 %s 的安装记录", serial)
        sys.exit(1)
    install_path = record.get("installPath")
    if not install_path:
        log.error("安装记录缺少 installPath")
        sys.exit(1)
    if not adb.check_path_exists(serial, install_path):
        log.error("frida-server 在设备上不存在: %s", install_path)
        sys.exit(1)
    android_port = port_mod.find_free_android_port(serial)
    log.info("使用 Android 端口: %d", android_port)
    frida_process = adb.run_frida_server_bg(serial, install_path, android_port)
    host_port = port_mod.find_free_host_port()
    log.info("使用主机端口: %d", host_port)
    adb.forward_port(serial, host_port, android_port)
    install_record.update_device_record(
        serial,
        hostTcpPort=host_port,
        androidTcpPort=android_port,
    )
    log.info("frida-server 已启动")
    log.info("主机端口 %d -> Android 端口 %d (设备: %s)", host_port, android_port, serial)
    return host_port, android_port, frida_process
_cleanup_registered = False
_cleanup_serial = None
_cleanup_host_port = None
_cleanup_process = None
def _do_cleanup() -> None:
    if _cleanup_serial and _cleanup_host_port:
        adb.remove_forward(_cleanup_serial, _cleanup_host_port)
    if _cleanup_process and _cleanup_process.poll() is None:
        _cleanup_process.terminate()
        try:
            _cleanup_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _cleanup_process.kill()
def register_cleanup(serial: str, host_port: int, frida_process: subprocess.Popen) -> None:
    global _cleanup_registered, _cleanup_serial, _cleanup_host_port, _cleanup_process
    _cleanup_serial = serial
    _cleanup_host_port = host_port
    _cleanup_process = frida_process
    if not _cleanup_registered:
        atexit.register(_do_cleanup)
        def signal_handler(signum, frame):
            log.info("收到终止信号，正在清理...")
            _do_cleanup()
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        _cleanup_registered = True
def main() -> None:
    args = parse_args()
    log.info("===== 开始启动 frida-server =====")
    serial = adb.resolve_device(args.serial)
    source_path = step1_download_frida_server(serial, args.upgrade)
    if source_path is not None:
        step2_install_to_device(serial, source_path)
    host_port, android_port, process = step3_run_frida_server(serial)
    register_cleanup(serial, host_port, process)
    log.info("===== frida-server 启动完成 =====")
    log.info("连接信息: 127.0.0.1:%d", host_port)
    log.info("按 Ctrl+C 停止 frida-server")
    try:
        process.wait()
    except KeyboardInterrupt:
        pass
if __name__ == "__main__":
    main()
