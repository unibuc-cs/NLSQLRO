"""CLI entrypoints for dataset generation, validation, and schema introspection."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from dataset_gen.config import AppConfig, load_config
from dataset_gen.pipeline import AgenticDatasetGenerator
from dataset_gen.providers import MockProvider, OpenAICompatibleProvider
from dataset_gen.schema import build_schema_snapshot
from dataset_gen.sql_runtime import SQLiteRuntime
from dataset_gen.validator import validate_master_jsonl


def _print_safe(text: str) -> None:
    """Print text safely on Windows terminals with limited code pages."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def _build_provider(config: AppConfig):
    """Factory for provider backend selected in config."""
    mode = config.provider.mode.lower().strip()
    if mode == "mock":
        return MockProvider(seed=config.random_seed)
    if mode == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=config.provider.base_url,
            api_key_env=config.provider.api_key_env,
            teacher_model=config.provider.teacher_model,
            translator_model=config.provider.translator_model,
            temperature=config.provider.temperature,
            max_tokens=config.provider.max_tokens,
            timeout_seconds=config.provider.timeout_seconds,
        )
    raise ValueError(f"Unknown provider mode: {config.provider.mode}")


def cmd_generate(args: argparse.Namespace) -> int:
    """Run full generation pipeline and write artifacts."""
    config = load_config(Path(args.config))
    if args.allow_empty:
        config.generation.strict_non_empty = False
    if args.seed is not None:
        config.random_seed = int(args.seed)
    random.seed(config.random_seed)

    provider = _build_provider(config)
    pipeline = AgenticDatasetGenerator(config=config, provider=provider)
    outcome = pipeline.run()

    print("Generation completed.")
    print(f"Total examples: {len(outcome.examples)}")
    for key, path in outcome.paths.items():
        print(f"{key}: {path}")
    print("Stats summary:")
    print(json.dumps(outcome.stats.get("aggregate", {}), indent=2, ensure_ascii=False))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Re-execute SQL for generated master dataset and report failures."""
    config = load_config(Path(args.config))
    strict_non_empty = not args.allow_empty
    master_path = Path(args.input) if args.input else (
        config.output.out_dir / config.output.master_jsonl
    )
    ok, summary = validate_master_jsonl(
        config=config, master_path=master_path, strict_non_empty=strict_non_empty
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def cmd_introspect(args: argparse.Namespace) -> int:
    """Print compact schema/value hints used for prompting."""
    config = load_config(Path(args.config))
    for domain in config.domains:
        runtime = SQLiteRuntime(domain.sql_dump)
        snapshot = build_schema_snapshot(runtime, domain.name, domain.db_id)
        runtime.close()
        _print_safe("=" * 80)
        _print_safe(f"{domain.name} ({domain.db_id})")
        _print_safe(snapshot.to_prompt_text(max_values=8))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command parser for generate/validate/introspect."""
    parser = argparse.ArgumentParser(description="RoGov-SQL dataset generation toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Run agentic dataset generation")
    gen.add_argument(
        "--config",
        default="dataset_gen/configs/default.mock.json",
        help="Path to config JSON",
    )
    gen.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow queries returning 0 rows.",
    )
    gen.add_argument("--seed", type=int, default=None, help="Override random seed")
    gen.set_defaults(func=cmd_generate)

    val = sub.add_parser("validate", help="Validate generated master JSONL")
    val.add_argument(
        "--config",
        default="dataset_gen/configs/default.mock.json",
        help="Path to config JSON",
    )
    val.add_argument(
        "--input",
        default=None,
        help="Optional master JSONL path; defaults to output path from config",
    )
    val.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow empty query results.",
    )
    val.set_defaults(func=cmd_validate)

    introspect = sub.add_parser(
        "introspect", help="Print schema and value hints from configured dumps"
    )
    introspect.add_argument(
        "--config",
        default="dataset_gen/configs/default.mock.json",
        help="Path to config JSON",
    )
    introspect.set_defaults(func=cmd_introspect)

    return parser


def main() -> int:
    """CLI main entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
