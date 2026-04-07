"""Prompt builders for generate/repair/translate provider calls."""

from __future__ import annotations

from typing import Dict, List

from dataset_gen.schema import SchemaSnapshot
from dataset_gen.types import QueryCandidate


def build_generation_messages(
    domain: str,
    snapshot: SchemaSnapshot,
    difficulty: int,
    min_rows: int,
    strict_non_empty: bool,
    feedback: List[str],
) -> List[Dict[str, str]]:
    """Construct chat messages for initial candidate generation."""
    system = (
        "You are a precise NL-to-SQL data generator. "
        "Return only JSON without markdown."
    )
    feedback_block = ""
    if feedback:
        feedback_lines = "\n".join(f"- {x}" for x in feedback[-5:])
        feedback_block = f"\nPrevious validation feedback:\n{feedback_lines}\n"

    requirement_non_empty = (
        f"The SQL should return at least {min_rows} rows."
        if strict_non_empty
        else "Empty results are allowed."
    )
    schema_text = snapshot.to_prompt_text(max_values=12)
    user = f"""
Generate one training item for domain "{domain}".
Difficulty target: {difficulty}
{requirement_non_empty}

Use SQLite SQL and only tables/columns from schema below.
No comments. No DDL/DML (SELECT only).

Output JSON format:
{{
  "question_en": "...",
  "sql": "...",
  "difficulty": {difficulty},
  "query_type": ["SELECT", "..."],
  "tables": ["table_name", "..."],
  "notes": "short rationale"
}}
{feedback_block}
Schema and hints:
{schema_text}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_repair_messages(
    snapshot: SchemaSnapshot,
    candidate: QueryCandidate,
    error_message: str,
    min_rows: int,
    strict_non_empty: bool,
) -> List[Dict[str, str]]:
    """Construct chat messages for SQL repair after a validation failure."""
    system = (
        "You repair NL-to-SQL examples. Return only JSON without markdown."
    )
    empty_requirement = (
        f"Ensure the repaired SQL returns at least {min_rows} rows."
        if strict_non_empty
        else "Empty results are allowed."
    )
    user = f"""
Repair the following candidate while keeping similar intent.
Use only valid schema names from the snapshot.
SQLite only. SELECT only.
{empty_requirement}

Validation error:
{error_message}

Original candidate:
question_en: {candidate.question_en}
sql: {candidate.sql}

Return JSON:
{{
  "question_en": "...",
  "sql": "...",
  "difficulty": {candidate.difficulty},
  "query_type": ["SELECT", "..."],
  "tables": ["table_name", "..."],
  "notes": "what changed"
}}

Schema and hints:
{snapshot.to_prompt_text(max_values=12)}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_translation_messages(question_en: str, domain: str) -> List[Dict[str, str]]:
    """Construct chat messages for EN -> RO translation."""
    system = (
        "Translate English user questions into natural Romanian. "
        "Return only the Romanian question text, no quotes."
    )
    user = f"""
Domain: {domain}
English question:
{question_en}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
