"""Clean and validate Madlad-translated Alpaca NL->SQL datasets.

Goals:
- keep SQL/context untouched (English table/column/sql syntax remains unchanged)
- fix mojibake only in Romanian natural-language fields
- optionally validate each example by executing context + output SQL in SQLite
- support parallel processing for large datasets
- produce cleaned JSONL files + manifest with drop reasons
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCHEMA_MARKER = "Schema / context SQL:\n"
QUESTION_LABEL_CANONICAL = "Întrebare:"
REQUIRED_KEYS = ("instruction", "input", "output", "system", "metadata")


SUSPICIOUS_TOKENS = (
    "Ã",
    "ÃŽ",
    "Ã®",
    "Ã¢",
    "Ã‚",
    "Äƒ",
    "Ä‚",
    "È™",
    "È˜",
    "È›",
    "Èš",
    "ÅŸ",
    "Å£",
    "Å¢",
    "â€™",
    "â€œ",
    "â€",
    "â€“",
    "â€”",
    "â€¦",
)


MANUAL_FIXES = {
    "â€™": "’",
    "â€œ": "“",
    "â€": "”",
    "â€“": "-",
    "â€”": "-",
    "â€¦": "...",
    "ÃŽ": "Î",
    "Ã®": "î",
    "Äƒ": "ă",
    "Ä‚": "Ă",
    "Ã¢": "â",
    "Ã‚": "Â",
    "È™": "ș",
    "È˜": "Ș",
    "È›": "ț",
    "Èš": "Ț",
    "ÅŸ": "ș",
    "Å¢": "Ț",
    "Å£": "ț",
}


SQL_ALLOWED_BY_TRACK = {
    "operators": {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE"},
    "queries": {"SELECT", "WITH"},
}

TRACK_TO_TASK = {
    "operators": "operator",
    "queries": "user",
}


@dataclass
class WorkerOptions:
    validate_sql: bool
    strict_sql_type: bool


def _first_sql_keyword(sql: str) -> str:
    sql = sql.lstrip()
    if not sql:
        return "UNKNOWN"
    token = []
    for ch in sql:
        if ch.isalpha() or ch == "_":
            token.append(ch)
        else:
            break
    return "".join(token).upper() if token else "UNKNOWN"


def _contains_suspicious(text: str) -> bool:
    return any(tok in text for tok in SUSPICIOUS_TOKENS)


def _score_text_quality(text: str) -> int:
    bad = sum(text.count(tok) for tok in SUSPICIOUS_TOKENS)
    good = sum(text.count(ch) for ch in "ăâîșțĂÂÎȘȚ")
    replacement = text.count("�")
    return good * 3 - bad * 4 - replacement * 8


def _manual_fix(text: str) -> str:
    out = text
    for src, dst in MANUAL_FIXES.items():
        out = out.replace(src, dst)
    return out


def _decode_candidates(text: str) -> List[str]:
    candidates = [text]
    for enc in ("latin1", "cp1252"):
        try:
            decoded = text.encode(enc).decode("utf-8")
            candidates.append(decoded)
        except Exception:
            pass
    return candidates


def fix_mojibake_text(text: str) -> Tuple[str, bool]:
    """Return potentially fixed text and whether a change was applied."""
    if not text:
        return text, False
    if not _contains_suspicious(text):
        return text, False

    best = text
    best_score = _score_text_quality(text)

    for cand in _decode_candidates(text):
        fixed = _manual_fix(cand)
        score = _score_text_quality(fixed)
        if score > best_score:
            best = fixed
            best_score = score

    # One extra pass on the selected variant to catch leftover tokens.
    best2 = _manual_fix(best)
    if _score_text_quality(best2) >= best_score:
        best = best2

    return best, best != text


def _split_input_context_question(raw_input: str) -> Optional[Tuple[str, str, str]]:
    """Parse input into context SQL, label, question text."""
    if SCHEMA_MARKER not in raw_input:
        return None

    _, tail = raw_input.split(SCHEMA_MARKER, 1)
    if "\n\n" not in tail:
        return None
    context_sql, question_block = tail.split("\n\n", 1)

    if "\n" in question_block:
        label, question_text = question_block.split("\n", 1)
    else:
        label, question_text = question_block, ""

    return context_sql, label.strip(), question_text.strip()


def _rebuild_input(context_sql: str, question_text_ro: str) -> str:
    return (
        f"{SCHEMA_MARKER}"
        f"{context_sql}\n\n"
        f"{QUESTION_LABEL_CANONICAL}\n"
        f"{question_text_ro}"
    )


def _validate_sql_with_context(context_sql: str, output_sql: str) -> Tuple[bool, str]:
    """Execute context script then output SQL in SQLite."""
    conn = sqlite3.connect(":memory:")
    try:
        cur = conn.cursor()
        if context_sql.strip():
            cur.executescript(context_sql)
        cur.execute(output_sql)
        try:
            cur.fetchall()
        except Exception:
            pass
        return True, ""
    except Exception as exc:
        return False, str(exc)
    finally:
        conn.close()


def _clean_one_record(
    line_no: int,
    raw_line: str,
    track: str,
    options: WorkerOptions,
) -> Dict[str, object]:
    result: Dict[str, object] = {
        "line_no": line_no,
        "ok": False,
        "drop_reason": "",
        "fixed_any_text": False,
        "changed_fields": [],
    }

    raw_line = raw_line.strip()
    if not raw_line:
        result["drop_reason"] = "empty_line"
        return result

    try:
        obj = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        result["drop_reason"] = f"invalid_json: {exc}"
        return result

    for req in REQUIRED_KEYS:
        if req not in obj:
            result["drop_reason"] = f"missing_key:{req}"
            return result

    if not isinstance(obj.get("metadata"), dict):
        result["drop_reason"] = "metadata_not_object"
        return result

    output_sql = str(obj.get("output", "")).strip()
    if not output_sql:
        result["drop_reason"] = "empty_output_sql"
        return result

    if options.strict_sql_type:
        keyword = _first_sql_keyword(output_sql)
        allowed = SQL_ALLOWED_BY_TRACK.get(track, set())
        if allowed and keyword not in allowed:
            result["drop_reason"] = f"sql_keyword_not_allowed:{keyword}"
            return result

    # Fix mojibake only in natural language fields.
    changed_fields: List[str] = []
    for field_name in ("instruction", "system"):
        fixed, changed = fix_mojibake_text(str(obj.get(field_name, "")))
        if changed:
            obj[field_name] = fixed
            changed_fields.append(field_name)

    meta = obj["metadata"]
    canonical_task = TRACK_TO_TASK.get(track, "user")
    obj["task"] = canonical_task
    meta["task"] = canonical_task
    if "sql_explanation_ro" in meta:
        fixed, changed = fix_mojibake_text(str(meta.get("sql_explanation_ro", "")))
        if changed:
            meta["sql_explanation_ro"] = fixed
            changed_fields.append("metadata.sql_explanation_ro")

    # Preserve SQL context exactly; normalize only question text and label.
    input_parts = _split_input_context_question(str(obj.get("input", "")))
    if input_parts is None:
        result["drop_reason"] = "input_parse_failed"
        return result
    context_sql, _label, question_text = input_parts
    fixed_question, q_changed = fix_mojibake_text(question_text)
    obj["input"] = _rebuild_input(context_sql=context_sql, question_text_ro=fixed_question)
    if q_changed:
        changed_fields.append("input.question_ro")

    if options.validate_sql:
        ok, err = _validate_sql_with_context(context_sql=context_sql, output_sql=output_sql)
        if not ok:
            result["drop_reason"] = f"sql_exec_failed:{err}"
            return result

    result["ok"] = True
    result["clean_line"] = json.dumps(obj, ensure_ascii=False)
    result["fixed_any_text"] = bool(changed_fields)
    result["changed_fields"] = changed_fields
    return result


def _iter_jsonl_lines(path: Path, max_lines: Optional[int]) -> Iterable[Tuple[int, str]]:
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, start=1):
            if max_lines is not None and idx > max_lines:
                break
            yield idx, line


def _clean_one_record_star(args: Tuple[int, str, str, WorkerOptions]) -> Dict[str, object]:
    return _clean_one_record(*args)


def clean_file(
    input_path: Path,
    output_path: Path,
    track: str,
    options: WorkerOptions,
    workers: int,
    max_lines: Optional[int],
) -> Dict[str, object]:
    counters = Counter()
    changed_fields_counter = Counter()
    sample_drops: List[Dict[str, object]] = []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines_iter = _iter_jsonl_lines(input_path, max_lines=max_lines)

    with output_path.open("w", encoding="utf-8") as out_fh:
        if workers <= 1:
            for line_no, raw_line in lines_iter:
                res = _clean_one_record(line_no, raw_line, track, options)
                counters["total"] += 1
                if res["ok"]:
                    counters["kept"] += 1
                    if res["fixed_any_text"]:
                        counters["rows_with_text_fixes"] += 1
                    for fld in res["changed_fields"]:
                        changed_fields_counter[fld] += 1
                    out_fh.write(str(res["clean_line"]) + "\n")
                else:
                    counters["dropped"] += 1
                    reason = str(res["drop_reason"]).split(":", 1)[0]
                    counters[f"drop_{reason}"] += 1
                    if len(sample_drops) < 20:
                        sample_drops.append(
                            {"line_no": line_no, "drop_reason": res["drop_reason"]}
                        )
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                args_iter = (
                    (line_no, raw_line, track, options) for line_no, raw_line in lines_iter
                )
                for res in ex.map(_clean_one_record_star, args_iter, chunksize=100):
                    counters["total"] += 1
                    if res["ok"]:
                        counters["kept"] += 1
                        if res["fixed_any_text"]:
                            counters["rows_with_text_fixes"] += 1
                        for fld in res["changed_fields"]:
                            changed_fields_counter[fld] += 1
                        out_fh.write(str(res["clean_line"]) + "\n")
                    else:
                        counters["dropped"] += 1
                        reason = str(res["drop_reason"]).split(":", 1)[0]
                        counters[f"drop_{reason}"] += 1
                        if len(sample_drops) < 20:
                            sample_drops.append(
                                {
                                    "line_no": res["line_no"],
                                    "drop_reason": res["drop_reason"],
                                }
                            )

    keep_rate = (counters["kept"] / counters["total"]) if counters["total"] else 0.0
    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "track": track,
        "workers": workers,
        "validate_sql": options.validate_sql,
        "strict_sql_type": options.strict_sql_type,
        "max_lines": max_lines,
        "counters": dict(counters),
        "keep_rate": keep_rate,
        "changed_fields": dict(changed_fields_counter),
        "sample_drops": sample_drops,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean and validate madlad_4gpu_full_merged dataset files."
    )
    parser.add_argument(
        "--input-dir",
        default="madlad_4gpu_full_merged",
        help="Input directory containing operators_alpaca_ro.jsonl and queries_alpaca_ro.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        default="madlad_4gpu_full_merged_clean",
        help="Output directory for cleaned files and manifest",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, os.cpu_count() or 1),
        help="Parallel workers (use 1 for sequential mode).",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=None,
        help="Optional cap for quick tests (per file).",
    )
    parser.add_argument(
        "--no-validate-sql",
        action="store_true",
        help="Skip SQL execution validation (faster, less strict).",
    )
    parser.add_argument(
        "--strict-sql-type",
        action="store_true",
        help="Enforce SQL keyword families by track (queries=SELECT/WITH, operators=DML/DDL).",
    )
    return parser


def _normalize_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return Path(os.path.abspath(str(path)))


def main() -> int:
    args = build_parser().parse_args()
    input_dir = _normalize_path(Path(args.input_dir))
    output_dir = _normalize_path(Path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    options = WorkerOptions(
        validate_sql=not args.no_validate_sql,
        strict_sql_type=bool(args.strict_sql_type),
    )

    file_specs = [
        (
            "operators",
            input_dir / "operators_alpaca_ro.jsonl",
            output_dir / "operators_alpaca_ro.clean.jsonl",
        ),
        (
            "queries",
            input_dir / "queries_alpaca_ro.jsonl",
            output_dir / "queries_alpaca_ro.clean.jsonl",
        ),
    ]

    summaries: Dict[str, object] = {}
    for track, in_path, out_path in file_specs:
        if not in_path.exists():
            raise FileNotFoundError(f"Missing input file: {in_path}")
        print(f"[{track}] cleaning {in_path} -> {out_path}")
        summary = clean_file(
            input_path=in_path,
            output_path=out_path,
            track=track,
            options=options,
            workers=max(1, int(args.workers)),
            max_lines=args.max_lines,
        )
        summaries[track] = summary
        counters = summary["counters"]
        print(
            f"[{track}] kept={counters.get('kept', 0)} "
            f"dropped={counters.get('dropped', 0)} "
            f"keep_rate={summary['keep_rate']:.4f}"
        )

    manifest = {
        "source_dir": str(input_dir),
        "output_dir": str(output_dir),
        "workers": max(1, int(args.workers)),
        "validate_sql": options.validate_sql,
        "strict_sql_type": options.strict_sql_type,
        "max_lines": args.max_lines,
        "results": summaries,
    }
    manifest_path = output_dir / "manifest_clean.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Manifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
