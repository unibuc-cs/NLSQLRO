"""Build schema snapshots used to ground prompt generation.

Snapshots include:
- table/column structure
- representative value hints extracted from live data
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from dataset_gen.sql_runtime import SQLiteRuntime


@dataclass
class SchemaSnapshot:
    """Prompt-ready schema object with table and sample value hints."""

    domain: str
    db_id: str
    table_columns: Dict[str, List[str]]
    value_hints: Dict[str, List[str]]

    def to_prompt_text(self, max_values: int = 10) -> str:
        """Render compact schema text for model prompts."""
        lines: List[str] = []
        lines.append(f"Domain: {self.domain}")
        lines.append(f"DB ID: {self.db_id}")
        lines.append("Tables and columns:")
        for table in sorted(self.table_columns):
            cols = ", ".join(self.table_columns[table])
            lines.append(f"- {table}({cols})")
        if self.value_hints:
            lines.append("Value hints:")
            for key in sorted(self.value_hints):
                values = self.value_hints[key][:max_values]
                joined = ", ".join(values)
                lines.append(f"- {key}: {joined}")
        return "\n".join(lines)


def _extract_education_level_tokens(values: List[str], limit: int = 20) -> List[str]:
    """Split concatenated education levels into unique tokens."""
    seen = set()
    out: List[str] = []
    for raw in values:
        for token in raw.split(","):
            clean = token.strip()
            if clean and clean not in seen:
                seen.add(clean)
                out.append(clean)
            if len(out) >= limit:
                return out
    return out


def build_schema_snapshot(runtime: SQLiteRuntime, domain: str, db_id: str) -> SchemaSnapshot:
    """Collect table schema and domain-specific hint columns from runtime."""
    table_columns = runtime.table_columns()
    hints: Dict[str, List[str]] = {}

    if domain == "education":
        hints["counties.county_name"] = runtime.fetch_distinct_values(
            "counties", "county_name", limit=30
        )
        hints["localities.residency_area"] = runtime.fetch_distinct_values(
            "localities", "residency_area", limit=10
        )
        hints["schools.unit_type"] = runtime.fetch_distinct_values(
            "schools", "unit_type", limit=10
        )
        raw_levels = runtime.fetch_distinct_values("schools", "education_level", limit=200)
        hints["schools.education_level_tokens"] = _extract_education_level_tokens(raw_levels)
    elif domain == "trains":
        hints["trains.operator_name"] = runtime.fetch_distinct_values(
            "trains", "operator_name", limit=20
        )
        hints["stations.station_name"] = runtime.fetch_distinct_values(
            "stations", "station_name", limit=40
        )
        hints["stations.top_station_names"] = runtime.fetch_top_station_names(limit=20)
        hints["timetables.day_type"] = runtime.fetch_distinct_values(
            "timetables", "day_type", limit=20
        )

    return SchemaSnapshot(
        domain=domain,
        db_id=db_id,
        table_columns=table_columns,
        value_hints=hints,
    )
