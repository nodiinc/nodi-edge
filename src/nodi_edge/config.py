# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cloud Server Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CloudServerConfig:
    host: str = "43.202.161.226"
    port: int = 1883
    username: str = "nodi"
    password: str = "PASS00371"
    keepalive: int = 30
    connection_timeout: float = 10.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Topic Formats
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class TopicFormats:
    report: str = "/ne/{sn}/report"
    request: str = "/ne/{sn}/request"
    response: str = "/ne/{sn}/response"
    result: str = "/ne/{sn}/result"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Directories
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATA_DIR = "/home/nodi/nodi-edge-data"
LOG_DIR = f"{DATA_DIR}/log"
BACKUP_DIR = f"{DATA_DIR}/backup"
OTA_BACKUP_DIR = f"{BACKUP_DIR}/ota"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Device Identity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_serial_number() -> str:
    """Get device serial number from unique config file."""
    import configparser
    import os

    # Try reading from existing config
    unique_ini = "/root/this/uniq/edge.ini"
    if os.path.exists(unique_ini):
        config = configparser.ConfigParser()
        config.read(unique_ini)
        try:
            return config.get("Unique", "SerialNumber")
        except (configparser.NoSectionError, configparser.NoOptionError):
            pass

    # Fallback: generate from hostname or use default
    import socket
    hostname = socket.gethostname()
    return f"NODI-{hostname.upper()}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Default Instances
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLOUD_SERVER = CloudServerConfig()
TOPIC_FORMATS = TopicFormats()
