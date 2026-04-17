#!/usr/bin/env python3
"""
Merge sharded outputs produced by prepare_gretel_text2sql_ro.py.

Each shard directory is expected to contain:
- queries_alpaca_ro.jsonl
- operators_alpaca_ro.jsonl
- manifest.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Any, Dict, List, Tuple


def load_manifest(shard_dir: str) -> Dict[str, Any]:
    manifest_path = os.path.join(shard_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Missing manifest.json in {shard_dir}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def resolve_shard_dirs(args: argparse.Namespace) -> List[str]:
    if args.shard_dirs:
        return args.shard_dirs
    if args.shard_glob:
        dirs = [p for p in glob.glob(args.shard_glob) if os.path.isdir(p)]
        if dirs:
            return dirs
    raise ValueError("Provide either --shard-dirs or --shard-glob.")


def sort_shard_dirs(shard_dirs: List[str]) -> List[Tuple[int, str, Dict[str, Any]]]:
    indexed: List[Tuple[int, str, Dict[str, Any]]] = []
    for shard_dir in shard_dirs:
        manifest = load_manifest(shard_dir)
        shard_index = int(manifest.get("shard_index", 0))
        indexed.append((shard_index, shard_dir, manifest))
    indexed.sort(key=lambda x: x[0])
    return indexed


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge sharded Romanian text-to-SQL outputs.")
    parser.add_argument(
        "--shard-dirs",
        nargs="+",
        default=None,
        help="Explicit list of shard directories.",
    )
    parser.add_argument(
        "--shard-glob",
        default=None,
        help="Glob pattern for shard directories, e.g. 'data_madlad_shard*'.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for merged outputs.",
    )
    args = parser.parse_args()

    shard_dirs = resolve_shard_dirs(args)
    indexed_shards = sort_shard_dirs(shard_dirs)

    all_queries: List[Dict[str, Any]] = []
    all_operators: List[Dict[str, Any]] = []
    shard_manifests: List[Dict[str, Any]] = []

    for shard_index, shard_dir, manifest in indexed_shards:
        queries_path = os.path.join(shard_dir, "queries_alpaca_ro.jsonl")
        operators_path = os.path.join(shard_dir, "operators_alpaca_ro.jsonl")
        all_queries.extend(read_jsonl(queries_path))
        all_operators.extend(read_jsonl(operators_path))
        shard_manifests.append(
            {
                "shard_index": shard_index,
                "shard_dir": shard_dir,
                "manifest": manifest,
            }
        )

    os.makedirs(args.output_dir, exist_ok=True)
    write_jsonl(os.path.join(args.output_dir, "queries_alpaca_ro.jsonl"), all_queries)
    write_jsonl(os.path.join(args.output_dir, "operators_alpaca_ro.jsonl"), all_operators)

    merged_manifest = {
        "merged_from": [p for _, p, _ in indexed_shards],
        "num_shards": len(indexed_shards),
        "queries_count": len(all_queries),
        "operators_count": len(all_operators),
        "shards": shard_manifests,
    }
    with open(os.path.join(args.output_dir, "manifest_merged.json"), "w", encoding="utf-8") as f:
        json.dump(merged_manifest, f, ensure_ascii=False, indent=2)

    print(json.dumps(merged_manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
