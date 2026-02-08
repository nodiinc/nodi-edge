#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install user accounts for nodi-edge."""
from __future__ import annotations

import getpass
import os
import grp
import pwd
import subprocess
import sys
from pathlib import Path

from tool import head, desc, info, warn, fail, done


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER_NODI = "nodi"
USER_GUEST = "guest"

DATA_DIR = Path("/home/nodi/nodi-edge-data")
GUEST_BIN_DIR = Path("/home/guest/bin")
SUDOERS_FILE = Path("/etc/sudoers.d/nodi-edge")

GUEST_ALLOWED_COMMANDS = [
    "/usr/bin/ping",
    "/usr/bin/ip",
    "/usr/bin/netstat",
    "/usr/bin/traceroute",
    "/usr/bin/ss",
    "/usr/bin/df",
    "/usr/bin/free",
    "/usr/bin/uptime",
    "/usr/bin/ps",
    "/usr/bin/top",
    "/usr/bin/vmstat",
    "/usr/bin/iostat",
    "/usr/bin/w",
    "/usr/bin/who",
    "/usr/bin/grep",
    "/usr/bin/exit",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def prompt_password(username: str) -> str:
    while True:
        pw1 = getpass.getpass(f"  Enter password for '{username}': ")
        pw2 = getpass.getpass(f"  Confirm password for '{username}': ")
        if pw1 == pw2:
            return pw1
        warn("Passwords do not match. Try again.")


def set_password(username: str, password: str) -> None:
    proc = subprocess.Popen(["chpasswd"],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    proc.communicate(input=f"{username}:{password}".encode())


def chown_recursive(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)
    for child in path.rglob("*"):
        os.chown(child, uid, gid)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Installation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

head("Install Users")


# ────────────────────────────────────────────────────────────
# Check Prerequisites
# ────────────────────────────────────────────────────────────

desc("Check Prerequisites")

if os.geteuid() != 0:
    fail("This script must be run as root.")
    info("Usage: sudo python3 install_users.py")
    sys.exit(1)

info("Running as root.")


# ────────────────────────────────────────────────────────────
# Create Nodi User
# ────────────────────────────────────────────────────────────

desc("Create Nodi User")

if user_exists(USER_NODI):
    info(f"User '{USER_NODI}' already exists.")
else:
    run(["useradd", "-m", "-s", "/bin/bash", USER_NODI])
    info(f"User '{USER_NODI}' created.")
    password = prompt_password(USER_NODI)
    set_password(USER_NODI, password)
    done("Password set.")


# ────────────────────────────────────────────────────────────
# Restrict Nodi Home
# ────────────────────────────────────────────────────────────

desc("Restrict Nodi Home")

nodi_home = Path(f"/home/{USER_NODI}")
run(["chmod", "750", str(nodi_home)])
info(f"{nodi_home} (750)")


# ────────────────────────────────────────────────────────────
# Create Guest User
# ────────────────────────────────────────────────────────────

desc("Create Guest User")

if user_exists(USER_GUEST):
    info(f"User '{USER_GUEST}' already exists.")
else:
    run(["useradd", "-m", "-s", "/bin/rbash", USER_GUEST])
    info(f"User '{USER_GUEST}' created (rbash).")
    password = prompt_password(USER_GUEST)
    set_password(USER_GUEST, password)
    done("Password set.")


# ────────────────────────────────────────────────────────────
# Setup Guest Commands
# ────────────────────────────────────────────────────────────

desc("Setup Guest Commands")

GUEST_BIN_DIR.mkdir(parents=True, exist_ok=True)

# Clear old symlinks
for existing in GUEST_BIN_DIR.iterdir():
    if existing.is_symlink():
        existing.unlink()

# Link allowed commands
linked_count = 0
for cmd_path in GUEST_ALLOWED_COMMANDS:
    cmd = Path(cmd_path)
    if cmd.exists():
        link_path = GUEST_BIN_DIR / cmd.name
        link_path.symlink_to(cmd)
        linked_count += 1
    else:
        warn(f"{cmd_path} not found.")

info(f"{linked_count} commands linked.")


# ────────────────────────────────────────────────────────────
# Configure Guest Bashrc
# ────────────────────────────────────────────────────────────

desc("Configure Guest Bashrc")

bashrc_path = Path(f"/home/{USER_GUEST}/.bashrc")

# Unlock if immutable
run(["chattr", "-i", str(bashrc_path)], check=False)

# Overwrite with restricted PATH
bashrc_path.write_text(f"export PATH={GUEST_BIN_DIR}\n")
info(f"{bashrc_path}")

# Lock bashrc
run(["chattr", "+i", str(bashrc_path)], check=False)
info("Locked (immutable).")


# ────────────────────────────────────────────────────────────
# Restrict Guest Home
# ────────────────────────────────────────────────────────────

desc("Restrict Guest Home")

guest_home = Path(f"/home/{USER_GUEST}")
run(["chown", "root:root", str(guest_home)])
run(["chmod", "755", str(guest_home)])
info(f"{guest_home} (755, root:root)")


# ────────────────────────────────────────────────────────────
# Create Data Directory
# ────────────────────────────────────────────────────────────

desc("Create Data Directory")

dirs = [
    DATA_DIR / "backup",
    DATA_DIR / "config" / "apps",
    DATA_DIR / "config" / "interfaces",
    DATA_DIR / "data" / "snapshots",
    DATA_DIR / "db",
    DATA_DIR / "license" / "tokens",
    DATA_DIR / "log",
]

for d in dirs:
    d.mkdir(parents=True, exist_ok=True)
    info(f"{d}")


# ────────────────────────────────────────────────────────────
# Set Data Ownership
# ────────────────────────────────────────────────────────────

desc("Set Data Ownership")

uid = pwd.getpwnam(USER_NODI).pw_uid
gid = grp.getgrnam(USER_NODI).gr_gid
chown_recursive(DATA_DIR, uid, gid)
info(f"{DATA_DIR} -> {USER_NODI}:{USER_NODI}")


# ────────────────────────────────────────────────────────────
# Setup Sudoers
# ────────────────────────────────────────────────────────────

desc("Setup Sudoers")

sudoers_content = """\
# nodi-edge service management
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl start ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl stop ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl restart ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl status ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl enable ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl disable ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl is-active ne-*
nodi ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload
nodi ALL=(root) NOPASSWD: /usr/bin/journalctl -u ne-*
"""

SUDOERS_FILE.write_text(sudoers_content)
run(["chmod", "440", str(SUDOERS_FILE)])
info(f"{SUDOERS_FILE}")


# ────────────────────────────────────────────────────────────
# Done
# ────────────────────────────────────────────────────────────

desc("Done")
info(f"nodi={USER_NODI}")
info(f"guest={USER_GUEST}")
info(f"data={DATA_DIR}")
