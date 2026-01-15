#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Git helper script for managing app submodules.

Usage:
    python scripts/git_apps.py status                    # Show status of all apps
    python scripts/git_apps.py pull                      # Pull all apps
    python scripts/git_apps.py pull monitoring           # Pull specific app
    python scripts/git_apps.py push                      # Push all apps
    python scripts/git_apps.py push monitoring           # Push specific app
    python scripts/git_apps.py commit -m "message"       # Commit all apps
    python scripts/git_apps.py commit monitoring -m "message"  # Commit specific app
    python scripts/git_apps.py add-all                   # Stage all changes in all apps
    python scripts/git_apps.py add-all monitoring        # Stage all changes in specific app
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ROOT_DIR = Path(__file__).parent.parent
APPS_DIR = ROOT_DIR / "apps"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_app_dirs(app_name: str | None = None) -> list[Path]:
    if not APPS_DIR.exists():
        return []

    if app_name:
        app_path = APPS_DIR / app_name
        if app_path.exists() and (app_path / ".git").exists():
            return [app_path]
        else:
            print(f"App not found or not a git repo: {app_name}")
            return []

    # Get all app directories with .git
    return [d for d in APPS_DIR.iterdir()
            if d.is_dir() and (d / ".git").exists()]


def run_git(app_dir: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n[{app_dir.name}] git {' '.join(args)}")
    result = subprocess.run(["git"] + args,
                            cwd=app_dir,
                            capture_output=False,
                            check=check)
    return result

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cmd_status(app_name: str | None = None) -> None:
    app_dirs = get_app_dirs(app_name)
    if not app_dirs:
        print("No apps found.")
        return

    for app_dir in app_dirs:
        run_git(app_dir, ["status", "-sb"], check=False)


def cmd_pull(app_name: str | None = None) -> None:
    app_dirs = get_app_dirs(app_name)
    if not app_dirs:
        print("No apps found.")
        return

    for app_dir in app_dirs:
        run_git(app_dir, ["pull"], check=False)


def cmd_push(app_name: str | None = None) -> None:
    app_dirs = get_app_dirs(app_name)
    if not app_dirs:
        print("No apps found.")
        return

    for app_dir in app_dirs:
        run_git(app_dir, ["push"], check=False)


def cmd_add_all(app_name: str | None = None) -> None:
    app_dirs = get_app_dirs(app_name)
    if not app_dirs:
        print("No apps found.")
        return

    for app_dir in app_dirs:
        run_git(app_dir, ["add", "-A"], check=False)


def cmd_commit(app_name: str | None = None, message: str | None = None) -> None:
    if not message:
        print("Error: commit message required (-m)")
        sys.exit(1)

    app_dirs = get_app_dirs(app_name)
    if not app_dirs:
        print("No apps found.")
        return

    for app_dir in app_dirs:
        run_git(app_dir, ["commit", "-m", message], check=False)


def cmd_acp(app_name: str | None = None, message: str | None = None) -> None:
    if not message:
        print("Error: commit message required (-m)")
        sys.exit(1)

    app_dirs = get_app_dirs(app_name)
    if not app_dirs:
        print("No apps found.")
        return

    for app_dir in app_dirs:
        run_git(app_dir, ["add", "-A"], check=False)
        run_git(app_dir, ["commit", "-m", message], check=False)
        run_git(app_dir, ["push"], check=False)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    parser = argparse.ArgumentParser(description="Git helper for app submodules")
    parser.add_argument("command",
                        choices=["status", "pull", "push", "add-all", "commit", "acp"],
                        help="Git command to run")
    parser.add_argument("app", nargs="?", default=None,
                        help="Specific app name (optional, default: all apps)")
    parser.add_argument("-m", "--message", default=None,
                        help="Commit message (for commit/acp)")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args.app)
    elif args.command == "pull":
        cmd_pull(args.app)
    elif args.command == "push":
        cmd_push(args.app)
    elif args.command == "add-all":
        cmd_add_all(args.app)
    elif args.command == "commit":
        cmd_commit(args.app, args.message)
    elif args.command == "acp":
        cmd_acp(args.app, args.message)


if __name__ == "__main__":
    main()
