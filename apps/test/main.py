#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test app."""
from __future__ import annotations

from nodi_edge import App


class TestApp(App):

    def on_prepare(self) -> None:
        pass

    def on_initiate(self) -> None:
        pass

    def on_execute(self) -> None:
        pass

    def on_terminate(self) -> None:
        pass


if __name__ == "__main__":
    app = TestApp("test")
    app.run()
