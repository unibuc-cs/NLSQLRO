# datasets_external

`datasets_external` contains the external text-to-SQL preprocessing and
translation workspace used to build Romanian SFT data from non-RoGov sources.

## Purpose

This area is for:

- external dataset translation/preprocessing
- shard execution and merge utilities
- intermediate artifacts before the final cleaned dataset is written into
  `datasets/`

## Main Files

- `run_with_preflight.sh`: external pipeline entry script
- `merge_shards.py`: merge per-shard outputs
- `clean_madlad_dataset.py`: cleanup helper for translated records
- `sft_queries_ro.yaml`: training-related configuration for external data usage

Log files may also appear here during external pipeline runs.

## Output Conventions

Raw merged external outputs are expected under:

- `datasets_external/madlad_4gpu_full_merged/`

Typical files:

- `queries_alpaca_ro.jsonl`
- `operators_alpaca_ro.jsonl`
- `manifest_merged.json`

## Cleaned Dataset Location

The cleaned dataset used by the main project is stored under:

- `datasets/madlad_4gpu_full_merged_clean/`

Typical files:

- `queries_alpaca_ro.clean.jsonl`
- `operators_alpaca_ro.clean.jsonl`
- `manifest_clean.json`

Cleanup into the final format is handled by the main package:

```bash
python -m dataset_generator.clean_madlad_dataset \
  --input-dir datasets_external/madlad_4gpu_full_merged \
  --output-dir datasets/madlad_4gpu_full_merged_clean \
  --workers 32 \
  --strict-sql-type
```

## Related Documentation

- [Repository root guide](/mnt/home/fizlabrl/NLSQLRO/README.md)
- [Generator guide](/mnt/home/fizlabrl/NLSQLRO/dataset_generator/README.md)
- [Fine-tuning runbook](/mnt/home/fizlabrl/NLSQLRO/FINETUNING.md)
