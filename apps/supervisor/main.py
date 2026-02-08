# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from nodi_edge.app import App, AppConfig
from nodi_edge.config import DB_PATH, LICENSE_DIR, CLOUD_PUBKEY_FILE
from nodi_edge.db import EdgeDB, PROTOCOL_MODULES, ADDON_MODULES


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_APP_ID = "supervisor"
_SYSTEMD_DIR = Path("/etc/systemd/system")
_VENV_PYTHON = "/root/venv/bin/python3"

# Service naming
_SVC_PREFIX_INTF = "ne-intf"
_SVC_PREFIX_ADDON = "ne-addon"

# TagBus command/event tags
_TAG_CMD_PREFIX = f"{_APP_ID}/_cmd"
_TAG_EVENT_PREFIX = f"{_APP_ID}/_event"
_TAG_META_PREFIX = f"{_APP_ID}/_meta"

# Healthcheck
_MAX_RESTART_COUNT = 5
_RESTART_COUNT_RESET_S = 300

# systemd unit templates
_INTF_SERVICE_TEMPLATE = """\
[Unit]
Description=Nodi Edge Interface: {app_id}
After=network.target ne-supervisor.service
Requires=ne-supervisor.service

[Service]
Type=simple
User=root
Group=root
ExecStart={python} -m {module} {intf_id}
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=300
StartLimitBurst=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

_ADDON_SERVICE_TEMPLATE = """\
[Unit]
Description=Nodi Edge Addon: {app_id}
After=network.target ne-supervisor.service
Requires=ne-supervisor.service

[Service]
Type=simple
User=root
Group=root
ExecStart={python} -m {module}
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=300
StartLimitBurst=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ServiceState:
    app_id: str
    category: str
    module: str
    enabled: bool
    active: bool = False
    restart_count: int = 0
    last_restart_ts: float = 0.0


@dataclass
class SupervisorConfig:
    db_path: str = DB_PATH
    license_dir: str = LICENSE_DIR
    pubkey_file: str = CLOUD_PUBKEY_FILE
    intf_poll_interval_s: float = 10.0
    license_check_interval_s: float = 60.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Supervisor App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SupervisorApp(App):

    def __init__(self,
                 supervisor_config: Optional[SupervisorConfig] = None,
                 app_config: Optional[AppConfig] = None):
        super().__init__(_APP_ID,
                         app_config=app_config or AppConfig(
                             execute_interval_s=5.0,
                             manage_interval_s=10.0))

        self._sv_conf = supervisor_config or SupervisorConfig()

        # Database
        self._db: Optional[EdgeDB] = None

        # License manager (lazy import to avoid hard dependency on PyJWT)
        self._license_mgr = None

        # Service state (in-memory runtime tracking)
        self._services: Dict[str, ServiceState] = {}
        self._lock = threading.Lock()

        # Change detection
        self._last_intf_updated_at: int = 0
        self._last_intf_poll_ts: float = 0.0
        self._last_license_check_ts: float = 0.0

        # Cycle counter for TagBus command polling
        self._cmd_poll_count: int = 0


    # ────────────────────────────────────────────────────────────
    # App Lifecycle
    # ────────────────────────────────────────────────────────────

    def on_prepare(self) -> None:
        # Open database
        self._db = EdgeDB(self._sv_conf.db_path)
        self._db.open()

        # Initialize license manager
        try:
            from nodi_edge.license import LicenseManager
            self._license_mgr = LicenseManager(
                pubkey_file=self._sv_conf.pubkey_file,
                cache_dir=self._sv_conf.license_dir)
        except Exception as exc:
            self.logger.warning(f"license manager unavailable: {exc}")

    def on_configure(self) -> None:
        # Register addon apps that are known but not yet in registry
        self._ensure_addon_registry()

    def on_connect(self) -> None:
        # Subscribe to command tags via TagBus
        self.databus.sync_tags([f"{_TAG_CMD_PREFIX}/**"])
        self.databus.set_on_tags_change(
            [f"{_TAG_CMD_PREFIX}/**"], self._on_command_tag)
        self.databus.commit()

        # Load initial state from app_registry
        self._load_registry()

        # Start all enabled services
        self._start_enabled_services()

        self.logger.info(f"started {self._count_active()} services")

    def on_execute(self) -> None:
        now = time.monotonic()

        # Poll intf table for changes
        if now - self._last_intf_poll_ts >= self._sv_conf.intf_poll_interval_s:
            self._last_intf_poll_ts = now
            self._sync_interfaces()

        # Check license expiry
        if now - self._last_license_check_ts >= self._sv_conf.license_check_interval_s:
            self._last_license_check_ts = now
            self._check_license_expiry()

    def on_manage(self) -> None:
        # Healthcheck
        self._healthcheck()

        # Publish status to TagBus
        self._publish_status()

    def on_recover(self) -> None:
        pass

    def on_disconnect(self) -> None:
        # Stop all managed services
        self._stop_all_services()

        # Close database
        if self._db:
            self._db.close()
            self._db = None


    # ────────────────────────────────────────────────────────────
    # Service Naming
    # ────────────────────────────────────────────────────────────

    def _get_service_name(self, app_id: str, category: str) -> str:
        if category == "interface":
            return f"{_SVC_PREFIX_INTF}-{app_id}"
        return f"{_SVC_PREFIX_ADDON}-{app_id}"

    def _get_service_path(self, app_id: str, category: str) -> Path:
        return _SYSTEMD_DIR / f"{self._get_service_name(app_id, category)}.service"


    # ────────────────────────────────────────────────────────────
    # Systemd Operations
    # ────────────────────────────────────────────────────────────

    def _systemctl(self, action: str, service: str) -> bool:
        cmd = ["sudo", "systemctl", action, service]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                self.logger.warning(
                    f"systemctl {action} {service}: {result.stderr.strip()}")
                return False
            return True
        except Exception as exc:
            self.logger.error(f"systemctl {action} {service} failed: {exc}")
            return False

    def _daemon_reload(self) -> bool:
        return self._systemctl("daemon-reload", "")

    def _is_service_active(self, app_id: str, category: str) -> bool:
        svc = self._get_service_name(app_id, category)
        cmd = ["sudo", "systemctl", "is-active", "--quiet", svc]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False

    def _create_service_unit(self, state: ServiceState,
                             intf_id: Optional[str] = None) -> bool:
        path = self._get_service_path(state.app_id, state.category)

        if state.category == "interface":
            content = _INTF_SERVICE_TEMPLATE.format(
                app_id=state.app_id,
                python=_VENV_PYTHON,
                module=state.module,
                intf_id=intf_id or state.app_id)
        else:
            content = _ADDON_SERVICE_TEMPLATE.format(
                app_id=state.app_id,
                python=_VENV_PYTHON,
                module=state.module)
        try:
            path.write_text(content)
            return True
        except Exception as exc:
            self.logger.error(f"create unit failed [{state.app_id}]: {exc}")
            return False

    def _remove_service_unit(self, app_id: str, category: str) -> bool:
        path = self._get_service_path(app_id, category)
        if path.exists():
            try:
                path.unlink()
                return True
            except Exception as exc:
                self.logger.error(f"remove unit failed [{app_id}]: {exc}")
                return False
        return True

    def _start_service(self, app_id: str, category: str) -> bool:
        svc = self._get_service_name(app_id, category)
        if self._systemctl("start", svc):
            self.logger.info(f"started: {svc}")
            return True
        return False

    def _stop_service(self, app_id: str, category: str) -> bool:
        svc = self._get_service_name(app_id, category)
        if self._systemctl("stop", svc):
            self.logger.info(f"stopped: {svc}")
            return True
        return False


    # ────────────────────────────────────────────────────────────
    # Registry & Startup
    # ────────────────────────────────────────────────────────────

    def _ensure_addon_registry(self) -> None:
        for addon_id, module in ADDON_MODULES.items():
            existing = self._db.select_app(addon_id)
            if not existing:
                self._db.upsert_app(addon_id, "addon", module, enabled=False)
                self.logger.info(f"registered addon: {addon_id}")

    def _load_registry(self) -> None:
        with self._lock:
            self._services.clear()
            rows = self._db.select_app_registry()
            for row in rows:
                self._services[row["app_id"]] = ServiceState(
                    app_id=row["app_id"],
                    category=row["category"],
                    module=row["module"],
                    enabled=bool(row["enabled"]))

    def _start_enabled_services(self) -> None:
        need_reload = False
        with self._lock:
            for state in self._services.values():
                if not state.enabled:
                    continue

                # Find intf_id for interface apps
                intf_id = None
                if state.category == "interface":
                    app_row = self._db.select_app(state.app_id)
                    if app_row:
                        intf_id = app_row["intf_id"]

                if self._create_service_unit(state, intf_id):
                    need_reload = True

        if need_reload:
            self._daemon_reload()

        with self._lock:
            for state in self._services.values():
                if state.enabled:
                    if self._start_service(state.app_id, state.category):
                        state.active = True

    def _stop_all_services(self) -> None:
        with self._lock:
            for state in self._services.values():
                if state.active:
                    self._stop_service(state.app_id, state.category)
                    state.active = False
            self.logger.info("stopped all managed services")

    def _count_active(self) -> int:
        with self._lock:
            return sum(1 for s in self._services.values() if s.active)


    # ────────────────────────────────────────────────────────────
    # Phase 2: Interface Sync
    # ────────────────────────────────────────────────────────────

    def _sync_interfaces(self) -> None:
        # Check if intf table has changed
        current_max = self._db.select_max_intf_updated_at()
        if current_max <= self._last_intf_updated_at:
            return
        self._last_intf_updated_at = current_max

        # Get current intf rows
        intf_rows = self._db.select_interfaces()
        db_intf_ids = {row["intf"]: row for row in intf_rows}

        # Get current registry interface entries
        registry_rows = self._db.select_app_registry("interface")
        registry_intf_ids = {}
        for row in registry_rows:
            if row["intf_id"]:
                registry_intf_ids[row["intf_id"]] = row["app_id"]

        need_reload = False

        # Detect removed interfaces
        removed = set(registry_intf_ids.keys()) - set(db_intf_ids.keys())
        for intf_id in removed:
            app_id = registry_intf_ids[intf_id]
            self._deactivate_service(app_id, "interface")
            self._remove_service_unit(app_id, "interface")
            self._db.delete_app(app_id)
            with self._lock:
                self._services.pop(app_id, None)
            self.logger.info(f"removed interface service: {app_id} (intf={intf_id})")
            need_reload = True

        # Detect added interfaces
        added = set(db_intf_ids.keys()) - set(registry_intf_ids.keys())
        for intf_id in added:
            row = db_intf_ids[intf_id]
            prot = row["prot"]
            module = PROTOCOL_MODULES.get(prot)
            if not module:
                self.logger.warning(f"unknown protocol: {prot} (intf={intf_id})")
                continue

            app_id = intf_id
            self._db.upsert_app(app_id, "interface", module,
                                enabled=True, intf_id=intf_id)
            state = ServiceState(app_id=app_id, category="interface",
                                 module=module, enabled=True)
            with self._lock:
                self._services[app_id] = state

            if self._create_service_unit(state, intf_id):
                need_reload = True
            self.logger.info(f"added interface service: {app_id} (prot={prot})")

        # Detect changed interfaces (protocol change)
        existing = set(db_intf_ids.keys()) & set(registry_intf_ids.keys())
        for intf_id in existing:
            app_id = registry_intf_ids[intf_id]
            row = db_intf_ids[intf_id]
            prot = row["prot"]
            new_module = PROTOCOL_MODULES.get(prot, "")

            with self._lock:
                state = self._services.get(app_id)
            if state and state.module != new_module and new_module:
                # Protocol changed — restart with new module
                self._deactivate_service(app_id, "interface")
                state.module = new_module
                self._db.upsert_app(app_id, "interface", new_module,
                                    enabled=True, intf_id=intf_id)
                if self._create_service_unit(state, intf_id):
                    need_reload = True
                self.logger.info(
                    f"updated interface service: {app_id} (new prot={prot})")

        if need_reload:
            self._daemon_reload()

        # Start newly added services
        for intf_id in added:
            app_id = intf_id
            with self._lock:
                state = self._services.get(app_id)
            if state:
                if self._start_service(app_id, "interface"):
                    state.active = True

        # Restart changed services
        for intf_id in existing:
            app_id = registry_intf_ids[intf_id]
            with self._lock:
                state = self._services.get(app_id)
            if state and state.enabled and not state.active:
                if self._start_service(app_id, "interface"):
                    state.active = True


    # ────────────────────────────────────────────────────────────
    # Phase 3: Addon Activation / Deactivation
    # ────────────────────────────────────────────────────────────

    def activate_addon(self, app_id: str, token: str) -> Dict[str, Any]:
        # Validate license token
        if not self._license_mgr:
            return {"ok": False, "error": "license manager unavailable"}

        claims = self._license_mgr.validate_token(token)
        if not claims:
            return {"ok": False, "error": "invalid or expired token"}

        # Check token matches app_id
        token_app = claims.get("app_id", "")
        if token_app != app_id:
            return {"ok": False, "error": f"token app mismatch: {token_app}"}

        expires_at = claims.get("exp", 0)
        module = ADDON_MODULES.get(app_id)
        if not module:
            return {"ok": False, "error": f"unknown addon: {app_id}"}

        # Cache token to disk
        self._license_mgr.cache_token(app_id, token)

        # Update DB
        self._db.update_app_license(app_id, token, expires_at, enabled=True)

        # Create and start service
        state = ServiceState(app_id=app_id, category="addon",
                             module=module, enabled=True)
        with self._lock:
            self._services[app_id] = state

        if self._create_service_unit(state):
            self._daemon_reload()
        if self._start_service(app_id, "addon"):
            state.active = True

        self.logger.info(f"addon activated: {app_id}")

        # Publish event
        self._publish_event("addon_activated", app_id)
        return {"ok": True, "app_id": app_id, "expires_at": expires_at}

    def deactivate_addon(self, app_id: str) -> Dict[str, Any]:
        self._deactivate_service(app_id, "addon")
        self._remove_service_unit(app_id, "addon")
        self._daemon_reload()

        # Update DB
        self._db.update_app_license(app_id, None, None, enabled=False)

        # Remove cached token
        if self._license_mgr:
            self._license_mgr.remove_cached_token(app_id)

        with self._lock:
            state = self._services.get(app_id)
            if state:
                state.enabled = False
                state.active = False

        self.logger.info(f"addon deactivated: {app_id}")
        self._publish_event("addon_deactivated", app_id)
        return {"ok": True, "app_id": app_id}

    def _check_license_expiry(self) -> None:
        if not self._license_mgr:
            return

        now = int(time.time())
        addon_rows = self._db.select_app_registry("addon")
        for row in addon_rows:
            if not row["enabled"]:
                continue
            expires_at = row["license_expires_at"]
            if expires_at and expires_at <= now:
                self.logger.warning(
                    f"license expired for addon: {row['app_id']}")
                self.deactivate_addon(row["app_id"])

    def _restore_addon_licenses(self) -> None:
        if not self._license_mgr:
            return

        cached_tokens = self._license_mgr.load_cached_tokens()
        for app_id, token in cached_tokens.items():
            existing = self._db.select_app(app_id)
            if existing and not existing["enabled"]:
                # Validate cached token
                claims = self._license_mgr.validate_token(token)
                if claims:
                    self.activate_addon(app_id, token)
                else:
                    self._license_mgr.remove_cached_token(app_id)


    # ────────────────────────────────────────────────────────────
    # Service Helpers
    # ────────────────────────────────────────────────────────────

    def _deactivate_service(self, app_id: str, category: str) -> None:
        with self._lock:
            state = self._services.get(app_id)
        if state and state.active:
            self._stop_service(app_id, category)
            state.active = False

    def _healthcheck(self) -> None:
        now = time.monotonic()
        with self._lock:
            for state in self._services.values():
                if not state.enabled or not state.active:
                    continue

                if not self._is_service_active(state.app_id, state.category):
                    # Reset counter if enough time has passed
                    if now - state.last_restart_ts > _RESTART_COUNT_RESET_S:
                        state.restart_count = 0

                    if state.restart_count >= _MAX_RESTART_COUNT:
                        self.logger.error(
                            f"service exceeded max restarts: {state.app_id}")
                        state.active = False
                        continue

                    self.logger.warning(
                        f"service died, restarting: {state.app_id} "
                        f"({state.restart_count + 1}/{_MAX_RESTART_COUNT})")
                    if self._start_service(state.app_id, state.category):
                        state.restart_count += 1
                        state.last_restart_ts = now
                    else:
                        state.active = False


    # ────────────────────────────────────────────────────────────
    # TagBus Commands
    # ────────────────────────────────────────────────────────────

    def _on_command_tag(self, tag_id: str, tag_data) -> None:
        # Parse command from tag_id: supervisor/_cmd/<command>
        parts = tag_id.split("/")
        if len(parts) < 3:
            return

        command = parts[2]
        try:
            payload = json.loads(tag_data.v) if isinstance(tag_data.v, str) else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        if command == "activate":
            app_id = payload.get("app_id", "")
            token = payload.get("token", "")
            if app_id and token:
                result = self.activate_addon(app_id, token)
                self._publish_event("activate_result", json.dumps(result))

        elif command == "deactivate":
            app_id = payload.get("app_id", "")
            if app_id:
                result = self.deactivate_addon(app_id)
                self._publish_event("deactivate_result", json.dumps(result))

        elif command == "restart":
            app_id = payload.get("app_id", "")
            self._restart_managed_service(app_id)

        elif command == "list":
            self._publish_event("service_list", json.dumps(self._get_service_list()))

    def _restart_managed_service(self, app_id: str) -> None:
        with self._lock:
            state = self._services.get(app_id)
        if not state:
            return
        self._stop_service(app_id, state.category)
        if self._start_service(app_id, state.category):
            state.active = True
        self.logger.info(f"restarted: {app_id}")


    # ────────────────────────────────────────────────────────────
    # Status & Events
    # ────────────────────────────────────────────────────────────

    def _get_service_list(self) -> Dict[str, Any]:
        result = {}
        with self._lock:
            for app_id, state in self._services.items():
                result[app_id] = {
                    "category": state.category,
                    "enabled": state.enabled,
                    "active": state.active,
                    "restart_count": state.restart_count,
                }
        return result

    def _publish_status(self) -> None:
        if not self.databus:
            return

        svc_list = self._get_service_list()
        active_count = sum(1 for s in svc_list.values() if s["active"])

        self.databus.set_tags({
            f"{_TAG_META_PREFIX}/state":
                self.current_state.name if self.current_state else "None",
            f"{_TAG_META_PREFIX}/service_count": len(svc_list),
            f"{_TAG_META_PREFIX}/active_count": active_count,
            f"{_TAG_META_PREFIX}/services": json.dumps(svc_list),
            f"{_TAG_META_PREFIX}/exception_count": self.stats.exception_count,
        })
        self.databus.commit()

    def _publish_event(self, event: str, data: Any = None) -> None:
        if not self.databus:
            return
        self.databus.set_tags({f"{_TAG_EVENT_PREFIX}/{event}": data})
        self.databus.commit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    app = SupervisorApp()
    app.start()
