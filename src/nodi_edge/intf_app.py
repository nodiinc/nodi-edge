# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional

from nodi_edge.app import App, AppConfig
from nodi_edge.db import EdgeDB, PROTOCOL_MODULES


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CONN_INFO_KEYS = ("host", "port", "timeout", "retry")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# InterfaceApp
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InterfaceApp(App):

    def __init__(self,
                 app_id: str,
                 protocol: str,
                 *,
                 app_config: Optional[AppConfig] = None,
                 **kwargs) -> None:
        super().__init__(app_id, app_config=app_config, **kwargs)

        # Validate --conn-id is provided
        if not self._cli_args.conn_id:
            self._logger.error("--conn-id is required")
            sys.exit(1)

        self._conn_id: str = self._cli_args.conn_id
        self._protocol: str = protocol

        # Config state (loaded from DB)
        self._db: Optional[EdgeDB] = None
        self._conn_config: Optional[Dict[str, Any]] = None
        self._block_configs: List[Dict[str, Any]] = []

        # System tag for config reload
        self._config_reload_tag = f"/system/{self._conn_id}/config_reload"


    # ────────────────────────────────────────────────────────────
    # Properties
    # ────────────────────────────────────────────────────────────

    @property
    def conn_id(self) -> str:
        return self._conn_id

    @property
    def conn_config(self) -> Optional[Dict[str, Any]]:
        return self._conn_config

    @property
    def block_configs(self) -> List[Dict[str, Any]]:
        return self._block_configs


    # ────────────────────────────────────────────────────────────
    # Config Loading
    # ────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """Load connection and block configs from DB."""
        row = self._db.select_conn(self._conn_id)
        if not row:
            raise RuntimeError(f"connection not found: {self._conn_id}")
        self._conn_config = dict(row)

        self._block_configs = [dict(r) for r in
                               self._db.select_blocks_by_conn(self._conn_id)]
        self._logger.info(
            f"loaded config: conn={self._conn_id}, "
            f"blocks={len(self._block_configs)}")

    @staticmethod
    def _is_conn_info_changed(prev: Dict[str, Any],
                              curr: Dict[str, Any]) -> bool:
        """Check if connection-level info (host/port/timeout/retry) changed."""
        for key in _CONN_INFO_KEYS:
            if prev.get(key) != curr.get(key):
                return True
        return False


    # ────────────────────────────────────────────────────────────
    # Config Reload Handler
    # ────────────────────────────────────────────────────────────

    def _on_config_reload_tag(self, tag_id: str, tag_data) -> None:
        """TagBus callback when config_reload system tag changes."""
        self._logger.info(f"config reload signal received: {tag_id}")

        # Save previous conn config for change detection
        prev_conn = dict(self._conn_config) if self._conn_config else {}

        # Reload from DB
        self._load_config()

        # Detect change type
        if self._is_conn_info_changed(prev_conn, self._conn_config):
            # Connection info changed -> need full restart
            self._logger.warning(
                "connection info changed, restarting via sys.exit()")
            sys.exit(0)  # systemd Restart=always will restart the process

        # Block-only change -> hot reload via reconfigure
        self.request_reconfigure()


    # ────────────────────────────────────────────────────────────
    # App Lifecycle
    # ────────────────────────────────────────────────────────────

    def on_prepare(self) -> None:
        # Open database
        self._db = EdgeDB()
        self._db.open()

        # Load initial config
        self._load_config()

        # Call protocol's prepare
        self.on_intf_prepare()

    def on_configure(self) -> None:
        # Reload config from DB (for reconfigure path)
        if self._conn_config is not None:
            self._load_config()

        # Call protocol's configure
        self.on_intf_configure()

    def on_connect(self) -> None:
        # Subscribe to config_reload system tag
        if self.databus and self.databus.is_running:
            self.databus.sync_tags([self._config_reload_tag])
            self.databus.set_on_tags_change(
                [self._config_reload_tag], self._on_config_reload_tag)
            self.databus.commit()

        # Call protocol's connect
        self.on_intf_connect()

    def on_execute(self) -> None:
        self.on_intf_execute()

    def on_recover(self) -> None:
        self.on_intf_recover()

    def on_disconnect(self) -> None:
        self.on_intf_disconnect()

        # Close database
        if self._db:
            self._db.close()
            self._db = None


    # ────────────────────────────────────────────────────────────
    # Protocol Override Points
    # ────────────────────────────────────────────────────────────

    def on_intf_prepare(self) -> None:
        pass

    def on_intf_configure(self) -> None:
        pass

    def on_intf_connect(self) -> None:
        pass

    def on_intf_execute(self) -> None:
        pass

    def on_intf_recover(self) -> None:
        pass

    def on_intf_disconnect(self) -> None:
        pass
