# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from nodi_edge.app import AppConfig
from nodi_edge.intf_app import InterfaceApp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ModbusTcpClientApp
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ModbusTcpClientApp(InterfaceApp):

    def __init__(self,
                 app_id: str,
                 app_config: Optional[AppConfig] = None) -> None:
        super().__init__(app_id, protocol="mtc",
                         app_config=app_config or AppConfig(
                             execute_interval_s=0.1))

        # Protocol state
        self._agent = None
        self._modbus_groups: List[Dict[str, Any]] = []

    def on_intf_prepare(self) -> None:
        # Parse block properties into Modbus unit/fc groups
        self._parse_modbus_groups()

    def on_intf_configure(self) -> None:
        # Re-parse groups after config reload
        self._parse_modbus_groups()

    def on_intf_connect(self) -> None:
        # Create Modbus TCP connection
        host = self._conn_config.get("host", "127.0.0.1")
        port = self._conn_config.get("port", 502)
        timeout = self._conn_config.get("timeout", 3.0)
        self._logger.info(f"connecting to {host}:{port}")
        # TODO: Create actual ModbusTcpClient agent
        # self._agent = ModbusTcpClient(host, port, timeout=timeout)
        # self._agent.connect()

    def on_intf_execute(self) -> None:
        # TODO: Read/write Modbus registers per block schedule
        pass

    def on_intf_disconnect(self) -> None:
        if self._agent:
            # self._agent.close()
            self._agent = None


    # ────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────

    def _parse_modbus_groups(self) -> None:
        self._modbus_groups.clear()
        for block in self._block_configs:
            props = json.loads(block.get("properties", "{}"))
            self._modbus_groups.append({
                "block_id": block["block"],
                "direction": block["direction"],
                "unit_id": props.get("unit_id", 1),
                "func_code": props.get("func_code", 3),
            })
        self._logger.info(f"parsed {len(self._modbus_groups)} modbus groups")
