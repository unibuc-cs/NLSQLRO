# dataset_generator

`dataset_generator` is the core package for synthetic Romanian NL-to-SQL data
generation, validation, export, and training-data preparation.

## Responsibilities

- load generation configs
- introspect SQL dumps
- call provider backends for NL-to-SQL generation
- validate generated SQL against SQLite dumps
- export `master`, `alpaca`, and `chat` artifacts
- prepare normalized LLaMA-Factory datasets
- orchestrate multi-GPU generation runs

## Main Commands

Run from repository root.

Generate:

```bash
python -m dataset_generator.cli generate \
  --config dataset_generator/configs/vllm.template.json
```

Validate:

```bash
python -m dataset_generator.cli validate \
  --config dataset_generator/configs/vllm.template.json
```

Inspect schema/value hints:

```bash
python -m dataset_generator.cli introspect \
  --config dataset_generator/configs/vllm.template.json
```

Multi-GPU generation:

```bash
python -m dataset_generator.cli generate-multi-gpu \
  --config dataset_generator/configs/vllm.template.json \
  --gpus 0,1,2,3 \
  --base-urls http://127.0.0.1:8001/v1,http://127.0.0.1:8002/v1,http://127.0.0.1:8003/v1,http://127.0.0.1:8004/v1 \
  --artifact alpaca \
  --work-dir datasets/multi_gpu_runs
```

Prepare LLaMA-Factory datasets:

```bash
python -m dataset_generator.cli prepare-llamafactory \
  --out-dir datasets/llamafactory
```

## Config Files

- `configs/default.mock.json`: mock/local smoke config
- `configs/vllm.smoke.8001.json`: single-endpoint smoke run
- `configs/vllm.template.json`: main vLLM generation template
- `configs/openai.template.json`: OpenAI-compatible template
- `configs/qwen.template.json`: Qwen-compatible template

## Important Config Fields

- `provider.mode`: backend type (`mock`, `qwen_compatible`, etc.)
- `provider.base_url`: endpoint root for OpenAI-compatible APIs
- `provider.teacher_model`: served model identifier
- `domains[].sql_dump`: path to SQL dump used for execution validation
- `generation.max_attempts_per_example`: retry limit per accepted sample
- `generation.max_total_attempts_factor`: global cap multiplier
- `output.out_dir`: output directory for generated artifacts

## Outputs

Standard generation writes:

- `rogov_master.jsonl`
- `rogov_alpaca.jsonl`
- `rogov_chat.jsonl`
- `stats.json`

Multi-GPU generation writes per-run artifacts under `datasets/multi_gpu_runs/`,
including merged outputs and worker manifests.

LLaMA-Factory preparation writes normalized training datasets under
`datasets/llamafactory/`.

## Related Documentation

- [Repository root guide](/mnt/home/fizlabrl/NLSQLRO/README.md)
- [External dataset guide](/mnt/home/fizlabrl/NLSQLRO/datasets_external/README.md)
- [Fine-tuning runbook](/mnt/home/fizlabrl/NLSQLRO/FINETUNING.md)
