"""Quick smoke test for Qwen model inference."""

from __future__ import annotations

import argparse
import time
from typing import Dict


DEFAULT_MODEL = "Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8"
DEFAULT_SYSTEM = (
    "You are a concise assistant. Answer clearly and keep the output short."
)
DEFAULT_PROMPT = "Write one SQLite query that lists 5 schools from Cluj county."


def _build_prompt(tokenizer, system_prompt: str, user_prompt: str) -> str:
    """Build chat-formatted prompt if tokenizer supports chat templates."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        return (
            f"System: {system_prompt}\n"
            f"User: {user_prompt}\n"
            "Assistant:"
        )


def _resolve_input_device(model):
    """Pick a device that accepts model inputs when using device_map='auto'."""
    device_map = getattr(model, "hf_device_map", None)
    if isinstance(device_map, dict):
        for location in device_map.values():
            if isinstance(location, int):
                return f"cuda:{location}"
            if isinstance(location, str) and location.startswith("cuda"):
                return location
    try:
        import torch

        return str(next(model.parameters()).device)
    except Exception:
        return "cpu"


def _load_model_and_tokenizer(model_id: str):
    """Load tokenizer + model with actionable errors."""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:
        raise RuntimeError(
            "Missing dependencies. Install: "
            "pip install -U torch transformers accelerate optimum"
        ) from exc

    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available. This smoke test expects NVIDIA GPU runtime."
        )
    is_gptq = "gptq" in model_id.lower()
    if is_gptq:
        try:
            import gptqmodel  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "Missing GPTQ backend. Install: "
                "pip install -U gptqmodel --no-build-isolation\n"
                "Note: AutoGPTQ is no longer supported by recent Transformers."
            ) from exc

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            trust_remote_code=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            device_map="auto",
            torch_dtype="auto",
            trust_remote_code=True,
        )
    except Exception as exc:
        message = str(exc).lower().replace("-", "_")
        if is_gptq and (
            "gptq" in message
            or "auto_gptq" in message
            or "gptqmodel" in message
            or "optimum" in message
        ):
            raise RuntimeError(
                "Failed to load GPTQ backend. Install: "
                "pip install -U accelerate optimum transformers gptqmodel"
            ) from exc
        raise
    return tokenizer, model


def _count_gptq_modules(model) -> int:
    """Heuristic: count modules that look like GPTQ quantized layers."""
    count = 0
    for module in model.modules():
        name = module.__class__.__name__.lower()
        if "quantlinear" in name or "gptq" in name:
            count += 1
            continue
        if hasattr(module, "qweight") and hasattr(module, "qzeros"):
            count += 1
    return count


def _print_runtime_info(model_id: str, model) -> None:
    """Print model/device diagnostics."""
    try:
        import torch

        gpu_count = torch.cuda.device_count()
    except Exception:
        gpu_count = 0

    device_map = getattr(model, "hf_device_map", None)
    print(f"model_id={model_id}")
    print(f"gpu_count={gpu_count}")
    if isinstance(device_map, dict):
        print(f"hf_device_map={device_map}")
    else:
        try:
            print(f"model_device={next(model.parameters()).device}")
        except Exception:
            print("model_device=unknown")


def run_test(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> int:
    """Run one generation pass and print output + timing."""
    import torch

    tokenizer, model = _load_model_and_tokenizer(model_id=model_id)
    gptq_layer_count = _count_gptq_modules(model)
    if "gptq" in model_id.lower() and gptq_layer_count == 0:
        raise RuntimeError(
            "Model loaded but GPTQ layers were not detected. "
            "This typically means incompatible Transformers/GPTQ backend and "
            "produces corrupted output.\n"
            "Upgrade stack:\n"
            "  pip install -U 'transformers[serving] @ "
            "git+https://github.com/huggingface/transformers.git@main'\n"
            "  pip install -U accelerate optimum gptqmodel --no-build-isolation"
        )
    _print_runtime_info(model_id=model_id, model=model)
    if "gptq" in model_id.lower():
        print(f"gptq_layer_count={gptq_layer_count}")

    prompt = _build_prompt(
        tokenizer=tokenizer,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    input_device = _resolve_input_device(model)
    inputs = tokenizer(prompt, return_tensors="pt")
    inputs = {k: v.to(input_device) for k, v in inputs.items()}

    generate_kwargs: Dict[str, object] = {
        "max_new_tokens": int(max_new_tokens),
        "do_sample": temperature > 0.0,
        "temperature": float(temperature),
        "top_p": float(top_p),
        "pad_token_id": tokenizer.eos_token_id,
    }
    if temperature <= 0.0:
        generate_kwargs.pop("temperature", None)
        generate_kwargs.pop("top_p", None)

    start = time.time()
    with torch.no_grad():
        output_ids = model.generate(**inputs, **generate_kwargs)
    elapsed = max(1e-6, time.time() - start)

    prompt_len = int(inputs["input_ids"].shape[1])
    completion_ids = output_ids[0][prompt_len:]
    completion_text = tokenizer.decode(completion_ids, skip_special_tokens=True).strip()

    token_count = int(completion_ids.shape[0])
    tok_per_sec = token_count / elapsed

    print(f"elapsed_seconds={elapsed:.2f}")
    print(f"generated_tokens={token_count}")
    print(f"tokens_per_second={tok_per_sec:.2f}")
    print("\n=== OUTPUT ===")
    print(completion_text or "<empty>")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke test Qwen model generation."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HF model id")
    parser.add_argument("--system", default=DEFAULT_SYSTEM, help="System prompt")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="User prompt")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_test(
        model_id=args.model,
        system_prompt=args.system,
        user_prompt=args.prompt,
        max_new_tokens=int(args.max_new_tokens),
        temperature=float(args.temperature),
        top_p=float(args.top_p),
    )


if __name__ == "__main__":
    raise SystemExit(main())
