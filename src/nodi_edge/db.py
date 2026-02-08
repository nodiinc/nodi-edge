# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from nodi_edge.config import DB_PATH


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AppCategory = str   # "interface", "addon"
IntfId = str
AppId = str

# Protocol code → module mapping
PROTOCOL_MODULES: Dict[str, str] = {
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

# Addon app modules
ADDON_MODULES: Dict[str, str] = {
    "vplc": "nodi_edge_addon.virtual_plc",
    "snf": "nodi_edge_addon.store_forward",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EdgeDB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EdgeDB:

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if not self._conn:
            raise RuntimeError("database not opened")
        return self._conn


    # App Registry - CRUD
    # ──────────────────────────────────────────────────────────────────────

    def select_app_registry(self,
                            category: Optional[str] = None) -> List[sqlite3.Row]:
        if category:
            return self.conn.execute(
                "SELECT * FROM app_registry WHERE category = ? ORDER BY app_id",
                (category,)).fetchall()
        return self.conn.execute(
            "SELECT * FROM app_registry ORDER BY app_id").fetchall()

    def select_app(self, app_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM app_registry WHERE app_id = ?",
            (app_id,)).fetchone()

    def upsert_app(self,
                   app_id: str,
                   category: str,
                   module: str,
                   enabled: bool = False,
                   config: Optional[Dict[str, Any]] = None,
                   intf_id: Optional[str] = None,
                   license_token: Optional[str] = None,
                   license_expires_at: Optional[int] = None) -> None:
        now = int(time.time())
        config_json = json.dumps(config) if config else "{}"
        self.conn.execute(
            "INSERT INTO app_registry "
            "(app_id, category, module, enabled, config, intf_id, "
            " license_token, license_expires_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(app_id) DO UPDATE SET "
            "  category=excluded.category, module=excluded.module, "
            "  enabled=excluded.enabled, config=excluded.config, "
            "  intf_id=excluded.intf_id, license_token=excluded.license_token, "
            "  license_expires_at=excluded.license_expires_at, "
            "  updated_at=excluded.updated_at",
            (app_id, category, module, int(enabled), config_json, intf_id,
             license_token, license_expires_at, now))
        self.conn.commit()

    def update_app_enabled(self, app_id: str, enabled: bool) -> None:
        now = int(time.time())
        self.conn.execute(
            "UPDATE app_registry SET enabled = ?, updated_at = ? WHERE app_id = ?",
            (int(enabled), now, app_id))
        self.conn.commit()

    def update_app_license(self,
                           app_id: str,
                           license_token: Optional[str],
                           license_expires_at: Optional[int],
                           enabled: bool) -> None:
        now = int(time.time())
        self.conn.execute(
            "UPDATE app_registry SET "
            "  license_token = ?, license_expires_at = ?, "
            "  enabled = ?, updated_at = ? "
            "WHERE app_id = ?",
            (license_token, license_expires_at, int(enabled), now, app_id))
        self.conn.commit()

    def delete_app(self, app_id: str) -> None:
        self.conn.execute(
            "DELETE FROM app_registry WHERE app_id = ?", (app_id,))
        self.conn.commit()


    # Interface - Read + Change Detection
    # ──────────────────────────────────────────────────────────────────────

    def select_interfaces(self) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intf ORDER BY intf").fetchall()

    def select_interface(self, intf_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intf WHERE intf = ?", (intf_id,)).fetchone()

    def select_interfaces_updated_after(self, ts: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM intf WHERE updated_at > ? ORDER BY intf",
            (ts,)).fetchall()

    def select_max_intf_updated_at(self) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(updated_at), 0) FROM intf").fetchone()
        return row[0]

    def select_intf_ids(self) -> List[str]:
        rows = self.conn.execute("SELECT intf FROM intf ORDER BY intf").fetchall()
        return [r[0] for r in rows]


    # prot_prop - Mapping Lookup
    # ──────────────────────────────────────────────────────────────────────

    def select_prot_prop_mapping(self,
                                 prot_code: str,
                                 layer: str) -> Dict[int, Tuple[str, str]]:
        rows = self.conn.execute(
            "SELECT pos, key, type FROM prot_prop "
            "WHERE prot = ? AND layer = ? ORDER BY pos",
            (prot_code, layer)).fetchall()
        return {r["pos"]: (r["key"], r["type"]) for r in rows}

    def select_prot_prop_labels(self,
                                prot_code: str,
                                layer: str) -> Dict[int, Tuple[str, str]]:
        rows = self.conn.execute(
            "SELECT pos, key, label FROM prot_prop "
            "WHERE prot = ? AND layer = ? ORDER BY pos",
            (prot_code, layer)).fetchall()
        return {r["pos"]: (r["key"], r["label"]) for r in rows}
