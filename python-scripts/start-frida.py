#!/usr/bin/env python3
"""一键启动 Android 上的 frida-server"""

import argparse
import atexit
import signal
import sys

from library import adb
from library.log import log


class FridaStartupClient:
    def __init__(self, serial: str, upgrade: bool, gui: bool = False) -> None:
        self._serial = serial
        self._upgrade = upgrade
        self._gui = gui

    def start(self) -> None:
        log.info("===== 开始启动 frida-server =====")

        if self._gui:
            self._launch_gui()
        else:
            self._start_and_wait()

    def _start_and_wait(self) -> None:
        from gui.frida_client_manager import FridaClientManager
        from gui.frida_client import FridaServerError

        manager = FridaClientManager()
        try:
            client = manager.start_frida_for_device(self._serial, upgrade=self._upgrade)
        except FridaServerError:
            log.error("frida-server 启动失败")
            sys.exit(1)

        atexit.register(manager.close_all)

        log.info("===== frida-server 启动完成 =====")
        log.info("连接信息: 127.0.0.1:%d", client.host_port)

        self._register_signal_handlers()
        log.info("按 Ctrl+C 停止 frida-server")
        self._wait(manager)

    def _launch_gui(self) -> None:
        from gui.app import launch_gui

        log.info("正在启动 GUI 模式...")
        launch_gui()

    def _register_signal_handlers(self) -> None:
        def signal_handler(signum, frame):
            log.info("收到终止信号，正在清理...")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _wait(self, manager) -> None:
        client = manager.get_client(self._serial)
        if client is None:
            return
        process = client._process
        if process is None:
            return
        try:
            process.wait()
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
        help="启动 GUI 管理界面 (无需预先指定设备)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.gui:
        FridaStartupClient(serial="", upgrade=args.upgrade, gui=True).start()
    else:
        serial = adb.resolve_device(args.serial)
        FridaStartupClient(serial=serial, upgrade=args.upgrade).start()


if __name__ == "__main__":
    main()
