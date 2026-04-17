"""Dedup and aggregation helpers for generated datasets."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable

from dataset_generator.dataset_types import GeneratedExample


_WS_RE = re.compile(r"\s+")


def normalize_sql(sql: str) -> str:
    """Normalize SQL for stable duplicate detection."""
    return _WS_RE.sub(" ", sql.strip()).lower()


def normalize_question(text: str) -> str:
    """Normalize natural-language questions for duplicate detection."""
    return _WS_RE.sub(" ", text.strip()).lower()


class DuplicateTracker:
    """Track seen SQL/questions according to configurable dedup policy."""

    def __init__(self, dedup_on_sql: bool = True, dedup_on_question: bool = True) -> None:
        self.dedup_on_sql = dedup_on_sql
        self.dedup_on_question = dedup_on_question
        self._sql_seen = set()
        self._question_seen = set()

    def seen(self, sql: str, question_en: str) -> bool:
        sql_norm = normalize_sql(sql)
        q_norm = normalize_question(question_en)
        if self.dedup_on_sql and sql_norm in self._sql_seen:
            return True
        if self.dedup_on_question and q_norm in self._question_seen:
            return True
        return False

    def add(self, sql: str, question_en: str) -> None:
        self._sql_seen.add(normalize_sql(sql))
        self._question_seen.add(normalize_question(question_en))


def summarize_examples(examples: Iterable[GeneratedExample]) -> Dict[str, object]:
    """Compute compact distribution stats for run reporting."""
    by_domain = defaultdict(int)
    by_task = defaultdict(int)
    by_difficulty = Counter()
    by_query_type = Counter()
    row_counts = []

    for ex in examples:
        by_domain[ex.domain] += 1
        by_task[ex.task] += 1
        by_difficulty[str(ex.difficulty)] += 1
        for q in ex.query_type:
            by_query_type[q] += 1
        row_counts.append(ex.row_count)

    row_summary = {
        "min": min(row_counts) if row_counts else 0,
        "max": max(row_counts) if row_counts else 0,
        "avg": (sum(row_counts) / len(row_counts)) if row_counts else 0.0,
    }
    return {
        "total_examples": sum(by_domain.values()),
        "by_domain": dict(sorted(by_domain.items())),
        "by_task": dict(sorted(by_task.items())),
        "by_difficulty": dict(sorted(by_difficulty.items())),
        "by_query_type": dict(sorted(by_query_type.items())),
        "row_count_summary": row_summary,
    }
