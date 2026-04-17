# NLSQLRO

NLSQLRO is a Romanian NL-to-SQL dataset project built around three parts:

- `dataset_generator/`: synthetic data generation pipeline
- `datasets_external/`: external dataset preprocessing and translation workspace
- `research_plan/`: source materials and SQL dump preparation scripts

The repository supports local generation with vLLM, dataset preparation for
LLaMA-Factory, and staged fine-tuning workflows.

## Repository Layout

- `dataset_generator/`: generation, validation, export, and training-data prep
- `datasets/`: generated datasets and normalized training artifacts
- `datasets_external/`: external pipeline scripts and raw merged artifacts
- `research_plan/Faza_1/`: scripts and input files for building SQLite SQL dumps
- `training/llamafactory/`: LLaMA-Factory training YAMLs
- `scripts/`: operational helper scripts
- `tests/`: endpoint checks and utility tests

## Prerequisites

- Python virtual environment in `.venv`
- CUDA-capable machine for vLLM generation
- SQL dump inputs in `research_plan/Faza_1/`
- vLLM and model weights installed separately in your active environment

Activate the project environment:

```bash
source scripts/activate.sh
python -V
```

## Prepare SQL Dumps

The generator expects these dump files:

- `research_plan/Faza_1/edu_reteaua_scolara.sql`
- `research_plan/Faza_1/rail_mers_tren.sql`

If they do not exist yet, build them with:

```bash
cd research_plan/Faza_1
python clean_educatie.py
python curatare_trenuri.py
cd ../..
```

## Run vLLM

Example single-endpoint launch:

```bash
CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8 \
  --host 0.0.0.0 \
  --port 8001 \
  --tensor-parallel-size 1 \
  --dtype auto \
  --max-model-len 32768 \
  --generation-config vllm
```

Smoke-check the endpoint:

```bash
python tests/check_vllm_qwen35_endpoint.py --base-url http://127.0.0.1:8001/v1
```

## Generate Data

Single-endpoint smoke run:

```bash
python -m dataset_generator.cli generate \
  --config dataset_generator/configs/vllm.smoke.8001.json \
  --progress-every 1

python -m dataset_generator.cli validate \
  --config dataset_generator/configs/vllm.smoke.8001.json
```

Main generation run:

```bash
python -m dataset_generator.cli generate \
  --config dataset_generator/configs/vllm.template.json \
  --progress-every 10

python -m dataset_generator.cli validate \
  --config dataset_generator/configs/vllm.template.json
```

Multi-GPU generation with one vLLM endpoint per GPU:

```bash
python -m dataset_generator.cli generate-multi-gpu \
  --config dataset_generator/configs/vllm.template.json \
  --gpus 0,1,2,3 \
  --base-urls http://127.0.0.1:8001/v1,http://127.0.0.1:8002/v1,http://127.0.0.1:8003/v1,http://127.0.0.1:8004/v1 \
  --artifact alpaca \
  --work-dir datasets/multi_gpu_runs \
  --progress-every 1
```

## Prepare Training Data

Normalize local datasets into a LLaMA-Factory-ready layout:

```bash
python -m dataset_generator.cli prepare-llamafactory \
  --out-dir datasets/llamafactory
```

This produces normalized Alpaca JSONL files plus
`datasets/llamafactory/dataset_info.json`.

## Fine-Tuning

LLaMA-Factory training configs are under `training/llamafactory/`.
The full runbook is in [FINETUNING.md](/mnt/home/fizlabrl/NLSQLRO/FINETUNING.md).

## Operations

Helper scripts are under `scripts/`:

- `source scripts/activate.sh`
- `bash scripts/clean_gpu_mem.sh --gpus "0 1 2 3"`
- `bash scripts/train_all.sh --gpus "0,1,2,3"`

## Local Documentation

- [Generator guide](/mnt/home/fizlabrl/NLSQLRO/dataset_generator/README.md)
- [External dataset guide](/mnt/home/fizlabrl/NLSQLRO/datasets_external/README.md)
- [Research materials guide](/mnt/home/fizlabrl/NLSQLRO/research_plan/README.md)
- [SQL dump preparation guide](/mnt/home/fizlabrl/NLSQLRO/research_plan/Faza_1/README.md)
- [Fine-tuning runbook](/mnt/home/fizlabrl/NLSQLRO/FINETUNING.md)
- [Operational scripts guide](/mnt/home/fizlabrl/NLSQLRO/scripts/README.md)
- [Project plan](/mnt/home/fizlabrl/NLSQLRO/PLAN.md)
