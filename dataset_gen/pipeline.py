"""Agentic generation pipeline.

Responsibilities:
- iterate domains from config
- run generate/repair loops with SQL execution feedback
- build validated examples
- export master/alpaca/chat datasets + stats
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from dataset_gen.config import AppConfig, DomainConfig
from dataset_gen.exporters import (
    write_alpaca_jsonl,
    write_chat_jsonl,
    write_master_jsonl,
    write_stats_json,
)
from dataset_gen.quality import DuplicateTracker, summarize_examples
from dataset_gen.schema import build_schema_snapshot
from dataset_gen.sql_runtime import SQLiteRuntime
from dataset_gen.types import GeneratedExample, QueryCandidate


@dataclass
class GenerationOutcome:
    """In-memory summary returned after one generation run."""

    examples: List[GeneratedExample]
    stats: Dict[str, object]
    paths: Dict[str, str]


class AgenticDatasetGenerator:
    """Coordinates provider calls, runtime validation, dedup, and exports."""

    def __init__(self, config: AppConfig, provider) -> None:
        self.config = config
        self.provider = provider

    def run(self) -> GenerationOutcome:
        """Generate all configured domains and write output artifacts."""
        started = time.time()
        all_examples: List[GeneratedExample] = []
        by_domain_stats: Dict[str, object] = {}

        for domain in self.config.domains:
            # Domain-level isolation keeps schema/runtime concerns separate.
            examples, domain_stats = self._generate_domain(domain)
            all_examples.extend(examples)
            by_domain_stats[domain.name] = domain_stats

        out_dir = self.config.output.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        master_path = out_dir / self.config.output.master_jsonl
        alpaca_path = out_dir / self.config.output.alpaca_jsonl
        chat_path = out_dir / self.config.output.chat_jsonl
        stats_path = out_dir / self.config.output.stats_json

        write_master_jsonl(master_path, all_examples)
        write_alpaca_jsonl(alpaca_path, all_examples)
        write_chat_jsonl(chat_path, all_examples)

        aggregate = summarize_examples(all_examples)
        full_stats: Dict[str, object] = {
            "runtime_seconds": round(time.time() - started, 3),
            "config": {
                "provider_mode": self.config.provider.mode,
                "strict_non_empty": self.config.generation.strict_non_empty,
            },
            "domains": by_domain_stats,
            "aggregate": aggregate,
            "outputs": {
                "master_jsonl": str(master_path),
                "alpaca_jsonl": str(alpaca_path),
                "chat_jsonl": str(chat_path),
            },
        }
        write_stats_json(stats_path, full_stats)

        return GenerationOutcome(
            examples=all_examples,
            stats=full_stats,
            paths={
                "master_jsonl": str(master_path),
                "alpaca_jsonl": str(alpaca_path),
                "chat_jsonl": str(chat_path),
                "stats_json": str(stats_path),
            },
        )

    def _generate_domain(self, domain: DomainConfig) -> Tuple[List[GeneratedExample], Dict[str, object]]:
        """Generate validated examples for one domain until target or attempt cap."""
        runtime = SQLiteRuntime(domain.sql_dump)
        snapshot = build_schema_snapshot(runtime, domain.name, domain.db_id)
        tracker = DuplicateTracker(
            dedup_on_sql=self.config.generation.dedup_on_sql,
            dedup_on_question=self.config.generation.dedup_on_question,
        )
        examples: List[GeneratedExample] = []

        counters: Dict[str, int] = {
            "attempts_total": 0,
            "accepted": 0,
            "failed_sql": 0,
            "failed_empty": 0,
            "failed_duplicate": 0,
            "failed_generation": 0,
            "translation_fallback": 0,
        }

        max_total_attempts = (
            max(1, domain.target_count)
            * max(1, self.config.generation.max_total_attempts_factor)
        )

        while len(examples) < domain.target_count and counters["attempts_total"] < max_total_attempts:
            counters["attempts_total"] += 1
            # Difficulty target cycles deterministically to enforce distribution.
            target_difficulty = self.config.generation.difficulty_cycle[
                len(examples) % len(self.config.generation.difficulty_cycle)
            ]

            feedback: List[str] = []
            candidate: QueryCandidate | None = None
            accepted = False

            for inner_attempt in range(self.config.generation.max_attempts_per_example):
                try:
                    if inner_attempt == 0 or candidate is None:
                        # First attempt uses fresh generation.
                        candidate = self.provider.generate_candidate(
                            domain=domain.name,
                            snapshot=snapshot,
                            difficulty=target_difficulty,
                            min_rows=domain.min_rows,
                            strict_non_empty=self.config.generation.strict_non_empty,
                            feedback=feedback,
                        )
                    else:
                        # Follow-up attempts repair the previous failed candidate.
                        candidate = self.provider.repair_candidate(
                            domain=domain.name,
                            snapshot=snapshot,
                            previous=candidate,
                            error_message=feedback[-1] if feedback else "Unknown error",
                            min_rows=domain.min_rows,
                            strict_non_empty=self.config.generation.strict_non_empty,
                        )
                except Exception as exc:
                    feedback.append(f"Generation failure: {exc}")
                    counters["failed_generation"] += 1
                    continue

                if not candidate.question_en or not candidate.sql:
                    feedback.append("Candidate missing question_en or sql.")
                    counters["failed_generation"] += 1
                    continue

                if tracker.seen(candidate.sql, candidate.question_en):
                    # Duplicate short-circuit keeps corpus diverse.
                    counters["failed_duplicate"] += 1
                    feedback.append("Duplicate candidate detected.")
                    break

                exec_result = runtime.execute(candidate.sql)
                if not exec_result.success:
                    # SQL errors are fed back to repair step.
                    counters["failed_sql"] += 1
                    feedback.append(f"SQL error: {exec_result.error}")
                    continue

                if (
                    self.config.generation.strict_non_empty
                    and exec_result.row_count < max(0, domain.min_rows)
                ):
                    # Empty/too-small results are rejected in strict mode.
                    counters["failed_empty"] += 1
                    feedback.append(
                        f"Row count {exec_result.row_count} is below minimum {domain.min_rows}."
                    )
                    continue

                try:
                    question_ro = self.provider.translate_to_romanian(
                        question_en=candidate.question_en,
                        domain=domain.name,
                        question_ro_hint=candidate.question_ro_hint,
                    )
                except Exception:
                    # Never block acceptance on translation service failures.
                    question_ro = candidate.question_ro_hint or candidate.question_en
                    counters["translation_fallback"] += 1

                example_id = f"{domain.id_prefix}_{len(examples) + 1:06d}"
                flags = ["sql_executable"]
                if exec_result.row_count >= domain.min_rows:
                    flags.append("meets_min_rows")
                if question_ro != candidate.question_en:
                    flags.append("translated_ro")

                generated = GeneratedExample(
                    id=example_id,
                    domain=domain.name,
                    db_id=domain.db_id,
                    question_en=candidate.question_en,
                    question_ro=question_ro,
                    sql=candidate.sql,
                    difficulty=int(candidate.difficulty),
                    query_type=candidate.query_type or ["SELECT"],
                    tables=candidate.tables or [],
                    row_count=exec_result.row_count,
                    validation_flags=flags,
                    expected_result_description_en=(
                        f"Returns {exec_result.row_count} row(s) on the current DB snapshot."
                    ),
                    notes=candidate.notes,
                )

                examples.append(generated)
                tracker.add(candidate.sql, candidate.question_en)
                counters["accepted"] += 1
                accepted = True
                break

            if not accepted:
                continue

        runtime.close()
        stats: Dict[str, object] = {
            "db_id": domain.db_id,
            "target_count": domain.target_count,
            "generated_count": len(examples),
            "counters": counters,
        }
        return examples, stats
