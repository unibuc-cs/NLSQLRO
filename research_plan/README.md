# research_plan

`research_plan` stores project reference material and source data-preparation
scripts.

## Structure

- `Faza_0/`: original project specification and planning materials
- `Faza_1/`: input files and scripts used to build SQL dumps consumed by the
  generator

## Active Use

The main generation pipeline depends on the SQL dumps produced in `Faza_1`:

- `research_plan/Faza_1/edu_reteaua_scolara.sql`
- `research_plan/Faza_1/rail_mers_tren.sql`

If those files are missing or need regeneration, follow the instructions in:

- [Faza_1 guide](/mnt/home/fizlabrl/NLSQLRO/research_plan/Faza_1/README.md)

## Related Documentation

- [Repository root guide](/mnt/home/fizlabrl/NLSQLRO/README.md)
- [Generator guide](/mnt/home/fizlabrl/NLSQLRO/dataset_generator/README.md)
