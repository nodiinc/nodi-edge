# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nodi_edge.db import EdgeDB


# upsert_app with conn_id
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_upsert_app_with_conn_id(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    db.upsert_app(
        app_id="mtc-01",
        category="interface",
        module="nodi_edge_intf.modbus_tcp_client",
        enabled=True,
        intf_id="intf-01",
        conn_id="mtc-01")

    row = db.select_app("mtc-01")
    assert row is not None
    assert row["app_id"] == "mtc-01"
    assert row["category"] == "interface"
    assert row["conn_id"] == "mtc-01"
    assert row["intf_id"] == "intf-01"
    assert row["enabled"] == 1


def test_upsert_app_conn_id_none_by_default(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    db.upsert_app(
        app_id="addon-01",
        category="addon",
        module="nodi_edge_addon.virtual_plc")

    row = db.select_app("addon-01")
    assert row is not None
    assert row["conn_id"] is None


def test_upsert_app_update_conn_id(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    # Insert initial
    db.upsert_app(
        app_id="mtc-01",
        category="interface",
        module="nodi_edge_intf.modbus_tcp_client",
        conn_id="conn-old")

    # Update with new conn_id
    db.upsert_app(
        app_id="mtc-01",
        category="interface",
        module="nodi_edge_intf.modbus_tcp_client",
        conn_id="conn-new")

    row = db.select_app("mtc-01")
    assert row["conn_id"] == "conn-new"
