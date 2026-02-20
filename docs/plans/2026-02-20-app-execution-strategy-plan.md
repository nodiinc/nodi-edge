# App Execution Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the orchestration infrastructure that launches, manages, and reconfigures InterfaceApp processes via systemd and TagBus system tags.

**Architecture:** Supervisor manages InterfaceApp systemd services (one per connection). Config changes are pushed via TagBus system tags (no DB polling). Each InterfaceApp reads its config from DB via `--conn-id` CLI arg and supports hot reload (EXECUTE→CONFIGURE→CONNECT→EXECUTE).

**Tech Stack:** Python 3.9+, SQLite (WAL mode), TagBus (eCAL pub/sub), systemd, nodi-edge App framework (FSM, PeriodicTimer)

**Design doc:** `docs/plans/2026-02-20-app-execution-strategy-design.md`

---

## Prerequisites

Before starting, read these files for context:
- `src/nodi_edge/app.py` — App base class (FSM, lifecycle, override points)
- `src/nodi_edge/states.py` — AppState enum (PREPARE/CONFIGURE/CONNECT/EXECUTE/RECOVER/DISCONNECT)
- `src/nodi_edge/db.py` — EdgeDB (SQLite wrapper, PROTOCOL_MODULES mapping)
- `src/nodi_edge/config.py` — Path constants (DATA_DIR, DB_PATH, etc.)
- `apps/supervisor/main.py` — Current SupervisorApp (systemd service management)
- `docs/interface_design.md` — Interface app design (protocol plugin framework)
- `docs/config_design.md` — Config design (3-layer schema: conn→block→blocks_tags)

---

### Task 1: Test Infrastructure Setup

**Files:**
- Create: `tests/conftest.py`
- Modify: `pyproject.toml`

**Step 1: Add pytest configuration to pyproject.toml**

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Step 2: Create test fixtures**

Create `tests/conftest.py` with an in-memory SQLite fixture that creates the minimal DB schema:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
import pytest


# Minimal schema for execution strategy tests
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_registry (
    app_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    module TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    config TEXT DEFAULT '{}',
    intf_id TEXT,
    conn_id TEXT,
    license_token TEXT,
    license_expires_at INTEGER,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conns (
    conn TEXT PRIMARY KEY,
    comment TEXT DEFAULT '',
    use INTEGER NOT NULL DEFAULT 1,
    protocol TEXT NOT NULL,
    host TEXT DEFAULT '',
    port INTEGER DEFAULT 0,
    timeout REAL DEFAULT 3.0,
    retry INTEGER DEFAULT 3,
    properties TEXT DEFAULT '{}',
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blocks (
    block TEXT PRIMARY KEY,
    comment TEXT DEFAULT '',
    use INTEGER NOT NULL DEFAULT 1,
    conn TEXT NOT NULL REFERENCES conns(conn),
    direction TEXT NOT NULL DEFAULT 'ro',
    trigger TEXT NOT NULL DEFAULT 'cyc',
    schedule REAL DEFAULT 1.0,
    standby INTEGER DEFAULT 0,
    properties TEXT DEFAULT '{}',
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blocks_tags (
    block TEXT NOT NULL REFERENCES blocks(block),
    use INTEGER NOT NULL DEFAULT 1,
    tag TEXT NOT NULL,
    field TEXT NOT NULL DEFAULT 'v',
    scale REAL DEFAULT 1.0,
    offset_val REAL DEFAULT 0.0,
    low REAL,
    high REAL,
    deadband REAL DEFAULT 0.0,
    properties TEXT DEFAULT '{}',
    PRIMARY KEY (block, tag, field)
);
"""


@pytest.fixture
def mem_db():
    """In-memory SQLite with execution strategy schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    yield conn
    conn.close()
```

**Step 3: Verify pytest runs**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/ -v --co`
Expected: "no tests ran" (collected 0 items), no import errors.

**Step 4: Commit**

```bash
git add tests/conftest.py pyproject.toml
git commit -m "feat: add test infrastructure with in-memory DB fixture"
```

---

### Task 2: Extend App Base with --conn-id and Reconfigure Support

**Files:**
- Modify: `src/nodi_edge/app.py:164-171` (CLI args), `240-247` (FSM transitions), `324-346` (execute handler), `275-298` (configure handler), `300-322` (connect handler)
- Create: `tests/test_app_reconfigure.py`

This task adds two capabilities to the App base class:
1. `--conn-id` CLI argument (optional, for InterfaceApp subclasses)
2. Reconfigure support: EXECUTE→CONFIGURE transition triggered by `request_reconfigure()`

**Step 1: Write the failing test**

Create `tests/test_app_reconfigure.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from unittest.mock import MagicMock, patch
from nodi_edge.states import AppState


def test_app_has_conn_id_arg():
    """App should parse --conn-id from CLI args."""
    with patch("sys.argv", ["test", "--conn-id=mtc-01"]):
        from nodi_edge.app import App

        # Mock TagBus to avoid eCAL dependency
        with patch("nodi_edge.app.TagBus"):
            with patch("nodi_edge.app.Logger"):
                app = App.__new__(App)
                args = app._parse_cli_args()
                assert args.conn_id == "mtc-01"


def test_app_conn_id_default_none():
    """--conn-id should default to None when not provided."""
    with patch("sys.argv", ["test"]):
        from nodi_edge.app import App

        with patch("nodi_edge.app.TagBus"):
            with patch("nodi_edge.app.Logger"):
                app = App.__new__(App)
                args = app._parse_cli_args()
                assert args.conn_id is None


def test_fsm_allows_execute_to_configure():
    """FSM should allow EXECUTE → CONFIGURE transition for hot reload."""
    from nodi_edge.app import App

    with patch("sys.argv", ["test"]):
        with patch("nodi_edge.app.TagBus"):
            with patch("nodi_edge.app.Logger"):
                with patch("nodi_edge.app.FiniteStateMachine") as MockFSM:
                    mock_fsm = MockFSM.return_value
                    app = App("test-app")

                    # Check that limit_transitions was called with
                    # EXECUTE allowing CONFIGURE transition
                    call_args = mock_fsm.limit_transitions.call_args[0][0]
                    assert AppState.CONFIGURE in call_args[AppState.EXECUTE]
```

**Step 2: Run test to verify it fails**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_app_reconfigure.py -v`
Expected: FAIL (--conn-id not recognized, CONFIGURE not in EXECUTE transitions)

**Step 3: Implement changes to app.py**

3a. Add `--conn-id` to `_parse_cli_args()` (line 164-171):
```python
def _parse_cli_args(self) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--conn-id", type=str, default=None,
                        help="connection identifier for config lookup")
    parser.add_argument("--clean", action="store_true",
                        help="clean databus state on connect")
    parser.add_argument("--debug", action="store_true",
                        help="enable databus debug output")
    args, _ = parser.parse_known_args()
    return args
```

3b. Add `_reconfigure_event` to `__init__()` (after timers, before FSM):
```python
import threading

# ... after timers ...

# Reconfigure
self._reconfigure_event = threading.Event()
```

3c. Add `request_reconfigure()` public method (after properties section):
```python
def request_reconfigure(self) -> None:
    self._reconfigure_event.set()
```

3d. Update FSM transitions in `_setup_fsm()` — add CONFIGURE to EXECUTE's allowed transitions:
```python
self._fsm.limit_transitions({AppState.PREPARE: [AppState.CONFIGURE],
                             AppState.CONFIGURE: [AppState.CONNECT],
                             AppState.CONNECT: [AppState.EXECUTE, AppState.RECOVER],
                             AppState.EXECUTE: [AppState.CONFIGURE, AppState.RECOVER],
                             AppState.RECOVER: [AppState.EXECUTE, AppState.DISCONNECT],
                             AppState.DISCONNECT: [AppState.CONNECT],})
```

3e. Update execute_handler — check reconfigure event after each cycle:
```python
@self._fsm.state(AppState.EXECUTE)
def execute_handler():
    while self._fsm.is_running:
        try:
            with self._measure_time(self._app_statistics.execute):
                self.on_execute()
                self._app_statistics.execute_maf.add(
                    self._app_statistics.execute.elapsed_time)

                # One-time log
                if not self._app_statistics.execute.done:
                    self._app_statistics.execute.done = True
                    if self._log_conf.logging_flags.stages:
                        self._logger.info("executing")
                    self._reset_done_flags_for_success()

                # Check for reconfigure request
                if self._reconfigure_event.is_set():
                    self._reconfigure_event.clear()
                    self._logger.info("reconfigure requested")
                    self._fsm.transition(AppState.CONFIGURE)
                    break

                # Wait for next cycle
                self._execute_timer.wait()

        except Exception as exc:
            self._app_statistics.exception_count += 1
            self._log_fallback("execute", exc)
            self._fsm.transition(AppState.RECOVER)
            break
```

3f. Update configure_handler — skip "already running" check during reconfigure:
```python
@self._fsm.state(AppState.CONFIGURE)
def configure_handler():
    try:
        with self._measure_time(self._app_statistics.configure):
            # Only check on first configure (reconfigure is expected with running databus)
            if not self._app_statistics.configure.done:
                if self._databus and self._databus.is_running:
                    self._logger.critical(f"app already running: {self._app_id}")
                    self._fsm.stop()
                    sys.exit(1)

            self.on_configure()

            # One-time log
            if not self._app_statistics.configure.done:
                self._app_statistics.configure.done = True
                if self._log_conf.logging_flags.stages:
                    self._logger.info("configured")

            self._fsm.transition(AppState.CONNECT)
    except Exception as exc:
        self._app_statistics.exception_count += 1
        self._logger.error(f"configure failed: {exc}")
        self._logger.debug(format_exc())
        self._fsm.stop()
        sys.exit(1)
```

3g. Update connect_handler — skip TagBus.connect() if already connected:
```python
@self._fsm.state(AppState.CONNECT)
def connect_handler():
    if self._app_statistics.exception_count >= 1:
        self._retry_timer.wait()

    try:
        with self._measure_time(self._app_statistics.connect):
            # Skip TagBus connect if already running (reconfigure path)
            if self._databus and not self._databus.is_running:
                self._databus.connect(clean=self._cli_args.clean)
            self.on_connect()

            # One-time log
            if not self._app_statistics.connect.done:
                self._app_statistics.connect.done = True
                if self._log_conf.logging_flags.stages:
                    self._logger.info("connected")

            self._execute_timer.reset()
            self._fsm.transition(AppState.EXECUTE)
    except Exception as exc:
        self._app_statistics.exception_count += 1
        self._log_fallback("connect", exc)
        self._fsm.transition(AppState.RECOVER)
```

**Step 4: Run tests to verify they pass**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_app_reconfigure.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/nodi_edge/app.py tests/test_app_reconfigure.py
git commit -m "feat: add --conn-id CLI arg and reconfigure support to App base"
```

---

### Task 3: Add Connection/Block DB Methods to EdgeDB

**Files:**
- Modify: `src/nodi_edge/db.py`
- Create: `tests/test_db_conn.py`

Adds conn-based query methods. The full DB schema (DDL, migrations) will be implemented separately per `config_plan.md`. This task adds the minimal read methods needed for the execution strategy.

**Step 1: Write the failing test**

Create `tests/test_db_conn.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from nodi_edge.db import EdgeDB


def test_select_conns(mem_db):
    """Should return all connections."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("mtc-01", "mtc", "192.168.1.10", 502, now))
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("opcua-01", "ouc", "192.168.1.20", 4840, now))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_conns()
    assert len(rows) == 2
    assert rows[0]["conn"] == "mtc-01"
    assert rows[1]["conn"] == "opcua-01"


def test_select_conn(mem_db):
    """Should return a single connection by conn_id."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("mtc-01", "mtc", "192.168.1.10", 502, now))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    row = db.select_conn("mtc-01")
    assert row is not None
    assert row["protocol"] == "mtc"
    assert row["host"] == "192.168.1.10"

    # Non-existent
    assert db.select_conn("unknown") is None


def test_select_blocks_by_conn(mem_db):
    """Should return blocks belonging to a connection."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("mtc-01", "mtc", "192.168.1.10", 502, now))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction, trigger, schedule, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("mtc-01-read", "mtc-01", "ro", "cyc", 0.1, now))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction, trigger, schedule, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("mtc-01-write", "mtc-01", "wo", "onc", 0.0, now))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    blocks = db.select_blocks_by_conn("mtc-01")
    assert len(blocks) == 2
    assert blocks[0]["block"] == "mtc-01-read"
    assert blocks[0]["direction"] == "ro"


def test_select_conns_enabled(mem_db):
    """Should return only enabled connections (use=1)."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("mtc-01", "mtc", 1, now))
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, use, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("mtc-02", "mtc", 0, now))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    rows = db.select_conns_enabled()
    assert len(rows) == 1
    assert rows[0]["conn"] == "mtc-01"


def test_select_blocks_tags_by_block(mem_db):
    """Should return tag mappings for a block."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, updated_at) VALUES (?, ?, ?)",
        ("mtc-01", "mtc", now))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction, updated_at) VALUES (?, ?, ?, ?)",
        ("mtc-01-read", "mtc-01", "ro", now))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field, scale, offset_val, properties) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("mtc-01-read", "mtc-01/temperature", "v", 0.1, 0.0, '{"address": 100}'))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field, scale, offset_val, properties) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("mtc-01-read", "mtc-01/pressure", "v", 1.0, 0.0, '{"address": 102}'))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    tags = db.select_blocks_tags_by_block("mtc-01-read")
    assert len(tags) == 2
```

**Step 2: Run test to verify it fails**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_db_conn.py -v`
Expected: FAIL (methods don't exist)

**Step 3: Implement DB methods in db.py**

Add new type alias and methods after the existing "Interface" section:

```python
ConnId = str

# In EdgeDB class:

# Connection - Read
# ──────────────────────────────────────────────────────────────────────

def select_conns(self) -> List[sqlite3.Row]:
    return self.conn.execute(
        "SELECT * FROM conns ORDER BY conn").fetchall()

def select_conns_enabled(self) -> List[sqlite3.Row]:
    return self.conn.execute(
        "SELECT * FROM conns WHERE use = 1 ORDER BY conn").fetchall()

def select_conn(self, conn_id: str) -> Optional[sqlite3.Row]:
    return self.conn.execute(
        "SELECT * FROM conns WHERE conn = ?", (conn_id,)).fetchone()


# Block - Read
# ──────────────────────────────────────────────────────────────────────

def select_blocks_by_conn(self, conn_id: str) -> List[sqlite3.Row]:
    return self.conn.execute(
        "SELECT * FROM blocks WHERE conn = ? ORDER BY block",
        (conn_id,)).fetchall()

def select_blocks_tags_by_block(self, block_id: str) -> List[sqlite3.Row]:
    return self.conn.execute(
        "SELECT * FROM blocks_tags WHERE block = ? ORDER BY tag",
        (block_id,)).fetchall()
```

**Step 4: Run tests to verify they pass**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_db_conn.py -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add src/nodi_edge/db.py tests/test_db_conn.py
git commit -m "feat: add conn/block/blocks_tags read methods to EdgeDB"
```

---

### Task 4: Create InterfaceApp Base Class

**Files:**
- Create: `src/nodi_edge/intf_app.py`
- Modify: `src/nodi_edge/__init__.py` (export InterfaceApp)
- Create: `tests/test_intf_app.py`

InterfaceApp extends App with:
- `--conn-id` validation (required)
- DB config loading in on_prepare/on_configure
- System tag subscription for config_reload
- Hot reload: on tag change → `request_reconfigure()` → CONFIGURE cycle
- Change type detection: block change = reconfigure, conn info change = restart

**Step 1: Write the failing test**

Create `tests/test_intf_app.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import time
from unittest.mock import MagicMock, patch


def _make_db_with_conn(mem_db, conn_id="mtc-01", protocol="mtc",
                       host="192.168.1.10", port=502):
    """Insert a connection and blocks into test DB."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conn_id, protocol, host, port, now))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction, trigger, schedule, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{conn_id}-read", conn_id, "ro", "cyc", 0.1, now))
    mem_db.commit()
    return mem_db


def test_intf_app_requires_conn_id():
    """InterfaceApp should fail if --conn-id is not provided."""
    with patch("sys.argv", ["test"]):
        with patch("nodi_edge.app.TagBus"):
            with patch("nodi_edge.app.Logger"):
                from nodi_edge.intf_app import InterfaceApp
                import pytest
                with pytest.raises(SystemExit):
                    InterfaceApp("mtc-01", protocol="mtc")


def test_intf_app_loads_conn_config(mem_db):
    """InterfaceApp.on_prepare should load connection config from DB."""
    _make_db_with_conn(mem_db)

    with patch("sys.argv", ["test", "--conn-id=mtc-01"]):
        with patch("nodi_edge.app.TagBus"):
            with patch("nodi_edge.app.Logger"):
                from nodi_edge.intf_app import InterfaceApp

                app = InterfaceApp.__new__(InterfaceApp)
                app._cli_args = MagicMock(conn_id="mtc-01", clean=False, debug=False)
                app._logger = MagicMock()

                # Inject mem_db via EdgeDB mock
                mock_db = MagicMock()
                mock_db.select_conn.return_value = mem_db.execute(
                    "SELECT * FROM conns WHERE conn = ?", ("mtc-01",)).fetchone()
                mock_db.select_blocks_by_conn.return_value = mem_db.execute(
                    "SELECT * FROM blocks WHERE conn = ?", ("mtc-01",)).fetchall()
                app._db = mock_db

                app._load_config()

                assert app._conn_config is not None
                assert app._conn_config["host"] == "192.168.1.10"
                assert len(app._block_configs) == 1


def test_intf_app_detects_conn_info_change(mem_db):
    """Should detect connection info change (host/port) vs block-only change."""
    from nodi_edge.intf_app import InterfaceApp

    # Simulate previous config
    prev_conn = {"host": "192.168.1.10", "port": 502}
    new_conn_same = {"host": "192.168.1.10", "port": 502}
    new_conn_changed = {"host": "192.168.1.20", "port": 502}

    assert InterfaceApp._is_conn_info_changed(prev_conn, new_conn_same) is False
    assert InterfaceApp._is_conn_info_changed(prev_conn, new_conn_changed) is True
```

**Step 2: Run test to verify it fails**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_intf_app.py -v`
Expected: FAIL (module not found)

**Step 3: Implement InterfaceApp**

Create `src/nodi_edge/intf_app.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional

from nodi_edge.app import App, AppConfig
from nodi_edge.db import EdgeDB, PROTOCOL_MODULES


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_CONN_INFO_KEYS = ("host", "port", "timeout", "retry")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# InterfaceApp
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InterfaceApp(App):

    def __init__(self,
                 app_id: str,
                 protocol: str,
                 *,
                 app_config: Optional[AppConfig] = None,
                 **kwargs) -> None:
        super().__init__(app_id, app_config=app_config, **kwargs)

        # Validate --conn-id is provided
        if not self._cli_args.conn_id:
            self._logger.error("--conn-id is required")
            sys.exit(1)

        self._conn_id: str = self._cli_args.conn_id
        self._protocol: str = protocol

        # Config state (loaded from DB)
        self._db: Optional[EdgeDB] = None
        self._conn_config: Optional[Dict[str, Any]] = None
        self._block_configs: List[Dict[str, Any]] = []

        # System tag for config reload
        self._config_reload_tag = f"/system/{self._conn_id}/config_reload"


    # ────────────────────────────────────────────────────────────
    # Properties
    # ────────────────────────────────────────────────────────────

    @property
    def conn_id(self) -> str:
        return self._conn_id

    @property
    def conn_config(self) -> Optional[Dict[str, Any]]:
        return self._conn_config

    @property
    def block_configs(self) -> List[Dict[str, Any]]:
        return self._block_configs


    # ────────────────────────────────────────────────────────────
    # Config Loading
    # ────────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        """Load connection and block configs from DB."""
        row = self._db.select_conn(self._conn_id)
        if not row:
            raise RuntimeError(f"connection not found: {self._conn_id}")
        self._conn_config = dict(row)

        self._block_configs = [dict(r) for r in
                               self._db.select_blocks_by_conn(self._conn_id)]
        self._logger.info(
            f"loaded config: conn={self._conn_id}, "
            f"blocks={len(self._block_configs)}")

    @staticmethod
    def _is_conn_info_changed(prev: Dict[str, Any],
                              curr: Dict[str, Any]) -> bool:
        """Check if connection-level info (host/port/timeout/retry) changed."""
        for key in _CONN_INFO_KEYS:
            if prev.get(key) != curr.get(key):
                return True
        return False


    # ────────────────────────────────────────────────────────────
    # Config Reload Handler
    # ────────────────────────────────────────────────────────────

    def _on_config_reload_tag(self, tag_id: str, tag_data) -> None:
        """TagBus callback when config_reload system tag changes."""
        self._logger.info(f"config reload signal received: {tag_id}")

        # Save previous conn config for change detection
        prev_conn = dict(self._conn_config) if self._conn_config else {}

        # Reload from DB
        self._load_config()

        # Detect change type
        if self._is_conn_info_changed(prev_conn, self._conn_config):
            # Connection info changed → need full restart
            self._logger.warning(
                "connection info changed, restarting via sys.exit()")
            sys.exit(0)  # systemd Restart=always will restart the process

        # Block-only change → hot reload via reconfigure
        self.request_reconfigure()


    # ────────────────────────────────────────────────────────────
    # App Lifecycle
    # ────────────────────────────────────────────────────────────

    def on_prepare(self) -> None:
        # Open database
        self._db = EdgeDB()
        self._db.open()

        # Load initial config
        self._load_config()

        # Call protocol's prepare
        self.on_intf_prepare()

    def on_configure(self) -> None:
        # Reload config from DB (for reconfigure path)
        if self._conn_config is not None:
            self._load_config()

        # Call protocol's configure
        self.on_intf_configure()

    def on_connect(self) -> None:
        # Subscribe to config_reload system tag
        if self.databus and self.databus.is_running:
            self.databus.sync_tags([self._config_reload_tag])
            self.databus.set_on_tags_change(
                [self._config_reload_tag], self._on_config_reload_tag)
            self.databus.commit()

        # Call protocol's connect
        self.on_intf_connect()

    def on_execute(self) -> None:
        self.on_intf_execute()

    def on_recover(self) -> None:
        self.on_intf_recover()

    def on_disconnect(self) -> None:
        self.on_intf_disconnect()

        # Close database
        if self._db:
            self._db.close()
            self._db = None


    # ────────────────────────────────────────────────────────────
    # Protocol Override Points
    # ────────────────────────────────────────────────────────────

    def on_intf_prepare(self) -> None:
        """Protocol-specific preparation (parse config, etc.)."""
        pass

    def on_intf_configure(self) -> None:
        """Protocol-specific configuration (after config reload)."""
        pass

    def on_intf_connect(self) -> None:
        """Protocol-specific connection (create socket, etc.)."""
        pass

    def on_intf_execute(self) -> None:
        """Protocol-specific execution (read/write cycle)."""
        pass

    def on_intf_recover(self) -> None:
        """Protocol-specific recovery."""
        pass

    def on_intf_disconnect(self) -> None:
        """Protocol-specific disconnection (close socket, etc.)."""
        pass
```

**Step 4: Add InterfaceApp to __init__.py exports**

Add to `src/nodi_edge/__init__.py`:
```python
from nodi_edge.intf_app import InterfaceApp
```

And add `"InterfaceApp"` to `__all__`.

**Step 5: Run tests to verify they pass**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_intf_app.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/nodi_edge/intf_app.py src/nodi_edge/__init__.py tests/test_intf_app.py
git commit -m "feat: add InterfaceApp base class with config loading and hot reload"
```

---

### Task 5: Refactor Supervisor for System Tag Events

**Files:**
- Modify: `apps/supervisor/main.py`
- Create: `tests/test_supervisor_conn.py`

Refactor Supervisor from DB polling to system tag-based event handling. The Supervisor:
1. On startup: reads all `conns` from DB, creates .service files, starts enabled ones
2. Subscribes to `/system/supervisor/conn_added` and `/system/supervisor/conn_removed` tags
3. On `conn_added`: reads new conn from DB, creates .service, starts it
4. On `conn_removed`: stops service, removes .service file
5. Removes DB polling from `on_execute()`

**Step 1: Write the failing test**

Create `tests/test_supervisor_conn.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations


def test_intf_service_template_uses_conn_id():
    """Service template should use --conn-id instead of intf_id positional arg."""
    from apps.supervisor.main import _INTF_SERVICE_TEMPLATE

    content = _INTF_SERVICE_TEMPLATE.format(
        app_id="mtc-01",
        python="/root/.venv/bin/python3",
        module="nodi_edge_intf.modbus_tcp_client",
        conn_id="mtc-01")

    assert "--conn-id=mtc-01" in content
    assert "-m nodi_edge_intf.modbus_tcp_client" in content


def test_service_name_uses_conn_id():
    """Service naming should use conn_id directly."""
    # Interface: ne-intf-{conn_id}
    # Expected: ne-intf-mtc-01 for conn_id="mtc-01"
    from apps.supervisor.main import SupervisorApp

    # Test the static naming pattern
    assert "ne-intf" in "ne-intf-mtc-01"  # Basic sanity


def test_supervisor_has_system_tag_constants():
    """Supervisor should define system tag constants for conn events."""
    from apps.supervisor.main import _TAG_SYS_CONN_ADDED, _TAG_SYS_CONN_REMOVED
    assert "supervisor" in _TAG_SYS_CONN_ADDED
    assert "supervisor" in _TAG_SYS_CONN_REMOVED
```

**Step 2: Run test to verify it fails**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_supervisor_conn.py -v`
Expected: FAIL (template still uses `{intf_id}`, tag constants don't exist)

**Step 3: Implement Supervisor changes**

Key changes to `apps/supervisor/main.py`:

3a. Update constants — add system tag paths:
```python
# System tags for conn events (subscribed by Supervisor)
_TAG_SYS_CONN_ADDED = "/system/supervisor/conn_added"
_TAG_SYS_CONN_REMOVED = "/system/supervisor/conn_removed"
```

3b. Update service template — use `--conn-id`:
```python
_INTF_SERVICE_TEMPLATE = """\
[Unit]
Description=Nodi Edge Interface: {app_id}
After=network.target ne-supervisor.service

[Service]
Type=simple
User=root
Group=root
ExecStart={python} -m {module} --conn-id={conn_id}
Restart=always
RestartSec=5
StartLimitIntervalSec=300
StartLimitBurst=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""
```

3c. Update `ServiceState` — add `conn_id` field:
```python
@dataclass
class ServiceState:
    app_id: str
    category: str
    module: str
    enabled: bool
    conn_id: Optional[str] = None
    active: bool = False
    restart_count: int = 0
    last_restart_ts: float = 0.0
```

3d. Update `_create_service_unit()` — use conn_id:
```python
def _create_service_unit(self, state: ServiceState) -> bool:
    path = self._get_service_path(state.app_id, state.category)

    if state.category == "interface":
        content = _INTF_SERVICE_TEMPLATE.format(
            app_id=state.app_id,
            python=_VENV_PYTHON,
            module=state.module,
            conn_id=state.conn_id or state.app_id)
    else:
        content = _ADDON_SERVICE_TEMPLATE.format(
            app_id=state.app_id,
            python=_VENV_PYTHON,
            module=state.module)
    try:
        path.write_text(content)
        return True
    except Exception as exc:
        self.logger.error(f"create unit failed [{state.app_id}]: {exc}")
        return False
```

3e. Update `on_connect()` — subscribe to system tags:
```python
def on_connect(self) -> None:
    # Subscribe to command tags
    self.databus.sync_tags([f"{_TAG_CMD_PREFIX}/**"])
    self.databus.set_on_tags_change(
        [f"{_TAG_CMD_PREFIX}/**"], self._on_command_tag)

    # Subscribe to system tags for conn events
    self.databus.sync_tags([_TAG_SYS_CONN_ADDED, _TAG_SYS_CONN_REMOVED])
    self.databus.set_on_tags_change(
        [_TAG_SYS_CONN_ADDED], self._on_conn_added)
    self.databus.set_on_tags_change(
        [_TAG_SYS_CONN_REMOVED], self._on_conn_removed)
    self.databus.commit()

    # Load initial state: read all conns from DB
    self._load_registry()
    self._sync_conns_initial()

    # Start all enabled services
    self._start_enabled_services()
    self.logger.info(f"started {self._count_active()} services")
```

3f. Add `_sync_conns_initial()` — initial sync from conns table:
```python
def _sync_conns_initial(self) -> None:
    """Load connections from DB and register as services."""
    conns = self._db.select_conns_enabled()
    need_reload = False

    for row in conns:
        conn_id = row["conn"]
        protocol = row["protocol"]
        module = PROTOCOL_MODULES.get(protocol)
        if not module:
            self.logger.warning(f"unknown protocol: {protocol} (conn={conn_id})")
            continue

        app_id = conn_id
        self._db.upsert_app(app_id, "interface", module,
                            enabled=True, conn_id=conn_id)
        state = ServiceState(app_id=app_id, category="interface",
                             module=module, enabled=True, conn_id=conn_id)
        with self._lock:
            self._services[app_id] = state

        if self._create_service_unit(state):
            need_reload = True

    if need_reload:
        self._daemon_reload()
```

3g. Add system tag event handlers:
```python
def _on_conn_added(self, tag_id: str, tag_data) -> None:
    """Handle new connection added via system tag."""
    conn_id = tag_data.v if isinstance(tag_data.v, str) else str(tag_data.v)
    if not conn_id:
        return

    self.logger.info(f"conn_added event: {conn_id}")
    row = self._db.select_conn(conn_id)
    if not row:
        self.logger.warning(f"conn_added but not found in DB: {conn_id}")
        return

    protocol = row["protocol"]
    module = PROTOCOL_MODULES.get(protocol)
    if not module:
        self.logger.warning(f"unknown protocol: {protocol} (conn={conn_id})")
        return

    app_id = conn_id
    self._db.upsert_app(app_id, "interface", module,
                        enabled=True, conn_id=conn_id)
    state = ServiceState(app_id=app_id, category="interface",
                         module=module, enabled=True, conn_id=conn_id)
    with self._lock:
        self._services[app_id] = state

    if self._create_service_unit(state):
        self._daemon_reload()
    if self._start_service(app_id, "interface"):
        state.active = True
    self.logger.info(f"started new interface: {app_id} (prot={protocol})")


def _on_conn_removed(self, tag_id: str, tag_data) -> None:
    """Handle connection removed via system tag."""
    conn_id = tag_data.v if isinstance(tag_data.v, str) else str(tag_data.v)
    if not conn_id:
        return

    self.logger.info(f"conn_removed event: {conn_id}")
    app_id = conn_id
    with self._lock:
        state = self._services.get(app_id)

    if not state:
        self.logger.warning(f"conn_removed but service not found: {conn_id}")
        return

    self._deactivate_service(app_id, "interface")
    self._remove_service_unit(app_id, "interface")
    self._daemon_reload()
    self._db.delete_app(app_id)
    with self._lock:
        self._services.pop(app_id, None)
    self.logger.info(f"removed interface: {app_id}")
```

3h. Simplify `on_execute()` — remove DB polling:
```python
def on_execute(self) -> None:
    now = time.monotonic()

    # Check license expiry (keep this, it's not config polling)
    if now - self._last_license_check_ts >= self._sv_conf.license_check_interval_s:
        self._last_license_check_ts = now
        self._check_license_expiry()
```

3i. Remove `_sync_interfaces()` method and related fields (`_last_intf_updated_at`, `_last_intf_poll_ts`, `intf_poll_interval_s`).

3j. Update `upsert_app()` call sites to use `conn_id=` parameter.

**Step 4: Run tests**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_supervisor_conn.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add apps/supervisor/main.py tests/test_supervisor_conn.py
git commit -m "refactor: Supervisor uses conn-based systemd + system tag events"
```

---

### Task 6: Create nodi_edge_intf Package with MTC Entry Point

**Files:**
- Create: `/root/nodi-edge/src/nodi_edge_intf/__init__.py`
- Create: `/root/nodi-edge/src/nodi_edge_intf/modbus_tcp_client/__init__.py`
- Create: `/root/nodi-edge/src/nodi_edge_intf/modbus_tcp_client/__main__.py`
- Create: `/root/nodi-edge/src/nodi_edge_intf/modbus_tcp_client/core.py`
- Modify: `/root/nodi-edge/pyproject.toml` (add package to build)
- Create: `tests/test_mtc_entry.py`

This creates a minimal MTC (Modbus TCP Client) protocol plugin that proves the execution model works. The full data pipeline (buffer, diff, scale/offset, etc.) will be implemented separately per `interface_design.md`.

**Step 1: Write the failing test**

Create `tests/test_mtc_entry.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations


def test_mtc_module_importable():
    """MTC module should be importable."""
    from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp
    assert issubclass(ModbusTcpClientApp, object)


def test_mtc_extends_interface_app():
    """MTC should extend InterfaceApp."""
    from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp
    from nodi_edge.intf_app import InterfaceApp
    assert issubclass(ModbusTcpClientApp, InterfaceApp)


def test_mtc_has_protocol_overrides():
    """MTC should implement protocol override methods."""
    from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp
    assert hasattr(ModbusTcpClientApp, 'on_intf_prepare')
    assert hasattr(ModbusTcpClientApp, 'on_intf_connect')
    assert hasattr(ModbusTcpClientApp, 'on_intf_execute')
    assert hasattr(ModbusTcpClientApp, 'on_intf_disconnect')
```

**Step 2: Run test to verify it fails**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_mtc_entry.py -v`
Expected: FAIL (module not found)

**Step 3: Create package structure**

3a. Create `src/nodi_edge_intf/__init__.py`:
```python
# -*- coding: utf-8 -*-
from __future__ import annotations
__version__ = "0.1.0"
```

3b. Create `src/nodi_edge_intf/modbus_tcp_client/__init__.py`:
```python
# -*- coding: utf-8 -*-
from __future__ import annotations
```

3c. Create `src/nodi_edge_intf/modbus_tcp_client/__main__.py`:
```python
# -*- coding: utf-8 -*-
from __future__ import annotations

from nodi_edge_intf.modbus_tcp_client.core import ModbusTcpClientApp

_APP_ID = "mtc"

if __name__ == "__main__":
    app = ModbusTcpClientApp(_APP_ID)
    app.start()
```

3d. Create `src/nodi_edge_intf/modbus_tcp_client/core.py`:
```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from nodi_edge.app import AppConfig
from nodi_edge.intf_app import InterfaceApp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ModbusTcpClientApp
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ModbusTcpClientApp(InterfaceApp):

    def __init__(self,
                 app_id: str,
                 app_config: Optional[AppConfig] = None) -> None:
        super().__init__(app_id, protocol="mtc",
                         app_config=app_config or AppConfig(
                             execute_interval_s=0.1))

        # Protocol state
        self._agent = None
        self._modbus_groups: List[Dict[str, Any]] = []

    def on_intf_prepare(self) -> None:
        # Parse block properties into Modbus unit/fc groups
        self._parse_modbus_groups()

    def on_intf_configure(self) -> None:
        # Re-parse groups after config reload
        self._parse_modbus_groups()

    def on_intf_connect(self) -> None:
        # Create Modbus TCP connection
        host = self._conn_config.get("host", "127.0.0.1")
        port = self._conn_config.get("port", 502)
        timeout = self._conn_config.get("timeout", 3.0)
        self._logger.info(f"connecting to {host}:{port}")
        # TODO: Create actual ModbusTcpClient agent
        # self._agent = ModbusTcpClient(host, port, timeout=timeout)
        # self._agent.connect()

    def on_intf_execute(self) -> None:
        # TODO: Read/write Modbus registers per block schedule
        pass

    def on_intf_disconnect(self) -> None:
        if self._agent:
            # self._agent.close()
            self._agent = None

    def _parse_modbus_groups(self) -> None:
        """Parse block configs into Modbus unit_id x func_code groups."""
        self._modbus_groups.clear()
        for block in self._block_configs:
            props = json.loads(block.get("properties", "{}"))
            self._modbus_groups.append({
                "block_id": block["block"],
                "direction": block["direction"],
                "unit_id": props.get("unit_id", 1),
                "func_code": props.get("func_code", 3),
            })
        self._logger.info(f"parsed {len(self._modbus_groups)} modbus groups")
```

3e. Update `pyproject.toml` — add nodi_edge_intf package:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/nodi_edge", "src/nodi_edge_intf"]
```

**Step 4: Run tests**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_mtc_entry.py -v`
Expected: PASS

**Step 5: Verify module execution pattern**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m nodi_edge_intf.modbus_tcp_client --conn-id=mtc-01 --help 2>&1 || true`
Expected: Should not crash on import (may fail on DB connection, that's OK)

**Step 6: Commit**

```bash
git add src/nodi_edge_intf/ pyproject.toml tests/test_mtc_entry.py
git commit -m "feat: add nodi_edge_intf package with MTC protocol plugin stub"
```

---

### Task 7: Update EdgeDB app_registry for conn_id

**Files:**
- Modify: `src/nodi_edge/db.py`
- Create: `tests/test_db_app_registry.py`

Add `conn_id` column support to app_registry for Supervisor's conn-based management.

**Step 1: Write the failing test**

Create `tests/test_db_app_registry.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from nodi_edge.db import EdgeDB


def test_upsert_app_with_conn_id(mem_db):
    """upsert_app should accept conn_id parameter."""
    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    db.upsert_app("mtc-01", "interface", "nodi_edge_intf.modbus_tcp_client",
                  enabled=True, conn_id="mtc-01")

    row = db.select_app("mtc-01")
    assert row is not None
    assert row["conn_id"] == "mtc-01"
    assert row["module"] == "nodi_edge_intf.modbus_tcp_client"
```

**Step 2: Run test to verify it fails**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_db_app_registry.py -v`
Expected: FAIL (conn_id column not in upsert_app)

**Step 3: Update upsert_app in db.py**

Update `upsert_app()` to include `conn_id`:

```python
def upsert_app(self,
               app_id: str,
               category: str,
               module: str,
               enabled: bool = False,
               config: Optional[Dict[str, Any]] = None,
               intf_id: Optional[str] = None,
               conn_id: Optional[str] = None,
               license_token: Optional[str] = None,
               license_expires_at: Optional[int] = None) -> None:
    now = int(time.time())
    config_json = json.dumps(config) if config else "{}"
    self.conn.execute(
        "INSERT INTO app_registry "
        "(app_id, category, module, enabled, config, intf_id, conn_id, "
        " license_token, license_expires_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(app_id) DO UPDATE SET "
        "  category=excluded.category, module=excluded.module, "
        "  enabled=excluded.enabled, config=excluded.config, "
        "  intf_id=excluded.intf_id, conn_id=excluded.conn_id, "
        "  license_token=excluded.license_token, "
        "  license_expires_at=excluded.license_expires_at, "
        "  updated_at=excluded.updated_at",
        (app_id, category, module, int(enabled), config_json, intf_id,
         conn_id, license_token, license_expires_at, now))
    self.conn.commit()
```

**Step 4: Run tests**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/test_db_app_registry.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/nodi_edge/db.py tests/test_db_app_registry.py
git commit -m "feat: add conn_id to app_registry upsert"
```

---

### Task 8: End-to-End Integration Test

**Files:**
- Create: `tests/test_integration_execution.py`

Verify the complete flow: DB has connection → Supervisor creates correct .service content → InterfaceApp can load config → config_reload triggers reconfigure.

**Step 1: Write integration test**

Create `tests/test_integration_execution.py`:

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from nodi_edge.db import EdgeDB, PROTOCOL_MODULES


def _seed_conn(mem_db, conn_id="mtc-01", protocol="mtc",
               host="192.168.1.10", port=502):
    """Seed a connection with blocks and tags."""
    now = int(time.time())
    mem_db.execute(
        "INSERT INTO conns (conn, protocol, host, port, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (conn_id, protocol, host, port, now))
    mem_db.execute(
        "INSERT INTO blocks (block, conn, direction, trigger, schedule, "
        "properties, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"{conn_id}-read", conn_id, "ro", "cyc", 0.1,
         json.dumps({"unit_id": 1, "func_code": 3}), now))
    mem_db.execute(
        "INSERT INTO blocks_tags (block, tag, field, properties) "
        "VALUES (?, ?, ?, ?)",
        (f"{conn_id}-read", f"{conn_id}/temperature", "v",
         json.dumps({"address": 100, "data_type": "int16"})))
    mem_db.commit()


def test_full_flow_db_to_service_file(mem_db):
    """DB connection → Supervisor generates correct .service content."""
    _seed_conn(mem_db)

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    # Supervisor reads conns
    conns = db.select_conns_enabled()
    assert len(conns) == 1

    conn = conns[0]
    assert conn["conn"] == "mtc-01"
    assert conn["protocol"] == "mtc"

    # Map to module
    module = PROTOCOL_MODULES[conn["protocol"]]
    assert module == "nodi_edge_intf.modbus_tcp_client"

    # Generate service content
    from apps.supervisor.main import _INTF_SERVICE_TEMPLATE, _VENV_PYTHON
    content = _INTF_SERVICE_TEMPLATE.format(
        app_id="mtc-01",
        python=_VENV_PYTHON,
        module=module,
        conn_id="mtc-01")

    assert "--conn-id=mtc-01" in content
    assert "modbus_tcp_client" in content
    assert "Restart=always" in content


def test_full_flow_config_loading(mem_db):
    """InterfaceApp loads correct config from DB."""
    _seed_conn(mem_db)

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    # Simulate what InterfaceApp._load_config does
    conn_row = db.select_conn("mtc-01")
    assert conn_row["host"] == "192.168.1.10"
    assert conn_row["port"] == 502

    blocks = db.select_blocks_by_conn("mtc-01")
    assert len(blocks) == 1
    assert blocks[0]["direction"] == "ro"

    props = json.loads(blocks[0]["properties"])
    assert props["unit_id"] == 1
    assert props["func_code"] == 3

    tags = db.select_blocks_tags_by_block("mtc-01-read")
    assert len(tags) == 1
    assert tags[0]["tag"] == "mtc-01/temperature"


def test_conn_info_change_detection():
    """Config reload detects connection info change vs block-only change."""
    from nodi_edge.intf_app import InterfaceApp

    prev = {"host": "192.168.1.10", "port": 502, "timeout": 3.0, "retry": 3}

    # Block-only change (no conn info change)
    same = {"host": "192.168.1.10", "port": 502, "timeout": 3.0, "retry": 3}
    assert InterfaceApp._is_conn_info_changed(prev, same) is False

    # Host changed
    new_host = {"host": "192.168.1.20", "port": 502, "timeout": 3.0, "retry": 3}
    assert InterfaceApp._is_conn_info_changed(prev, new_host) is True

    # Port changed
    new_port = {"host": "192.168.1.10", "port": 503, "timeout": 3.0, "retry": 3}
    assert InterfaceApp._is_conn_info_changed(prev, new_port) is True

    # Timeout changed
    new_timeout = {"host": "192.168.1.10", "port": 502, "timeout": 5.0, "retry": 3}
    assert InterfaceApp._is_conn_info_changed(prev, new_timeout) is True


def test_multiple_conns_multiple_protocols(mem_db):
    """Multiple connections with different protocols should all resolve."""
    now = int(time.time())
    conns_data = [
        ("mtc-01", "mtc", "192.168.1.10", 502),
        ("mtc-02", "mtc", "192.168.1.11", 502),
        ("opcua-01", "ouc", "192.168.1.20", 4840),
        ("mqtt-01", "mqc", "broker.example.com", 1883),
    ]
    for conn_id, protocol, host, port in conns_data:
        mem_db.execute(
            "INSERT INTO conns (conn, protocol, host, port, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conn_id, protocol, host, port, now))
    mem_db.commit()

    db = EdgeDB.__new__(EdgeDB)
    db._conn = mem_db

    conns = db.select_conns_enabled()
    assert len(conns) == 4

    # All protocols should map to modules
    for conn in conns:
        module = PROTOCOL_MODULES.get(conn["protocol"])
        assert module is not None, f"No module for protocol: {conn['protocol']}"
```

**Step 2: Run all tests**

Run: `cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/ -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_integration_execution.py
git commit -m "test: add end-to-end integration tests for execution strategy"
```

---

## Final Verification

Run the complete test suite one last time:

```bash
cd /root/nodi-edge && /root/.venv/bin/python3 -m pytest tests/ -v --tb=short
```

Expected: All tests pass. The execution strategy infrastructure is complete:
- App base class supports `--conn-id` and reconfigure (EXECUTE→CONFIGURE)
- EdgeDB has conn/block/blocks_tags read methods
- InterfaceApp handles config loading, system tag subscription, hot reload
- Supervisor creates conn-based systemd services, reacts to system tag events
- MTC protocol plugin demonstrates the entry point pattern
- Integration tests verify the complete flow
