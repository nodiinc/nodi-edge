# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from traceback import format_exc
from contextlib import contextmanager
from typing import Deque, Generator, Optional

from tagbus import TagBus
from nodi_libs.fsm import FiniteStateMachine
from nodi_libs.logger import Logger, LoggerConfig, LoggingLevel
from nodi_libs.timer import PeriodicTimer

from nodi_edge.states import AppState

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_DEFAULT_DOMAIN_ID = "default"
_DATA_DIR = "/home/nodi/nodi-edge-data"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class AppConfig:
    execute_interval_s: float = 1.0
    manage_interval_s: float = 1.0
    retry_delay_s: float = 3.0
    pause_time_s: float = 0.0
    exception_limit: int = 1
    maf_size: int = 60
    time_decimal: int = 6
    suppress_stdout: bool = False
    process_title: str = "ne-{app_id}"


@dataclass
class LoggingFlags:
    stages: bool = True
    fallback: bool = True
    traceback: bool = True


@dataclass
class AppLoggerConfig(LoggerConfig):
    name: str = "ne-{app_id}"
    file_out: bool = True
    file_path: str = f"{_DATA_DIR}/log/ne-{{app_id}}.log"
    logging_flags: LoggingFlags = field(default_factory=LoggingFlags)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Utils
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MovingAverage:

    def __init__(self, size: int = 10, decimal: int = 4):
        self.size = size
        self.decimal = decimal
        self._samples: Deque[float] = deque()
        self._sum: float = 0.0
        self.mean: float = 0.0

    def add(self, sample: float) -> None:
        self._samples.append(sample)
        self._sum += sample
        if len(self._samples) > self.size:
            self._sum -= self._samples.popleft()
        self.mean = round(self._sum / len(self._samples), self.decimal)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Statistics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class StageStatistics:
    elapsed_time: float = 0.0
    done: bool = False


@dataclass
class AppStatistics:
    prepare: StageStatistics = field(default_factory=StageStatistics)
    configure: StageStatistics = field(default_factory=StageStatistics)
    connect: StageStatistics = field(default_factory=StageStatistics)
    execute: StageStatistics = field(default_factory=StageStatistics)
    recover: StageStatistics = field(default_factory=StageStatistics)
    disconnect: StageStatistics = field(default_factory=StageStatistics)
    execute_maf: MovingAverage = field(default_factory=MovingAverage)
    exception_count: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class App:

    def __init__(self,
                 app_id: str,
                 domain_id: str = _DEFAULT_DOMAIN_ID,
                 *,
                 app_config: Optional[AppConfig] = None,
                 logger_config: Optional[AppLoggerConfig] = None) -> None:

        # Parse CLI arguments
        self._cli_args = self._parse_cli_args()

        # Config
        self._app_conf = app_config or AppConfig()
        self._log_conf = logger_config or AppLoggerConfig()
        self._log_conf.name = self._log_conf.name.format(app_id=app_id)
        self._log_conf.file_path = self._log_conf.file_path.format(app_id=app_id)

        # Parameters
        self._app_id = app_id
        self._domain_id = domain_id

        # Suppress stdout (disabled if debug mode)
        if self._app_conf.suppress_stdout and not self._cli_args.debug:
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")

        # Set process title
        try:
            from setproctitle import setproctitle
            setproctitle(self._app_conf.process_title.format(app_id=app_id))
        except ImportError:
            pass

        # Logger
        self._logger = Logger(self._log_conf)

        # TagBus
        self._databus: Optional[TagBus] = None

        # Stats
        self._app_statistics = AppStatistics(
            execute_maf=MovingAverage(size=self._app_conf.maf_size,
            decimal=self._app_conf.time_decimal))

        # Timers
        self._execute_timer = PeriodicTimer(self._app_conf.execute_interval_s)
        self._manage_timer = PeriodicTimer(self._app_conf.manage_interval_s)
        self._retry_timer = PeriodicTimer(self._app_conf.retry_delay_s)

        # FSM
        self._fsm = FiniteStateMachine()
        self._setup_fsm()

    def _parse_cli_args(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--clean", action="store_true",
                            help="clean databus state on connect")
        parser.add_argument("--debug", action="store_true",
                            help="enable databus debug output")
        args, _ = parser.parse_known_args()
        return args

    # ────────────────────────────────────────────────────────────
    # Properties
    # ────────────────────────────────────────────────────────────

    @property
    def app_id(self) -> str:
        return self._app_id

    @property
    def databus(self) -> Optional[TagBus]:
        return self._databus

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def stats(self) -> AppStatistics:
        return self._app_statistics

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
    # Helpers
    # ────────────────────────────────────────────────────────────

    @contextmanager
    def _measure_time(self, stage: StageStatistics) -> Generator[None, None, None]:
        start_time = time.perf_counter()
        yield
        stage.elapsed_time = round(time.perf_counter() - start_time,
                                   self._app_conf.time_decimal)

    def _log_fallback(self, location: str, exc: Exception) -> None:
        if self._app_statistics.exception_count <= self._app_conf.exception_limit:
            if self._log_conf.logging_flags.fallback:
                self._logger.warning(f"loc: {location} | "
                                     f"err: {exc} | "
                                     f"cnt: {self._app_statistics.exception_count}/"
                                     f"{self._app_conf.exception_limit}",
                                     stacklevel=3)
            if self._log_conf.logging_flags.traceback:
                self._logger.debug(format_exc(), stacklevel=3)

    def _reset_done_flags_for_retry(self) -> None:
        self._app_statistics.connect.done = False
        self._app_statistics.execute.done = False

    def _reset_done_flags_for_success(self) -> None:
        self._app_statistics.recover.done = False
        self._app_statistics.disconnect.done = False
        self._app_statistics.exception_count = 0

    # ────────────────────────────────────────────────────────────
    # FSM Setup
    # ────────────────────────────────────────────────────────────

    def _setup_fsm(self) -> None:

        self._fsm.limit_transitions({AppState.PREPARE: [AppState.CONFIGURE],
                                     AppState.CONFIGURE: [AppState.CONNECT],
                                     AppState.CONNECT: [AppState.EXECUTE, AppState.RECOVER],
                                     AppState.EXECUTE: [AppState.RECOVER],
                                     AppState.RECOVER: [AppState.EXECUTE, AppState.DISCONNECT],
                                     AppState.DISCONNECT: [AppState.CONNECT],})

        @self._fsm.state(AppState.PREPARE)
        def prepare_handler():
            try:
                with self._measure_time(self._app_statistics.prepare):
                    self._databus = TagBus(self._app_id, self._domain_id,
                                            debug=self._cli_args.debug,
                                            heartbeat_interval_s=1.0)
                    self.on_prepare()

                    # One-time log
                    if not self._app_statistics.prepare.done:
                        self._app_statistics.prepare.done = True
                        if self._log_conf.logging_flags.stages:
                            self._logger.info("prepared")

                    if self._app_conf.pause_time_s > 0:
                        time.sleep(self._app_conf.pause_time_s)

                    self._fsm.transition(AppState.CONFIGURE)
            except Exception as exc:
                self._app_statistics.exception_count += 1
                self._logger.error(f"prepare failed: {exc}")
                self._logger.debug(format_exc())
                self._fsm.stop()
                sys.exit(1)

        @self._fsm.state(AppState.CONFIGURE)
        def configure_handler():
            try:
                with self._measure_time(self._app_statistics.configure):
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

        @self._fsm.state(AppState.CONNECT)
        def connect_handler():
            if self._app_statistics.exception_count >= 1:
                self._retry_timer.wait()

            try:
                with self._measure_time(self._app_statistics.connect):
                    if self._databus:
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

        @self._fsm.state(AppState.EXECUTE)
        def execute_handler():
            while self._fsm.is_running:
                try:
                    with self._measure_time(self._app_statistics.execute):
                        self.on_execute()
                        self._app_statistics.execute_maf.add(self._app_statistics.execute.elapsed_time)

                        # One-time log
                        if not self._app_statistics.execute.done:
                            self._app_statistics.execute.done = True
                            if self._log_conf.logging_flags.stages:
                                self._logger.info("executing")
                            self._reset_done_flags_for_success()

                        # Wait for next cycle
                        self._execute_timer.wait()

                except Exception as exc:
                    self._app_statistics.exception_count += 1
                    self._log_fallback("execute", exc)
                    self._fsm.transition(AppState.RECOVER)
                    break

        @self._fsm.state(AppState.RECOVER)
        def recover_handler():
            try:
                with self._measure_time(self._app_statistics.recover):
                    self.on_recover()

                    # One-time log
                    if not self._app_statistics.recover.done:
                        self._app_statistics.recover.done = True
                        if self._log_conf.logging_flags.stages:
                            self._logger.warning("recovering")

                    # Recovery success → back to EXECUTE
                    self._execute_timer.reset()
                    self._fsm.transition(AppState.EXECUTE)

            except Exception as exc:
                self._log_fallback("recover", exc)
                # Recovery fail → DISCONNECT
                self._fsm.transition(AppState.DISCONNECT)

        @self._fsm.state(AppState.DISCONNECT)
        def disconnect_handler():
            # Call on_disconnect callback (before databus disconnect)
            try:
                with self._measure_time(self._app_statistics.disconnect):
                    self.on_disconnect()

                    # One-time log
                    if not self._app_statistics.disconnect.done:
                        self._app_statistics.disconnect.done = True
                        if self._log_conf.logging_flags.stages:
                            self._logger.info("disconnected")

            except Exception as exc:
                self._log_fallback("disconnect", exc)

            # Disconnect databus (always, even if on_disconnect failed)
            if self._databus:
                try:
                    self._databus.disconnect()
                except Exception:
                    pass

            # Reset flags for retry
            self._reset_done_flags_for_retry()
            self._retry_timer.reset()
            self._fsm.transition(AppState.CONNECT)

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
    # Lifecycle
    # ────────────────────────────────────────────────────────────

    def start(self) -> None:
        # Register SIGTERM handler for graceful shutdown
        signal.signal(signal.SIGTERM, self._sigterm_handler)

        self._fsm.start(AppState.PREPARE)
        try:
            while self._fsm.is_running:
                self._manage_timer.wait()
                self._do_manage()
        except KeyboardInterrupt:
            self._logger.info("keyboard interrupt received")
        finally:
            self._stop()

    def _sigterm_handler(self, _signum: int, _frame) -> None:
        self._logger.info("SIGTERM received")
        self._fsm.stop()

    def _do_manage(self) -> None:
        try:
            self.on_manage()
        except Exception as exc:
            self._log_fallback("manage", exc)

    def _stop(self, timeout: float = 5.0) -> None:
        self._fsm.stop(timeout)

        # Cleanup databus
        if self._databus:
            try:
                self._databus.disconnect()
            except Exception:
                pass

    # ────────────────────────────────────────────────────────────
    # Override Points
    # ────────────────────────────────────────────────────────────

    def on_prepare(self) -> None:
        pass

    def on_configure(self) -> None:
        pass

    def on_connect(self) -> None:
        pass

    def on_execute(self) -> None:
        pass

    def on_recover(self) -> None:
        pass

    def on_disconnect(self) -> None:
        pass

    def on_manage(self) -> None:
        pass
