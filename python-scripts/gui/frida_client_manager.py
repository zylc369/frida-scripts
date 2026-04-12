"""FridaClientManager: thread-safe singleton managing all FridaClient instances."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from library.log import log

if TYPE_CHECKING:
    from .frida_client import FridaClient


class FridaClientManager:
    _instance: FridaClientManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> FridaClientManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._clients: dict[str, FridaClient] = {}
                cls._instance._clients_lock = threading.Lock()
            return cls._instance

    def start_frida_for_device(
        self, device_id: str, upgrade: bool = False
    ) -> FridaClient:
        from .frida_client import FridaClient

        with self._clients_lock:
            if device_id in self._clients:
                existing = self._clients[device_id]
                if existing.is_server_running:
                    log.info(
                        "设备 %s 已有运行中的 FridaClient，直接返回", device_id
                    )
                    return existing
                log.info(
                    "设备 %s 已有 FridaClient 但未运行，将重新启动", device_id
                )
                existing.start_server()
                return existing

            client = FridaClient(device_id)
            self._clients[device_id] = client

        client.install_server(upgrade=upgrade)
        client.start_server()
        return client

    def get_client(self, device_id: str) -> FridaClient | None:
        with self._clients_lock:
            return self._clients.get(device_id)

    def close_client(self, device_id: str) -> None:
        with self._clients_lock:
            client = self._clients.pop(device_id, None)
        if client is not None:
            log.info("关闭设备 %s 的 FridaClient", device_id)
            client.cleanup()

    def close_all(self) -> None:
        with self._clients_lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            log.info("关闭设备 %s 的 FridaClient (close_all)", client.device_id)
            client.cleanup()

    def list_active_devices(self) -> list[str]:
        with self._clients_lock:
            return [
                device_id
                for device_id, client in self._clients.items()
                if client.is_server_running
            ]

    def is_device_active(self, device_id: str) -> bool:
        client = self.get_client(device_id)
        return client is not None and client.is_server_running

    def remove_disconnected_device(self, device_id: str) -> None:
        log.info("移除断联设备 %s 的资源", device_id)
        with self._clients_lock:
            client = self._clients.pop(device_id, None)
        if client is not None:
            try:
                client._cleanup_spawned_processes()
            except Exception as e:
                log.warning(
                    "清理 spawned 进程失败 (设备 %s，已断联): %s", device_id, e
                )
            try:
                client._cleanup_process()
            except Exception as e:
                log.warning(
                    "清理进程失败 (设备 %s，已断联): %s", device_id, e
                )
            client._host_port = None
            client._android_port = None
            client._frida_pid = None
            client._frida_install_path = None
            client._process = None
