#!/usr/bin/env python3
"""Evaluate O/A/B/C model variants on a fixed NL->SQL JSONL test set.

Variants:
- O: base model only
- A: base + stage A adapter
- B: base + stage B adapter
- C: base + stage C adapter

Outputs:
- summary.json (aggregate metrics per variant)
- predictions.jsonl (per-case details for error analysis)
"""

from __future__ import annotations

import argparse
import gc
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_SYSTEM_PROMPT = (
    "You are a SQLite text-to-SQL engine.\n"
    "Return exactly one valid SQLite SQL statement and nothing else.\n"
    "Use SQL keywords in English only.\n"
    "Do not translate SQL keywords to Romanian.\n"
    "Do not include markdown fences, comments, or explanations."
)
DEFAULT_DOMAIN_TO_DBID = {
    "education": "edu_reteaua_scolara",
    "trains": "rail_mers_tren",
}
REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SQL_STARTS = (
    "SELECT",
    "WITH",
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "ALTER",
    "DROP",
    "REPLACE",
    "PRAGMA",
    "EXPLAIN",
    "VACUUM",
)


@dataclass
class EvalCase:
    case_id: str
    db_id: str
    system_prompt: str
    user_prompt: str
    gold_sql: str
    source_line: int


@dataclass
class ExecSignature:
    ok: bool
    error: Optional[str]
    signature: Optional[Tuple[str, Tuple[str, ...], Tuple[str, ...], int]]


class SQLiteMemoryRuntime:
    """Execute SQL against in-memory SQLite initialized from dump SQL."""

    def __init__(self, sql_dump_path: Path) -> None:
        self.sql_dump_path = sql_dump_path
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        script = sql_dump_path.read_text(encoding="utf-8")
        self.conn.executescript(script)

    def close(self) -> None:
        self.conn.close()

    def execute_signature(self, sql: str) -> ExecSignature:
        text = str(sql or "").strip()
        if not text:
            return ExecSignature(ok=False, error="empty sql", signature=None)

        cur = self.conn.cursor()
        lowered = text.lower().lstrip()
        try:
            if lowered.startswith("select") or lowered.startswith("with"):
                cur.execute(text)
                rows = cur.fetchall()
                columns = tuple((d[0] if d else "") for d in (cur.description or []))

                # Order-insensitive row signature; keeps duplicates by sorting fingerprints.
                row_fingerprint = tuple(
                    sorted(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
                )
                return ExecSignature(
                    ok=True,
                    error=None,
                    signature=("select", columns, row_fingerprint, len(rows)),
                )

            savepoint = "_eval_savepoint_"
            before = self.conn.total_changes
            self.conn.execute(f"SAVEPOINT {savepoint}")
            try:
                cur.execute(text)
                delta = max(0, int(self.conn.total_changes - before))
                self.conn.execute(f"ROLLBACK TO {savepoint}")
                self.conn.execute(f"RELEASE {savepoint}")
                return ExecSignature(
                    ok=True,
                    error=None,
                    signature=("mutation", tuple(), tuple(), delta),
                )
            except Exception:
                self.conn.execute(f"ROLLBACK TO {savepoint}")
                self.conn.execute(f"RELEASE {savepoint}")
                raise
        except Exception as exc:
            return ExecSignature(ok=False, error=str(exc), signature=None)


def _normalize_sql(sql: str) -> str:
    return " ".join(str(sql or "").strip().split()).rstrip(";").strip().lower()


def _extract_sql(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    if "```" in raw:
        parts = raw.split("```")
        if len(parts) >= 3:
            block = parts[1].strip()
            if block.lower().startswith("sql"):
                block = block[3:].strip()
            raw = block

    low = raw.lower()
    if low.startswith("sql:"):
        raw = raw[4:].strip()

    if ";" in raw:
        first = raw.split(";", 1)[0].strip()
        if first:
            return first + ";"

    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line
    return raw


def _starts_with_sql_keyword(sql: str) -> bool:
    """Check whether output starts with a known SQL keyword."""
    text = str(sql or "").strip()
    if not text:
        return False
    match = re.match(r"^[A-Za-z_]+", text)
    if not match:
        return False
    first = match.group(0).upper()
    return first in ALLOWED_SQL_STARTS


def _parse_db_map(entries: Iterable[str]) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for entry in entries:
        text = str(entry).strip()
        if not text:
            continue
        if "=" not in text:
            raise ValueError(
                f"Invalid --db-map '{text}'. Expected db_id=/path/to/dump.sql"
            )
        db_id, path_str = text.split("=", 1)
        mapping[db_id.strip()] = _resolve_input_path(Path(path_str.strip()))
    return mapping


def _resolve_input_path(path: Path) -> Path:
    """Resolve input paths robustly across working directories.

    Priority:
    1) absolute / expanded path
    2) current working directory
    3) repository root (NLSQLRO)
    """
    p = path.expanduser()
    if p.is_absolute():
        return p
    cwd_candidate = (Path.cwd() / p).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    return (REPO_ROOT / p).resolve()


def _resolve_output_path(path: Path) -> Path:
    """Resolve output path to repo root when relative."""
    p = path.expanduser()
    if p.is_absolute():
        return p
    return (REPO_ROOT / p).resolve()


def _extract_case(
    row: Dict[str, Any],
    line_no: int,
    use_romanian_question: bool,
) -> Optional[EvalCase]:
    metadata = row.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    gold_sql = str(row.get("sql", "")).strip() or str(row.get("output", "")).strip()
    if not gold_sql:
        return None

    db_id = str(row.get("db_id", "")).strip() or str(metadata.get("db_id", "")).strip()
    if not db_id:
        domain = str(row.get("domain", "")).strip() or str(metadata.get("domain", "")).strip()
        db_id = DEFAULT_DOMAIN_TO_DBID.get(domain.lower(), "")
    if not db_id:
        return None

    if "instruction" in row or "input" in row:
        instruction = str(row.get("instruction", "")).strip()
        inp = str(row.get("input", "")).strip()
        if instruction and inp:
            user_prompt = f"{instruction}\n\n{inp}"
        else:
            user_prompt = instruction or inp
        system_prompt = str(row.get("system", "")).strip() or DEFAULT_SYSTEM_PROMPT
    else:
        q_ro = str(row.get("question_ro", "")).strip()
        q_en = str(row.get("question_en", "")).strip()
        user_prompt = q_ro if use_romanian_question else q_en
        if not user_prompt:
            user_prompt = q_en or q_ro
        system_prompt = DEFAULT_SYSTEM_PROMPT

    if not user_prompt:
        return None

    case_id = (
        str(row.get("id", "")).strip()
        or str(metadata.get("id", "")).strip()
        or f"line_{line_no}"
    )
    return EvalCase(
        case_id=case_id,
        db_id=db_id,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        gold_sql=gold_sql,
        source_line=line_no,
    )


def _load_cases(
    test_set_path: Path,
    use_romanian_question: bool,
    max_samples: Optional[int],
) -> List[EvalCase]:
    cases: List[EvalCase] = []
    with test_set_path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            case = _extract_case(
                row=row,
                line_no=line_no,
                use_romanian_question=use_romanian_question,
            )
            if case is None:
                continue
            cases.append(case)
            if max_samples is not None and len(cases) >= max_samples:
                break
    return cases


def _dtype_arg(dtype: str):
    import torch

    key = dtype.lower().strip()
    if key == "auto":
        return "auto"
    if key == "bf16":
        return torch.bfloat16
    if key == "fp16":
        return torch.float16
    if key == "fp32":
        return torch.float32
    raise ValueError(f"Unsupported dtype: {dtype}")


def _load_model_and_tokenizer(
    base_model: str,
    adapter_path: Optional[Path],
    dtype: str,
    trust_remote_code: bool,
):
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        base_model,
        trust_remote_code=trust_remote_code,
    )
    if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=_dtype_arg(dtype),
        device_map="auto",
        trust_remote_code=trust_remote_code,
    )
    if adapter_path is not None:
        model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()
    return tokenizer, model


def _generate_sql(
    model: Any,
    tokenizer: Any,
    system_prompt: str,
    user_prompt: str,
    max_new_tokens: int,
    retry_hint: Optional[str] = None,
) -> str:
    import torch

    effective_user_prompt = user_prompt
    if retry_hint:
        effective_user_prompt = f"{user_prompt}\n\n{retry_hint}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": effective_user_prompt},
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    tokens = tokenizer(prompt, return_tensors="pt")
    device = next(model.parameters()).device
    tokens = {k: v.to(device) for k, v in tokens.items()}

    with torch.no_grad():
        outputs = model.generate(
            **tokens,
            do_sample=False,
            temperature=0.0,
            top_p=1.0,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated = outputs[0][tokens["input_ids"].shape[1] :]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    return _extract_sql(text)


def _free_model(model: Any, tokenizer: Any) -> None:
    del model
    del tokenizer
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate O/A/B/C variants on an NL->SQL JSONL test set."
    )
    parser.add_argument("--test-set", required=True, help="Path to test JSONL.")
    parser.add_argument(
        "--base-model",
        default="OpenLLM-Ro/RoLlama3.1-8b-Instruct",
        help="Base model id/path.",
    )
    parser.add_argument(
        "--adapter-a",
        default="/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora",
        help="Adapter path for variant A.",
    )
    parser.add_argument(
        "--adapter-b",
        default="/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_b_rogov_lora",
        help="Adapter path for variant B.",
    )
    parser.add_argument(
        "--adapter-c",
        default="/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_c_mix_lora",
        help="Adapter path for variant C.",
    )
    parser.add_argument(
        "--db-map",
        action="append",
        default=[],
        help="Repeatable: db_id=/path/to/sql_dump.sql",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/eval_variants",
        help="Directory for summary.json and predictions.jsonl",
    )
    parser.add_argument("--max-samples", type=int, default=200)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--dtype", choices=["auto", "bf16", "fp16", "fp32"], default="bf16")
    parser.add_argument(
        "--use-english-question",
        action="store_true",
        help="For master rows, use question_en instead of question_ro.",
    )
    parser.add_argument(
        "--sql-retry-count",
        type=int,
        default=2,
        help=(
            "Additional retries if output does not start with a valid SQL keyword. "
            "Total attempts = 1 + sql-retry-count."
        ),
    )
    parser.add_argument("--trust-remote-code", action="store_true")
    args = parser.parse_args()

    test_set_path = _resolve_input_path(Path(args.test_set))
    if not test_set_path.exists():
        raise FileNotFoundError(f"Missing test set: {test_set_path}")

    out_dir = _resolve_output_path(Path(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    db_map = _parse_db_map(args.db_map)
    if not db_map:
        db_map = {
            "edu_reteaua_scolara": _resolve_input_path(
                Path("research_plan/Faza_1/edu_reteaua_scolara.sql")
            ),
            "rail_mers_tren": _resolve_input_path(
                Path("research_plan/Faza_1/rail_mers_tren.sql")
            ),
        }
    missing = [f"{db}:{path}" for db, path in db_map.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing SQL dumps:\n- " + "\n- ".join(missing))

    cases = _load_cases(
        test_set_path=test_set_path,
        use_romanian_question=not args.use_english_question,
        max_samples=args.max_samples,
    )
    if not cases:
        raise ValueError("No valid eval rows found in test set.")

    runtimes = {db_id: SQLiteMemoryRuntime(path) for db_id, path in db_map.items()}
    gold_exec: Dict[str, ExecSignature] = {}
    for case in cases:
        rt = runtimes.get(case.db_id)
        if rt is None:
            gold_exec[case.case_id] = ExecSignature(
                ok=False,
                error=f"unknown db_id {case.db_id}",
                signature=None,
            )
        else:
            gold_exec[case.case_id] = rt.execute_signature(case.gold_sql)

    variants: List[Tuple[str, Optional[Path]]] = [("O", None)]
    for name, path_str in [("A", args.adapter_a), ("B", args.adapter_b), ("C", args.adapter_c)]:
        if path_str:
            path = Path(path_str)
            if path.exists():
                variants.append((name, path))
            else:
                print(f"[eval] skip {name}: adapter path not found: {path}", flush=True)

    summary: Dict[str, Any] = {
        "test_set": str(test_set_path),
        "num_cases": len(cases),
        "variants": {},
        "created_epoch": int(time.time()),
    }
    details_path = out_dir / "predictions.jsonl"
    summary_path = out_dir / "summary.json"

    with details_path.open("w", encoding="utf-8") as details_fh:
        for variant_name, adapter_path in variants:
            label = f"{variant_name} (base)" if adapter_path is None else f"{variant_name} ({adapter_path})"
            print(f"[eval] loading {label}", flush=True)
            t0 = time.time()

            tokenizer, model = _load_model_and_tokenizer(
                base_model=args.base_model,
                adapter_path=adapter_path,
                dtype=args.dtype,
                trust_remote_code=bool(args.trust_remote_code),
            )

            metrics = {
                "total": 0,
                "generated": 0,
                "generation_errors": 0,
                "sql_prefix_failures": 0,
                "exact_sql_match": 0,
                "pred_exec_ok": 0,
                "exec_match": 0,
                "gold_exec_failures": 0,
            }

            for i, case in enumerate(cases, start=1):
                metrics["total"] += 1
                gold = gold_exec.get(case.case_id)
                rt = runtimes.get(case.db_id)

                result_row: Dict[str, Any] = {
                    "variant": variant_name,
                    "case_id": case.case_id,
                    "db_id": case.db_id,
                    "gold_sql": case.gold_sql,
                    "source_line": case.source_line,
                }

                if rt is None or gold is None or not gold.ok:
                    metrics["gold_exec_failures"] += 1
                    result_row["error"] = (
                        "gold_exec_failed: "
                        + (gold.error if gold is not None else f"unknown db_id {case.db_id}")
                    )
                    details_fh.write(json.dumps(result_row, ensure_ascii=False) + "\n")
                    continue

                pred_sql = ""
                generation_exception: Optional[Exception] = None
                used_attempts = 0
                max_attempts = max(1, 1 + int(args.sql_retry_count))
                for attempt in range(max_attempts):
                    retry_hint = None
                    if attempt > 0:
                        retry_hint = (
                            "Previous answer was invalid. Return only one SQLite SQL statement. "
                            "Start with one of: SELECT, WITH, INSERT, UPDATE, DELETE, CREATE, "
                            "ALTER, DROP, REPLACE, PRAGMA, EXPLAIN, VACUUM."
                        )
                    try:
                        candidate_sql = _generate_sql(
                            model=model,
                            tokenizer=tokenizer,
                            system_prompt=case.system_prompt,
                            user_prompt=case.user_prompt,
                            max_new_tokens=args.max_new_tokens,
                            retry_hint=retry_hint,
                        )
                        used_attempts = attempt + 1
                        pred_sql = candidate_sql
                        if _starts_with_sql_keyword(candidate_sql):
                            break
                    except Exception as exc:
                        generation_exception = exc
                        used_attempts = attempt + 1
                        pred_sql = ""
                        break

                if generation_exception is not None:
                    metrics["generation_errors"] += 1
                    result_row["error"] = f"generation_failed: {generation_exception}"
                    details_fh.write(json.dumps(result_row, ensure_ascii=False) + "\n")
                    continue
                metrics["generated"] += 1

                if not _starts_with_sql_keyword(pred_sql):
                    metrics["sql_prefix_failures"] += 1
                    result_row.update(
                        {
                            "pred_sql": pred_sql,
                            "pred_exec_ok": False,
                            "pred_exec_error": (
                                f"invalid_sql_prefix_after_{used_attempts}_attempts; "
                                f"allowed={','.join(ALLOWED_SQL_STARTS)}"
                            ),
                            "exact_sql_match": False,
                            "exec_match": False,
                            "retry_attempts": used_attempts,
                        }
                    )
                    details_fh.write(json.dumps(result_row, ensure_ascii=False) + "\n")
                    continue

                pred_exec = rt.execute_signature(pred_sql)
                exact = _normalize_sql(pred_sql) == _normalize_sql(case.gold_sql)
                exec_match = bool(
                    pred_exec.ok
                    and gold.ok
                    and pred_exec.signature is not None
                    and pred_exec.signature == gold.signature
                )

                if exact:
                    metrics["exact_sql_match"] += 1
                if pred_exec.ok:
                    metrics["pred_exec_ok"] += 1
                if exec_match:
                    metrics["exec_match"] += 1

                result_row.update(
                    {
                        "pred_sql": pred_sql,
                        "pred_exec_ok": pred_exec.ok,
                        "pred_exec_error": pred_exec.error,
                        "exact_sql_match": exact,
                        "exec_match": exec_match,
                        "retry_attempts": used_attempts,
                    }
                )
                details_fh.write(json.dumps(result_row, ensure_ascii=False) + "\n")

                if i % 20 == 0 or i == len(cases):
                    print(
                        f"[eval] {variant_name} {i}/{len(cases)} "
                        f"exact={metrics['exact_sql_match']} exec={metrics['exec_match']}",
                        flush=True,
                    )

            elapsed = time.time() - t0
            denom = max(1, metrics["total"] - metrics["gold_exec_failures"])
            variant_summary = {
                **metrics,
                "exact_sql_match_rate": metrics["exact_sql_match"] / denom,
                "pred_exec_ok_rate": metrics["pred_exec_ok"] / denom,
                "exec_match_rate": metrics["exec_match"] / denom,
                "elapsed_seconds": elapsed,
            }
            summary["variants"][variant_name] = variant_summary

            print(
                f"[eval] done {variant_name} in {elapsed:.1f}s | "
                f"exact={variant_summary['exact_sql_match_rate']:.3f} "
                f"exec={variant_summary['exec_match_rate']:.3f}",
                flush=True,
            )
            _free_model(model=model, tokenizer=tokenizer)

    for rt in runtimes.values():
        rt.close()

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[eval] summary: {summary_path}", flush=True)
    print(f"[eval] details: {details_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
