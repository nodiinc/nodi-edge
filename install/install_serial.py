#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install device serial number to /etc/nodi/identity."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tool import head, desc, info, warn, fail


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IDENTITY_DIR = Path("/etc/nodi-edge")
IDENTITY_FILE = IDENTITY_DIR / "identity"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Installation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

head("Install Serial Number")


# ────────────────────────────────────────────────────────────
# Check Prerequisites
# ────────────────────────────────────────────────────────────

desc("Check Prerequisites")

if os.geteuid() != 0:
    fail("This script must be run as root.")
    info("Usage: sudo python3 install_serial.py <serial_number>")
    sys.exit(1)

if len(sys.argv) != 2:
    fail("Serial number argument required.")
    info("Usage: sudo python3 install_serial.py <serial_number>")
    info("Example: sudo python3 install_serial.py NE-EBOW4")
    sys.exit(1)

serial_number = sys.argv[1].strip()

if not serial_number:
    fail("Serial number cannot be empty.")
    sys.exit(1)

info(f"serial_number={serial_number}")


# ────────────────────────────────────────────────────────────
# Check Existing
# ────────────────────────────────────────────────────────────

desc("Check Existing")

if IDENTITY_FILE.exists():
    existing = IDENTITY_FILE.read_text().strip()
    for line in existing.split("\n"):
        if line.startswith("SERIAL_NUMBER="):
            old_serial = line.split("=", 1)[1]
            warn(f"Already exists: {old_serial}")
            confirm = input("  Overwrite? [y/N]: ").strip().lower()
            if confirm != "y":
                info("Aborted.")
                sys.exit(0)
            break
else:
    info("No existing identity file.")


# ────────────────────────────────────────────────────────────
# Create Directory
# ────────────────────────────────────────────────────────────

desc("Create Directory")

IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
info(f"{IDENTITY_DIR}")


# ────────────────────────────────────────────────────────────
# Write Identity
# ────────────────────────────────────────────────────────────

desc("Write Identity")

if IDENTITY_FILE.exists():
    os.chmod(IDENTITY_FILE, 0o644)
identity_content = f"SERIAL_NUMBER={serial_number}\n"
IDENTITY_FILE.write_text(identity_content)
os.chmod(IDENTITY_FILE, 0o444)
info(f"{IDENTITY_FILE}")


# ────────────────────────────────────────────────────────────
# Set Hostname
# ────────────────────────────────────────────────────────────

desc("Set Hostname")

subprocess.run(["hostnamectl", "set-hostname", serial_number], check=True)
info(f"{serial_number}")


# ────────────────────────────────────────────────────────────
# Done
# ────────────────────────────────────────────────────────────

desc("Done")
info(f"serial_number={serial_number}")
