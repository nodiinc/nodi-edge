#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor app - monitors app health and tag status."""
from __future__ import annotations

from nodi_edge import App


class MonitorApp(App):

    def on_prepare(self) -> None:
        self._monitored_apps: dict = {}

    def on_initiate(self) -> None:
        # Subscribe to all app status tags
        self.databus.sync_tags(["*/status", "*/health"])
        self.databus.on_tags_update(["*/status"], self._on_status_update)
        self.databus.flush()
        self.logger.info("subscribed to status tags")

    def on_execute(self) -> None:
        # Check app heartbeats
        apps = self.databus.get_all_apps()
        for app_id, app_data in apps.items():
            if app_id == self.app_id:
                continue
            prev_status = self._monitored_apps.get(app_id)
            curr_status = app_data.status
            if prev_status != curr_status:
                self.logger.info(f"app [{app_id}] status: {prev_status} -> {curr_status}")
                self._monitored_apps[app_id] = curr_status

    def on_terminate(self) -> None:
        self._monitored_apps.clear()

    def _on_status_update(self, tag_id: str, tag_data) -> None:
        self.logger.info(f"tag update: {tag_id} = {tag_data.v}")


if __name__ == "__main__":
    app = MonitorApp("monitor", execute_interval_s=3.0)
    app.run()
