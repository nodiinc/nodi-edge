# -*- coding: utf-8 -*-
from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    """Application lifecycle states.

    State transitions:
        PREPARE → INITIATE → EXECUTE ↔ (loop)
                     ↑          ↓
                     └── TERMINATE

    - PREPARE: One-time setup (logger, databus creation)
    - INITIATE: Connection and initialization (databus connect, resource setup)
    - EXECUTE: Main loop (tag publish/subscribe, business logic)
    - TERMINATE: Error recovery and cleanup (before retry INITIATE)
    """
    PREPARE = auto()
    INITIATE = auto()
    EXECUTE = auto()
    TERMINATE = auto()
