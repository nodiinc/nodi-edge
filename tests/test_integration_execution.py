# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nodi_edge_apps.supervisor.core import _INTERFACE_SERVICE_TEMPLATE, _VENV_PYTHON

from nodi_edge.db import EdgeDB, PROTOCOL_MODULES
from nodi_edge.interface_app import InterfaceApp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _seed_conn(mem_db, conn_id="mtc-01", protocol="mtc",
               host="192.168.1.10", port=502):
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conn_id, protocol, host, port, now))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction, trigger, schedule, "
        "properties, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"{conn_id}-read", conn_id, "ro", "cyc", 0.1,
         json.dumps({"unit_id": 1, "func_code": 3}), now))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field, properties) "
        "VALUES (?, ?, ?, ?)",
        (f"{conn_id}-read", f"{conn_id}/temperature", "v",
         json.dumps({"address": 100, "data_type": "int16"})))
    mem_db.commit()


def _make_edge_db(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db
    return db


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test: Full Flow — DB to Service File
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_full_flow_db_to_service_file(mem_db):
    _seed_conn(mem_db, conn_id="mtc-01", protocol="mtc")
    db = _make_edge_db(mem_db)

    # Read conn from DB
    row = db.select_conn("mtc-01")
    assert row is not None

    # Map protocol to module
    protocol = row["protocol"]
    module = PROTOCOL_MODULES[protocol]
    assert module == "nodi_edge_interface.modbus_tcp_client"

    # Format service template
    content = _INTERFACE_SERVICE_TEMPLATE.format(
        app_id="mtc-01",
        python=_VENV_PYTHON,
        module=module,
        conn_id="mtc-01")

    # Verify key fields in generated service file
    assert "--conn-id=mtc-01" in content
    assert f"-m {module}" in content
    assert _VENV_PYTHON in content
    assert "Restart=always" in content
    assert "Description=Nodi Edge Interface: mtc-01" in content


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test: Full Flow — Config Loading
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_full_flow_config_loading(mem_db):
    _seed_conn(mem_db, conn_id="mtc-01", protocol="mtc",
               host="192.168.1.10", port=502)
    db = _make_edge_db(mem_db)

    # Read conn config
    conn_row = db.select_conn("mtc-01")
    assert conn_row is not None
    assert conn_row["host"] == "192.168.1.10"
    assert conn_row["port"] == 502
    assert conn_row["protocol"] == "mtc"

    # Read blocks for this conn
    blocks = db.select_blocks_by_conn("mtc-01")
    assert len(blocks) == 1
    block = blocks[0]
    assert block["block"] == "mtc-01-read"
    assert block["direction"] == "ro"
    assert block["trigger"] == "cyc"
    assert block["schedule"] == 0.1

    # Verify block properties JSON parses correctly
    props = json.loads(block["properties"])
    assert props["unit_id"] == 1
    assert props["func_code"] == 3

    # Read tags for this block
    tags = db.select_blocks_tags_by_block("mtc-01-read")
    assert len(tags) == 1
    tag = tags[0]
    assert tag["tag"] == "mtc-01/temperature"
    assert tag["field"] == "v"

    # Verify tag properties JSON parses correctly
    tag_props = json.loads(tag["properties"])
    assert tag_props["address"] == 100
    assert tag_props["data_type"] == "int16"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test: Connection Info Change Detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_conn_info_change_detection():
    base = {"host": "10.0.0.1", "port": 502, "timeout": 3.0, "retry": 3}

    # Same config -> False
    assert InterfaceApp._is_conn_info_changed(base, dict(base)) is False

    # Host change -> True
    changed = dict(base, host="10.0.0.2")
    assert InterfaceApp._is_conn_info_changed(base, changed) is True

    # Port change -> True
    changed = dict(base, port=503)
    assert InterfaceApp._is_conn_info_changed(base, changed) is True

    # Timeout change -> True
    changed = dict(base, timeout=5.0)
    assert InterfaceApp._is_conn_info_changed(base, changed) is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test: Multiple Connections / Multiple Protocols
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_multiple_conns_multiple_protocols(mem_db):
    now = int(time.time())
    conns = [
        ("mtc-01", "mtc", "192.168.1.10", 502),
        ("mtc-02", "mtc", "192.168.1.11", 502),
        ("ouc-01", "ouc", "192.168.2.10", 4840),
        ("mqc-01", "mqc", "broker.local", 1883),
    ]
    for conn_id, protocol, host, port in conns:
        mem_db.execute(
            "INSERT INTO conns (conn, protocol, host, port, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conn_id, protocol, host, port, now))
    mem_db.commit()

    db = _make_edge_db(mem_db)

    # Verify all 4 connections are readable
    rows = db.select_conns()
    assert len(rows) == 4

    # Verify each conn reads correctly and its protocol maps to PROTOCOL_MODULES
    for conn_id, protocol, host, port in conns:
        row = db.select_conn(conn_id)
        assert row is not None
        assert row["host"] == host
        assert row["port"] == port
        assert row["protocol"] == protocol
        assert protocol in PROTOCOL_MODULES


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test: Disabled Connections Excluded
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_disabled_conns_excluded(mem_db):
    now = int(time.time())

    # Insert enabled conn
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("conn-on", "mtc", 1, now))

    # Insert disabled conn
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("conn-off", "mtc", 0, now))
    mem_db.commit()

    db = _make_edge_db(mem_db)

    # select_conns_enabled returns only the enabled one
    rows = db.select_conns_enabled()
    assert len(rows) == 1
    assert rows[0]["conn"] == "conn-on"

    # select_conns returns both
    all_rows = db.select_conns()
    assert len(all_rows) == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test: App Registry Roundtrip
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_app_registry_roundtrip(mem_db):
    db = _make_edge_db(mem_db)

    # Upsert an interface app with conn_id
    db.upsert_app(
        app_id="mtc-01",
        category="interface",
        module="nodi_edge_interface.modbus_tcp_client",
        enabled=True,
        conn_id="mtc-01",
        config={"poll_rate": 0.1})

    # Read back and verify all fields
    row = db.select_app("mtc-01")
    assert row is not None
    assert row["app_id"] == "mtc-01"
    assert row["category"] == "interface"
    assert row["module"] == "nodi_edge_interface.modbus_tcp_client"
    assert row["enabled"] == 1
    assert row["conn_id"] == "mtc-01"

    # Verify config JSON roundtrip
    config = json.loads(row["config"])
    assert config["poll_rate"] == 0.1

    # Verify updated_at is set
    assert row["updated_at"] > 0
