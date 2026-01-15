#!/bin/bash
# nodi-edge setup script

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Clone dependency libraries (if not exists)
if [ ! -d "$PARENT_DIR/nodi-libs" ]; then
    git clone https://github.com/nodiinc/nodi-libs.git "$PARENT_DIR/nodi-libs"
fi

if [ ! -d "$PARENT_DIR/nodi-databus" ]; then
    git clone https://github.com/nodiinc/nodi-databus.git "$PARENT_DIR/nodi-databus"
fi

# Install dependency libraries
pip install -e "$PARENT_DIR/nodi-libs"
pip install -e "$PARENT_DIR/nodi-databus"

# Install main project
pip install -e "$SCRIPT_DIR"
