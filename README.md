# RoGov-SQL: Bilingual NL-to-SQL Benchmark (RO/EN)

## Romanian

### Despre proiect

RoGov-SQL este un benchmark bilingv `NL -> SQL` pentru date guvernamentale deschise din Romania.

Scopul: intrebari in romana si engleza care se mapeaza la SQL corect pentru doua domenii:

- educatie (`edu_reteaua_scolara`)
- transport feroviar (`rail_mers_tren`)

Repository-ul este un pipeline de pregatire date, nu un API sau o aplicatie web.

### Structura repository

- `Faza_0/`: specificatii initiale
- `Faza_1/`: scripturi de curatare + SQL generat
- `README.md`: descriere proiect + template-uri NL-to-SQL

### Schema reala (conform `Faza_1`)

Schema educatie:

- `counties(county_id, county_code, county_name)`
- `localities(locality_id, locality_name, residency_area, county_id)`
- `schools(school_id, school_name, short_name, siiir_code, locality_id, ownership_type, unit_type, education_level, number_of_students)`

Schema trenuri:

- `stations(station_id, station_number, station_name, county)`
- `trains(train_id, train_number, operator_name, category)`
- `timetables(timetable_id, train_id, station_id, arrival_time, departure_time, service_category, day_type)`

### Template-uri NL-to-SQL corecte pe schema

#### Educatie

Template E1:

- RO: `Listeaza toate scolile din judetul [COUNTY_NAME].`
- EN: `List all schools in [COUNTY_NAME] county.`

```sql
SELECT s.school_id, s.school_name, l.locality_name
FROM schools s
JOIN localities l ON s.locality_id = l.locality_id
JOIN counties c ON l.county_id = c.county_id
WHERE c.county_name = '[COUNTY_NAME]';
```

Template E2:

- RO: `Listeaza scolile din mediul [RESIDENCY_AREA] din judetul [COUNTY_NAME].`
- EN: `List schools in [RESIDENCY_AREA] areas from [COUNTY_NAME] county.`

```sql
SELECT s.school_id, s.school_name, l.locality_name
FROM schools s
JOIN localities l ON s.locality_id = l.locality_id
JOIN counties c ON l.county_id = c.county_id
WHERE c.county_name = '[COUNTY_NAME]'
  AND l.residency_area = '[RESIDENCY_AREA]';
```

Template E3:

- RO: `Care este numarul total de elevi in scolile liceale (PJ) din judetul [COUNTY_NAME]?`
- EN: `What is the total number of students in high-school-level legal-entity schools in [COUNTY_NAME] county?`

```sql
SELECT SUM(s.number_of_students) AS total_students
FROM schools s
JOIN localities l ON s.locality_id = l.locality_id
JOIN counties c ON l.county_id = c.county_id
WHERE c.county_name = '[COUNTY_NAME]'
  AND s.unit_type = 'PJ'
  AND s.education_level LIKE '%Liceal%';
```

#### Trenuri

Template T1:

- RO: `Listeaza toate trenurile operate de [OPERATOR].`
- EN: `List all trains operated by [OPERATOR].`

```sql
SELECT t.train_id, t.train_number, t.category
FROM trains t
WHERE t.operator_name = '[OPERATOR]';
```

Template T2:

- RO: `Listeaza toate trenurile care pleaca din statia [STATION_NAME] intre [TIME_START] si [TIME_END].`
- EN: `List all trains departing from [STATION_NAME] between [TIME_START] and [TIME_END].`

```sql
SELECT DISTINCT t.train_number, t.operator_name, tt.departure_time
FROM trains t
JOIN timetables tt ON t.train_id = tt.train_id
JOIN stations s ON tt.station_id = s.station_id
WHERE s.station_name = '[STATION_NAME]'
  AND tt.departure_time >= '[TIME_START]'
  AND tt.departure_time <= '[TIME_END]'
ORDER BY tt.departure_time;
```

Template T3:

- RO: `Listeaza trenurile care trec prin [STATION_A] si apoi prin [STATION_B].`
- EN: `List trains that pass through [STATION_A] and then [STATION_B].`

```sql
SELECT DISTINCT t.train_number, t.operator_name
FROM trains t
JOIN timetables tta ON t.train_id = tta.train_id
JOIN stations sa ON tta.station_id = sa.station_id
JOIN timetables ttb ON t.train_id = ttb.train_id
JOIN stations sb ON ttb.station_id = sb.station_id
WHERE sa.station_name = '[STATION_A]'
  AND sb.station_name = '[STATION_B]'
  AND tta.timetable_id < ttb.timetable_id;
```

### Observatii importante

- Pentru educatie, `AR` are de regula `number_of_students = NULL`; pentru agregari, filtrati cu `s.unit_type = 'PJ'`.
- Pentru nivel educational, folositi `LIKE` pe `education_level`, nu egalitate stricta.
- Pentru trenuri, folositi tabela `timetables` (plural), nu `timetable`.

### Dataset extern (intermediate finetune)

Pentru pre-antrenare intermediara NL-to-SQL in romana, proiectul foloseste si dataset-ul extern:

- `madlad_4gpu_full_merged/operators_alpaca_ro.jsonl`
- `madlad_4gpu_full_merged/queries_alpaca_ro.jsonl`
- `madlad_4gpu_full_merged/manifest_merged.json`

Acest dataset este util, dar necesita curatare inainte de finetune:

- unele randuri au probleme de dialect SQL / executie (`DATE_SUB`, `DATEADD`, `NOW`, `YEAR`, etc.)
- exista texte cu encoding inconsistent in campurile de limbaj natural

Curatarea se face cu:

- `dataset_gen/clean_madlad_dataset.py`

Reguli tehnice ale curatarii:

- SQL-ul (`output`) si contextul SQL din `input` NU sunt rescrise
- nume de tabele/coloane/comenzi SQL raman in engleza
- se normalizeaza doar campurile de limbaj natural (`instruction`, `system`, intrebare RO, `metadata.sql_explanation_ro`)
- optional se valideaza executia SQL per rand in SQLite (`context + output`)
- optional se aplica reguli pe tip de track:
  - `queries`: doar `SELECT/WITH`
  - `operators`: doar DML/DDL

Comanda recomandata pe server (paralel):

```powershell
python -m dataset_gen.clean_madlad_dataset `
  --input-dir madlad_4gpu_full_merged `
  --output-dir madlad_4gpu_full_merged_clean `
  --workers 32 `
  --strict-sql-type
```

Output:

- `madlad_4gpu_full_merged_clean/operators_alpaca_ro.clean.jsonl`
- `madlad_4gpu_full_merged_clean/queries_alpaca_ro.clean.jsonl`
- `madlad_4gpu_full_merged_clean/manifest_clean.json` (rate de pastrare, motive de drop, statistici)

#### Strategie recomandata de finetune (2 etape)

Etapa 1: intermediate SFT pe dataset extern curatat

- scop: invatare generala NL-to-SQL in romana
- date: `operators_alpaca_ro.clean.jsonl` + `queries_alpaca_ro.clean.jsonl`
- amestec recomandat:
  - 60% `queries`
  - 40% `operators`

Etapa 2: in-domain SFT pe RoGov

- scop: adaptare la schema/tabelele reale din proiect (`edu_reteaua_scolara`, `rail_mers_tren`)
- date: setul intern generat/validat (`rogov_master.jsonl` sau export Alpaca/Chat)
- amestec recomandat la inceputul etapei:
  - 80% RoGov
  - 20% subset extern curatat (pentru retenție de generalizare)

Checkpoint-uri de evaluare recomandate:

- dupa Etapa 1: validare pe benchmark intern mic RoGov + subset extern holdout
- dupa Etapa 2: validare stricta pe RoGov (executie SQL) + evaluare de robustete pe extern holdout

---

## English

### About the project

RoGov-SQL is a bilingual `NL -> SQL` benchmark over Romanian open government data.

Goal: questions in Romanian and English mapped to valid SQL in two domains:

- education (`edu_reteaua_scolara`)
- rail transport (`rail_mers_tren`)

This repository is a data-preparation pipeline, not a web API/application.

### Repository layout

- `Faza_0/`: initial specifications
- `Faza_1/`: cleaning scripts + generated SQL
- `README.md`: project overview + NL-to-SQL templates

### Actual schema (from `Faza_1`)

Education schema:

- `counties(county_id, county_code, county_name)`
- `localities(locality_id, locality_name, residency_area, county_id)`
- `schools(school_id, school_name, short_name, siiir_code, locality_id, ownership_type, unit_type, education_level, number_of_students)`

Rail schema:

- `stations(station_id, station_number, station_name, county)`
- `trains(train_id, train_number, operator_name, category)`
- `timetables(timetable_id, train_id, station_id, arrival_time, departure_time, service_category, day_type)`

### Schema-aligned NL-to-SQL templates

#### Education

Template E1:

- RO: `Listeaza toate scolile din judetul [COUNTY_NAME].`
- EN: `List all schools in [COUNTY_NAME] county.`

```sql
SELECT s.school_id, s.school_name, l.locality_name
FROM schools s
JOIN localities l ON s.locality_id = l.locality_id
JOIN counties c ON l.county_id = c.county_id
WHERE c.county_name = '[COUNTY_NAME]';
```

Template E2:

- RO: `Listeaza scolile din mediul [RESIDENCY_AREA] din judetul [COUNTY_NAME].`
- EN: `List schools in [RESIDENCY_AREA] areas from [COUNTY_NAME] county.`

```sql
SELECT s.school_id, s.school_name, l.locality_name
FROM schools s
JOIN localities l ON s.locality_id = l.locality_id
JOIN counties c ON l.county_id = c.county_id
WHERE c.county_name = '[COUNTY_NAME]'
  AND l.residency_area = '[RESIDENCY_AREA]';
```

Template E3:

- RO: `Care este numarul total de elevi in scolile liceale (PJ) din judetul [COUNTY_NAME]?`
- EN: `What is the total number of students in high-school-level legal-entity schools in [COUNTY_NAME] county?`

```sql
SELECT SUM(s.number_of_students) AS total_students
FROM schools s
JOIN localities l ON s.locality_id = l.locality_id
JOIN counties c ON l.county_id = c.county_id
WHERE c.county_name = '[COUNTY_NAME]'
  AND s.unit_type = 'PJ'
  AND s.education_level LIKE '%Liceal%';
```

#### Rail

Template T1:

- RO: `Listeaza toate trenurile operate de [OPERATOR].`
- EN: `List all trains operated by [OPERATOR].`

```sql
SELECT t.train_id, t.train_number, t.category
FROM trains t
WHERE t.operator_name = '[OPERATOR]';
```

Template T2:

- RO: `Listeaza toate trenurile care pleaca din statia [STATION_NAME] intre [TIME_START] si [TIME_END].`
- EN: `List all trains departing from [STATION_NAME] between [TIME_START] and [TIME_END].`

```sql
SELECT DISTINCT t.train_number, t.operator_name, tt.departure_time
FROM trains t
JOIN timetables tt ON t.train_id = tt.train_id
JOIN stations s ON tt.station_id = s.station_id
WHERE s.station_name = '[STATION_NAME]'
  AND tt.departure_time >= '[TIME_START]'
  AND tt.departure_time <= '[TIME_END]'
ORDER BY tt.departure_time;
```

Template T3:

- RO: `Listeaza trenurile care trec prin [STATION_A] si apoi prin [STATION_B].`
- EN: `List trains that pass through [STATION_A] and then [STATION_B].`

```sql
SELECT DISTINCT t.train_number, t.operator_name
FROM trains t
JOIN timetables tta ON t.train_id = tta.train_id
JOIN stations sa ON tta.station_id = sa.station_id
JOIN timetables ttb ON t.train_id = ttb.train_id
JOIN stations sb ON ttb.station_id = sb.station_id
WHERE sa.station_name = '[STATION_A]'
  AND sb.station_name = '[STATION_B]'
  AND tta.timetable_id < ttb.timetable_id;
```

### Important notes

- In education data, `AR` rows usually have `number_of_students = NULL`; for totals use `s.unit_type = 'PJ'`.
- For education level filters, use `LIKE` on `education_level` instead of strict equality.
- For rail queries, use the `timetables` table (plural), not `timetable`.

### External Dataset (Intermediate Finetune)

For intermediate Romanian NL-to-SQL tuning, the project also uses:

- `madlad_4gpu_full_merged/operators_alpaca_ro.jsonl`
- `madlad_4gpu_full_merged/queries_alpaca_ro.jsonl`
- `madlad_4gpu_full_merged/manifest_merged.json`

This dataset is useful but should be cleaned before SFT:

- some rows fail due to SQL dialect/execution issues (`DATE_SUB`, `DATEADD`, `NOW`, `YEAR`, etc.)
- some natural-language fields have inconsistent encoding artifacts

Cleaning utility:

- `dataset_gen/clean_madlad_dataset.py`

Technical behavior:

- SQL output (`output`) and SQL context in `input` are NOT rewritten
- SQL/table/column names stay in English
- only natural-language fields are normalized (`instruction`, `system`, Romanian question text, `metadata.sql_explanation_ro`)
- optional per-row SQL execution validation (`context + output`) in SQLite
- optional track keyword rules:
  - `queries`: only `SELECT/WITH`
  - `operators`: only DML/DDL

Recommended parallel server run:

```powershell
python -m dataset_gen.clean_madlad_dataset `
  --input-dir madlad_4gpu_full_merged `
  --output-dir madlad_4gpu_full_merged_clean `
  --workers 32 `
  --strict-sql-type
```

Outputs:

- `madlad_4gpu_full_merged_clean/operators_alpaca_ro.clean.jsonl`
- `madlad_4gpu_full_merged_clean/queries_alpaca_ro.clean.jsonl`
- `madlad_4gpu_full_merged_clean/manifest_clean.json` (keep rates, drop reasons, cleaning stats)

#### Recommended Finetuning Schedule (2 stages)

Stage 1: intermediate SFT on cleaned external dataset

- goal: broad Romanian NL-to-SQL competence
- data: `operators_alpaca_ro.clean.jsonl` + `queries_alpaca_ro.clean.jsonl`
- recommended mixture:
  - 60% `queries`
  - 40% `operators`

Stage 2: in-domain SFT on RoGov

- goal: specialize to real project schemas (`edu_reteaua_scolara`, `rail_mers_tren`)
- data: internal validated set (`rogov_master.jsonl` or Alpaca/Chat export)
- recommended starting mixture:
  - 80% RoGov
  - 20% cleaned external subset (to preserve generalization)

Recommended evaluation checkpoints:

- after Stage 1: evaluate on small internal RoGov benchmark + external holdout
- after Stage 2: strict RoGov SQL-execution evaluation + robustness check on external holdout
