# -*- coding: utf-8 -*-
from __future__ import annotations


def test_mtc_module_importable():
    from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp
    assert ModbusTcpClientApp is not None


def test_mtc_extends_interface_app():
    from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp
    from nodi_edge.intf_app import InterfaceApp
    assert issubclass(ModbusTcpClientApp, InterfaceApp)


def test_mtc_has_protocol_overrides():
    from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp
    assert hasattr(ModbusTcpClientApp, 'on_intf_prepare')
    assert hasattr(ModbusTcpClientApp, 'on_intf_connect')
    assert hasattr(ModbusTcpClientApp, 'on_intf_execute')
    assert hasattr(ModbusTcpClientApp, 'on_intf_disconnect')
    assert hasattr(ModbusTcpClientApp, 'on_intf_configure')


def test_mtc_main_module_exists():
    import importlib
    mod = importlib.import_module("nodi_edge_intf.modbus_tcp_client.__main__")
    assert hasattr(mod, "_APP_ID")
    assert mod._APP_ID == "mtc"
