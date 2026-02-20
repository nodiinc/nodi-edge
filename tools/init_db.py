# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sqlite3

from nodi_edge.config import DB_DIR, DB_PATH


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Schema
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEMA_SQL = """
-- Protocol metadata
CREATE TABLE IF NOT EXISTS prot (
    prot      CHAR(3) PRIMARY KEY,
    cmt       VARCHAR,
    prot_dtyp CHAR(3),
    prot_dim  CHAR(2),
    prot_unit CHAR(4)
);

-- Protocol field definitions (vertical normalization)
CREATE TABLE IF NOT EXISTS prot_prop (
    prot     CHAR(3) REFERENCES prot(prot),
    layer    VARCHAR NOT NULL,
    pos      INTEGER NOT NULL,
    key      VARCHAR NOT NULL,
    label    VARCHAR NOT NULL,
    type     VARCHAR DEFAULT 'str',
    required CHAR(1) DEFAULT 'N',
    hint     VARCHAR,
    PRIMARY KEY (prot, layer, pos)
);

-- Interface
CREATE TABLE IF NOT EXISTS interface (
    interface VARCHAR PRIMARY KEY,
    cmt       VARCHAR,
    prot      CHAR(3) REFERENCES prot(prot),
    host      VARCHAR,
    port      INTEGER,
    prop      TEXT DEFAULT '{}',
    tout      REAL DEFAULT 5.0,
    rtr       REAL DEFAULT 10.0,
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Block
CREATE TABLE IF NOT EXISTS blck (
    blck VARCHAR PRIMARY KEY,
    cmt  VARCHAR,
    use  CHAR(1) DEFAULT 'Y',
    interface VARCHAR REFERENCES interface(interface),
    prop TEXT DEFAULT '{}',
    rw   CHAR(2) DEFAULT 'ro',
    trig CHAR(3) DEFAULT 'cyc',
    tm   VARCHAR DEFAULT '1',
    stby REAL DEFAULT 1.0,
    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Block map (tag mapping)
CREATE TABLE IF NOT EXISTS blck_map (
    blck VARCHAR REFERENCES blck(blck),
    tag  VARCHAR REFERENCES tag(tag),
    idx  CHAR(2) DEFAULT 'v',
    prop TEXT DEFAULT '{}'
);

-- Tag
CREATE TABLE IF NOT EXISTS tag (
    tag  VARCHAR PRIMARY KEY,
    cmt  VARCHAR,
    init VARCHAR
);

-- Archive
CREATE TABLE IF NOT EXISTS arcv (
    arcv VARCHAR PRIMARY KEY,
    cmt  VARCHAR,
    sto  VARCHAR,
    rev  VARCHAR,
    ret  VARCHAR
);

-- Archive map
CREATE TABLE IF NOT EXISTS arcv_map (
    arcv VARCHAR REFERENCES arcv(arcv),
    tag  VARCHAR REFERENCES tag(tag)
);

-- App registry (supervisor manages services via this table)
CREATE TABLE IF NOT EXISTS app_registry (
    app_id            VARCHAR PRIMARY KEY,
    category          VARCHAR NOT NULL,
    module            VARCHAR NOT NULL,
    enabled           INTEGER DEFAULT 0,
    config            TEXT DEFAULT '{}',
    interface_id      VARCHAR,
    license_token     TEXT,
    license_expires_at INTEGER,
    updated_at        INTEGER DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_app_registry_category ON app_registry(category);
CREATE INDEX IF NOT EXISTS idx_app_registry_interface_id ON app_registry(interface_id);
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Seed Data
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SEED_PROT = [
    ("nei", "Nodi Edge Internal", "str", "1d", "blck"),
    ("dsc", "Data Store Client", "str", "1d", "blck"),
    ("mtc", "Modbus TCP Client", "int", "1d", "blck"),
    ("mts", "Modbus TCP Server", "int", "1d", "blck"),
    ("mvc", "Modbus RTU via TCP Client", "int", "1d", "blck"),
    ("mvs", "Modbus RTU via TCP Server", "int", "1d", "blck"),
    ("mrc", "Modbus RTU Client", "int", "1d", "blck"),
    ("mrs", "Modbus RTU Server", "int", "1d", "blck"),
    ("ouc", "OPC UA Client", "str", "1d", "blck"),
    ("ous", "OPC UA Server", "str", "1d", "blck"),
    ("mqc", "MQTT Client", "str", "1d", "blck"),
    ("mqs", "MQTT Broker", "str", "1d", "blck"),
    ("kfc", "Kafka Client", "str", "1d", "blck"),
    ("kfs", "Kafka Server", "str", "1d", "blck"),
    ("rdc", "Relation DB Client", "str", "1d", "blck"),
    ("rac", "REST API Client", "str", "1d", "blck"),
    ("ras", "REST API Server", "str", "1d", "blck"),
]

_SEED_PROT_PROP = [
    # Modbus TCP Client (mtc)
    ("mtc", "blck", 1, "base_address", "0/1-based", "int", "N", "0 or 1-based addressing"),
    ("mtc", "map", 1, "unit_id", "Unit ID", "int", "Y", "Slave ID (1-247)"),
    ("mtc", "map", 2, "func_code", "Function Code", "int", "Y", "1,2,3,4,5,6,15,16"),
    ("mtc", "map", 3, "address", "Address", "int", "Y", "Register address"),
    ("mtc", "map", 4, "data_type", "Data Type", "str", "Y", "int16,uint16,int32,float32,..."),
    ("mtc", "map", 5, "bit_mask", "Bit Mask", "str", "N", "Bit or multiple mask"),
    # Modbus TCP Server (mts)
    ("mts", "blck", 1, "unit_id", "Unit ID", "int", "Y", "Slave ID"),
    ("mts", "blck", 2, "memory_area", "Memory Area", "str", "Y", "Memory area"),
    ("mts", "map", 1, "address", "Address", "int", "Y", "Register address"),
    # OPC UA Client (ouc)
    ("ouc", "interface", 1, "path", "Path", "str", "Y", "URL path"),
    ("ouc", "interface", 2, "auth_type", "Auth Type", "str", "Y", "anonymous,certificate"),
    ("ouc", "interface", 3, "certificate", "Certificate", "str", "N", "Certificate file path"),
    ("ouc", "interface", 4, "private_key", "Private Key", "str", "N", "Private key file path"),
    ("ouc", "blck", 1, "server_uri", "Namespace", "str", "Y", "Server URI"),
    ("ouc", "map", 1, "node_id", "Node ID", "str", "Y", "OPC UA Node ID"),
    # OPC UA Server (ous)
    ("ous", "interface", 1, "path", "Path", "str", "Y", "URL path"),
    ("ous", "interface", 2, "server_name", "Server Name", "str", "Y", "Server name (URI)"),
    ("ous", "interface", 3, "auth_type", "Auth Type", "str", "N", "anonymous,certificate"),
    ("ous", "interface", 4, "certificate", "Certificate", "str", "N", "Certificate file path"),
    ("ous", "interface", 5, "private_key", "Private Key", "str", "N", "Private key file path"),
    ("ous", "blck", 1, "server_uri", "Namespace", "str", "Y", "Server URI"),
    ("ous", "map", 1, "identifier", "Identifier", "str", "Y", "Identifier"),
    ("ous", "map", 2, "path", "Path", "str", "N", "Node path"),
    ("ous", "map", 3, "writable", "Writable", "bool", "N", "true/false"),
    # MQTT Client (mqc)
    ("mqc", "interface", 1, "client_id", "Client ID", "str", "N", "MQTT client ID"),
    ("mqc", "interface", 2, "username", "Username", "str", "N", "MQTT username"),
    ("mqc", "interface", 3, "password", "Password", "str", "N", "MQTT password"),
    ("mqc", "blck", 1, "qos", "QoS", "int", "N", "0, 1, 2"),
    ("mqc", "blck", 2, "retain", "Retain", "bool", "N", "true/false"),
    ("mqc", "map", 1, "topic", "Topic", "str", "Y", "MQTT topic"),
    # Kafka Client (kfc)
    ("kfc", "blck", 1, "group_id", "Group ID", "str", "N", "Consumer group ID"),
    ("kfc", "map", 1, "topic", "Topic", "str", "Y", "Kafka topic"),
    # Relation DB Client (rdc)
    ("rdc", "interface", 1, "driver", "Driver", "str", "Y", "postgresql,sqlite3,..."),
    ("rdc", "interface", 2, "database", "Database", "str", "Y", "DB path or name"),
    ("rdc", "interface", 3, "username", "Username", "str", "N", "DB username"),
    ("rdc", "interface", 4, "password", "Password", "str", "N", "DB password"),
    ("rdc", "blck", 1, "query", "Query", "str", "Y", "SQL query"),
    # REST API Client (rac)
    ("rac", "interface", 1, "base_url", "Base URL", "str", "Y", "Base URL"),
    ("rac", "interface", 2, "auth_type", "Auth Type", "str", "N", "none,basic,bearer,api_key"),
    ("rac", "interface", 3, "auth_value", "Auth Value", "str", "N", "Token or API key"),
    ("rac", "blck", 1, "method", "Method", "str", "Y", "GET,POST,PUT,DELETE"),
    ("rac", "blck", 2, "endpoint", "Endpoint", "str", "Y", "API endpoint path"),
    # REST API Server (ras)
    ("ras", "interface", 1, "base_path", "Base Path", "str", "N", "API base path"),
    ("ras", "blck", 1, "endpoint", "Endpoint", "str", "Y", "API endpoint path"),
    ("ras", "blck", 2, "method", "Method", "str", "Y", "GET,POST,PUT,DELETE"),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_db(db_path: str = DB_PATH) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    # Pragmas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create tables
    conn.executescript(_SCHEMA_SQL)

    # Seed prot
    conn.executemany(
        "INSERT OR IGNORE INTO prot (prot, cmt, prot_dtyp, prot_dim, prot_unit) "
        "VALUES (?, ?, ?, ?, ?)",
        _SEED_PROT)

    # Seed prot_prop
    conn.executemany(
        "INSERT OR IGNORE INTO prot_prop (prot, layer, pos, key, label, type, required, hint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        _SEED_PROT_PROP)

    conn.commit()
    conn.close()
    print(f"Database initialized: {db_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    init_db(path)
