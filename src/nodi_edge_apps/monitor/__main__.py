# -*- coding: utf-8 -*-
from __future__ import annotations

from nodi_edge import AppConfig
from nodi_edge_apps.monitor.core import MonitorApp

if __name__ == "__main__":
    app_config = AppConfig(execute_interval_s=3.0, manage_interval_s=1.0)
    app = MonitorApp("monitor", app_config=app_config)
    app.start()
