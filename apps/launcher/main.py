# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from nodi_edge.app import App, AppConfig

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_APP_ID = "launcher"
_SYSTEMD_DIR = Path("/etc/systemd/system")
_VENV_PYTHON = "/root/venv/bin/python3"

# Service unit template
_SERVICE_TEMPLATE = """[Unit]
Description=Nodi Edge Interface: {intf_id}
After=network.target ne-launcher.service
Requires=ne-launcher.service

[Service]
Type=simple
User=nodi
Group=nodi
ExecStart={python} -m {module} {intf_id}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class InterfaceConfig:
    intf_id: str
    protocol: str
    enabled: bool = True


# Protocol code → module mapping
PROTOCOL_MODULES = {
    "mtc": "nodi_edge_intf.modbus_tcp_client",
    "mts": "nodi_edge_intf.modbus_tcp_server",
    "mvc": "nodi_edge_intf.modbus_rtu_tcp_client",
    "mvs": "nodi_edge_intf.modbus_rtu_tcp_server",
    "mrc": "nodi_edge_intf.modbus_rtu_client",
    "mrs": "nodi_edge_intf.modbus_rtu_server",
    "ouc": "nodi_edge_intf.opcua_client",
    "ous": "nodi_edge_intf.opcua_server",
    "mqc": "nodi_edge_intf.mqtt_client",
    "mqs": "nodi_edge_intf.mqtt_broker",
    "kfc": "nodi_edge_intf.kafka_client",
    "kfs": "nodi_edge_intf.kafka_server",
    "rdc": "nodi_edge_intf.rdb_client",
    "rac": "nodi_edge_intf.rest_client",
    "ras": "nodi_edge_intf.rest_server",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Launcher App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LauncherApp(App):

    def __init__(self):
        super().__init__(_APP_ID,
                         app_config=AppConfig(execute_interval_s=5.0,
                                              manage_interval_s=10.0))

        # State
        self._current_interfaces: Dict[str, InterfaceConfig] = {}
        self._running_services: Set[str] = set()
        self._lock = threading.Lock()

    # ────────────────────────────────────────────────────────────
    # Config Loading (TODO: implement with actual config source)
    # ────────────────────────────────────────────────────────────

    def _load_config(self) -> Dict[str, InterfaceConfig]:
        # TODO: load from DB or other config source
        return {}

    def _config_changed(self) -> bool:
        # TODO: detect config changes from DB or other source
        return False

    # ────────────────────────────────────────────────────────────
    # Systemd Service Management
    # ────────────────────────────────────────────────────────────

    def _get_service_name(self, intf_id: str) -> str:
        return f"ne-intf-{intf_id}"

    def _get_service_path(self, intf_id: str) -> Path:
        return _SYSTEMD_DIR / f"{self._get_service_name(intf_id)}.service"

    def _create_service_unit(self, intf: InterfaceConfig) -> bool:
        module = PROTOCOL_MODULES.get(intf.protocol)
        if not module:
            self.logger.warning(f"unknown protocol: {intf.protocol}")
            return False

        service_path = self._get_service_path(intf.intf_id)
        content = _SERVICE_TEMPLATE.format(intf_id=intf.intf_id,
                                           python=_VENV_PYTHON,
                                           module=module)
        try:
            service_path.write_text(content)
            self.logger.info(f"created service unit: {service_path}")
            return True
        except Exception as exc:
            self.logger.error(f"create service unit failed: {exc}")
            return False

    def _remove_service_unit(self, intf_id: str) -> bool:
        service_path = self._get_service_path(intf_id)
        if service_path.exists():
            try:
                service_path.unlink()
                self.logger.info(f"removed service unit: {service_path}")
                return True
            except Exception as exc:
                self.logger.error(f"remove service unit failed: {exc}")
                return False
        return True

    def _systemctl(self, action: str, service: str) -> bool:
        cmd = ["sudo", "systemctl", action, service]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.warning(f"systemctl {action} {service}: {result.stderr.strip()}")
                return False
            return True
        except Exception as exc:
            self.logger.error(f"systemctl {action} {service} failed: {exc}")
            return False

    def _daemon_reload(self) -> bool:
        return self._systemctl("daemon-reload", "")

    def _start_service(self, intf_id: str) -> bool:
        service = self._get_service_name(intf_id)
        if self._systemctl("start", service):
            self._running_services.add(intf_id)
            self.logger.info(f"started: {service}")
            return True
        return False

    def _stop_service(self, intf_id: str) -> bool:
        service = self._get_service_name(intf_id)
        if self._systemctl("stop", service):
            self._running_services.discard(intf_id)
            self.logger.info(f"stopped: {service}")
            return True
        return False

    def _is_service_active(self, intf_id: str) -> bool:
        service = self._get_service_name(intf_id)
        cmd = ["sudo", "systemctl", "is-active", "--quiet", service]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False

    # ────────────────────────────────────────────────────────────
    # Sync Logic
    # ────────────────────────────────────────────────────────────

    def _sync_interfaces(self, new_config: Dict[str, InterfaceConfig]) -> None:
        with self._lock:
            old_ids = set(self._current_interfaces.keys())
            new_ids = set(new_config.keys())

            # Stop and remove deleted interfaces
            removed_ids = old_ids - new_ids
            for intf_id in removed_ids:
                self._stop_service(intf_id)
                self._remove_service_unit(intf_id)
                self.logger.info(f"removed interface: {intf_id}")

            # Add new interfaces
            added_ids = new_ids - old_ids
            need_reload = False
            for intf_id in added_ids:
                intf = new_config[intf_id]
                if intf.enabled:
                    if self._create_service_unit(intf):
                        need_reload = True

            # Check for config changes in existing interfaces
            for intf_id in old_ids & new_ids:
                old_intf = self._current_interfaces[intf_id]
                new_intf = new_config[intf_id]

                # Enabled state changed
                if old_intf.enabled != new_intf.enabled:
                    if new_intf.enabled:
                        if self._create_service_unit(new_intf):
                            need_reload = True
                    else:
                        self._stop_service(intf_id)
                        self._remove_service_unit(intf_id)

                # Protocol changed (need to recreate service)
                elif old_intf.protocol != new_intf.protocol:
                    self._stop_service(intf_id)
                    if self._create_service_unit(new_intf):
                        need_reload = True

            # Reload systemd if needed
            if need_reload:
                self._daemon_reload()

            # Start newly added/enabled services
            for intf_id in added_ids:
                intf = new_config[intf_id]
                if intf.enabled:
                    self._start_service(intf_id)

            # Restart services with changed protocols
            for intf_id in old_ids & new_ids:
                old_intf = self._current_interfaces[intf_id]
                new_intf = new_config[intf_id]
                if new_intf.enabled:
                    if old_intf.protocol != new_intf.protocol:
                        self._start_service(intf_id)
                    elif not old_intf.enabled and new_intf.enabled:
                        self._start_service(intf_id)

            # Update state
            self._current_interfaces = new_config

    def _healthcheck(self) -> None:
        with self._lock:
            for intf_id, intf in self._current_interfaces.items():
                if not intf.enabled:
                    continue

                if intf_id in self._running_services:
                    if not self._is_service_active(intf_id):
                        self.logger.warning(f"service died, restarting: {intf_id}")
                        self._start_service(intf_id)

    # ────────────────────────────────────────────────────────────
    # App Lifecycle
    # ────────────────────────────────────────────────────────────

    def on_connect(self) -> None:
        # Load initial config
        self._current_interfaces = self._load_config()

        # Start enabled interfaces
        need_reload = False
        for intf_id, intf in self._current_interfaces.items():
            if intf.enabled:
                if self._create_service_unit(intf):
                    need_reload = True

        if need_reload:
            self._daemon_reload()

        for intf_id, intf in self._current_interfaces.items():
            if intf.enabled:
                self._start_service(intf_id)

        self.logger.info(f"started {len(self._running_services)} interfaces")

    def on_execute(self) -> None:
        # Check config changes
        if self._config_changed():
            self.logger.info("config changed, syncing interfaces")
            new_config = self._load_config()
            self._sync_interfaces(new_config)

    def on_manage(self) -> None:
        # Periodic healthcheck
        self._healthcheck()

    def on_disconnect(self) -> None:
        # Stop all managed services
        with self._lock:
            for intf_id in list(self._running_services):
                self._stop_service(intf_id)
            self.logger.info("stopped all interfaces")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    app = LauncherApp()
    app.start()
