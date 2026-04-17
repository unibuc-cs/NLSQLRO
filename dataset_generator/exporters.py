"""Export helpers for master/alpaca/chat datasets and run stats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List

from dataset_generator.dataset_types import GeneratedExample


def _write_jsonl(path: Path, records: Iterable[Dict[str, object]]) -> None:
    """Write iterable records to JSONL with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _alpaca_instruction(ex: GeneratedExample) -> str:
    if ex.task == "operator":
        return (
            f"Write one valid SQLite operator statement for database '{ex.db_id}' "
            "(INSERT/UPDATE/DELETE/CREATE/ALTER/DROP). Return SQL only."
        )
    return (
        f"Write a valid read-only SQLite SQL query for database '{ex.db_id}' "
        "(SELECT/WITH). Return SQL only."
    )


def _chat_system_message(ex: GeneratedExample) -> str:
    if ex.task == "operator":
        return (
            "You generate SQLite operator statements for Romanian NL-to-SQL tasks. "
            "Use DML/DDL only and return only SQL."
        )
    return (
        "You generate SQLite read-only queries for Romanian NL-to-SQL tasks. "
        "Use SELECT/WITH only and return only SQL."
    )


def write_master_jsonl(path: Path, examples: List[GeneratedExample]) -> None:
    """Write canonical rich-format dataset."""
    _write_jsonl(path, (x.to_record() for x in examples))


def write_alpaca_jsonl(path: Path, examples: List[GeneratedExample]) -> None:
    """Write Alpaca-style SFT dataset."""
    records = []
    for ex in examples:
        records.append(
            {
                "id": ex.id,
                "task": ex.task,
                "instruction": _alpaca_instruction(ex),
                "input": (
                    f"Task: {ex.task}\n"
                    f"Romanian question: {ex.question_ro}\n"
                    f"English question: {ex.question_en}"
                ),
                "output": ex.sql,
                "metadata": {
                    "task": ex.task,
                    "domain": ex.domain,
                    "difficulty": ex.difficulty,
                    "query_type": ex.query_type,
                    "tables": ex.tables,
                },
            }
        )
    _write_jsonl(path, records)


def write_chat_jsonl(path: Path, examples: List[GeneratedExample]) -> None:
    """Write chat/messages style SFT dataset."""
    records = []
    for ex in examples:
        records.append(
            {
                "id": ex.id,
                "task": ex.task,
                "messages": [
                    {
                        "role": "system",
                        "content": _chat_system_message(ex),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Task: {ex.task}\n"
                            f"Database: {ex.db_id}\n"
                            f"Question (RO): {ex.question_ro}\n"
                            f"Question (EN): {ex.question_en}"
                        ),
                    },
                    {"role": "assistant", "content": ex.sql},
                ],
                "metadata": {
                    "task": ex.task,
                    "domain": ex.domain,
                    "difficulty": ex.difficulty,
                    "query_type": ex.query_type,
                    "tables": ex.tables,
                },
            }
        )
    _write_jsonl(path, records)


def write_stats_json(path: Path, stats: Dict[str, object]) -> None:
    """Write pretty-printed run stats."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
