"""CLI entrypoints for dataset generation, validation, and schema introspection."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from dataset_generator.config import load_config


def _print_safe(text: str) -> None:
    """Print text safely on Windows terminals with limited code pages."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def _build_provider(config):
    """Factory for provider backend selected in config."""
    from dataset_generator.providers import MockProvider, QwenCompatibleProvider

    mode = config.provider.mode.lower().strip()
    if mode == "mock":
        return MockProvider(seed=config.random_seed)
    if mode in {"qwen_compatible", "qwen_local", "openai_compatible"}:
        return QwenCompatibleProvider(
            base_url=config.provider.base_url,
            api_key_env=config.provider.api_key_env,
            teacher_model=config.provider.teacher_model,
            translator_model=config.provider.translator_model,
            temperature=config.provider.temperature,
            max_tokens=config.provider.max_tokens,
            timeout_seconds=config.provider.timeout_seconds,
            translation_max_new_tokens=config.provider.translation_max_new_tokens,
            translation_num_beams=config.provider.translation_num_beams,
            remote_params=config.provider.remote_params,
        )
    raise ValueError(
        f"Unknown provider mode: {config.provider.mode}. "
        "Expected one of: mock, qwen_local, qwen_compatible, openai_compatible."
    )


def cmd_generate(args: argparse.Namespace) -> int:
    """Run full generation pipeline and write artifacts."""
    from dataset_generator.pipeline import AgenticDatasetGenerator

    config = load_config(Path(args.config))
    print(
        (
            "[worker] generate start "
            f"provider_mode={config.provider.mode} "
            f"teacher_model={config.provider.teacher_model} "
            f"translator_model={config.provider.translator_model}"
        ),
        flush=True,
    )
    if args.allow_empty:
        config.generation.strict_non_empty = False
    if args.seed is not None:
        config.random_seed = int(args.seed)
    random.seed(config.random_seed)

    provider = _build_provider(config)
    pipeline = AgenticDatasetGenerator(
        config=config,
        provider=provider,
        progress_every_accepted=max(0, int(args.progress_every)),
        progress_every_attempts=max(0, int(args.progress_every)),
    )
    outcome = pipeline.run()

    print("Generation completed.")
    print(f"Total examples: {len(outcome.examples)}")
    for key, path in outcome.paths.items():
        print(f"{key}: {path}")
    print("Stats summary:")
    print(json.dumps(outcome.stats.get("aggregate", {}), indent=2, ensure_ascii=False))
    return 0


def cmd_generate_multi_gpu(args: argparse.Namespace) -> int:
    """Run generation on multiple GPU-pinned workers and merge outputs."""
    from dataset_generator.multi_gpu_generate import run_multi_gpu_generation

    gpus = [part.strip() for part in str(args.gpus).split(",") if part.strip()]
    if not gpus:
        raise ValueError("Argument --gpus must contain at least one GPU id.")
    base_urls = [
        part.strip()
        for part in str(args.base_urls).split(",")
        if part.strip()
    ] if args.base_urls else None

    return int(
        run_multi_gpu_generation(
            config_path=Path(args.config),
            gpus=gpus,
            artifact=str(args.artifact),
            output_file=Path(args.output_file) if args.output_file else None,
            work_dir=Path(args.work_dir),
            status_every_seconds=float(args.status_every_seconds),
            progress_every=max(1, int(args.progress_every)),
            allow_empty=bool(args.allow_empty),
            python_bin=str(args.python_bin) if args.python_bin else None,
            base_seed=int(args.seed) if args.seed is not None else None,
            base_urls=base_urls,
        )
    )


def cmd_validate(args: argparse.Namespace) -> int:
    """Re-execute SQL for generated master dataset and report failures."""
    from dataset_generator.validator import validate_master_jsonl

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
    from dataset_generator.schema import build_schema_snapshot
    from dataset_generator.sql_runtime import SQLiteRuntime

    config = load_config(Path(args.config))
    for domain in config.domains:
        runtime = SQLiteRuntime(domain.sql_dump)
        snapshot = build_schema_snapshot(runtime, domain.name, domain.db_id)
        runtime.close()
        _print_safe("=" * 80)
        _print_safe(f"{domain.name} ({domain.db_id})")
        _print_safe(snapshot.to_prompt_text(max_values=8))
    return 0


def cmd_prepare_llamafactory(args: argparse.Namespace) -> int:
    """Normalize datasets and emit LLaMA-Factory dataset_info.json."""
    from dataset_generator.prepare_llamafactory_data import (
        DEFAULT_EXTERNAL_OPERATORS,
        DEFAULT_EXTERNAL_QUERIES,
        DEFAULT_MULTI_GPU_DIR,
        _find_latest_nonempty_rogov_merge,
        prepare_llamafactory_data,
    )

    rogov_path = (
        Path(args.rogov)
        if args.rogov
        else _find_latest_nonempty_rogov_merge(DEFAULT_MULTI_GPU_DIR)
    )
    manifest = prepare_llamafactory_data(
        rogov_path=rogov_path,
        external_queries_path=Path(args.external_queries),
        external_operators_path=Path(args.external_operators),
        out_dir=Path(args.out_dir),
        limit=args.limit,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command parser for generate/validate/introspect."""
    from dataset_generator.prepare_llamafactory_data import (
        DEFAULT_EXTERNAL_OPERATORS,
        DEFAULT_EXTERNAL_QUERIES,
        DEFAULT_OUTPUT_DIR,
    )

    parser = argparse.ArgumentParser(description="RoGov-SQL dataset generation toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Run agentic dataset generation")
    gen.add_argument(
        "--config",
        default="dataset_generator/configs/default.mock.json",
        help="Path to config JSON",
    )
    gen.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow task=user queries returning 0 rows.",
    )
    gen.add_argument("--seed", type=int, default=None, help="Override random seed")
    gen.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Emit progress line every N attempts/accepted examples (0 disables).",
    )
    gen.set_defaults(func=cmd_generate)

    multi = sub.add_parser(
        "generate-multi-gpu",
        help="Run generation on multiple GPU-pinned workers and merge artifacts",
    )
    multi.add_argument(
        "--config",
        default="dataset_generator/configs/default.mock.json",
        help="Path to base config JSON",
    )
    multi.add_argument(
        "--gpus",
        default="0,1,2,3",
        help="Comma-separated GPU ids, e.g. 0,1,2,3",
    )
    multi.add_argument(
        "--base-urls",
        default=None,
        help=(
            "Comma-separated OpenAI-compatible endpoints for workers "
            "(one URL for all workers or one URL per GPU). "
            "Example: http://127.0.0.1:8001/v1,http://127.0.0.1:8002/v1"
        ),
    )
    multi.add_argument(
        "--artifact",
        choices=["master", "alpaca", "chat"],
        default="alpaca",
        help="Which per-worker artifact to merge into one final JSONL file",
    )
    multi.add_argument(
        "--output-file",
        default=None,
        help="Merged output file path (defaults under work dir run folder)",
    )
    multi.add_argument(
        "--work-dir",
        default="datasets/multi_gpu_runs",
        help="Directory for worker configs/logs/outputs/manifests",
    )
    multi.add_argument(
        "--status-every-seconds",
        type=float,
        default=5.0,
        help="How often to print aggregate worker status",
    )
    multi.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Per-worker progress cadence for both attempts and accepted examples",
    )
    multi.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow task=user queries returning 0 rows.",
    )
    multi.add_argument(
        "--python-bin",
        default=None,
        help="Python executable for worker subprocesses (default: current Python)",
    )
    multi.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Base random seed override; each worker uses base + worker_index",
    )
    multi.set_defaults(func=cmd_generate_multi_gpu)

    val = sub.add_parser("validate", help="Validate generated master JSONL")
    val.add_argument(
        "--config",
        default="dataset_generator/configs/default.mock.json",
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
        help="Allow empty task=user query results.",
    )
    val.set_defaults(func=cmd_validate)

    introspect = sub.add_parser(
        "introspect", help="Print schema and value hints from configured dumps"
    )
    introspect.add_argument(
        "--config",
        default="dataset_generator/configs/default.mock.json",
        help="Path to config JSON",
    )
    introspect.set_defaults(func=cmd_introspect)

    prep = sub.add_parser(
        "prepare-llamafactory",
        help="Normalize datasets and create LLaMA-Factory dataset_info.json",
    )
    prep.add_argument(
        "--rogov",
        default=None,
        help=(
            "Path to RoGov Alpaca JSONL. If omitted, uses latest non-empty "
            "datasets/multi_gpu_runs/run_*/rogov_alpaca.merged.jsonl"
        ),
    )
    prep.add_argument(
        "--external-queries",
        default=str(DEFAULT_EXTERNAL_QUERIES),
        help="Path to external queries Alpaca JSONL",
    )
    prep.add_argument(
        "--external-operators",
        default=str(DEFAULT_EXTERNAL_OPERATORS),
        help="Path to external operators Alpaca JSONL",
    )
    prep.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for normalized files and dataset_info.json",
    )
    prep.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max normalized rows per input file (smoke testing)",
    )
    prep.set_defaults(func=cmd_prepare_llamafactory)

    return parser


def main() -> int:
    """CLI main entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

