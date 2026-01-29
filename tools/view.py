# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
import curses
import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from tagbus import TagBus, TagCache


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TagId = str
TagPattern = str


@dataclass
class ViewConfig:
    patterns: List[TagPattern] = field(default_factory=lambda: ["**"])
    refresh_interval_s: float = 0.5
    max_value_length: int = 50
    show_quality: bool = True
    show_timestamp: bool = True
    json_output: bool = False


@dataclass
class TagSnapshot:
    tag_id: TagId
    value: Any
    quality: str
    timestamp: int
    updated: bool = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tag View Core (for web/API reuse)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TagView:

    _DOMAIN_ID = "default"
    _STATE_DIR = Path("/var/lib/nodi-databus") / _DOMAIN_ID
    _SNAPSHOT_FILE = _STATE_DIR / "view_snapshot.json"

    def __init__(self,
                 app_id: str = "view",
                 patterns: Optional[List[TagPattern]] = None):
        self._app_id = app_id
        self._patterns = patterns or ["**"]
        self._databus: Optional[TagBus] = None
        self._lock = threading.Lock()

        # Tag cache
        self._tags: Dict[TagId, TagSnapshot] = {}
        self._updated_tags: Set[TagId] = set()

        # Snapshot for persistence
        self._snapshot: Dict[TagId, TagCache] = {}
        self._last_snapshot_ts: float = 0.0
        self._snapshot_interval_s: float = 5.0

        # Callbacks
        self._on_update: Optional[Callable[[TagId, TagSnapshot], None]] = None

    @property
    def patterns(self) -> List[TagPattern]:
        return self._patterns.copy()

    @property
    def tag_count(self) -> int:
        with self._lock:
            return len(self._tags)

    def connect(self, initial_wait_s: float = 1.0) -> None:
        # Load previously saved snapshot
        saved_snapshot = self._load_snapshot()

        self._databus = TagBus(self._app_id, debug=False)
        self._databus.connect(clean=True, tag_caches_snapshot=saved_snapshot)
        self._databus.sync_tags(self._patterns)
        self._databus.on_tags_update(self._patterns, self._on_tag_update)
        self._databus.commit()

        # Wait for initial data sync
        time.sleep(initial_wait_s)

        # Load initial tags from databus cache
        # - Snapshot tags: already marked UNK by databus
        # - FQ response tags: marked GOOD by databus
        initial_tags = self._databus.get_tags()
        with self._lock:
            for tag_id, tag_data in initial_tags.items():
                self._tags[tag_id] = TagSnapshot(tag_id=tag_id,
                                                  value=tag_data.v,
                                                  quality=tag_data.q,
                                                  timestamp=tag_data.t,
                                                  updated=False)
            self._snapshot = dict(initial_tags)

    def disconnect(self) -> None:
        # Save current snapshot before disconnect
        self._save_snapshot()
        if self._databus:
            self._databus.disconnect()
            self._databus = None

    def _save_snapshot(self) -> None:  # 🤪
        if not self._databus:
            return
        try:
            self._STATE_DIR.mkdir(parents=True, exist_ok=True)
            snapshot = self._databus.get_tags()
            data = {tag_id: [tc.v, tc.t, tc.q] for tag_id, tc in snapshot.items()}
            with open(self._SNAPSHOT_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load_snapshot(self) -> Dict[TagId, TagCache]:  # 🤪
        try:
            if self._SNAPSHOT_FILE.exists():
                with open(self._SNAPSHOT_FILE, "r") as f:
                    data = json.load(f)
                return {tag_id: TagCache(v=item[0], t=item[1], q=item[2])
                        for tag_id, item in data.items()}
        except Exception:
            pass
        return {}

    def set_patterns(self, patterns: List[TagPattern]) -> None:
        old_patterns = self._patterns
        self._patterns = patterns
        if self._databus:
            self._databus.off_tags_update(old_patterns, self._on_tag_update)
            self._databus.sync_tags(patterns)
            self._databus.on_tags_update(patterns, self._on_tag_update)
            self._databus.commit()

            # Reload tags from cache (use databus quality as-is)
            with self._lock:
                self._tags.clear()
                initial_tags = self._databus.get_tags()
                for tag_id, tag_data in initial_tags.items():
                    self._tags[tag_id] = TagSnapshot(tag_id=tag_id,
                                                      value=tag_data.v,
                                                      quality=tag_data.q,
                                                      timestamp=tag_data.t,
                                                      updated=False)
                self._snapshot = dict(initial_tags)

    def set_on_update(self, callback: Callable[[TagId, TagSnapshot], None]) -> None:
        self._on_update = callback

    def get_snapshots(self) -> Dict[TagId, TagSnapshot]:
        with self._lock:
            return self._tags.copy()

    def get_updated_snapshots(self) -> Dict[TagId, TagSnapshot]:
        with self._lock:
            result = {tag_id: self._tags[tag_id]
                      for tag_id in self._updated_tags
                      if tag_id in self._tags}
            self._updated_tags.clear()
            return result

    def clear_updated_flags(self) -> None:
        with self._lock:
            for snapshot in self._tags.values():
                snapshot.updated = False

    def maybe_save_snapshot(self) -> None:  # 🤪
        now = time.time()
        if now - self._last_snapshot_ts >= self._snapshot_interval_s:
            self._save_snapshot()
            self._last_snapshot_ts = now

    def to_json(self) -> str:
        with self._lock:
            data = {tag_id: {"value": snap.value,
                             "quality": snap.quality,
                             "timestamp": snap.timestamp}
                    for tag_id, snap in self._tags.items()}
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    def _on_tag_update(self, tag_id: TagId, tag_data: TagCache) -> None:
        with self._lock:
            snapshot = TagSnapshot(tag_id=tag_id,
                                   value=tag_data.v,
                                   quality=tag_data.q,
                                   timestamp=tag_data.t,
                                   updated=True)
            self._tags[tag_id] = snapshot
            self._updated_tags.add(tag_id)

        if self._on_update:
            self._on_update(tag_id, snapshot)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI View (curses-based)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CliView:

    # Menu items: (command_key, label, description, needs_args)
    _MENU_ITEMS: List[Tuple[str, str, str, bool]] = [
        ("set", "Set Tag", "Set a tag value (int/float/bool/str)", True),
        ("get", "Get Tag", "Get a specific tag value", True),
        ("get_all", "Get All Tags", "Get all tag values", False),
        ("del", "Delete Tag", "Delete a specific tag", True),
        ("del_app", "Delete App Tags", "Delete all tags for an app", True),
        ("browse_apps", "Browse Apps", "List all connected apps", False),
        ("browse_tags", "Browse Tags", "Browse all tags (optional pattern)", False),
        ("status", "Status", "Show databus connection status", False),
        ("clear_caches", "Clear Caches", "Clear tag caches (optional pattern)", False),
        ("clear_domain", "Clear Domain", "Stop all apps and clear domain", False),
        ("restart", "Restart", "Reconnect view to databus", False),
    ]

    _DOMAIN_ID = "default"
    _LOCKS_DIR = Path("/var/lib/nodi-databus") / _DOMAIN_ID / "lock"

    def __init__(self, config: ViewConfig):
        self._config = config
        self._tag_view = TagView(app_id="view", patterns=config.patterns)
        self._running = False
        self._scroll_offset = 0
        self._filter_text = ""
        self._input_mode = False
        self._sorted_tag_ids: List[TagId] = []
        self._needs_resort = True

        # Command console state
        self._console_open = False
        self._console_cursor = 0
        self._console_input = ""
        self._console_phase = "menu"  # "menu" | "input" | "confirm"
        self._console_selected_cmd = ""
        self._console_prompt = ""

        # Result overlay state
        self._result_lines: List[str] = []
        self._result_scroll = 0
        self._show_result = False

    def run(self) -> None:
        if self._config.json_output:
            self._run_json_mode()
        else:
            curses.wrapper(self._run_curses)

    def _run_json_mode(self) -> None:
        self._tag_view.connect()
        try:
            while True:
                print("\033[2J\033[H", end="")
                print(self._tag_view.to_json())
                self._tag_view.maybe_save_snapshot()
                time.sleep(self._config.refresh_interval_s)
        except KeyboardInterrupt:
            pass
        finally:
            self._tag_view.disconnect()

    def _run_curses(self, stdscr) -> None:
        curses.set_escdelay(25)
        curses.curs_set(0)
        curses.use_default_colors()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, -1)   # Good quality
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Stale quality
        curses.init_pair(3, curses.COLOR_RED, -1)     # Bad quality
        curses.init_pair(4, curses.COLOR_CYAN, -1)    # Updated
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_CYAN)  # Selected menu item
        stdscr.nodelay(True)
        stdscr.timeout(int(self._config.refresh_interval_s * 1000))

        self._tag_view.connect()
        self._running = True

        try:
            while self._running:
                self._handle_input(stdscr)
                self._draw(stdscr)
                self._tag_view.clear_updated_flags()
                self._tag_view.maybe_save_snapshot()
        except KeyboardInterrupt:
            pass
        finally:
            self._tag_view.disconnect()

    # Input Handling
    # ──────────────────────────────────────────────────────────────────────

    def _handle_input(self, stdscr) -> None:
        try:
            key = stdscr.getch()
        except Exception:
            return

        if key == -1:
            return

        if self._show_result:
            self._handle_result_input(key, stdscr)
            return

        if self._console_open:
            self._handle_console_input(key, stdscr)
            return

        if self._input_mode:
            self._handle_filter_input(key)
            return

        # Normal mode
        if key == ord('q') or key == 27:
            self._running = False
        elif key == ord('/'):
            self._input_mode = True
            self._filter_text = ""
        elif key == ord(':'):
            self._open_console()
        elif key == curses.KEY_UP or key == ord('k'):
            self._scroll_offset = max(0, self._scroll_offset - 1)
        elif key == curses.KEY_DOWN or key == ord('j'):
            self._scroll_offset += 1
        elif key == curses.KEY_PPAGE:
            self._scroll_offset = max(0, self._scroll_offset - 10)
        elif key == curses.KEY_NPAGE:
            self._scroll_offset += 10
        elif key == ord('g'):
            self._scroll_offset = 0
        elif key == ord('G'):
            self._scroll_offset = max(0, self._tag_view.tag_count - 1)
        elif key == ord('c'):
            self._filter_text = ""
        elif key == ord('r'):
            self._needs_resort = True

    def _handle_filter_input(self, key) -> None:
        if key == 27 or key == 10 or key == 13:
            self._input_mode = False
        elif key == curses.KEY_BACKSPACE or key == 127:
            self._filter_text = self._filter_text[:-1]
        elif 32 <= key <= 126:
            self._filter_text += chr(key)

    def _handle_result_input(self, key, stdscr) -> None:
        if key == ord('q') or key == 27 or key == 10 or key == 13:
            self._show_result = False
            self._result_lines = []
            self._result_scroll = 0
            stdscr.clear()
        elif key == curses.KEY_UP or key == ord('k'):
            self._result_scroll = max(0, self._result_scroll - 1)
        elif key == curses.KEY_DOWN or key == ord('j'):
            self._result_scroll += 1
        elif key == curses.KEY_PPAGE:
            self._result_scroll = max(0, self._result_scroll - 10)
        elif key == curses.KEY_NPAGE:
            self._result_scroll += 10

    # Console (Command Palette)
    # ──────────────────────────────────────────────────────────────────────

    def _open_console(self) -> None:
        self._console_open = True
        self._console_cursor = 0
        self._console_phase = "menu"
        self._console_input = ""
        self._console_prompt = ""
        self._console_selected_cmd = ""

    def _close_console(self) -> None:
        self._console_open = False
        self._console_phase = "menu"
        self._console_input = ""

    def _handle_console_input(self, key, stdscr) -> None:
        if self._console_phase == "menu":
            self._handle_console_menu(key, stdscr)
        elif self._console_phase == "input":
            self._handle_console_text_input(key, stdscr)
        elif self._console_phase == "confirm":
            self._handle_console_confirm(key, stdscr)

    def _handle_console_menu(self, key, stdscr) -> None:
        if key == 27:  # ESC
            self._close_console()
            stdscr.clear()
        elif key == curses.KEY_UP or key == ord('k'):
            self._console_cursor = max(0, self._console_cursor - 1)
        elif key == curses.KEY_DOWN or key == ord('j'):
            self._console_cursor = min(len(self._MENU_ITEMS) - 1,
                                       self._console_cursor + 1)
        elif key == 10 or key == 13:  # Enter
            self._select_menu_item(stdscr)

    def _select_menu_item(self, stdscr) -> None:
        cmd_key, label, desc, needs_args = self._MENU_ITEMS[self._console_cursor]
        self._console_selected_cmd = cmd_key

        if cmd_key == "clear_domain":
            # Show confirmation with running apps info
            running = self._find_running_apps()
            if running:
                self._console_phase = "confirm"
                self._console_prompt = (f"Stop {len(running)} app(s) "
                                        f"({', '.join(running)}) and clear domain? "
                                        f"[y/N]")
            else:
                self._console_phase = "confirm"
                self._console_prompt = "Clear domain? [y/N]"
        elif needs_args:
            self._console_phase = "input"
            if cmd_key == "set":
                self._console_prompt = "tag_id value: "
            elif cmd_key == "get":
                self._console_prompt = "tag_id: "
            elif cmd_key == "del":
                self._console_prompt = "tag_id: "
            elif cmd_key == "del_app":
                self._console_prompt = "app_id: "
            self._console_input = ""
        else:
            self._close_console()
            stdscr.clear()
            self._run_command(cmd_key, "")

    def _handle_console_text_input(self, key, stdscr) -> None:
        if key == 27:  # ESC - back to menu
            self._console_phase = "menu"
            self._console_input = ""
        elif key == 10 or key == 13:  # Enter - execute
            args = self._console_input.strip()
            self._close_console()
            stdscr.clear()
            if args:
                self._run_command(self._console_selected_cmd, args)
        elif key == curses.KEY_BACKSPACE or key == 127:
            self._console_input = self._console_input[:-1]
        elif 32 <= key <= 126:
            self._console_input += chr(key)

    def _handle_console_confirm(self, key, stdscr) -> None:
        if key == ord('y') or key == ord('Y'):
            self._close_console()
            stdscr.clear()
            self._run_command(self._console_selected_cmd, "confirmed")
        elif key == 27 or key == ord('n') or key == ord('N') or key == 10:
            self._console_phase = "menu"

    # Command Execution
    # ──────────────────────────────────────────────────────────────────────

    def _run_command(self, cmd_key: str, args: str) -> None:
        try:
            if cmd_key == "set":
                self._cmd_set(args)
            elif cmd_key == "get":
                self._cmd_get(args)
            elif cmd_key == "get_all":
                self._cmd_get("*")
            elif cmd_key == "del":
                self._cmd_del(args)
            elif cmd_key == "del_app":
                self._cmd_del_app(args)
            elif cmd_key == "browse_apps":
                self._cmd_browse_apps()
            elif cmd_key == "browse_tags":
                self._cmd_browse_tags(args)
            elif cmd_key == "status":
                self._cmd_status()
            elif cmd_key == "clear_caches":
                self._cmd_clear_caches(args)
            elif cmd_key == "clear_domain":
                self._cmd_clear_domain()
            elif cmd_key == "restart":
                self._cmd_restart()
        except Exception as exc:
            self._show_result_lines([f"Error: {exc}"])

    def _show_result_lines(self, lines: List[str]) -> None:
        self._result_lines = lines
        self._result_scroll = 0
        self._show_result = True

    def _cmd_set(self, args: str) -> None:
        parts = args.split(None, 1)
        if len(parts) < 2:
            self._show_result_lines(["Error: need tag_id and value"])
            return
        tag_id, raw_value = parts[0], parts[1]
        value = self._parse_value(raw_value)

        db = self._tag_view._databus
        if not db:
            self._show_result_lines(["Error: not connected"])
            return
        db.set_tags({tag_id: value})
        db.commit()
        self._show_result_lines([f"Set {tag_id} = {value!r}"])

    def _cmd_get(self, args: str) -> None:
        target = args.strip()
        if not target:
            self._show_result_lines(["Error: need tag_id or *"])
            return

        db = self._tag_view._databus
        if not db:
            self._show_result_lines(["Error: not connected"])
            return

        if target == "*":
            tags = db.get_tags()
        else:
            tags = db.get_tags([target])

        if not tags:
            self._show_result_lines(["No tags found."])
            return

        lines = [f"{'TAG ID':<50} {'VALUE':<30} {'TIMESTAMP':<23} {'QUALITY'}", ""]
        for tag_id in sorted(tags.keys()):
            tag_data = tags[tag_id]
            if tag_data is not None:
                val_str = self._format_value(tag_data.v)
                ts_str = self._format_timestamp(tag_data.t)
                lines.append(f"{tag_id:<50} {val_str:<30} {ts_str:<23} {tag_data.q}")
            else:
                lines.append(f"{tag_id:<50} {'(no data)':<30}")
        self._show_result_lines(lines)

    def _cmd_del(self, args: str) -> None:
        tag_id = args.strip()
        if not tag_id:
            self._show_result_lines(["Error: need tag_id"])
            return

        db = self._tag_view._databus
        if not db:
            self._show_result_lines(["Error: not connected"])
            return

        app_ids = db.get_app_ids_by_tag_id(tag_id)
        if not app_ids:
            self._show_result_lines([f"Tag '{tag_id}' not found or no owner."])
            return

        owner = app_ids[0]
        if owner == self._tag_view._app_id:
            # Own tag - can delete directly
            db.del_tags([tag_id])
            db.commit()
            self._show_result_lines([f"Deleted tag '{tag_id}'."])
        else:
            # Tag owned by another app - need disconnect/reconnect
            self._tag_view.disconnect()
            try:
                owner_db = TagBus(owner, debug=False)
                owner_db.connect()
                owner_db.del_tags([tag_id])
                owner_db.commit()
                owner_db.disconnect()
                msg = f"Deleted tag '{tag_id}' (owner: {owner})."
            except Exception as exc:
                msg = f"Error deleting tag '{tag_id}' (owner: {owner}): {exc}"
            self._tag_view.connect()
            self._needs_resort = True
            self._show_result_lines([msg])

    def _cmd_del_app(self, args: str) -> None:
        app_id = args.strip()
        if not app_id:
            self._show_result_lines(["Error: need app_id"])
            return

        self._tag_view.disconnect()
        try:
            db = TagBus(app_id, debug=False)
            db.connect()
            db.del_tags()
            db.commit()
            db.disconnect()
            msg = f"Deleted all tags for app '{app_id}'."
        except Exception as exc:
            msg = f"Error: {exc}"
        self._tag_view.connect()
        self._needs_resort = True
        self._show_result_lines([msg])

    def _cmd_browse_apps(self) -> None:
        db = self._tag_view._databus
        if not db:
            self._show_result_lines(["Error: not connected"])
            return

        apps = db.browse_apps()
        app_tag_counts = {}
        for app_id in apps:
            app_tag_counts[app_id] = len(db.get_tag_ids_by_app_id(app_id))

        if not apps:
            self._show_result_lines(["No apps found."])
            return
        lines = [f"{'APP ID':<30} {'TAGS':>6}", ""]
        for app_id in sorted(apps.keys()):
            lines.append(f"{app_id:<30} {app_tag_counts.get(app_id, 0):>6}")
        self._show_result_lines(lines)

    def _cmd_browse_tags(self, args: str) -> None:
        db = self._tag_view._databus
        if not db:
            self._show_result_lines(["Error: not connected"])
            return

        pattern = args.strip() or None
        tags = db.browse_tags(pattern)

        if not tags:
            self._show_result_lines(["No tags found."])
            return
        lines = [f"{'TAG ID':<50} {'OWNER':<20} {'LABEL'}", ""]
        for tag_id, tag_info in sorted(tags.items()):
            owner = getattr(tag_info, 'app_id', '') or ''
            label = getattr(tag_info, 'label', '') or ''
            lines.append(f"{tag_id:<50} {owner:<20} {label}")
        self._show_result_lines(lines)

    def _cmd_status(self) -> None:
        if not self._tag_view._databus:
            self._show_result_lines(["Not connected."])
            return
        status = self._tag_view._databus.report_all_statistics()
        lines = ["TagBus Status:", ""]
        for section_name in sorted(dir(status)):
            if section_name.startswith('_'):
                continue
            section = getattr(status, section_name)
            if callable(section):
                continue
            lines.append(f"  [{section_name}]")
            if hasattr(section, '__dict__'):
                for key, val in vars(section).items():
                    if not key.startswith('_'):
                        lines.append(f"    {key}: {val}")
            elif hasattr(section, '_asdict'):
                for key, val in section._asdict().items():
                    lines.append(f"    {key}: {val}")
            else:
                lines.append(f"    {section}")
            lines.append("")
        self._show_result_lines(lines)

    def _cmd_clear_caches(self, args: str) -> None:
        db = self._tag_view._databus
        if not db:
            self._show_result_lines(["Error: not connected"])
            return

        pattern = args.strip() or None
        patterns = [pattern] if pattern else None
        result = db.clear_tags(patterns)
        lines = ["Tag caches cleared:"]
        for key, val in result.items():
            lines.append(f"  {key}: {val}")
        self._show_result_lines(lines)

    def _cmd_clear_domain(self) -> None:
        # Disconnect view first
        self._tag_view.disconnect()

        # Find and stop running apps
        running = self._find_running_apps()
        stopped = []
        for app_id in running:
            pid = self._find_lock_pid(app_id)
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    stopped.append(f"{app_id} (pid={pid})")
                except ProcessLookupError:
                    stopped.append(f"{app_id} (already exited)")
                except PermissionError:
                    stopped.append(f"{app_id} (permission denied)")

        # Wait for processes to exit
        if stopped:
            time.sleep(1.0)

        # Execute clear domain
        db = TagBus("view_cmd", debug=False)
        try:
            result = db.clear_domain()
            lines = ["Domain cleared:"]
            for key, val in result.items():
                lines.append(f"  {key}: {val}")
            if stopped:
                lines.append("")
                lines.append("Stopped apps:")
                for s in stopped:
                    lines.append(f"  {s}")
        except Exception as exc:
            lines = [f"Error: {exc}"]
            if stopped:
                lines.append("")
                lines.append("Attempted to stop:")
                for s in stopped:
                    lines.append(f"  {s}")

        # Reconnect view
        self._tag_view.connect()
        self._needs_resort = True
        self._show_result_lines(lines)

    def _cmd_restart(self) -> None:
        self._tag_view.disconnect()
        time.sleep(0.5)
        self._tag_view.connect()
        self._needs_resort = True
        self._show_result_lines(["View reconnected."])

    # Helper: Find Running Apps
    # ──────────────────────────────────────────────────────────────────────

    def _find_running_apps(self) -> List[str]:
        running = []
        if not self._LOCKS_DIR.exists():
            return running
        for lock_file in self._LOCKS_DIR.glob("*.lock"):
            app_id = lock_file.stem
            if app_id == "view":
                continue
            if self._is_lock_active(lock_file):
                running.append(app_id)
        return running

    def _is_lock_active(self, lock_path: Path) -> bool:
        import fcntl
        try:
            fd = open(lock_path, 'w')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
                return False
            except BlockingIOError:
                fd.close()
                return True
        except Exception:
            return False

    def _find_lock_pid(self, app_id: str) -> Optional[int]:
        lock_path = self._LOCKS_DIR / f"{app_id}.lock"
        if not lock_path.exists():
            return None
        try:
            result = subprocess.run(["fuser", str(lock_path)],
                                    capture_output=True, text=True, timeout=5)
            pids = result.stdout.strip().split()
            if pids:
                return int(pids[0])
        except Exception:
            pass
        return None

    # Value Parsing
    # ──────────────────────────────────────────────────────────────────────

    def _parse_value(self, raw: str) -> Any:
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        if raw.lower() in ("true", "yes", "on"):
            return True
        if raw.lower() in ("false", "no", "off"):
            return False
        if raw.startswith(("{", "[")):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass
        return raw

    # Drawing
    # ──────────────────────────────────────────────────────────────────────

    def _draw(self, stdscr) -> None:
        height, width = stdscr.getmaxyx()

        if self._show_result:
            self._draw_result(stdscr, height, width)
            return

        # Draw main tag view
        self._draw_tags(stdscr, height, width)

        # Draw console overlay on top
        if self._console_open:
            self._draw_console(stdscr, height, width)

        stdscr.refresh()

    def _parse_filters(self, filter_text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Parse filter text into (tag_filter, value_filter, quality_filter)."""
        tag_f, val_f, qual_f = None, None, None
        if not filter_text:
            return (tag_f, val_f, qual_f)

        parts = filter_text.split()
        for part in parts:
            lower = part.lower()
            if lower.startswith("t:"):
                tag_f = part[2:]
            elif lower.startswith("v:"):
                val_f = part[2:]
            elif lower.startswith("q:"):
                qual_f = part[2:]
            else:
                tag_f = part
        return (tag_f, val_f, qual_f)

    def _match_filter(self, snapshot: TagSnapshot,
                      tag_f: Optional[str], val_f: Optional[str], qual_f: Optional[str]) -> bool:
        """Check if snapshot matches all filters."""
        if tag_f and tag_f.lower() not in snapshot.tag_id.lower():
            return False
        if val_f and val_f.lower() not in str(snapshot.value).lower():
            return False
        if qual_f and qual_f.lower() not in snapshot.quality.lower():
            return False
        return True

    def _draw_tags(self, stdscr, height: int, width: int) -> None:
        snapshots = self._tag_view.get_snapshots()

        current_tag_ids = set(snapshots.keys())
        if self._needs_resort or current_tag_ids != set(self._sorted_tag_ids):
            self._sorted_tag_ids = sorted(snapshots.keys())
            self._needs_resort = False
            stdscr.clear()

        if self._filter_text:
            tag_f, val_f, qual_f = self._parse_filters(self._filter_text)
            display_tag_ids = [t for t in self._sorted_tag_ids
                               if t in snapshots and
                               self._match_filter(snapshots[t], tag_f, val_f, qual_f)]
        else:
            display_tag_ids = self._sorted_tag_ids

        total_tags = len(display_tag_ids)

        # Header
        header = f" TagView | Tags: {total_tags} "
        if self._filter_text:
            header += f"| Filter: '{self._filter_text}' (t:tag v:val q:qual) "
        header += "| q:Quit /:Filter c:Clear ::Cmd"
        stdscr.attron(curses.color_pair(5))
        try:
            stdscr.addstr(0, 0, header[:width-1].ljust(width-1))
        except curses.error:
            pass
        stdscr.attroff(curses.color_pair(5))

        # Column header
        col_header = f"{'TAG ID':<50} {'VALUE':<30}"
        if self._config.show_timestamp:
            col_header += f" {'TIMESTAMP':<23}"
        if self._config.show_quality:
            col_header += f" {'QUALITY'}"
        stdscr.attron(curses.A_BOLD)
        try:
            stdscr.addstr(1, 0, col_header[:width-1])
        except curses.error:
            pass
        stdscr.attroff(curses.A_BOLD)

        visible_rows = height - 3
        if self._scroll_offset > max(0, total_tags - visible_rows):
            self._scroll_offset = max(0, total_tags - visible_rows)

        for i in range(visible_rows):
            row = i + 2
            tag_idx = self._scroll_offset + i

            if tag_idx < total_tags:
                tag_id = display_tag_ids[tag_idx]
                snapshot = snapshots.get(tag_id)

                if snapshot:
                    value_str = self._format_value(snapshot.value)
                    line = f"{tag_id:<50} {value_str:<30}"
                    if self._config.show_timestamp:
                        ts_str = self._format_timestamp(snapshot.timestamp)
                        line += f" {ts_str:<23}"
                    if self._config.show_quality:
                        line += f" {snapshot.quality}"

                    color = 0
                    if snapshot.updated:
                        color = curses.color_pair(4) | curses.A_BOLD
                    elif snapshot.quality == "good":
                        color = curses.color_pair(1)
                    elif snapshot.quality == "stale":
                        color = curses.color_pair(2)
                    elif snapshot.quality.startswith("bad"):
                        color = curses.color_pair(3)

                    try:
                        stdscr.addstr(row, 0, line[:width-1].ljust(width-1), color)
                    except curses.error:
                        pass
                else:
                    try:
                        stdscr.addstr(row, 0, " " * (width-1))
                    except curses.error:
                        pass
            else:
                try:
                    stdscr.addstr(row, 0, " " * (width-1))
                except curses.error:
                    pass

        # Footer
        footer = f" {min(visible_rows, max(0, total_tags - self._scroll_offset))}/{total_tags} "
        if self._input_mode:
            footer = f" Filter: {self._filter_text}_ "
        try:
            stdscr.addstr(height-1, 0, footer[:width-1].ljust(width-1))
        except curses.error:
            pass

    def _draw_console(self, stdscr, height: int, width: int) -> None:
        # Console dimensions (centered overlay)
        menu_count = len(self._MENU_ITEMS)
        con_h = menu_count + 4  # header + items + footer + input
        con_w = min(60, width - 4)
        con_y = max(1, (height - con_h) // 2)
        con_x = max(1, (width - con_w) // 2)

        # Draw border/background
        for row in range(con_h):
            y = con_y + row
            if y >= height - 1:
                break
            try:
                stdscr.addstr(y, con_x, " " * con_w, curses.A_REVERSE)
            except curses.error:
                pass

        # Header
        title = " Command Console "
        try:
            stdscr.addstr(con_y, con_x + (con_w - len(title)) // 2,
                          title, curses.A_REVERSE | curses.A_BOLD)
        except curses.error:
            pass

        # Menu items
        for i, (cmd_key, label, desc, _) in enumerate(self._MENU_ITEMS):
            y = con_y + 2 + i
            if y >= con_y + con_h - 2:
                break

            if i == self._console_cursor:
                attr = curses.color_pair(6) | curses.A_BOLD
                prefix = "> "
            else:
                attr = curses.A_REVERSE
                prefix = "  "

            item_text = f"{prefix}{label:<20} {desc}"
            try:
                stdscr.addstr(y, con_x, item_text[:con_w].ljust(con_w), attr)
            except curses.error:
                pass

        # Footer / input area
        footer_y = con_y + con_h - 1
        if self._console_phase == "input":
            input_line = f" {self._console_prompt}{self._console_input}_ "
            try:
                stdscr.addstr(footer_y, con_x,
                              input_line[:con_w].ljust(con_w), curses.A_REVERSE)
            except curses.error:
                pass
        elif self._console_phase == "confirm":
            try:
                stdscr.addstr(footer_y, con_x,
                              f" {self._console_prompt} "[:con_w].ljust(con_w),
                              curses.A_REVERSE)
            except curses.error:
                pass
        else:
            hint = " j/k:Move Enter:Select ESC:Close "
            try:
                stdscr.addstr(footer_y, con_x,
                              hint[:con_w].ljust(con_w), curses.A_REVERSE)
            except curses.error:
                pass

    def _draw_result(self, stdscr, height: int, width: int) -> None:
        header = " Result | q/ESC/Enter:Close j/k:Scroll "
        stdscr.attron(curses.color_pair(5))
        try:
            stdscr.addstr(0, 0, header[:width-1].ljust(width-1))
        except curses.error:
            pass
        stdscr.attroff(curses.color_pair(5))

        visible_rows = height - 2
        total_lines = len(self._result_lines)
        if self._result_scroll > max(0, total_lines - visible_rows):
            self._result_scroll = max(0, total_lines - visible_rows)

        for i in range(visible_rows):
            row = i + 1
            line_idx = self._result_scroll + i
            if line_idx < total_lines:
                line = self._result_lines[line_idx]
                try:
                    stdscr.addstr(row, 0, line[:width-1].ljust(width-1))
                except curses.error:
                    pass
            else:
                try:
                    stdscr.addstr(row, 0, " " * (width-1))
                except curses.error:
                    pass

        footer = f" Line {self._result_scroll + 1}/{total_lines} "
        try:
            stdscr.addstr(height-1, 0, footer[:width-1].ljust(width-1))
        except curses.error:
            pass

        stdscr.refresh()

    def _format_value(self, value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            return f"{value:.3f}"
        if isinstance(value, (dict, list)):
            s = json.dumps(value, ensure_ascii=False)
            if len(s) > self._config.max_value_length:
                return s[:self._config.max_value_length - 3] + "..."
            return s
        s = str(value)
        if len(s) > self._config.max_value_length:
            return s[:self._config.max_value_length - 3] + "..."
        return s

    def _format_timestamp(self, ts: int) -> str:
        try:
            # TagBus timestamp is in milliseconds (ms)
            dt = datetime.fromtimestamp(ts / 1_000)
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except Exception:
            return str(ts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    parser = argparse.ArgumentParser(description="TagView - Real-time databus tag monitor")
    parser.add_argument("patterns", nargs="*", default=["**"],
                        help="Tag patterns to monitor (default: **)")
    parser.add_argument("-r", "--refresh", type=float, default=0.5,
                        help="Refresh interval in seconds (default: 0.5)")
    parser.add_argument("-j", "--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--no-quality", action="store_true",
                        help="Hide quality column")
    parser.add_argument("--no-timestamp", action="store_true",
                        help="Hide timestamp column")

    args = parser.parse_args()

    config = ViewConfig(patterns=args.patterns,
                        refresh_interval_s=args.refresh,
                        show_quality=not args.no_quality,
                        show_timestamp=not args.no_timestamp,
                        json_output=args.json)

    view = CliView(config)
    view.run()


if __name__ == "__main__":
    main()
