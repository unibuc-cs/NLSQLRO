"""Prepare local datasets for LLaMA-Factory supervised fine-tuning.

This utility normalizes the two project datasets into a single consistent
Alpaca schema and writes a `dataset_info.json` compatible with LLaMA-Factory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, TextIO


DEFAULT_EXTERNAL_QUERIES = Path(
    "datasets/madlad_4gpu_full_merged_clean/queries_alpaca_ro.clean.jsonl"
)
DEFAULT_EXTERNAL_OPERATORS = Path(
    "datasets/madlad_4gpu_full_merged_clean/operators_alpaca_ro.clean.jsonl"
)
DEFAULT_MULTI_GPU_DIR = Path("datasets/multi_gpu_runs")
DEFAULT_OUTPUT_DIR = Path("datasets/llamafactory")
DEFAULT_SYSTEM_PROMPT = (
    "You are a text-to-SQL assistant. Return only valid SQL."
)


def _find_latest_nonempty_rogov_merge(base_dir: Path) -> Path:
    candidates = [
        path
        for path in base_dir.glob("run_*/rogov_alpaca.merged.jsonl")
        if path.is_file() and path.stat().st_size > 0
    ]
    if not candidates:
        raise FileNotFoundError(
            "No non-empty rogov_alpaca.merged.jsonl found under "
            f"{base_dir.as_posix()}"
        )
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _normalize_record(
    obj: Dict[str, object],
    source_name: str,
    default_system_prompt: str,
) -> Optional[Dict[str, object]]:
    instruction = str(obj.get("instruction", "")).strip()
    output = str(obj.get("output", "")).strip()
    if not instruction or not output:
        return None

    input_text = str(obj.get("input", ""))
    system_prompt = str(obj.get("system", "")).strip() or default_system_prompt

    metadata_raw = obj.get("metadata")
    metadata: Dict[str, object] = (
        dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    )
    if "id" in obj and "id" not in metadata:
        metadata["id"] = obj["id"]
    if "task" in obj and "task" not in metadata:
        metadata["task"] = obj["task"]
    metadata["source_dataset"] = source_name

    return {
        "instruction": instruction,
        "input": input_text,
        "output": output,
        "system": system_prompt,
        "metadata": metadata,
    }


def _convert_jsonl(
    input_path: Path,
    output_path: Path,
    source_name: str,
    default_system_prompt: str,
    limit: Optional[int] = None,
    mirror_writer: Optional[TextIO] = None,
) -> Dict[str, int]:
    stats = {"read": 0, "written": 0, "dropped": 0}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8") as in_fh, output_path.open(
        "w", encoding="utf-8"
    ) as out_fh:
        for raw_line in in_fh:
            line = raw_line.strip()
            if not line:
                continue

            stats["read"] += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                stats["dropped"] += 1
                continue

            normalized = _normalize_record(
                obj=obj,
                source_name=source_name,
                default_system_prompt=default_system_prompt,
            )
            if normalized is None:
                stats["dropped"] += 1
                continue

            encoded = json.dumps(normalized, ensure_ascii=False)
            out_fh.write(encoded + "\n")
            if mirror_writer is not None:
                mirror_writer.write(encoded + "\n")
            stats["written"] += 1

            if limit is not None and stats["written"] >= limit:
                break

    return stats


def prepare_llamafactory_data(
    rogov_path: Path,
    external_queries_path: Path,
    external_operators_path: Path,
    out_dir: Path,
    limit: Optional[int] = None,
) -> Dict[str, object]:
    if not rogov_path.exists():
        raise FileNotFoundError(f"Missing RoGov dataset: {rogov_path.as_posix()}")
    if rogov_path.stat().st_size == 0:
        raise ValueError(f"RoGov dataset is empty: {rogov_path.as_posix()}")
    if not external_queries_path.exists():
        raise FileNotFoundError(
            f"Missing external queries dataset: {external_queries_path.as_posix()}"
        )
    if not external_operators_path.exists():
        raise FileNotFoundError(
            "Missing external operators dataset: "
            f"{external_operators_path.as_posix()}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)

    out_external_queries = out_dir / "external_queries.alpaca.jsonl"
    out_external_operators = out_dir / "external_operators.alpaca.jsonl"
    out_external_all = out_dir / "external_all.alpaca.jsonl"
    out_rogov = out_dir / "rogov.alpaca.jsonl"
    out_dataset_info = out_dir / "dataset_info.json"
    out_manifest = out_dir / "manifest_prep.json"

    with out_external_all.open("w", encoding="utf-8") as ext_all_fh:
        queries_stats = _convert_jsonl(
            input_path=external_queries_path,
            output_path=out_external_queries,
            source_name="external_queries",
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
            limit=limit,
            mirror_writer=ext_all_fh,
        )
        operators_stats = _convert_jsonl(
            input_path=external_operators_path,
            output_path=out_external_operators,
            source_name="external_operators",
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
            limit=limit,
            mirror_writer=ext_all_fh,
        )

    rogov_stats = _convert_jsonl(
        input_path=rogov_path,
        output_path=out_rogov,
        source_name="rogov_generated",
        default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        limit=limit,
        mirror_writer=None,
    )

    columns_map = {
        "prompt": "instruction",
        "query": "input",
        "response": "output",
        "system": "system",
    }
    dataset_info = {
        "nlsqlro_external_queries_sft": {
            "file_name": out_external_queries.name,
            "formatting": "alpaca",
            "columns": columns_map,
        },
        "nlsqlro_external_operators_sft": {
            "file_name": out_external_operators.name,
            "formatting": "alpaca",
            "columns": columns_map,
        },
        "nlsqlro_external_all_sft": {
            "file_name": out_external_all.name,
            "formatting": "alpaca",
            "columns": columns_map,
        },
        "nlsqlro_rogov_sft": {
            "file_name": out_rogov.name,
            "formatting": "alpaca",
            "columns": columns_map,
        },
    }
    out_dataset_info.write_text(
        json.dumps(dataset_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest: Dict[str, object] = {
        "inputs": {
            "rogov": rogov_path.as_posix(),
            "external_queries": external_queries_path.as_posix(),
            "external_operators": external_operators_path.as_posix(),
            "limit_per_file": limit,
        },
        "outputs": {
            "external_queries": out_external_queries.as_posix(),
            "external_operators": out_external_operators.as_posix(),
            "external_all": out_external_all.as_posix(),
            "rogov": out_rogov.as_posix(),
            "dataset_info": out_dataset_info.as_posix(),
        },
        "stats": {
            "external_queries": queries_stats,
            "external_operators": operators_stats,
            "external_all_rows": queries_stats["written"] + operators_stats["written"],
            "rogov": rogov_stats,
        },
    }
    out_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize NLSQLRO datasets and generate LLaMA-Factory dataset_info.json"
        )
    )
    parser.add_argument(
        "--rogov",
        default=None,
        help=(
            "Path to RoGov Alpaca dataset (defaults to latest non-empty "
            "datasets/multi_gpu_runs/run_*/rogov_alpaca.merged.jsonl)"
        ),
    )
    parser.add_argument(
        "--external-queries",
        default=str(DEFAULT_EXTERNAL_QUERIES),
        help="Path to external queries Alpaca JSONL",
    )
    parser.add_argument(
        "--external-operators",
        default=str(DEFAULT_EXTERNAL_OPERATORS),
        help="Path to external operators Alpaca JSONL",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for normalized datasets + dataset_info.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max normalized rows per input file for smoke tests",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
