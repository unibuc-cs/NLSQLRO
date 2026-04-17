# scripts

`scripts` contains operational helpers for environment activation, GPU cleanup,
and staged training.

## Files

- `activate.sh`: activate the repository virtual environment
- `clean_gpu_mem.sh`: terminate CUDA processes and report GPU memory state
- `train_all.sh`: prepare training data and run staged LLaMA-Factory training
- `make_eval_dataset.py`: build reproducible sampled eval datasets from clean Madlad JSONL files

## Usage

Activate the environment:

```bash
source scripts/activate.sh
```

Clean GPUs:

```bash
bash scripts/clean_gpu_mem.sh --gpus "0 1 2 3"
```

Run staged training:

```bash
bash scripts/train_all.sh --gpus "0,1,2,3"
```

Create eval split (default 20% per task, seed 42):

```bash
python scripts/make_eval_dataset.py
```

Custom ratio/seed:

```bash
python scripts/make_eval_dataset.py --ratio 0.1 --seed 123 --out-dir datasets/evaluatedataset
```

## Notes

- `activate.sh` must be sourced, not executed.
- `train_all.sh` expects the LLaMA-Factory environment and configs to already be
  set up correctly.

## Related Documentation

- [Repository root guide](/mnt/home/fizlabrl/NLSQLRO/README.md)
- [Fine-tuning runbook](/mnt/home/fizlabrl/NLSQLRO/FINETUNING.md)
