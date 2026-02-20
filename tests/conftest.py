# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3

import pytest


# Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS app_registry (
    app_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    module TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    config TEXT DEFAULT '{}',
    interface_id TEXT,
    conn_id TEXT,
    license_token TEXT,
    license_expires_at INTEGER,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conns (
    conn TEXT PRIMARY KEY,
    comment TEXT DEFAULT '',
    use INTEGER NOT NULL DEFAULT 1,
    protocol TEXT NOT NULL,
    host TEXT DEFAULT '',
    port INTEGER DEFAULT 0,
    timeout REAL DEFAULT 3.0,
    retry INTEGER DEFAULT 3,
    properties TEXT DEFAULT '{}',
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blocks (
    block TEXT PRIMARY KEY,
    comment TEXT DEFAULT '',
    use INTEGER NOT NULL DEFAULT 1,
    conn TEXT NOT NULL REFERENCES conns(conn),
    direction TEXT NOT NULL DEFAULT 'ro',
    trigger TEXT NOT NULL DEFAULT 'cyc',
    schedule REAL DEFAULT 1.0,
    standby INTEGER DEFAULT 0,
    properties TEXT DEFAULT '{}',
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blocks_tags (
    block TEXT NOT NULL REFERENCES blocks(block),
    use INTEGER NOT NULL DEFAULT 1,
    tag TEXT NOT NULL,
    field TEXT NOT NULL DEFAULT 'v',
    scale REAL DEFAULT 1.0,
    offset_val REAL DEFAULT 0.0,
    low REAL,
    high REAL,
    deadband REAL DEFAULT 0.0,
    properties TEXT DEFAULT '{}',
    PRIMARY KEY (block, tag, field)
);
"""


@pytest.fixture
def mem_db():
    """Provide an in-memory SQLite database with the supervisor schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    yield conn
    conn.close()
