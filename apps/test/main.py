#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test app - demonstrates lifecycle stages and error recovery."""
from __future__ import annotations

from nodi_edge import App, AppConfig


class TestApp(App):

    def on_prepare(self) -> None:
        self._counter: int = 0
        self._error_threshold: int = 10

    def on_configure(self) -> None:
        pass

    def on_connect(self) -> None:
        self._counter = 0
        self.databus.set_tags({f"{self.app_id}/stages/prepare": True,
                               f"{self.app_id}/stages/configure": True,
                               f"{self.app_id}/stages/connect": True})
        self.databus.apply()
        self.logger.info("counter reset")

    def on_execute(self) -> None:
        self._counter += 1
        self.databus.set_tags({f"{self.app_id}/counter": self._counter})
        self.databus.apply()
        self.logger.info(f"counter: {self._counter}")
        if self._counter >= self._error_threshold:
            raise RuntimeError(f"counter reached threshold: {self._error_threshold}")

    def on_recover(self) -> None:
        self.databus.set_tags({f"{self.app_id}/stages/recover": True,
                               f"{self.app_id}/stages/disconnect": True})
        self.databus.apply()
        raise RuntimeError("recovery failed intentionally")

    def on_disconnect(self) -> None:
        pass

    def on_manage(self) -> None:
        # Publish app statistics
        self.databus.set_tags({f"{self.app_id}/state": self.current_state.name if self.current_state else "None",
                               f"{self.app_id}/execute_time_avg": self.stats.execute_maf.mean,
                               f"{self.app_id}/exception_count": self.stats.exception_count})
        self.databus.apply()


if __name__ == "__main__":
    app = TestApp("test", app_config=AppConfig(execute_interval_s=1.0))
    app.start()
