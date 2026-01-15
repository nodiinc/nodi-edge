# -*- coding: utf-8 -*-
"""nodi-edge: Edge application framework with Databus, FSM, and Logger."""
from __future__ import annotations

__version__ = "0.1.0"

from nodi_edge.states import AppState
from nodi_edge.app import App

__all__ = ["App", "AppState"]
