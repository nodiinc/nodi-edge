# -*- coding: utf-8 -*-
from __future__ import annotations

from nodi_edge_apps.supervisor.core import (
    _INTERFACE_SERVICE_TEMPLATE, _VENV_PYTHON, _SVC_PREFIX_INTERFACE,
    _TAG_SYS_CONN_ADDED, _TAG_SYS_CONN_REMOVED, ServiceState
)


# _INTERFACE_SERVICE_TEMPLATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_interface_service_template_uses_conn_id():
    content = _INTERFACE_SERVICE_TEMPLATE.format(
        app_id="mtc-01",
        python=_VENV_PYTHON,
        module="nodi_edge_interface.modbus_tcp_client",
        conn_id="mtc-01")
    assert "--conn-id=mtc-01" in content


def test_interface_service_template_uses_restart_always():
    content = _INTERFACE_SERVICE_TEMPLATE.format(
        app_id="test-app",
        python=_VENV_PYTHON,
        module="nodi_edge_interface.modbus_tcp_client",
        conn_id="test-app")
    assert "Restart=always" in content


# System Tag Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_supervisor_has_system_tag_constants():
    assert "supervisor" in _TAG_SYS_CONN_ADDED
    assert "supervisor" in _TAG_SYS_CONN_REMOVED
    assert _TAG_SYS_CONN_ADDED != _TAG_SYS_CONN_REMOVED


# ServiceState
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_service_state_has_conn_id():
    state = ServiceState(
        app_id="mtc-01",
        category="interface",
        module="nodi_edge_interface.modbus_tcp_client",
        enabled=True,
        conn_id="mtc-01")
    assert state.conn_id == "mtc-01"


def test_service_state_conn_id_defaults_none():
    state = ServiceState(
        app_id="vplc",
        category="addon",
        module="nodi_edge_addon.virtual_plc",
        enabled=True)
    assert state.conn_id is None


# Service Naming
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_service_name_pattern():
    assert _SVC_PREFIX_INTERFACE == "ne-interface"

    # Verify naming pattern: ne-interface-{app_id}
    app_id = "mtc-01"
    expected = f"ne-interface-{app_id}"
    assert expected == f"{_SVC_PREFIX_INTERFACE}-{app_id}"
