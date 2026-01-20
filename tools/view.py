# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
import curses
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from nodi_databus import Databus
from nodi_databus.databus import TagCache


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

    def __init__(self,
                 app_id: str = "view",
                 patterns: Optional[List[TagPattern]] = None):
        self._app_id = app_id
        self._patterns = patterns or ["**"]
        self._databus: Optional[Databus] = None
        self._lock = threading.Lock()

        # Tag cache
        self._tags: Dict[TagId, TagSnapshot] = {}
        self._updated_tags: Set[TagId] = set()

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
        self._databus = Databus(self._app_id, debug=False)
        self._databus.connect(clean=True)
        self._databus.sync_tags(self._patterns)
        self._databus.on_tags_update(self._patterns, self._on_tag_update)
        self._databus.apply()

        # Wait for initial data sync
        time.sleep(initial_wait_s)

        # Load initial tags from synced tag IDs (DB manifest)
        synced_ids = self._databus.get_synced_tag_ids()
        initial_tags = self._databus.get_tags(synced_ids)
        with self._lock:
            for tag_id in synced_ids:
                tag_data = initial_tags.get(tag_id)
                if tag_data is not None:
                    self._tags[tag_id] = TagSnapshot(tag_id=tag_id,
                                                      value=tag_data.v,
                                                      quality=tag_data.q,
                                                      timestamp=tag_data.t,
                                                      updated=False)
                else:
                    # Tag exists in manifest but no cached data yet
                    self._tags[tag_id] = TagSnapshot(tag_id=tag_id,
                                                      value=None,
                                                      quality="unk",
                                                      timestamp=0,
                                                      updated=False)

    def disconnect(self) -> None:
        if self._databus:
            self._databus.disconnect()
            self._databus = None

    def set_patterns(self, patterns: List[TagPattern]) -> None:
        self._patterns = patterns
        if self._databus:
            self._databus.off_tags_update(self._patterns, self._on_tag_update)
            self._databus.sync_tags(patterns)
            self._databus.on_tags_update(patterns, self._on_tag_update)
            self._databus.apply()

            # Reload tags from synced tag IDs (DB manifest)
            with self._lock:
                self._tags.clear()
                synced_ids = self._databus.get_synced_tag_ids()
                initial_tags = self._databus.get_tags(synced_ids)
                for tag_id in synced_ids:
                    tag_data = initial_tags.get(tag_id)
                    if tag_data is not None:
                        self._tags[tag_id] = TagSnapshot(tag_id=tag_id,
                                                          value=tag_data.v,
                                                          quality=tag_data.q,
                                                          timestamp=tag_data.t,
                                                          updated=False)
                    else:
                        self._tags[tag_id] = TagSnapshot(tag_id=tag_id,
                                                          value=None,
                                                          quality="unk",
                                                          timestamp=0,
                                                          updated=False)

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

    def __init__(self, config: ViewConfig):
        self._config = config
        self._tag_view = TagView(app_id="view", patterns=config.patterns)
        self._running = False
        self._scroll_offset = 0
        self._selected_index = 0
        self._filter_text = ""
        self._input_mode = False
        self._sorted_tag_ids: List[TagId] = []  # Fixed order tag list
        self._needs_resort = True

    def run(self) -> None:
        if self._config.json_output:
            self._run_json_mode()
        else:
            curses.wrapper(self._run_curses)

    def _run_json_mode(self) -> None:
        self._tag_view.connect()
        try:
            while True:
                print("\033[2J\033[H", end="")  # Clear screen
                print(self._tag_view.to_json())
                time.sleep(self._config.refresh_interval_s)
        except KeyboardInterrupt:
            pass
        finally:
            self._tag_view.disconnect()

    def _run_curses(self, stdscr) -> None:
        # Setup curses
        curses.set_escdelay(25)  # Reduce ESC key delay (default 1000ms)
        curses.curs_set(0)
        curses.use_default_colors()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, -1)   # Good quality
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Stale quality
        curses.init_pair(3, curses.COLOR_RED, -1)     # Bad quality
        curses.init_pair(4, curses.COLOR_CYAN, -1)    # Updated
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header
        stdscr.nodelay(True)
        stdscr.timeout(int(self._config.refresh_interval_s * 1000))

        # Connect
        self._tag_view.connect()
        self._running = True

        try:
            while self._running:
                self._handle_input(stdscr)
                self._draw(stdscr)
                self._tag_view.clear_updated_flags()
        except KeyboardInterrupt:
            pass
        finally:
            self._tag_view.disconnect()

    def _handle_input(self, stdscr) -> None:
        try:
            key = stdscr.getch()
        except Exception:
            return

        if key == -1:
            return

        if self._input_mode:
            self._handle_input_mode(stdscr, key)
            return

        if key == ord('q') or key == 27:  # q or ESC
            self._running = False
        elif key == ord('/'):
            self._input_mode = True
            self._filter_text = ""
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

    def _handle_input_mode(self, stdscr, key) -> None:
        if key == 27 or key == 10 or key == 13:  # ESC or Enter
            self._input_mode = False
        elif key == curses.KEY_BACKSPACE or key == 127:
            self._filter_text = self._filter_text[:-1]
        elif 32 <= key <= 126:
            self._filter_text += chr(key)

    def _draw(self, stdscr) -> None:
        height, width = stdscr.getmaxyx()

        # Get snapshots
        snapshots = self._tag_view.get_snapshots()

        # Update sorted tag list only when needed (new tags or resort requested)
        current_tag_ids = set(snapshots.keys())
        if self._needs_resort or current_tag_ids != set(self._sorted_tag_ids):
            self._sorted_tag_ids = sorted(snapshots.keys())
            self._needs_resort = False
            stdscr.clear()  # Clear only on resort

        # Apply filter
        if self._filter_text:
            display_tag_ids = [t for t in self._sorted_tag_ids
                               if self._filter_text.lower() in t.lower()]
        else:
            display_tag_ids = self._sorted_tag_ids

        total_tags = len(display_tag_ids)

        # Header
        header = f" TagView | Patterns: {', '.join(self._config.patterns)} | Tags: {total_tags} "
        if self._filter_text:
            header += f"| Filter: '{self._filter_text}' "
        header += "| q:Quit /:Filter c:Clear r:Resort j/k:Scroll"
        stdscr.attron(curses.color_pair(5))
        stdscr.addstr(0, 0, header[:width-1].ljust(width-1))
        stdscr.attroff(curses.color_pair(5))

        # Column header
        col_header = f"{'TAG ID':<50} {'VALUE':<30}"
        if self._config.show_quality:
            col_header += f" {'Q':>5}"
        if self._config.show_timestamp:
            col_header += f" {'TIMESTAMP':<23}"
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(1, 0, col_header[:width-1])
        stdscr.attroff(curses.A_BOLD)

        # Adjust scroll
        visible_rows = height - 3
        if self._scroll_offset > max(0, total_tags - visible_rows):
            self._scroll_offset = max(0, total_tags - visible_rows)

        # Draw tags (overwrite each line, no clear)
        for i in range(visible_rows):
            row = i + 2
            tag_idx = self._scroll_offset + i

            if tag_idx < total_tags:
                tag_id = display_tag_ids[tag_idx]
                snapshot = snapshots.get(tag_id)

                if snapshot:
                    # Format value
                    value_str = self._format_value(snapshot.value)

                    # Build line
                    line = f"{tag_id:<50} {value_str:<30}"
                    if self._config.show_quality:
                        line += f" {snapshot.quality:>5}"
                    if self._config.show_timestamp:
                        ts_str = self._format_timestamp(snapshot.timestamp)
                        line += f" {ts_str:<23}"

                    # Color based on quality/update
                    color = 0
                    if snapshot.updated:
                        color = curses.color_pair(4) | curses.A_BOLD
                    elif snapshot.quality == "good":
                        color = curses.color_pair(1)
                    elif snapshot.quality == "stale":
                        color = curses.color_pair(2)
                    elif snapshot.quality == "bad":
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
                # Clear empty rows
                try:
                    stdscr.addstr(row, 0, " " * (width-1))
                except curses.error:
                    pass

        # Footer
        footer = f" Showing {min(visible_rows, max(0, total_tags - self._scroll_offset))}/{total_tags} "
        if self._input_mode:
            footer = f" Filter: {self._filter_text}_ "
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
            # Databus timestamp is in milliseconds (ms)
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
