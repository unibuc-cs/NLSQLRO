# Fine-Tuning and Evaluation Runbook

This repo is ready for staged SFT with LLaMA-Factory (A -> B -> optional C).

## Format status

Both datasets are Alpaca-compatible (`instruction`, `input`, `output`), but they
are not identical:

- external cleaned data includes `system` + `metadata`
- RoGov generated data includes `id`/`task` + `metadata`, but no `system`

LLaMA-Factory supports this via `dataset_info.json` column mapping, but the repo
now includes a normalizer to make them fully consistent before training.

## 1) Prepare LLaMA-Factory-ready data

Run from repo root:

```bash
python -m dataset_generator.cli prepare-llamafactory --out-dir datasets/llamafactory
```

Generated:

- `datasets/llamafactory/external_queries.alpaca.jsonl`
- `datasets/llamafactory/external_operators.alpaca.jsonl`
- `datasets/llamafactory/external_all.alpaca.jsonl`
- `datasets/llamafactory/rogov.alpaca.jsonl`
- `datasets/llamafactory/dataset_info.json`
- `datasets/llamafactory/manifest_prep.json`

`dataset_info.json` dataset names:

- `nlsqlro_external_queries_sft`
- `nlsqlro_external_operators_sft`
- `nlsqlro_external_all_sft`
- `nlsqlro_rogov_sft`

## 2) Train with LLaMA-Factory (OpenLLM-Ro fork)

Clone/install your LLaMA-Factory fork, then run training with the YAML files in:

- `training/llamafactory/sft_stage_a_external_lora.yaml`
- `training/llamafactory/sft_stage_b_rogov_lora.yaml`
- `training/llamafactory/sft_stage_c_mix_lora.yaml` (optional consolidation pass)

Important: set `dataset_dir` in all YAMLs to your real absolute path:

- `/path/to/NLSQLRO/datasets/llamafactory`

Run (single-node, 4 GPUs):

```bash
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train training/llamafactory/sft_stage_a_external_lora.yaml
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train training/llamafactory/sft_stage_b_rogov_lora.yaml
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train training/llamafactory/sft_stage_c_mix_lora.yaml
```

Resume variant (continue same stage from checkpoint):

```bash
CKPT=/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora/checkpoint-6000
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train training/llamafactory/sft_stage_a_external_lora.yaml \
  resume_from_checkpoint=$CKPT overwrite_output_dir=false
```

Use Stage A checkpoint as start point for Stage B:

```bash
CKPT_A=/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora/checkpoint-6000
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train training/llamafactory/sft_stage_b_rogov_lora.yaml \
  adapter_name_or_path=$CKPT_A create_new_adapter=false
```

Then continue to Stage C from Stage B output:

```bash
ADAPTER_B=/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_b_rogov_lora
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train training/llamafactory/sft_stage_c_mix_lora.yaml \
  adapter_name_or_path=$ADAPTER_B create_new_adapter=false
```

Notes:

- `resume_from_checkpoint` keeps optimizer/scheduler state for the same stage.
- `adapter_name_or_path` initializes the next stage from adapter weights only.
- If your LLaMA-Factory version does not accept CLI `key=value` overrides, set
  these fields directly in the YAML before launching.

## 3) Monitoring (W&B + TensorBoard)

The YAMLs are configured with:

- `report_to: [wandb, tensorboard]`
- per-stage `run_name`
- per-stage `logging_dir`

Before training:

```bash
wandb login
export WANDB_PROJECT=nlsqlro
export WANDB_ENTITY=<your_team_or_user>
```

TensorBoard view:

```bash
tensorboard --logdir outputs --port 6006
```

If you want to disable one backend, edit `report_to` in the YAML.

## 4) Helper scripts

Operational scripts are now under `scripts/`:

- `scripts/activate.sh`
- `scripts/clean_gpu_mem.sh`
- `scripts/train_all.sh`

Examples:

```bash
source scripts/activate.sh
bash scripts/clean_gpu_mem.sh --gpus "0 1 2 3"
bash scripts/train_all.sh --gpus "0,1,2,3"
```

`train_all.sh` defaults:

- prepares `datasets/llamafactory`
- runs Stage A -> Stage B -> Stage C

Useful flags:

- `--skip-prepare`
- `--prepare-only`
- `--no-stage-c`
- `--out-dir <path>`

## 5) Recommended schedule

- Stage A (external): broader SQL behavior
- Stage B (RoGov): in-domain schema adaptation
- Stage C (optional): 80/20 RoGov/external mix to reduce forgetting
- Use lower LR at each later stage (already set in templates)

## 6) H100 notes (4x80GB)

- Templates are tuned for this setup: LoRA on all layers, `lora_rank=32`,
  `cutoff_len=4096`, `flash_attn=fa2`, bf16, and larger effective batch.
- If you hit OOM at `cutoff_len=4096`, reduce:
  - `per_device_train_batch_size` from `4 -> 2` (Stage A)
  - or `cutoff_len` from `4096 -> 3072`.
- Current RoGov dataset has only ~1000 rows. For materially better Stage B/C
  quality, generate more RoGov samples before final training.

## 7) Dataset sizes for O/A/B/C and 20% evaluation split

The current prepared corpora (from `datasets/llamafactory/manifest_prep.json`)
contain:

- External (queries + operators): **76,307** examples
- RoGov generated: **1,000** examples

Training variants used in this project:

- **O** (baseline): base model only, no fine-tuning data consumed
- **A** (Stage A): trained on external corpus (**76,307** examples)
- **B** (Stage B): continued from A on RoGov corpus (**1,000** examples)
- **C** (Stage C): continued from B on a mixed stream drawn from RoGov and
  external pools with `interleave_probs = 0.8, 0.2` and
  `mix_strategy = interleave_under`

20% held-out evaluation split (from `datasets/evaluatedataset/manifest_eval20.json`):

- Queries track: **13,570 / 67,852** examples (20%)
- Operators track: **1,691 / 8,455** examples (20%)
- Combined eval set: **15,261** examples

Paper-ready paragraph:

> We evaluate four model states in a staged SFT setup: O (base model, no
> domain fine-tuning), A (fine-tuned on 76,307 external NL-SQL examples), B
> (continued from A on 1,000 in-domain RoGov examples), and C (continued from
> B using probabilistic interleaving of RoGov and external data at an 80/20
> ratio). For held-out testing, we construct a stratified 20% split from the
> cleaned external corpus, yielding 13,570 query-oriented examples and 1,691
> operator-oriented examples (15,261 total). This protocol separates
> broad-coverage SQL learning (A), in-domain adaptation (B), and anti-forgetting
> consolidation (C), while preserving a fixed, reproducible evaluation set.

## 8) Citation, translation model, and baseline definition

### External NL-SQL dataset citation

The external dataset used in this pipeline is sourced from:

- Hugging Face mirror used in preprocessing manifests:
  `philschmid/gretel-synthetic-text-to-sql`
- Canonical dataset page:
  `https://huggingface.co/datasets/gretelai/synthetic_text_to_sql`
- Gretel release blog:
  `https://gretel.ai/blog/synthetic-text-to-sql-dataset`

The dataset card references arXiv `2306.05685`, with DOI:

- `https://doi.org/10.48550/arXiv.2306.05685`

If your paper requires strict artifact citation, cite the dataset URL + access
date, and include the Gretel blog and the arXiv DOI above as linked metadata.

### Translation model details

External preprocessing manifests record `translator: madlad` and
`dtype: bfloat16`. In this repository defaults, the translation checkpoint is:

- `google/madlad400-10b-mt`

Translation settings in `dataset_generator/config.py` defaults:

- `translation_max_new_tokens: 256`
- `translation_num_beams: 4`

### Baseline (O) definition

Variant **O** is a **zero-shot baseline with respect to this project’s NL-SQL
training datasets** (external + RoGov): it evaluates the base model directly,
without loading any LoRA adapter. It is not “from scratch”; it remains an
instruction-tuned foundation model.

## 9) Training hyperparameters and reproducibility

### Stage hyperparameters (A/B/C)

Shared core setup:

- Base model: `OpenLLM-Ro/RoLlama3.1-8b-Instruct`
- Method: LoRA SFT, `lora_target=all`, `lora_rank=32`, `lora_alpha=64`,
  `lora_dropout=0.05`, `use_rslora=true`
- Attention/dtype: `flash_attn=fa2`, `bf16=true`
- Sequence/packing: `cutoff_len=4096`, `packing=true`, `neat_packing=false`
- Scheduler: cosine, `warmup_ratio=0.03`
- Data workers: `preprocessing_num_workers=8`, `dataloader_num_workers=8`

Per-stage values from YAMLs:

| Stage | Dataset | LR | Train batch / device | Grad accum | Epochs | Val split | Save/Eval steps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | `nlsqlro_external_all_sft` | `8e-5` | `4` | `4` | `100` | `0.01` | `1000` |
| B | `nlsqlro_rogov_sft` | `3e-5` | `2` | `8` | `200` | `0.10` | `200` |
| C | `nlsqlro_rogov_sft,nlsqlro_external_all_sft` (`interleave_under`, probs `0.8,0.2`) | `2e-5` | `2` | `8` | `200` | `0.02` | `200` |

### Reproducibility controls

- Data manifests to archive:
  - `datasets/llamafactory/manifest_prep.json`
  - `datasets/evaluatedataset/manifest_eval20.json`
  - `datasets/madlad_4gpu_full_merged_clean/manifest_clean.json`
- Generation/eval split seeds currently tracked in manifests:
  - external preprocessing shards: `seed=42`
  - 20% eval split: `seed=42`, `sampling_ratio=0.2`
- For training determinism, pass explicit seeds at launch:

```bash
FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train training/llamafactory/sft_stage_a_external_lora.yaml \
  seed=42 data_seed=42
```

Evaluation determinism in `tests/evaluate_model_variants.py` is configured as
greedy decoding (`do_sample=false`, `temperature=0.0`, `top_p=1.0`) with fixed
SQLite execution checks.

## Notes

- If you only want one external subset, change `dataset:` in Stage A YAML
  (`nlsqlro_external_queries_sft` or `nlsqlro_external_operators_sft`).
- `manifest_prep.json` records exact input/output files and row counts used.

## 10) Compare O/A/B/C on a fixed test set

Use:

- O = base model only
- A = Stage A adapter
- B = Stage B adapter
- C = Stage C adapter

Run from the LLaMA-Factory environment (so `transformers` + `peft` are available):

```bash
cd /mnt/home/fizlabrl/NLSQLRO
python tests/evaluate_model_variants.py \
  --test-set datasets/mocked/rogov_master.jsonl \
  --base-model OpenLLM-Ro/RoLlama3.1-8b-Instruct \
  --adapter-a /mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora \
  --adapter-b /mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_b_rogov_lora \
  --adapter-c /mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_c_mix_lora \
  --out-dir outputs/eval_variants \
  --max-samples 200 \
  --trust-remote-code
```

Outputs:

- `outputs/eval_variants/summary.json`
- `outputs/eval_variants/predictions.jsonl`

Metrics include exact SQL match and execution-result match on SQLite dumps.

## 11) Ablation: A3000 vs A6000 paths

Goal: compare two full continuation paths:

- path A3000: `A@checkpoint-3000 -> B -> C`
- path A6000: `A@checkpoint-6000 -> B -> C`

Run from the LLaMA-Factory environment.

### Train B/C from A3000

```bash
CKPT_A3000=/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora/checkpoint-3000

FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train /mnt/home/fizlabrl/NLSQLRO/training/llamafactory/sft_stage_b_rogov_lora.yaml \
  adapter_name_or_path=$CKPT_A3000 \
  output_dir=/mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a3000_stage_b \
  run_name=ablation_a3000_stage_b \
  create_new_adapter=false

FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train /mnt/home/fizlabrl/NLSQLRO/training/llamafactory/sft_stage_c_mix_lora.yaml \
  adapter_name_or_path=/mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a3000_stage_b \
  output_dir=/mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a3000_stage_c \
  run_name=ablation_a3000_stage_c \
  create_new_adapter=false
```

### Train B/C from A6000

```bash
CKPT_A6000=/mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora/checkpoint-6000

FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train /mnt/home/fizlabrl/NLSQLRO/training/llamafactory/sft_stage_b_rogov_lora.yaml \
  adapter_name_or_path=$CKPT_A6000 \
  output_dir=/mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a6000_stage_b \
  run_name=ablation_a6000_stage_b \
  create_new_adapter=false

FORCE_TORCHRUN=1 CUDA_VISIBLE_DEVICES=0,1,2,3 \
  llamafactory-cli train /mnt/home/fizlabrl/NLSQLRO/training/llamafactory/sft_stage_c_mix_lora.yaml \
  adapter_name_or_path=/mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a6000_stage_b \
  output_dir=/mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a6000_stage_c \
  run_name=ablation_a6000_stage_c \
  create_new_adapter=false
```

### Evaluate both paths

```bash
python /mnt/home/fizlabrl/NLSQLRO/tests/evaluate_model_variants.py \
  --test-set /mnt/home/fizlabrl/NLSQLRO/datasets/mocked/rogov_master.jsonl \
  --base-model OpenLLM-Ro/RoLlama3.1-8b-Instruct \
  --adapter-a /mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora/checkpoint-3000 \
  --adapter-b /mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a3000_stage_b \
  --adapter-c /mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a3000_stage_c \
  --out-dir /mnt/home/fizlabrl/NLSQLRO/outputs/eval_ablation_a3000 \
  --max-samples 200 \
  --trust-remote-code

python /mnt/home/fizlabrl/NLSQLRO/tests/evaluate_model_variants.py \
  --test-set /mnt/home/fizlabrl/NLSQLRO/datasets/mocked/rogov_master.jsonl \
  --base-model OpenLLM-Ro/RoLlama3.1-8b-Instruct \
  --adapter-a /mnt/home/fizlabrl/LLaMA-Factory/outputs/rolamma31_stage_a_external_lora/checkpoint-6000 \
  --adapter-b /mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a6000_stage_b \
  --adapter-c /mnt/home/fizlabrl/LLaMA-Factory/outputs/ablation_a6000_stage_c \
  --out-dir /mnt/home/fizlabrl/NLSQLRO/outputs/eval_ablation_a6000 \
  --max-samples 200 \
  --trust-remote-code
```

### Compare summaries in one table

```bash
python /mnt/home/fizlabrl/NLSQLRO/tests/compare_ablation.py \
  --left-summary /mnt/home/fizlabrl/NLSQLRO/outputs/eval_ablation_a3000/summary.json \
  --right-summary /mnt/home/fizlabrl/NLSQLRO/outputs/eval_ablation_a6000/summary.json \
  --left-label A3000_path \
  --right-label A6000_path \
  --out-json /mnt/home/fizlabrl/NLSQLRO/outputs/eval_ablation_compare.json
```

Notes:

- Keep dataset, seed, and generation settings identical between paths.
- Use separate `output_dir` per ablation branch to avoid checkpoint overwrite.
- Primary selection metric: `C.exec_match_rate`; secondary: `C.pred_exec_ok_rate`.
