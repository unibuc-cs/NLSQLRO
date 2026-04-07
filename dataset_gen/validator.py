"""Validation pass for generated master JSONL datasets.

Checks:
- JSON validity
- known db_id mapping
- SQL execution
- optional non-empty policy
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from dataset_gen.config import AppConfig
from dataset_gen.sql_runtime import SQLiteRuntime


def validate_master_jsonl(
    config: AppConfig,
    master_path: Path,
    strict_non_empty: bool,
) -> Tuple[bool, Dict[str, object]]:
    """Validate all rows and return (ok, summary)."""
    runtimes: Dict[str, SQLiteRuntime] = {}
    dbid_to_domain: Dict[str, str] = {}
    for d in config.domains:
        runtimes[d.db_id] = SQLiteRuntime(d.sql_dump)
        dbid_to_domain[d.db_id] = d.name

    ok = True
    counters = {
        "total": 0,
        "passed": 0,
        "failed_json": 0,
        "failed_db_id": 0,
        "failed_sql": 0,
        "failed_empty": 0,
    }
    failures: List[Dict[str, object]] = []
    min_rows_by_dbid = {d.db_id: d.min_rows for d in config.domains}

    with master_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            counters["total"] += 1
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                ok = False
                counters["failed_json"] += 1
                failures.append({"line": line_no, "error": f"invalid json: {exc}"})
                continue

            db_id = str(row.get("db_id", ""))
            sql = str(row.get("sql", ""))
            if db_id not in runtimes:
                ok = False
                counters["failed_db_id"] += 1
                failures.append(
                    {
                        "line": line_no,
                        "id": row.get("id"),
                        "error": f"unknown db_id '{db_id}'",
                    }
                )
                continue

            result = runtimes[db_id].execute(sql)
            if not result.success:
                ok = False
                counters["failed_sql"] += 1
                failures.append(
                    {
                        "line": line_no,
                        "id": row.get("id"),
                        "error": result.error or "sql execution failed",
                    }
                )
                continue

            min_rows = min_rows_by_dbid.get(db_id, 0)
            if strict_non_empty and result.row_count < min_rows:
                ok = False
                counters["failed_empty"] += 1
                failures.append(
                    {
                        "line": line_no,
                        "id": row.get("id"),
                        "error": f"row_count={result.row_count} < min_rows={min_rows}",
                    }
                )
                continue

            counters["passed"] += 1

    for runtime in runtimes.values():
        runtime.close()

    summary: Dict[str, object] = {
        "ok": ok,
        "strict_non_empty": strict_non_empty,
        "counters": counters,
        "sample_failures": failures[:20],
    }
    return ok, summary
