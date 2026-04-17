"""Endpoint smoke test for Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8 on vLLM.

This script checks:
1) /v1/models reachability
2) /v1/chat/completions response
3) local import paths for vLLM/FlashInfer modules (helpful for mixed-venv bugs)
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8"
DEFAULT_PROMPT = "Return only: SELECT 1;"


def _module_path(name: str) -> str:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return f"<not importable: {exc}>"
    return str(getattr(module, "__file__", "<built-in>"))


def _print_runtime_diagnostics() -> None:
    print("=== PYTHON DIAGNOSTICS ===")
    print(f"python_executable={sys.executable}")
    print(f"python_version={sys.version.split()[0]}")
    print(f"PYTHONPATH={os.getenv('PYTHONPATH', '')}")
    for mod_name in ("vllm", "flashinfer", "flashinfer.data", "tvm_ffi"):
        print(f"{mod_name}={_module_path(mod_name)}")
    print()


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> tuple[int, str]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body
    except Exception as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def _safe_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def run_check(
    base_url: str,
    model: str,
    prompt: str,
    timeout: int,
    skip_env_diagnostics: bool,
) -> int:
    if not skip_env_diagnostics:
        _print_runtime_diagnostics()

    models_url = f"{base_url.rstrip('/')}/models"
    chat_url = f"{base_url.rstrip('/')}/chat/completions"

    print(f"GET {models_url}")
    status, body = _http_json("GET", models_url, timeout=timeout)
    print(f"models_status={status}")
    if status != 200:
        print(body[:2000])
        return 2

    models_payload = _safe_json(body)
    if isinstance(models_payload, dict):
        model_count = len(models_payload.get("data", []))
        print(f"models_count={model_count}")
    else:
        print("models_response=non_json")

    chat_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 512,
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    print(f"\nPOST {chat_url}")
    status, body = _http_json("POST", chat_url, payload=chat_payload, timeout=timeout)
    print(f"chat_status={status}")

    if status != 200:
        print(body[:4000])
        if "EngineCore encountered an issue" in body:
            print(
                "\nHint: EngineCore crashed server-side. If server logs show missing "
                "FlashInfer headers, check that vllm/flashinfer/tvm_ffi are loaded "
                "from the same virtualenv."
            )
        return 1

    payload = _safe_json(body)
    if not isinstance(payload, dict):
        print("chat_response=non_json")
        print(body[:2000])
        return 1

    try:
        content = payload["choices"][0]["message"]["content"]
    except Exception:
        print("chat_response_json_missing_choices")
        print(json.dumps(payload, indent=2)[:4000])
        return 1

    print("=== COMPLETION ===")
    print(str(content).strip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test a local vLLM endpoint.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--skip-env-diagnostics",
        action="store_true",
        help="Skip local python/module path diagnostics output.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_check(
        base_url=args.base_url,
        model=args.model,
        prompt=args.prompt,
        timeout=int(args.timeout),
        skip_env_diagnostics=bool(args.skip_env_diagnostics),
    )


if __name__ == "__main__":
    raise SystemExit(main())
