# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from nodi_edge.states import AppState


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _create_app(**kwargs):
    """Create an App instance with all external dependencies mocked."""
    with patch("nodi_edge.app.TagBus"), \
         patch("nodi_edge.app.TagBusConfig"), \
         patch("nodi_edge.app.FiniteStateMachine"), \
         patch("nodi_edge.app.Logger"), \
         patch("nodi_edge.app.PeriodicTimer"):
        from nodi_edge.app import App
        app = App("test-app", **kwargs)
    return app


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - CLI Arguments
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestCliArgs:

    def test_conn_id_parsed(self):
        """Verify --conn-id is parsed from CLI args."""
        test_args = ["prog", "--conn-id", "my-conn-1"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()
        assert app._cli_args.conn_id == "my-conn-1"

    def test_conn_id_default_none(self):
        """Verify --conn-id defaults to None when not provided."""
        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()
        assert app._cli_args.conn_id is None

    def test_conn_id_with_other_args(self):
        """Verify --conn-id works alongside --clean and --debug."""
        test_args = ["prog", "--conn-id", "conn-42", "--clean", "--debug"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()
        assert app._cli_args.conn_id == "conn-42"
        assert app._cli_args.clean is True
        assert app._cli_args.debug is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - FSM Transitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestFsmTransitions:

    def test_execute_allows_configure_transition(self):
        """Verify EXECUTE state allows transition to CONFIGURE."""
        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()

        # Extract the limit_transitions call args
        fsm_mock = app._fsm
        fsm_mock.limit_transitions.assert_called_once()
        transitions = fsm_mock.limit_transitions.call_args[0][0]

        assert AppState.CONFIGURE in transitions[AppState.EXECUTE]
        assert AppState.RECOVER in transitions[AppState.EXECUTE]

    def test_all_transitions_present(self):
        """Verify all expected FSM transitions are defined."""
        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()

        transitions = app._fsm.limit_transitions.call_args[0][0]

        assert transitions[AppState.PREPARE] == [AppState.CONFIGURE]
        assert transitions[AppState.CONFIGURE] == [AppState.CONNECT]
        assert transitions[AppState.CONNECT] == [AppState.EXECUTE, AppState.RECOVER]
        assert transitions[AppState.EXECUTE] == [AppState.CONFIGURE, AppState.RECOVER]
        assert transitions[AppState.RECOVER] == [AppState.EXECUTE, AppState.DISCONNECT]
        assert transitions[AppState.DISCONNECT] == [AppState.CONNECT]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests - Reconfigure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestReconfigure:

    def test_reconfigure_event_exists(self):
        """Verify _reconfigure_event is a threading.Event."""
        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()
        assert isinstance(app._reconfigure_event, threading.Event)

    def test_request_reconfigure_sets_event(self):
        """Verify request_reconfigure() sets the event."""
        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()

        assert not app._reconfigure_event.is_set()
        app.request_reconfigure()
        assert app._reconfigure_event.is_set()

    def test_request_reconfigure_idempotent(self):
        """Verify calling request_reconfigure() multiple times is safe."""
        test_args = ["prog"]
        with patch.object(sys, "argv", test_args):
            app = _create_app()

        app.request_reconfigure()
        app.request_reconfigure()
        assert app._reconfigure_event.is_set()
