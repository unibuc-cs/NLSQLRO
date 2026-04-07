#!/usr/bin/env python3
"""
Validate NL-to-SQL JSONL examples against generated SQL dumps.

Checks performed:
1. JSON parse for each line in each JSONL file.
2. Required fields presence and type sanity.
3. SQL execution against an in-memory SQLite DB loaded from the target .sql dump.
4. Optional non-empty result enforcement.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


DEFAULT_CASES = (
    {
        "label": "education",
        "sql_dump": Path("Faza_1/edu_reteaua_scolara.sql"),
        "jsonl": Path("edu_examples_10.jsonl"),
        "expected_domain": "education",
        "expected_db_id": "edu_reteaua_scolara",
    },
    {
        "label": "trains",
        "sql_dump": Path("Faza_1/rail_mers_tren.sql"),
        "jsonl": Path("rail_examples_10.jsonl"),
        "expected_domain": "trains",
        "expected_db_id": "rail_mers_tren",
    },
)

REQUIRED_FIELDS = (
    "id",
    "domain",
    "db_id",
    "question_ro",
    "question_en",
    "sql",
    "difficulty",
    "query_type",
    "tables",
    "expected_result_description_en",
)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}")
    raise SystemExit(1)


def validate_object_shape(obj: dict, line_no: int, jsonl_path: Path) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in obj]
    if missing:
        fail(
            f"{jsonl_path} line {line_no}: missing required fields: {', '.join(missing)}"
        )
    if not isinstance(obj["id"], str):
        fail(f"{jsonl_path} line {line_no}: 'id' must be a string")
    if not isinstance(obj["domain"], str):
        fail(f"{jsonl_path} line {line_no}: 'domain' must be a string")
    if not isinstance(obj["db_id"], str):
        fail(f"{jsonl_path} line {line_no}: 'db_id' must be a string")
    if not isinstance(obj["sql"], str):
        fail(f"{jsonl_path} line {line_no}: 'sql' must be a string")
    if not isinstance(obj["difficulty"], int):
        fail(f"{jsonl_path} line {line_no}: 'difficulty' must be an integer")
    if not isinstance(obj["query_type"], list):
        fail(f"{jsonl_path} line {line_no}: 'query_type' must be a list")
    if not isinstance(obj["tables"], list):
        fail(f"{jsonl_path} line {line_no}: 'tables' must be a list")


def read_jsonl(jsonl_path: Path) -> list[tuple[int, dict]]:
    if not jsonl_path.exists():
        fail(f"JSONL file not found: {jsonl_path}")

    parsed: list[tuple[int, dict]] = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                fail(f"{jsonl_path} line {line_no}: invalid JSON ({exc})")
            if not isinstance(obj, dict):
                fail(f"{jsonl_path} line {line_no}: JSON object expected")
            validate_object_shape(obj, line_no, jsonl_path)
            parsed.append((line_no, obj))
    if not parsed:
        fail(f"{jsonl_path}: file has no JSON objects")
    return parsed


def load_sql_dump(sql_dump_path: Path) -> sqlite3.Connection:
    if not sql_dump_path.exists():
        fail(f"SQL dump not found: {sql_dump_path}")
    script = sql_dump_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(script)
    return conn


def run_case(
    label: str,
    sql_dump_path: Path,
    jsonl_path: Path,
    expected_domain: str,
    expected_db_id: str,
    require_non_empty: bool,
) -> tuple[int, int]:
    examples = read_jsonl(jsonl_path)
    conn = load_sql_dump(sql_dump_path)
    cur = conn.cursor()

    print(f"\n[{label}]")
    print(f"  sql_dump: {sql_dump_path}")
    print(f"  jsonl:    {jsonl_path}")

    success_count = 0
    for line_no, obj in examples:
        qid = obj["id"]
        if obj["domain"] != expected_domain:
            fail(
                f"{jsonl_path} line {line_no} ({qid}): domain='{obj['domain']}'"
                f" expected '{expected_domain}'"
            )
        if obj["db_id"] != expected_db_id:
            fail(
                f"{jsonl_path} line {line_no} ({qid}): db_id='{obj['db_id']}'"
                f" expected '{expected_db_id}'"
            )
        try:
            cur.execute(obj["sql"])
            rows = cur.fetchall()
        except Exception as exc:
            fail(f"{jsonl_path} line {line_no} ({qid}): SQL execution failed: {exc}")

        row_count = len(rows)
        if require_non_empty and row_count == 0:
            fail(
                f"{jsonl_path} line {line_no} ({qid}): query returned 0 rows "
                "(strict non-empty mode)"
            )
        success_count += 1
        print(f"  OK {qid}: {row_count} rows")

    conn.close()
    print(f"  Summary: {success_count}/{len(examples)} passed")
    return success_count, len(examples)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate NL-to-SQL JSONL examples against SQL dumps."
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow queries that return zero rows.",
    )
    args = parser.parse_args()
    require_non_empty = not args.allow_empty

    total_ok = 0
    total_all = 0
    for case in DEFAULT_CASES:
        ok, total = run_case(
            label=case["label"],
            sql_dump_path=case["sql_dump"],
            jsonl_path=case["jsonl"],
            expected_domain=case["expected_domain"],
            expected_db_id=case["expected_db_id"],
            require_non_empty=require_non_empty,
        )
        total_ok += ok
        total_all += total

    print("\nValidation completed successfully.")
    print(f"Total: {total_ok}/{total_all} examples passed.")
    if require_non_empty:
        print("Mode: strict non-empty results.")
    else:
        print("Mode: empty results allowed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # defensive fallback
        print(f"Unexpected failure: {exc}", file=sys.stderr)
        raise SystemExit(1)
