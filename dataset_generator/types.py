"""Compatibility wrapper for code still importing `dataset_generator.types`."""

from dataset_generator.dataset_types import (
    ExecutionResult,
    GeneratedExample,
    QueryCandidate,
    VALID_TASKS,
    normalize_task,
)

__all__ = [
    "ExecutionResult",
    "GeneratedExample",
    "QueryCandidate",
    "VALID_TASKS",
    "normalize_task",
]
