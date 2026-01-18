# -*- coding: utf-8 -*-
from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    """Application lifecycle states.

    State flow:
        PREPARE → CONFIGURE → CONNECT → EXECUTE ↔ (loop)
                                 ↑          ↓
                                 │      [exception]
                                 │          ↓
                                 │       RECOVER ─── (success) ──→ EXECUTE
                                 │          ↓ (fail)
                                 └───── DISCONNECT
                                           ↓
                                     [retry delay]

    Fatal errors (PREPARE/CONFIGURE fail):
        → sys.exit(1) → systemctl restarts

    - PREPARE: One-time setup (databus creation) - fatal on error
    - CONFIGURE: Configuration loading - fatal on error
    - CONNECT: Connection/server start (databus connect)
    - EXECUTE: Main loop (tag publish/subscribe, business logic)
    - RECOVER: Error recovery attempt (success → EXECUTE, fail → DISCONNECT)
    - DISCONNECT: Resource cleanup (databus disconnect)
    """
    PREPARE = auto()
    CONFIGURE = auto()
    CONNECT = auto()
    EXECUTE = auto()
    RECOVER = auto()
    DISCONNECT = auto()
