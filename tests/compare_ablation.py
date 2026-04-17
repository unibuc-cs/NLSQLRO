#!/usr/bin/env python3
"""Compare two evaluation summary.json files side-by-side.

Intended for ablations like:
- path 1: A3000 -> B -> C
- path 2: A6000 -> B -> C
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def _load_summary(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "variants" not in data:
        raise ValueError(f"Invalid summary format: {path}")
    variants = data.get("variants")
    if not isinstance(variants, dict):
        raise ValueError(f"Invalid variants format: {path}")
    return data


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fmt_delta(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.2f}pp"


def _variant_metrics(summary: Dict[str, Any], variant: str) -> Dict[str, float]:
    variants = summary.get("variants", {})
    raw = variants.get(variant, {})
    return {
        "exact_sql_match_rate": float(raw.get("exact_sql_match_rate", 0.0)),
        "pred_exec_ok_rate": float(raw.get("pred_exec_ok_rate", 0.0)),
        "exec_match_rate": float(raw.get("exec_match_rate", 0.0)),
    }


def _build_rows(
    left_summary: Dict[str, Any],
    right_summary: Dict[str, Any],
    variants: List[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for v in variants:
        l = _variant_metrics(left_summary, v)
        r = _variant_metrics(right_summary, v)
        rows.append(
            {
                "variant": v,
                "left": l,
                "right": r,
                "delta_exact": r["exact_sql_match_rate"] - l["exact_sql_match_rate"],
                "delta_exec_ok": r["pred_exec_ok_rate"] - l["pred_exec_ok_rate"],
                "delta_exec_match": r["exec_match_rate"] - l["exec_match_rate"],
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two evaluation summary.json files."
    )
    parser.add_argument("--left-summary", required=True, help="Path to left summary.json")
    parser.add_argument("--right-summary", required=True, help="Path to right summary.json")
    parser.add_argument("--left-label", default="A3000 path", help="Label for left run")
    parser.add_argument("--right-label", default="A6000 path", help="Label for right run")
    parser.add_argument(
        "--variants",
        default="O,A,B,C",
        help="Comma-separated variants to compare (default: O,A,B,C)",
    )
    parser.add_argument(
        "--out-json",
        default=None,
        help="Optional path to write comparison JSON payload.",
    )
    args = parser.parse_args()

    left_path = Path(args.left_summary)
    right_path = Path(args.right_summary)
    left = _load_summary(left_path)
    right = _load_summary(right_path)

    variants = [v.strip() for v in str(args.variants).split(",") if v.strip()]
    rows = _build_rows(left, right, variants)

    print(f"Left : {args.left_label} ({left_path})")
    print(f"Right: {args.right_label} ({right_path})")
    print()
    print(
        "| Variant | Exact (L) | Exact (R) | Delta | ExecOK (L) | ExecOK (R) | Delta | ExecMatch (L) | ExecMatch (R) | Delta |"
    )
    print(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for row in rows:
        l = row["left"]
        r = row["right"]
        print(
            "| {variant} | {el} | {er} | {de} | {ol} | {or_} | {do} | {ml} | {mr} | {dm} |".format(
                variant=row["variant"],
                el=_fmt_pct(l["exact_sql_match_rate"]),
                er=_fmt_pct(r["exact_sql_match_rate"]),
                de=_fmt_delta(row["delta_exact"]),
                ol=_fmt_pct(l["pred_exec_ok_rate"]),
                or_=_fmt_pct(r["pred_exec_ok_rate"]),
                do=_fmt_delta(row["delta_exec_ok"]),
                ml=_fmt_pct(l["exec_match_rate"]),
                mr=_fmt_pct(r["exec_match_rate"]),
                dm=_fmt_delta(row["delta_exec_match"]),
            )
        )

    # Short decision helper focused on final variant C.
    c_row = next((x for x in rows if x["variant"] == "C"), None)
    if c_row is not None:
        better = args.right_label if c_row["delta_exec_match"] > 0 else args.left_label
        if c_row["delta_exec_match"] == 0:
            better = "tie"
        print()
        print(
            "C-variant decision (by exec_match_rate): "
            f"{better} ({_fmt_delta(c_row['delta_exec_match'])})"
        )

    if args.out_json:
        payload = {
            "left_label": args.left_label,
            "right_label": args.right_label,
            "left_summary": str(left_path),
            "right_summary": str(right_path),
            "rows": rows,
        }
        out_path = Path(args.out_json)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"comparison_json: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

