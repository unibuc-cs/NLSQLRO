"""Load and normalize dataset generation configuration from JSON.

This module converts raw JSON payloads into typed dataclasses used by the
pipeline. It also resolves relative paths against the config file location.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class DomainConfig:
    """Static configuration for one database domain."""

    name: str
    db_id: str
    sql_dump: Path
    id_prefix: str
    target_count: int
    min_rows: int = 1


@dataclass
class ProviderConfig:
    """Runtime settings for the model provider layer."""

    mode: str = "mock"
    teacher_model: str = "Qwen2.5-Coder-32B-Instruct"
    translator_model: str = "gpt-5-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.2
    max_tokens: int = 900
    timeout_seconds: int = 90


@dataclass
class GenerationConfig:
    """Controls retries, dedup, and acceptance criteria."""

    max_attempts_per_example: int = 4
    max_total_attempts_factor: int = 40
    strict_non_empty: bool = True
    difficulty_cycle: List[int] = field(default_factory=lambda: [1, 1, 2, 2, 3])
    dedup_on_sql: bool = True
    dedup_on_question: bool = True


@dataclass
class OutputConfig:
    """Output file naming and destination directory."""

    out_dir: Path = Path("generated")
    master_jsonl: str = "rogov_master.jsonl"
    alpaca_jsonl: str = "rogov_alpaca.jsonl"
    chat_jsonl: str = "rogov_chat.jsonl"
    stats_json: str = "stats.json"


@dataclass
class AppConfig:
    """Top-level typed configuration object."""

    random_seed: int
    domains: List[DomainConfig]
    provider: ProviderConfig
    generation: GenerationConfig
    output: OutputConfig


def _require(data: Dict[str, Any], key: str) -> Any:
    """Return required key or fail early with a clear config error."""
    if key not in data:
        raise ValueError(f"Missing required config key: {key}")
    return data[key]


def _as_path(base_dir: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = base_dir / path
    return _normalize_path(path)


def _normalize_path(path: Path) -> Path:
    """Normalize paths while tolerating mapped-drive resolve failures on Windows."""
    try:
        return path.resolve()
    except OSError:
        # Some mapped/network drives fail on resolve() in certain environments.
        return Path(os.path.abspath(str(path)))


def _load_domains(base_dir: Path, payload: List[Dict[str, Any]]) -> List[DomainConfig]:
    domains: List[DomainConfig] = []
    for item in payload:
        domains.append(
            DomainConfig(
                name=str(_require(item, "name")),
                db_id=str(_require(item, "db_id")),
                sql_dump=_as_path(base_dir, str(_require(item, "sql_dump"))),
                id_prefix=str(item.get("id_prefix", item["name"][:3])),
                target_count=int(_require(item, "target_count")),
                min_rows=int(item.get("min_rows", 1)),
            )
        )
    return domains


def load_config(config_path: Path) -> AppConfig:
    """Load JSON config and map sections into typed config dataclasses."""
    config_path = _normalize_path(config_path)
    base_dir = config_path.parent
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    provider_payload = payload.get("provider", {})
    generation_payload = payload.get("generation", {})
    output_payload = payload.get("output", {})

    provider = ProviderConfig(
        mode=str(provider_payload.get("mode", "mock")),
        teacher_model=str(
            provider_payload.get("teacher_model", "Qwen2.5-Coder-32B-Instruct")
        ),
        translator_model=str(provider_payload.get("translator_model", "gpt-5-mini")),
        base_url=str(provider_payload.get("base_url", "https://api.openai.com/v1")),
        api_key_env=str(provider_payload.get("api_key_env", "OPENAI_API_KEY")),
        temperature=float(provider_payload.get("temperature", 0.2)),
        max_tokens=int(provider_payload.get("max_tokens", 900)),
        timeout_seconds=int(provider_payload.get("timeout_seconds", 90)),
    )

    generation = GenerationConfig(
        max_attempts_per_example=int(
            generation_payload.get("max_attempts_per_example", 4)
        ),
        max_total_attempts_factor=int(
            generation_payload.get("max_total_attempts_factor", 40)
        ),
        strict_non_empty=bool(generation_payload.get("strict_non_empty", True)),
        difficulty_cycle=[
            int(x) for x in generation_payload.get("difficulty_cycle", [1, 1, 2, 2, 3])
        ],
        dedup_on_sql=bool(generation_payload.get("dedup_on_sql", True)),
        dedup_on_question=bool(generation_payload.get("dedup_on_question", True)),
    )

    output = OutputConfig(
        out_dir=_as_path(base_dir, str(output_payload.get("out_dir", "generated"))),
        master_jsonl=str(output_payload.get("master_jsonl", "rogov_master.jsonl")),
        alpaca_jsonl=str(output_payload.get("alpaca_jsonl", "rogov_alpaca.jsonl")),
        chat_jsonl=str(output_payload.get("chat_jsonl", "rogov_chat.jsonl")),
        stats_json=str(output_payload.get("stats_json", "stats.json")),
    )

    domains = _load_domains(base_dir, payload.get("domains", []))
    if not domains:
        raise ValueError("Config must contain at least one domain in 'domains'")

    random_seed = int(payload.get("random_seed", 42))
    return AppConfig(
        random_seed=random_seed,
        domains=domains,
        provider=provider,
        generation=generation,
        output=output,
    )
