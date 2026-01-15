# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from traceback import format_exc
from typing import Optional

from nodi_databus import Databus
from nodi_libs.fsm import FiniteStateMachine
from nodi_libs.logger import Logger, LoggingLevel

from nodi_edge.states import AppState

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_DEFAULT_DOMAIN_ID = "default"
_DEFAULT_RETRY_DELAY_S = 3.0
_DEFAULT_EXECUTE_INTERVAL_S = 1.0
_DEFAULT_EXCEPTION_LIMIT = 10

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class App:

    def __init__(self,
                 app_id: str,
                 domain_id: str = _DEFAULT_DOMAIN_ID,
                 *,
                 retry_delay_s: float = _DEFAULT_RETRY_DELAY_S,
                 execute_interval_s: float = _DEFAULT_EXECUTE_INTERVAL_S,
                 exception_limit: int = _DEFAULT_EXCEPTION_LIMIT,
                 logging_level: LoggingLevel = LoggingLevel.INFO,
                 console_out: bool = True,
                 file_out: bool = False,
                 log_file_path: Optional[str] = None) -> None:

        # Parameters
        self._app_id = app_id
        self._domain_id = domain_id
        self._retry_delay_s = retry_delay_s
        self._execute_interval_s = execute_interval_s
        self._exception_limit = exception_limit

        # Stats
        self._exception_count: int = 0
        self._execute_count: int = 0

        # Logger
        self._logger = Logger(logger_name=f"nodi-edge.{app_id}",
                              logging_level=logging_level,
                              console_out=console_out,
                              file_out=file_out,
                              file_path=log_file_path or f"./log/{app_id}.log")

        # Databus (not connected yet)
        self._databus: Optional[Databus] = None

        # FSM
        self._fsm = FiniteStateMachine()
        self._setup_fsm()

    # ────────────────────────────────────────────────────────────
    # Properties
    # ────────────────────────────────────────────────────────────

    @property
    def app_id(self) -> str:
        return self._app_id

    @property
    def databus(self) -> Optional[Databus]:
        return self._databus

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def fsm(self) -> FiniteStateMachine:
        return self._fsm

    @property
    def current_state(self) -> Optional[AppState]:
        return self._fsm.current_state

    @property
    def is_running(self) -> bool:
        return self._fsm.is_running

    # ────────────────────────────────────────────────────────────
    # FSM Setup
    # ────────────────────────────────────────────────────────────

    def _setup_fsm(self) -> None:

        # Limit transitions
        self._fsm.limit_transitions({
            AppState.PREPARE: [AppState.INITIATE],
            AppState.INITIATE: [AppState.EXECUTE, AppState.TERMINATE],
            AppState.EXECUTE: [AppState.EXECUTE, AppState.TERMINATE],
            AppState.TERMINATE: [AppState.INITIATE],
        })

        # State handlers
        @self._fsm.state(AppState.PREPARE)
        def prepare_handler():
            self._on_prepare()
            self._fsm.transition(AppState.INITIATE)

        @self._fsm.state(AppState.INITIATE)
        def initiate_handler():
            try:
                self._on_initiate()
                self._exception_count = 0
                self._fsm.transition(AppState.EXECUTE)
            except Exception as exc:
                self._handle_exception("initiate", exc)
                self._fsm.transition(AppState.TERMINATE)

        @self._fsm.state(AppState.EXECUTE)
        def execute_handler():
            try:
                self._on_execute()
                self._execute_count += 1
                self._exception_count = 0
                time.sleep(self._execute_interval_s)
                self._fsm.transition(AppState.EXECUTE)
            except Exception as exc:
                self._handle_exception("execute", exc)
                self._fsm.transition(AppState.TERMINATE)

        @self._fsm.state(AppState.TERMINATE)
        def terminate_handler():
            try:
                self._on_terminate()
            except Exception as exc:
                self._logger.warning(f"terminate error: {exc}")

            # Retry delay
            time.sleep(self._retry_delay_s)
            self._fsm.transition(AppState.INITIATE)

        # Error callback
        @self._fsm.on_error()
        def error_handler(exc: Exception):
            self._logger.error(f"fsm error: {exc}")
            self._logger.debug(format_exc())

        # Transition callback
        @self._fsm.on_transition()
        def transition_handler(prev: AppState, next: AppState):
            self._logger.debug(f"state: {prev} -> {next}")

    # ────────────────────────────────────────────────────────────
    # Internal Handlers
    # ────────────────────────────────────────────────────────────

    def _on_prepare(self) -> None:
        self._logger.info(f"preparing app: {self._app_id}")

        # Create databus instance
        self._databus = Databus(self._app_id, self._domain_id)

        # Override point
        self.on_prepare()

    def _on_initiate(self) -> None:
        self._logger.info(f"initiating app: {self._app_id}")

        # Connect databus
        if self._databus:
            self._databus.connect()

        # Override point
        self.on_initiate()

    def _on_execute(self) -> None:
        # Override point
        self.on_execute()

    def _on_terminate(self) -> None:
        self._logger.warning(f"terminating app: {self._app_id}")

        # Disconnect databus
        if self._databus:
            try:
                self._databus.disconnect()
            except Exception:
                pass

        # Override point
        self.on_terminate()

    def _handle_exception(self, loc: str, exc: Exception) -> None:
        self._exception_count += 1
        if self._exception_count <= self._exception_limit:
            self._logger.warning(f"loc: {loc} | "
                                 f"err: {exc} | "
                                 f"cnt: {self._exception_count}/{self._exception_limit}")
            self._logger.debug(format_exc())

    # ────────────────────────────────────────────────────────────
    # Override Points
    # ────────────────────────────────────────────────────────────

    def on_prepare(self) -> None:
        pass

    def on_initiate(self) -> None:
        pass

    def on_execute(self) -> None:
        pass

    def on_terminate(self) -> None:
        pass

    # ────────────────────────────────────────────────────────────
    # Lifecycle
    # ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._fsm.start(AppState.PREPARE)

    def stop(self, timeout: float = 5.0) -> None:
        self._fsm.stop(timeout)

        # Cleanup databus
        if self._databus:
            try:
                self._databus.disconnect()
            except Exception:
                pass

    def run(self) -> None:
        self.start()

        # Block until stopped
        try:
            while self._fsm.is_running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self._logger.info("keyboard interrupt received")
        finally:
            self.stop()
