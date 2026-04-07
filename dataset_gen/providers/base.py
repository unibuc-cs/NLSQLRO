"""Provider abstraction for generation/repair/translation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from dataset_gen.schema import SchemaSnapshot
from dataset_gen.types import QueryCandidate


class ProviderError(RuntimeError):
    """Provider-layer error surfaced to pipeline retry logic."""

    pass


class AgenticProvider(ABC):
    """Minimal contract required by the agentic generation loop."""

    @abstractmethod
    def generate_candidate(
        self,
        domain: str,
        snapshot: SchemaSnapshot,
        difficulty: int,
        min_rows: int,
        strict_non_empty: bool,
        feedback: List[str],
    ) -> QueryCandidate:
        raise NotImplementedError

    @abstractmethod
    def repair_candidate(
        self,
        domain: str,
        snapshot: SchemaSnapshot,
        previous: QueryCandidate,
        error_message: str,
        min_rows: int,
        strict_non_empty: bool,
    ) -> QueryCandidate:
        raise NotImplementedError

    @abstractmethod
    def translate_to_romanian(
        self, question_en: str, domain: str, question_ro_hint: Optional[str] = None
    ) -> str:
        raise NotImplementedError
