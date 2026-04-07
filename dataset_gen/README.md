# dataset_gen

Configurable agentic pipeline for generating Romanian NL-to-SQL training data.

## What it does

- reads the real SQL dumps for each domain
- builds schema + value hints
- runs a generation loop (`generate -> execute -> repair/retry`)
- translates EN questions to RO
- keeps only validated samples
- exports:
  - `master` JSONL (rich metadata)
  - `alpaca` JSONL
  - `chat/messages` JSONL
  - stats JSON

## Provider modes

- `mock`:
  - local, no API calls
  - useful for fast testing and CI
- `openai_compatible`:
  - teacher model + translator model via `/chat/completions`
  - use for real synthetic generation

## Quick start

From repo root:

```bash
python -m dataset_gen.cli generate --config dataset_gen/configs/default.mock.json
python -m dataset_gen.cli validate --config dataset_gen/configs/default.mock.json
```

Optional:

```bash
python -m dataset_gen.cli introspect --config dataset_gen/configs/default.mock.json
```

## Real generation setup

1. Copy `dataset_gen/configs/openai.template.json` and edit values.
2. Set API key env variable:

```bash
set OPENAI_API_KEY=your_key_here
```

3. Run:

```bash
python -m dataset_gen.cli generate --config dataset_gen/configs/openai.template.json
python -m dataset_gen.cli validate --config dataset_gen/configs/openai.template.json
```

## Clean external madlad dataset

This utility cleans natural-language mojibake and validates SQL executability
using each row's embedded SQL context. SQL output/context is not rewritten.

```bash
python -m dataset_gen.clean_madlad_dataset \
  --input-dir madlad_4gpu_full_merged \
  --output-dir madlad_4gpu_full_merged_clean \
  --workers 16
```

Useful flags:

- `--strict-sql-type`:
  - `queries` keeps only `SELECT/WITH`
  - `operators` keeps only DML/DDL families
- `--no-validate-sql`: faster run (skips SQLite execution checks)
- `--max-lines N`: quick sample run per file

Outputs:

- `operators_alpaca_ro.clean.jsonl`
- `queries_alpaca_ro.clean.jsonl`
- `manifest_clean.json` (drop reasons, keep rates, field change stats)

## Output schema (master JSONL)

Each row contains:

- `id`
- `domain`
- `db_id`
- `question_en`
- `question_ro`
- `sql`
- `difficulty`
- `query_type`
- `tables`
- `row_count`
- `validation_flags`
- `expected_result_description_en`
- `notes`

## Notes

- Strict non-empty behavior is configurable (`generation.strict_non_empty`).
- Duplicate filtering is configurable (`dedup_on_sql`, `dedup_on_question`).
- Paths in config are resolved relative to the config file location.
