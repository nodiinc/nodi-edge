# -*- coding: utf-8 -*-
from __future__ import annotations

import psutil
from typing import Any, Dict

from nodi_edge import AppConfig
from nodi_edge.config import get_serial_number
from nodi_edge_apps.cloud.core import CloudApp, CloudConfig

if __name__ == "__main__":
    cloud_config = CloudConfig(report_interval_s=10.0)
    app_config = AppConfig(execute_interval_s=1.0,
                           retry_delay_s=5.0)
    app = CloudApp(app_id="ne-cloud",
                   serial_number=get_serial_number(),
                   cloud_config=cloud_config,
                   app_config=app_config)

    # Report data getter
    def get_report_data() -> Dict[str, Any]:
        return {"cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent}

    app.set_report_data_getter(get_report_data)

    app.start()
