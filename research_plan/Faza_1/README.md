# Faza_1

`Faza_1` contains the source files and scripts used to generate the SQLite SQL
dumps required by `dataset_generator`.

## Required Input Files

Education:

- `retea-scolara-2024-2025.xlsx`
- `elevi-inmatriculati-2024-2025.xlsx`

Rail:

- `trenuri-2025-2026_interregional-calatori.xml`

Keep these files in this directory before running the preparation scripts.

## Build SQL Dumps

From `research_plan/Faza_1/`:

```bash
python clean_educatie.py
python curatare_trenuri.py
```

Generated outputs:

- `edu_reteaua_scolara.sql`
- `rail_mers_tren.sql`

## Usage in the Project

These dump files are referenced by generator configs such as:

- `dataset_generator/configs/vllm.template.json`
- `dataset_generator/configs/vllm.smoke.8001.json`
- `dataset_generator/configs/default.mock.json`

## SQL Contents

`edu_reteaua_scolara.sql` typically contains:

- `counties`
- `localities`
- `schools`

`rail_mers_tren.sql` typically contains:

- `stations`
- `trains`
- `timetables`

## Related Documentation

- [Research plan guide](/mnt/home/fizlabrl/NLSQLRO/research_plan/README.md)
- [Repository root guide](/mnt/home/fizlabrl/NLSQLRO/README.md)
