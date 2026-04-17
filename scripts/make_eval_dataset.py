#!/usr/bin/env python3
"""Create a reproducible evaluation split from cleaned Madlad datasets.

Default behavior:
- sample 20% from queries file
- sample 20% from operators file
- write outputs in datasets/evaluatedataset
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple


def _suffix_from_ratio(ratio: float) -> str:
    pct = ratio * 100.0
    rounded = round(pct)
    if abs(pct - rounded) < 1e-9:
        return str(int(rounded))
    return str(pct).replace(".", "p")


def _sample_lines(lines: List[str], ratio: float, rng: random.Random) -> Tuple[List[str], int]:
    total = len(lines)
    sampled_count = int(total * ratio)
    sampled_count = max(1, sampled_count)
    sampled_count = min(sampled_count, total)
    indices = sorted(rng.sample(range(total), sampled_count))
    sampled = [lines[i] for i in indices]
    return sampled, sampled_count


def _read_nonempty_lines(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8") as fh:
        return [ln.rstrip("\n") for ln in fh if ln.strip()]


def _write_jsonl(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line)
            fh.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create random evaluation dataset from clean Madlad JSONL files."
    )
    parser.add_argument(
        "--queries-in",
        default="datasets/madlad_4gpu_full_merged_clean/queries_alpaca_ro.clean.jsonl",
        help="Path to clean queries JSONL.",
    )
    parser.add_argument(
        "--operators-in",
        default="datasets/madlad_4gpu_full_merged_clean/operators_alpaca_ro.clean.jsonl",
        help="Path to clean operators JSONL.",
    )
    parser.add_argument(
        "--out-dir",
        default="datasets/evaluatedataset",
        help="Output directory for sampled files and manifest.",
    )
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.2,
        help="Sampling ratio per task file, in (0, 1]. Default: 0.2",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling. Default: 42",
    )
    parser.add_argument(
        "--shuffle-combined",
        action="store_true",
        help="Shuffle combined output after concatenating queries/operators samples.",
    )
    args = parser.parse_args()

    if not (0.0 < args.ratio <= 1.0):
        raise ValueError(f"--ratio must be in (0, 1], got {args.ratio}")

    queries_in = Path(args.queries_in).expanduser()
    operators_in = Path(args.operators_in).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not queries_in.exists():
        raise FileNotFoundError(f"Missing queries file: {queries_in}")
    if not operators_in.exists():
        raise FileNotFoundError(f"Missing operators file: {operators_in}")

    ratio_suffix = _suffix_from_ratio(float(args.ratio))
    rng = random.Random(int(args.seed))

    queries_lines = _read_nonempty_lines(queries_in)
    operators_lines = _read_nonempty_lines(operators_in)
    if not queries_lines:
        raise ValueError(f"Queries file has no non-empty lines: {queries_in}")
    if not operators_lines:
        raise ValueError(f"Operators file has no non-empty lines: {operators_in}")

    queries_sampled, queries_k = _sample_lines(queries_lines, args.ratio, rng)
    operators_sampled, operators_k = _sample_lines(operators_lines, args.ratio, rng)

    queries_out = out_dir / f"queries_alpaca_ro.clean.eval{ratio_suffix}.jsonl"
    operators_out = out_dir / f"operators_alpaca_ro.clean.eval{ratio_suffix}.jsonl"
    all_out = out_dir / f"all_alpaca_ro.clean.eval{ratio_suffix}.jsonl"
    manifest_out = out_dir / f"manifest_eval{ratio_suffix}.json"

    _write_jsonl(queries_out, queries_sampled)
    _write_jsonl(operators_out, operators_sampled)

    combined = queries_sampled + operators_sampled
    if args.shuffle_combined:
        rng.shuffle(combined)
    _write_jsonl(all_out, combined)

    manifest: Dict[str, object] = {
        "seed": int(args.seed),
        "sampling_ratio": float(args.ratio),
        "outputs": {
            "queries": {
                "source": str(queries_in),
                "output": str(queries_out),
                "total_rows": len(queries_lines),
                "sampled_rows": queries_k,
            },
            "operators": {
                "source": str(operators_in),
                "output": str(operators_out),
                "total_rows": len(operators_lines),
                "sampled_rows": operators_k,
            },
            "all": {
                "output": str(all_out),
                "sampled_rows": len(combined),
                "shuffled": bool(args.shuffle_combined),
            },
        },
    }

    manifest_out.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

