# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nodi_edge.db import EdgeDB


# select_conns
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_conns_returns_all_ordered(mem_db):
    mem_db.execute(
        "INSERT INTO conns (conn, protocol) VALUES (?, ?)", ("conn-b", "mtc"))
    mem_db.execute(
        "INSERT INTO conns (conn, protocol) VALUES (?, ?)", ("conn-a", "ouc"))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_conns()
    assert len(rows) == 2
    assert rows[0]["conn"] == "conn-a"
    assert rows[1]["conn"] == "conn-b"


def test_select_conns_empty(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_conns()
    assert rows == []


# select_conn
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_conn_found(mem_db):
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port) VALUES (?, ?, ?, ?)",
        ("conn-01", "mtc", "192.168.1.10", 502))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    row = db.select_conn("conn-01")
    assert row is not None
    assert row["conn"] == "conn-01"
    assert row["protocol"] == "mtc"
    assert row["host"] == "192.168.1.10"
    assert row["port"] == 502


def test_select_conn_not_found(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    row = db.select_conn("unknown")
    assert row is None


# select_conns_enabled
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_conns_enabled(mem_db):
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use) VALUES (?, ?, ?)",
        ("conn-on", "mtc", 1))
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use) VALUES (?, ?, ?)",
        ("conn-off", "mtc", 0))
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use) VALUES (?, ?, ?)",
        ("conn-on2", "ouc", 1))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_conns_enabled()
    assert len(rows) == 2
    assert rows[0]["conn"] == "conn-on"
    assert rows[1]["conn"] == "conn-on2"


# select_blocks_by_conn
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_blocks_by_conn(mem_db):
    mem_db.execute(
        "INSERT INTO conns (conn, protocol) VALUES (?, ?)", ("conn-01", "mtc"))
    mem_db.execute(
        "INSERT INTO conns (conn, protocol) VALUES (?, ?)", ("conn-02", "ouc"))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction) VALUES (?, ?, ?)",
        ("blk-b", "conn-01", "ro"))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction) VALUES (?, ?, ?)",
        ("blk-a", "conn-01", "rw"))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction) VALUES (?, ?, ?)",
        ("blk-c", "conn-02", "ro"))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_blocks_by_conn("conn-01")
    assert len(rows) == 2
    assert rows[0]["block"] == "blk-a"
    assert rows[1]["block"] == "blk-b"

    # Verify other conn's blocks are not included
    rows2 = db.select_blocks_by_conn("conn-02")
    assert len(rows2) == 1
    assert rows2[0]["block"] == "blk-c"


def test_select_blocks_by_conn_empty(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_blocks_by_conn("no-such-conn")
    assert rows == []


# select_blocks_tags_by_block
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_blocks_tags_by_block(mem_db):
    mem_db.execute(
        "INSERT INTO conns (conn, protocol) VALUES (?, ?)", ("conn-01", "mtc"))
    mem_db.execute(
        "INSERT INTO blocks (block, conn) VALUES (?, ?)", ("blk-01", "conn-01"))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field) VALUES (?, ?, ?)",
        ("blk-01", "tag-z", "v"))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field) VALUES (?, ?, ?)",
        ("blk-01", "tag-a", "v"))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field) VALUES (?, ?, ?)",
        ("blk-01", "tag-m", "q"))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_blocks_tags_by_block("blk-01")
    assert len(rows) == 3

    # Verify ordered by tag
    assert rows[0]["tag"] == "tag-a"
    assert rows[1]["tag"] == "tag-m"
    assert rows[2]["tag"] == "tag-z"


def test_select_blocks_tags_by_block_empty(mem_db):
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_blocks_tags_by_block("no-such-block")
    assert rows == []
