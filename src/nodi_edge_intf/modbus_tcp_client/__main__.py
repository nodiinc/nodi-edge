# -*- coding: utf-8 -*-
from __future__ import annotations

from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp

_APP_ID = "mtc"

if __name__ == "__main__":
    app = ModbusTcpClientApp(_APP_ID)
    app.start()
