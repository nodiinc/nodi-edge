#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installer utility functions."""
from __future__ import annotations


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Colors
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RESET = '\033[0m'
BOLD = '\033[1m'
CYAN = '\033[36m'
YELLOW = '\033[33m'
RED = '\033[31m'
GREEN = '\033[32m'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Output Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def head(text: str) -> None:
    section = (
        f'\n'
        f'{BOLD}{CYAN}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓{RESET}\n'
        f'{BOLD}{CYAN}  {text}{RESET}\n'
        f'{BOLD}{CYAN}┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{RESET}\n')
    print(section)


def desc(text: str) -> None:
    section = (
        f'\n'
        f'{CYAN}┌──────────────────────────────────────────────────┐{RESET}\n'
        f'{CYAN}  {text}{RESET}\n'
        f'{CYAN}└──────────────────────────────────────────────────┘{RESET}\n')
    print(section)


def info(text: str) -> None:
    print(f'  [INFO] {text}')


def warn(text: str) -> None:
    print(f'  {YELLOW}[WARN]{RESET} {text}')


def fail(text: str) -> None:
    print(f'  {RED}[FAIL]{RESET} {text}')


def done(text: str) -> None:
    print(f'  {GREEN}[DONE]{RESET} {text}')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Identity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IDENTITY_FILE = "/etc/nodi/identity"


def get_identity(key: str) -> str | None:
    import os
    if not os.path.exists(IDENTITY_FILE):
        return None
    with open(IDENTITY_FILE) as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return None


def get_serial_number() -> str | None:
    return get_identity("SERIAL_NUMBER")
