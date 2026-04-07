"""Shared dataclasses for candidates, execution results, and final examples."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QueryCandidate:
    """Model-produced candidate before execution validation."""

    question_en: str
    sql: str
    difficulty: int
    query_type: List[str]
    tables: List[str]
    notes: str = ""
    question_ro_hint: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueryCandidate":
        return cls(
            question_en=str(data.get("question_en", "")).strip(),
            sql=str(data.get("sql", "")).strip(),
            difficulty=int(data.get("difficulty", 1)),
            query_type=[str(x) for x in data.get("query_type", [])],
            tables=[str(x) for x in data.get("tables", [])],
            notes=str(data.get("notes", "")).strip(),
            question_ro_hint=(
                str(data["question_ro_hint"]).strip()
                if data.get("question_ro_hint") is not None
                else None
            ),
        )


@dataclass
class ExecutionResult:
    """Outcome of running a SQL query against SQLite runtime."""

    success: bool
    row_count: int
    error: Optional[str] = None
    column_names: List[str] = field(default_factory=list)


@dataclass
class GeneratedExample:
    """Accepted training example with metadata and validation flags."""

    id: str
    domain: str
    db_id: str
    question_en: str
    question_ro: str
    sql: str
    difficulty: int
    query_type: List[str]
    tables: List[str]
    row_count: int
    validation_flags: List[str]
    expected_result_description_en: str
    notes: str = ""

    def to_record(self) -> Dict[str, Any]:
        """Serialize to JSONL-friendly dict."""
        return {
            "id": self.id,
            "domain": self.domain,
            "db_id": self.db_id,
            "question_en": self.question_en,
            "question_ro": self.question_ro,
            "sql": self.sql,
            "difficulty": self.difficulty,
            "query_type": self.query_type,
            "tables": self.tables,
            "row_count": self.row_count,
            "validation_flags": self.validation_flags,
            "expected_result_description_en": self.expected_result_description_en,
            "notes": self.notes,
        }
