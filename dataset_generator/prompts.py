"""Prompt builders for generate/repair/translate provider calls."""

from __future__ import annotations

from typing import Dict, List

from dataset_generator.dataset_types import QueryCandidate, normalize_task
from dataset_generator.schema import SchemaSnapshot


def _duplicate_avoidance_rules(feedback_text: str) -> str:
    """Add prompt guidance when the previous attempt was duplicate-like."""
    if "duplicate" not in feedback_text.lower():
        return ""
    return """
Duplicate-avoidance requirement:
The previous attempt was rejected as duplicate.
Generate a materially different candidate.
Change at least two of the following dimensions:
- join path or primary table set
- filter column/value
- aggregation/grouping strategy
- ordering/limit strategy
Do not reuse the same SQL skeleton with minor text changes.
""".strip()


def _task_sql_rules(task: str, min_rows: int, strict_non_empty: bool) -> str:
    """Return task-specific SQL constraints for prompting."""
    task_norm = normalize_task(task, default="user")
    if task_norm == "operator":
        return (
            "Task target is operator.\n"
            "Generate exactly one SQLite operator statement from DML/DDL "
            "families (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP).\n"
            "Do not generate SELECT-only queries."
        )
    requirement_non_empty = (
        f"The SQL should return at least {min_rows} rows."
        if strict_non_empty
        else "Empty results are allowed."
    )
    return (
        "Task target is user.\n"
        "Generate a read-only SQLite query (SELECT or WITH + SELECT).\n"
        "No DDL/DML statements.\n"
        f"{requirement_non_empty}"
    )


def _task_query_type_hint(task: str) -> str:
    """Return a task-aware example for `query_type` in prompt JSON."""
    task_norm = normalize_task(task, default="user")
    if task_norm == "operator":
        return '"query_type": ["UPDATE", "..."]'
    return '"query_type": ["SELECT", "..."]'


def build_generation_messages(
    domain: str,
    task: str,
    snapshot: SchemaSnapshot,
    difficulty: int,
    min_rows: int,
    strict_non_empty: bool,
    feedback: List[str],
) -> List[Dict[str, str]]:
    """Construct chat messages for initial candidate generation."""
    task_norm = normalize_task(task, default="user")
    system = "You are a precise NL-to-SQL data generator. Return only JSON without markdown."

    feedback_block = ""
    feedback_text = ""
    if feedback:
        feedback_lines = "\n".join(f"- {x}" for x in feedback[-5:])
        feedback_text = "\n".join(feedback[-5:])
        feedback_block = f"\nPrevious validation feedback:\n{feedback_lines}\n"
    duplicate_rules = _duplicate_avoidance_rules(feedback_text)

    schema_text = snapshot.to_prompt_text(max_values=12)
    user = f"""
Generate one training item for domain "{domain}".
Task: {task_norm}
Difficulty target: {difficulty}
{_task_sql_rules(task=task_norm, min_rows=min_rows, strict_non_empty=strict_non_empty)}

Use SQLite SQL and only tables/columns from schema below.
No comments.

Output JSON format:
{{
  "task": "{task_norm}",
  "question_en": "...",
  "sql": "...",
  "difficulty": {difficulty},
  {_task_query_type_hint(task_norm)},
  "tables": ["table_name", "..."],
  "notes": "short rationale"
}}
{feedback_block}
{duplicate_rules}
Schema and hints:
{schema_text}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_repair_messages(
    domain: str,
    task: str,
    snapshot: SchemaSnapshot,
    candidate: QueryCandidate,
    error_message: str,
    min_rows: int,
    strict_non_empty: bool,
) -> List[Dict[str, str]]:
    """Construct chat messages for SQL repair after a validation failure."""
    task_norm = normalize_task(task, default=candidate.task)
    system = "You repair NL-to-SQL examples. Return only JSON without markdown."
    duplicate_rules = _duplicate_avoidance_rules(error_message)

    user = f"""
Repair the following candidate while keeping similar intent.
Domain: {domain}
Task: {task_norm}
Use only valid schema names from the snapshot.
SQLite only.
{_task_sql_rules(task=task_norm, min_rows=min_rows, strict_non_empty=strict_non_empty)}

Validation error:
{error_message}
{duplicate_rules}

Original candidate:
task: {candidate.task}
question_en: {candidate.question_en}
sql: {candidate.sql}

Return JSON:
{{
  "task": "{task_norm}",
  "question_en": "...",
  "sql": "...",
  "difficulty": {candidate.difficulty},
  {_task_query_type_hint(task_norm)},
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
