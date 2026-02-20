# -*- coding: utf-8 -*-
from __future__ import annotations


def test_mtc_module_importable():
    from nodi_edge_interface.modbus_tcp_client.core import ModbusTcpClientApp
    assert ModbusTcpClientApp is not None


def test_mtc_extends_interface_app():
    from nodi_edge_interface.modbus_tcp_client.core import ModbusTcpClientApp
    from nodi_edge.interface_app import InterfaceApp
    assert issubclass(ModbusTcpClientApp, InterfaceApp)


def test_mtc_has_protocol_overrides():
    from nodi_edge_interface.modbus_tcp_client.core import ModbusTcpClientApp
    assert hasattr(ModbusTcpClientApp, 'on_interface_prepare')
    assert hasattr(ModbusTcpClientApp, 'on_interface_connect')
    assert hasattr(ModbusTcpClientApp, 'on_interface_execute')
    assert hasattr(ModbusTcpClientApp, 'on_interface_disconnect')
    assert hasattr(ModbusTcpClientApp, 'on_interface_configure')


def test_mtc_main_module_exists():
    import importlib
    mod = importlib.import_module("nodi_edge_interface.modbus_tcp_client.__main__")
    assert hasattr(mod, "_APP_ID")
    assert mod._APP_ID == "mtc"
