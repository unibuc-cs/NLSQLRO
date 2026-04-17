# PLAN: RoGov-SQL Synthetic NL->SQL Dataset Pipeline

## Purpose

Build a scalable, updateable pipeline that generates high-quality Romanian NL->SQL training data for OpenLLM-Ro instruction models, using:

- an open-source coding SLM as SQL generator
- GPT-5-mini for EN->RO translation and consistency checks
- strict execution validation on the real SQLite schemas

This file is a living plan and will be updated as we implement.

## Current Baseline

- SQL dumps available:
  - `research_plan/Faza_1/edu_reteaua_scolara.sql`
  - `research_plan/Faza_1/rail_mers_tren.sql`
- Current dataset outputs:
  - `datasets/multi_gpu_runs/run_*/rogov_alpaca.merged.jsonl`
  - `datasets/madlad_4gpu_full_merged_clean/*.clean.jsonl`
- Validator available:
  - `python -m dataset_generator.cli validate --config <config.json>`

## Recommended Model Stack

- Target fine-tune base (default): `OpenLLM-Ro/RoLlama3.1-8b-Instruct`
- Alternative target: `OpenLLM-Ro/RoGemma2-9b-Instruct` (evaluate after pilot)
- SQL teacher (default): `Qwen2.5-Coder-32B-Instruct`
- SQL teacher fallback: `DeepSeek-Coder-V2-Instruct`
- Translation + semantic parity checks: `GPT-5-mini`

Note: confirm OpenLLM-Ro license constraints before any commercial deployment.

## Canonical Master Dataset Schema

Each row in master JSONL should contain at least:

- `id`
- `domain` (`education` | `trains`)
- `db_id` (`edu_reteaua_scolara` | `rail_mers_tren`)
- `question_en`
- `question_ro`
- `sql`
- `difficulty` (1/2/3)
- `query_type` (list)
- `tables` (list)
- `row_count`
- `validation_flags` (list)
- `notes` (optional)

## Generation Loop (Agentic)

1. Generate candidate `question_en + sql` from schema metadata and templates.
2. Execute SQL on in-memory SQLite loaded from target `.sql` dump.
3. If SQL fails or result policy fails, run auto-repair prompt and retry up to `N` times.
4. Translate `question_en -> question_ro` with GPT-5-mini.
5. Consistency check:
   - regenerate SQL from `question_ro` (or verify intent),
   - compare with original via execution/result-signature checks.
6. Store accepted sample in master JSONL.
7. Deduplicate and rebalance periodically.

## Quality Gates

Hard requirements:

- 100% JSON-valid samples
- 100% executable SQL
- correct `domain` / `db_id` mapping

Target thresholds:

- >= 95% non-empty results (domain-dependent exceptions allowed)
- low duplication (SQL-normalized and text-similarity checks)
- balanced difficulty and query_type distribution
- balanced domain coverage (education vs trains)

## Output Formats for Training

Primary storage:

- master JSONL (rich metadata, validation traces)

Training exports:

- Alpaca-style (`instruction`, `input`, `output`) for SFT
- optional chat/messages format for chat-style trainers

## Implementation Milestones

### M1 - Foundation

- [ ] Create/maintain `dataset_generator/` package structure
- [ ] Add schema introspection utility (tables, columns, sample values)
- [ ] Add SQL execution + retry-repair module
- [ ] Add deterministic IDs and run metadata

### M2 - Generation

- [ ] Add prompt templates per difficulty/query family
- [ ] Integrate teacher model client (local/API adapter)
- [ ] Add translation adapter (GPT-5-mini)
- [ ] Add RO/EN semantic consistency checks

### M3 - Data Quality

- [ ] Add deduplication (normalized SQL + text similarity)
- [ ] Add distribution balancer for query types and domains
- [ ] Add quality report (`stats.json` + markdown summary)

### M4 - Export + Training Prep

- [ ] Add Alpaca export script
- [ ] Add chat/messages export script
- [ ] Add train/val/test split utility (stratified)
- [ ] Add reproducible run config files

## Initial Scale Plan

- Pilot: 2k samples/domain
- Expansion: 10k samples/domain
- Full run: 25k-50k samples/domain (after quality review)

## Open Questions

- [ ] Final training framework (LLaMA-Factory vs alternative)?
- [ ] Non-empty policy strictness for aggregate queries?
- [ ] Exact ratio of template-seeded vs fully generated prompts?
- [ ] Preferred storage for run artifacts and audit logs?

## Update Log

- 2026-04-04: Initial plan created from recap, recommendations, and pipeline design decisions.

