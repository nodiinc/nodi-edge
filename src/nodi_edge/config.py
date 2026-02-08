# -*- coding: utf-8 -*-
from __future__ import annotations


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Directories
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATA_DIR = "/home/nodi/nodi-edge-data"
CONFIG_DIR = f"{DATA_DIR}/config"
DB_DIR = f"{DATA_DIR}/db"
DB_PATH = f"{DB_DIR}/edge.db"
LOG_DIR = f"{DATA_DIR}/log"
LICENSE_DIR = f"{DATA_DIR}/license/tokens"
BACKUP_DIR = f"{DATA_DIR}/backup"
OTA_BACKUP_DIR = f"{BACKUP_DIR}/ota"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Security
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLOUD_PUBKEY_FILE = "/etc/nodi/cloud_pubkey.pem"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Device Identity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IDENTITY_FILE = "/etc/nodi/identity"


def get_serial_number() -> str:
    import os
    import socket

    # Read from identity file
    if os.path.exists(IDENTITY_FILE):
        with open(IDENTITY_FILE) as f:
            for line in f:
                if line.startswith("SERIAL_NUMBER="):
                    return line.split("=", 1)[1].strip()

    # Fallback: generate from hostname
    hostname = socket.gethostname()
    return f"NODI-{hostname.upper()}"
