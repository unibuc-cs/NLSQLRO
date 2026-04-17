"""SQLite runtime helpers for schema introspection and query execution."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

from dataset_generator.dataset_types import ExecutionResult


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class SQLiteRuntime:
    """Thin wrapper over sqlite3 connection used by generation and validation."""

    def __init__(self, sql_dump_path: Path) -> None:
        self.sql_dump_path = sql_dump_path
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        script = sql_dump_path.read_text(encoding="utf-8")
        self.conn.executescript(script)

    def close(self) -> None:
        self.conn.close()

    def execute(self, sql: str) -> ExecutionResult:
        """Execute SQL and return success/error plus row-count metadata."""
        cur = self.conn.cursor()
        text = sql.strip()
        lowered = text.lower()
        try:
            if lowered.startswith("select") or lowered.startswith("with"):
                cur.execute(sql)
                rows = cur.fetchall()
                col_names = [x[0] for x in (cur.description or [])]
                return ExecutionResult(
                    success=True,
                    row_count=len(rows),
                    column_names=col_names,
                )

            savepoint = "_nlsqlro_validation_"
            before_changes = self.conn.total_changes
            self.conn.execute(f"SAVEPOINT {savepoint}")
            try:
                cur.execute(sql)
                after_changes = self.conn.total_changes
                row_count = max(0, int(after_changes - before_changes))
                self.conn.execute(f"ROLLBACK TO {savepoint}")
                self.conn.execute(f"RELEASE {savepoint}")
                return ExecutionResult(
                    success=True,
                    row_count=row_count,
                    column_names=[],
                )
            except Exception:
                self.conn.execute(f"ROLLBACK TO {savepoint}")
                self.conn.execute(f"RELEASE {savepoint}")
                raise
        except Exception as exc:
            return ExecutionResult(success=False, row_count=0, error=str(exc))

    def table_names(self) -> List[str]:
        """List user tables excluding SQLite internals."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        return [r[0] for r in cur.fetchall()]

    def table_columns(self) -> Dict[str, List[str]]:
        """Return mapping of table name to column names."""
        mapping: Dict[str, List[str]] = {}
        cur = self.conn.cursor()
        for table in self.table_names():
            cur.execute(f"PRAGMA table_info({_quote_ident(table)})")
            mapping[table] = [row[1] for row in cur.fetchall()]
        return mapping

    def fetch_distinct_values(self, table: str, column: str, limit: int = 50) -> List[str]:
        """Get representative distinct values for prompt grounding."""
        cur = self.conn.cursor()
        query = (
            f"SELECT DISTINCT {_quote_ident(column)} "
            f"FROM {_quote_ident(table)} "
            f"WHERE {_quote_ident(column)} IS NOT NULL "
            f"ORDER BY {_quote_ident(column)} "
            f"LIMIT ?"
        )
        cur.execute(query, (int(limit),))
        values: List[str] = []
        for (val,) in cur.fetchall():
            if val is None:
                continue
            text = str(val).strip()
            if text:
                values.append(text)
        return values

    def fetch_top_station_names(self, limit: int = 20) -> List[str]:
        """Return stations with the highest number of timetable rows."""
        cur = self.conn.cursor()
        query = """
            SELECT s.station_name, COUNT(*) AS stop_count
            FROM timetables tt
            JOIN stations s ON s.station_id = tt.station_id
            GROUP BY s.station_id, s.station_name
            ORDER BY stop_count DESC, s.station_name
            LIMIT ?
        """
        try:
            cur.execute(query, (int(limit),))
            return [str(r[0]) for r in cur.fetchall() if r[0] is not None]
        except Exception:
            return []
