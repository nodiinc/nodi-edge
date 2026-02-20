# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from nodi_edge.interface_app import InterfaceApp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _create_interface_app(conn_id: str = "mtc-01",
                     protocol: str = "mtc",
                     app_id: str = "mtc-01"):
    """Create an InterfaceApp with all external dependencies mocked."""
    with patch("sys.argv", ["test", f"--conn-id={conn_id}"]), \
         patch("nodi_edge.app.TagBus"), \
         patch("nodi_edge.app.TagBusConfig"), \
         patch("nodi_edge.app.FiniteStateMachine"), \
         patch("nodi_edge.app.Logger"), \
         patch("nodi_edge.app.PeriodicTimer"):
        app = InterfaceApp(app_id, protocol)
    return app


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - conn-id Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConnIdValidation:

    def test_interface_app_requires_conn_id(self):
        """Verify SystemExit when --conn-id is not provided."""
        with patch("sys.argv", ["test"]), \
             patch("nodi_edge.app.TagBus"), \
             patch("nodi_edge.app.TagBusConfig"), \
             patch("nodi_edge.app.FiniteStateMachine"), \
             patch("nodi_edge.app.Logger"), \
             patch("nodi_edge.app.PeriodicTimer"):
            with pytest.raises(SystemExit):
                InterfaceApp("mtc-01", "mtc")

    def test_conn_id_property(self):
        """Verify conn_id returns the correct value."""
        app = _create_interface_app(conn_id="my-conn-42")
        assert app.conn_id == "my-conn-42"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - Config Loading
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConfigLoading:

    def test_load_config(self):
        """Verify _load_config populates _conn_config and _block_configs."""
        app = _create_interface_app()

        # Mock EdgeDB
        mock_db = MagicMock()
        mock_conn_row = MagicMock()
        mock_conn_row.__iter__ = MagicMock(return_value=iter([]))
        dict_result = {"conn": "mtc-01", "host": "10.0.0.1",
                       "port": 502, "timeout": 3.0, "retry": 3}
        mock_conn_row.keys.return_value = dict_result.keys()

        # Make dict(row) work by mocking the Row behavior
        mock_db.select_conn.return_value = dict_result
        mock_db.select_blocks_by_conn.return_value = [
            {"block": "blk-01", "conn": "mtc-01"},
            {"block": "blk-02", "conn": "mtc-01"},
        ]

        app._db = mock_db

        # Patch dict() conversion — use dicts directly since mock returns dicts
        app._load_config()

        assert app._conn_config == dict_result
        assert len(app._block_configs) == 2
        assert app._block_configs[0]["block"] == "blk-01"
        assert app._block_configs[1]["block"] == "blk-02"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - Connection Info Change Detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConnInfoChanged:

    def test_is_conn_info_changed_false(self):
        """Same host/port/timeout/retry returns False."""
        prev = {"host": "10.0.0.1", "port": 502, "timeout": 3.0, "retry": 3}
        curr = {"host": "10.0.0.1", "port": 502, "timeout": 3.0, "retry": 3}
        assert InterfaceApp._is_conn_info_changed(prev, curr) is False

    def test_is_conn_info_changed_host(self):
        """Different host returns True."""
        prev = {"host": "10.0.0.1", "port": 502, "timeout": 3.0, "retry": 3}
        curr = {"host": "10.0.0.2", "port": 502, "timeout": 3.0, "retry": 3}
        assert InterfaceApp._is_conn_info_changed(prev, curr) is True

    def test_is_conn_info_changed_port(self):
        """Different port returns True."""
        prev = {"host": "10.0.0.1", "port": 502, "timeout": 3.0, "retry": 3}
        curr = {"host": "10.0.0.1", "port": 503, "timeout": 3.0, "retry": 3}
        assert InterfaceApp._is_conn_info_changed(prev, curr) is True

    def test_is_conn_info_changed_timeout(self):
        """Different timeout returns True."""
        prev = {"host": "10.0.0.1", "port": 502, "timeout": 3.0, "retry": 3}
        curr = {"host": "10.0.0.1", "port": 502, "timeout": 5.0, "retry": 3}
        assert InterfaceApp._is_conn_info_changed(prev, curr) is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - Config Reload Tag
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestConfigReloadTag:

    def test_config_reload_tag_format(self):
        """Verify tag matches /system/{conn_id}/config_reload."""
        app = _create_interface_app(conn_id="my-conn-01")
        assert app._config_reload_tag == "/system/my-conn-01/config_reload"
