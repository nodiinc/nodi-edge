# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import csv
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from nodi_edge.config import CONFIG_DIR, DB_PATH
from nodi_edge.db import EdgeDB


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_LEGEND_PATTERN = re.compile(
    r"^#\[(\w+)\]\s*(.+)$")

_LEGEND_FIELD_PATTERN = re.compile(
    r"prop(\d+)\s*=\s*(\w+)(?:\(([^)]*)\))?")

_MAX_PROP_N = 10


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Legend Parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_legend_rows(lines: List[str]) -> Dict[str, Dict[int, Tuple[str, str]]]:
    legends: Dict[str, Dict[int, Tuple[str, str]]] = {}
    for line in lines:
        line = line.strip()
        m = _LEGEND_PATTERN.match(line)
        if not m:
            continue
        prot_code = m.group(1)
        fields_str = m.group(2)

        mapping: Dict[int, Tuple[str, str]] = {}
        for fm in _LEGEND_FIELD_PATTERN.finditer(fields_str):
            pos = int(fm.group(1))
            key = fm.group(2)
            label = fm.group(3) or key
            mapping[pos] = (key, label)

        if mapping:
            legends[prot_code] = mapping
    return legends


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# propN ↔ JSON Conversion
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def propn_to_json(row: Dict[str, str],
                  mapping: Dict[int, Tuple[str, str]],
                  type_mapping: Optional[Dict[int, Tuple[str, str]]] = None) -> str:
    result = {}
    for pos in range(1, _MAX_PROP_N + 1):
        val = row.get(f"prop{pos}", "").strip()
        if not val:
            continue

        if pos in mapping:
            key = mapping[pos][0]
        elif type_mapping and pos in type_mapping:
            key = type_mapping[pos][0]
        else:
            key = f"prop{pos}"

        # Type casting from prot_prop
        typ = "str"
        if type_mapping and pos in type_mapping:
            typ = type_mapping[pos][1]

        if typ == "int":
            try:
                val = int(val)
            except ValueError:
                pass
        elif typ == "float":
            try:
                val = float(val)
            except ValueError:
                pass
        elif typ == "bool":
            val = val.lower() in ("true", "1", "yes")

        result[key] = val
    return json.dumps(result, ensure_ascii=False)


def json_to_propn(json_str: str,
                  mapping: Dict[int, Tuple[str, str]]) -> Dict[str, str]:
    data = json.loads(json_str) if json_str else {}

    # Build reverse mapping: key → pos
    key_to_pos = {v[0]: k for k, v in mapping.items()}

    result = {}
    for key, val in data.items():
        pos = key_to_pos.get(key)
        if pos:
            result[f"prop{pos}"] = str(val)
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSV File Loading
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _read_csv_with_legends(file_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    legend_lines = []
    data_lines = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("#"):
                legend_lines.append(stripped)
            elif stripped:
                data_lines.append(stripped)

    # Parse data rows as CSV
    if not data_lines:
        return legend_lines, []

    reader = csv.DictReader(data_lines)
    rows = list(reader)
    return legend_lines, rows


def load_intf_csv(db: EdgeDB, file_path: str) -> int:
    legend_lines, rows = _read_csv_with_legends(file_path)
    legends = parse_legend_rows(legend_lines)
    now = int(time.time())
    count = 0

    for row in rows:
        intf_id = row.get("intf", "").strip()
        prot = row.get("prot", "").strip()
        if not intf_id or not prot:
            continue

        # Get mapping: legend first, then prot_prop fallback
        mapping = legends.get(prot, {})
        type_mapping = db.select_prot_prop_mapping(prot, "intf")
        if not mapping:
            mapping = {pos: (key, key) for pos, (key, typ) in type_mapping.items()}

        prop_json = propn_to_json(row, mapping, type_mapping)

        db.conn.execute(
            "INSERT OR REPLACE INTO intf (intf, cmt, prot, host, port, prop, tout, rtr, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (intf_id,
             row.get("cmt", ""),
             prot,
             row.get("host", ""),
             int(row.get("port", 0) or 0),
             prop_json,
             float(row.get("tout", 5.0) or 5.0),
             float(row.get("rtr", 10.0) or 10.0),
             now))
        count += 1

    db.conn.commit()
    return count


def load_blck_csv(db: EdgeDB, file_path: str) -> int:
    legend_lines, rows = _read_csv_with_legends(file_path)
    legends = parse_legend_rows(legend_lines)
    now = int(time.time())
    count = 0

    for row in rows:
        blck_id = row.get("blck", "").strip()
        intf_id = row.get("intf", "").strip()
        if not blck_id:
            continue

        # Get protocol from intf table
        intf_row = db.select_interface(intf_id)
        prot = intf_row["prot"] if intf_row else ""

        mapping = legends.get(prot, {})
        type_mapping = db.select_prot_prop_mapping(prot, "blck") if prot else {}
        if not mapping and type_mapping:
            mapping = {pos: (key, key) for pos, (key, typ) in type_mapping.items()}

        prop_json = propn_to_json(row, mapping, type_mapping)

        db.conn.execute(
            "INSERT OR REPLACE INTO blck "
            "(blck, cmt, use, intf, prop, rw, trig, tm, stby, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (blck_id,
             row.get("cmt", ""),
             row.get("use", "Y"),
             intf_id,
             prop_json,
             row.get("rw", "ro"),
             row.get("trig", "cyc"),
             row.get("tm", "1"),
             float(row.get("stby", 1.0) or 1.0),
             now))
        count += 1

    db.conn.commit()
    return count


def load_blck_map_csv(db: EdgeDB, file_path: str) -> int:
    legend_lines, rows = _read_csv_with_legends(file_path)
    legends = parse_legend_rows(legend_lines)
    count = 0

    # Build blck → prot lookup cache
    blck_prot_cache: Dict[str, str] = {}

    for row in rows:
        blck_id = row.get("blck", "").strip()
        tag_id = row.get("tag", "").strip()
        if not blck_id or not tag_id:
            continue

        # Lookup protocol for this block
        if blck_id not in blck_prot_cache:
            blck_row = db.conn.execute(
                "SELECT i.prot FROM blck b JOIN intf i ON b.intf = i.intf "
                "WHERE b.blck = ?", (blck_id,)).fetchone()
            blck_prot_cache[blck_id] = blck_row[0] if blck_row else ""

        prot = blck_prot_cache[blck_id]

        mapping = legends.get(prot, {})
        type_mapping = db.select_prot_prop_mapping(prot, "map") if prot else {}
        if not mapping and type_mapping:
            mapping = {pos: (key, key) for pos, (key, typ) in type_mapping.items()}

        prop_json = propn_to_json(row, mapping, type_mapping)

        db.conn.execute(
            "INSERT INTO blck_map (blck, tag, idx, prop) VALUES (?, ?, ?, ?)",
            (blck_id, tag_id, row.get("idx", "v"), prop_json))
        count += 1

    db.conn.commit()
    return count


def load_tag_csv(db: EdgeDB, file_path: str) -> int:
    _, rows = _read_csv_with_legends(file_path)
    count = 0

    for row in rows:
        tag_id = row.get("tag", "").strip()
        if not tag_id:
            continue
        db.conn.execute(
            "INSERT OR REPLACE INTO tag (tag, cmt, init) VALUES (?, ?, ?)",
            (tag_id, row.get("cmt", ""), row.get("init", "")))
        count += 1

    db.conn.commit()
    return count


def load_arcv_csv(db: EdgeDB, file_path: str) -> int:
    _, rows = _read_csv_with_legends(file_path)
    count = 0

    for row in rows:
        arcv_id = row.get("arcv", "").strip()
        if not arcv_id:
            continue
        db.conn.execute(
            "INSERT OR REPLACE INTO arcv (arcv, cmt, sto, rev, ret) "
            "VALUES (?, ?, ?, ?, ?)",
            (arcv_id, row.get("cmt", ""), row.get("sto", ""),
             row.get("rev", ""), row.get("ret", "")))
        count += 1

    db.conn.commit()
    return count


def load_arcv_map_csv(db: EdgeDB, file_path: str) -> int:
    _, rows = _read_csv_with_legends(file_path)
    count = 0

    for row in rows:
        arcv_id = row.get("arcv", "").strip()
        tag_id = row.get("tag", "").strip()
        if not arcv_id or not tag_id:
            continue
        db.conn.execute(
            "INSERT INTO arcv_map (arcv, tag) VALUES (?, ?)",
            (arcv_id, tag_id))
        count += 1

    db.conn.commit()
    return count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSV Export
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def export_blck_map_csv(db: EdgeDB, file_path: str) -> int:
    rows = db.conn.execute(
        "SELECT bm.blck, bm.tag, bm.idx, bm.prop, i.prot "
        "FROM blck_map bm "
        "JOIN blck b ON bm.blck = b.blck "
        "JOIN intf i ON b.intf = i.intf "
        "ORDER BY bm.blck, bm.tag").fetchall()

    if not rows:
        return 0

    # Collect all used protocols
    used_prots = set()
    for row in rows:
        used_prots.add(row["prot"])

    # Generate legend rows (using label from prot_prop)
    legends = []
    for prot in sorted(used_prots):
        label_mapping = db.select_prot_prop_labels(prot, "map")
        if label_mapping:
            parts = [f"prop{pos}={key}({label})"
                     for pos, (key, label) in sorted(label_mapping.items())]
            legends.append(f"#[{prot}] {', '.join(parts)}")

    # Determine max prop columns needed
    max_prop = 5
    for prot in used_prots:
        mapping = db.select_prot_prop_mapping(prot, "map")
        if mapping:
            max_prop = max(max_prop, max(mapping.keys()))

    # Write CSV
    prop_headers = [f"prop{i}" for i in range(1, max_prop + 1)]
    headers = ["blck", "tag", "idx"] + prop_headers

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        for legend in legends:
            f.write(legend + "\n")

        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for row in rows:
            prot = row["prot"]
            mapping = db.select_prot_prop_mapping(prot, "map")
            prop_cols = json_to_propn(row["prop"], mapping)

            csv_row = {"blck": row["blck"], "tag": row["tag"], "idx": row["idx"]}
            csv_row.update(prop_cols)
            writer.writerow(csv_row)

    return len(rows)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Full Load
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_all(config_dir: str = CONFIG_DIR, db_path: str = DB_PATH) -> Dict[str, int]:
    db = EdgeDB(db_path)
    db.open()
    results = {}

    config_path = Path(config_dir) / "interfaces"

    # Clear existing blck_map (reloaded entirely)
    db.conn.execute("DELETE FROM blck_map")
    db.conn.execute("DELETE FROM arcv_map")

    # Load in dependency order
    loaders = [
        ("tag", load_tag_csv, "tag.csv"),
        ("intf", load_intf_csv, "intf.csv"),
        ("blck", load_blck_csv, "blck.csv"),
        ("blck_map", load_blck_map_csv, "blck_map.csv"),
        ("arcv", load_arcv_csv, "arcv.csv"),
        ("arcv_map", load_arcv_map_csv, "arcv_map.csv"),
    ]

    for name, loader, filename in loaders:
        csv_file = config_path / filename
        if csv_file.exists():
            count = loader(db, str(csv_file))
            results[name] = count
            print(f"  {name}: {count} rows loaded")
        else:
            results[name] = 0
            print(f"  {name}: file not found ({csv_file})")

    db.close()
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CSV → edge.db loader")
    parser.add_argument("--config-dir", default=CONFIG_DIR,
                        help=f"Config directory (default: {CONFIG_DIR})")
    parser.add_argument("--db-path", default=DB_PATH,
                        help=f"Database path (default: {DB_PATH})")
    args = parser.parse_args()

    print(f"Loading CSVs from: {args.config_dir}/interfaces/")
    print(f"Database: {args.db_path}")
    load_all(args.config_dir, args.db_path)
    print("Done.")
