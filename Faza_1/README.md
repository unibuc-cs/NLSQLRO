# Faza 1: Data Cleaning and Database Generation (RO/EN)

## Romanian

### Scop

Acest folder contine scripturile Python care proceseaza date brute guvernamentale si genereaza fisiere SQL pentru cele doua domenii din proiect:

- educatie (`edu_reteaua_scolara.sql`)
- transport feroviar (`rail_mers_tren.sql`)

### 1. Domeniul Educatie (`edu_reteaua_scolara`)

#### 1.1 Fisiere de intrare necesare

Plaseaza aceste fisiere in acelasi folder cu scriptul:

- `retea-scolara-2024-2025.xlsx` (dataset: https://data.gov.ro/dataset/retea-scolara)
- `elevi-inmatriculati-2024-2025.xlsx` (dataset: https://data.gov.ro/dataset/elevi-inmatriculati)

#### 1.2 Dependinte

- Python 3.12+
- `openpyxl`

Instalare:

```bash
pip install openpyxl
```

#### 1.3 Rulare

```bash
python clean_educatie.py
```

Output: `edu_reteaua_scolara.sql` (`CREATE TABLE` + `INSERT INTO` pentru SQLite).

#### 1.4 Structura bazei de date

- `counties(county_id, county_code, county_name)`
- `localities(locality_id, locality_name, residency_area, county_id)`
- `schools(school_id, school_name, short_name, siiir_code, locality_id, ownership_type, unit_type, education_level, number_of_students)`

#### 1.5 Note tehnice importante

- `county_name` este populat dintr-un dictionar intern (`COUNTY_MAP`) pe baza codului de judet.
- `siiir_code` este normalizat cu `zfill(10)` ca sa pastreze zerourile initiale.
- Legatura dintre cele doua fisiere Excel se face logic prin:
  - `Cod SIIIR PJ` (reteaua scolara)
  - `Cod unitate PJ` (elevi)
- `number_of_students` se agregeaza doar pentru `unit_type = 'PJ'`.
- Pentru `AR`, `number_of_students` si `education_level` raman de regula `NULL`.
- `education_level` poate contine mai multe valori concatenate, deci pentru filtre foloseste `LIKE`.

#### 1.6 Statistici (conform rulajului descris de echipa)

- Input:
  - randuri din reteaua scolara: 18,200
  - randuri din elevi inmatriculati: 133,838
- Output:
  - judete: 42
  - localitati unice: 7,284
  - unitati scolare (PJ + AR): 18,200

### 2. Domeniul Transport Feroviar (`rail_mers_tren`)

#### 2.1 Fisier de intrare necesar

Scriptul cauta local fisierul:

- `trenuri-2025-2026_interregional-calator.xml`

Dataset sursa: https://data.gov.ro/dataset/mers-tren-interregional-calatori

Nota: daca fisierul descarcat are alt nume, redenumeste-l la numele asteptat de script sau modifica scriptul.

#### 2.2 Dependinte

- Python 3.12+
- doar biblioteca standard (`xml.etree.ElementTree`)

#### 2.3 Rulare

```bash
python curatare_trenuri.py
```

Output: `rail_mers_tren.sql` (`CREATE TABLE` + `INSERT INTO` in batch-uri).

#### 2.4 Structura bazei de date

- `stations(station_id, station_number, station_name, county)`
- `trains(train_id, train_number, operator_name, category)`
- `timetables(timetable_id, train_id, station_id, arrival_time, departure_time, service_category, day_type)`

#### 2.5 Note tehnice importante

- `station_name` vine din `DenStaDestinatie`.
- `county` este inferat euristic pe baza numelui statiei; statii neclasificate: `Alte Judete`.
- `train_number` vine din atributul XML `Numar`.
- `operator_name` vine din atributul XML `Operator`.
- `arrival_time` si `departure_time` sunt convertite din secunde brute in `HH:MM`.
- `day_type` este decodat din bitmask-ul `Zile` (ex: `Zilnic`, `Luni - Vineri`).

### Fisiere generate

- `edu_reteaua_scolara.sql`
- `rail_mers_tren.sql`

---

## English

### Purpose

This folder contains Python scripts that process raw government data and generate SQL files for the two project domains:

- education (`edu_reteaua_scolara.sql`)
- rail transport (`rail_mers_tren.sql`)

### 1. Education domain (`edu_reteaua_scolara`)

#### 1.1 Required input files

Place these files in the same folder as the script:

- `retea-scolara-2024-2025.xlsx` (dataset: https://data.gov.ro/dataset/retea-scolara)
- `elevi-inmatriculati-2024-2025.xlsx` (dataset: https://data.gov.ro/dataset/elevi-inmatriculati)

#### 1.2 Dependencies

- Python 3.12+
- `openpyxl`

Install:

```bash
pip install openpyxl
```

#### 1.3 Run

```bash
python clean_educatie.py
```

Output: `edu_reteaua_scolara.sql` (`CREATE TABLE` + `INSERT INTO` for SQLite).

#### 1.4 Database schema

- `counties(county_id, county_code, county_name)`
- `localities(locality_id, locality_name, residency_area, county_id)`
- `schools(school_id, school_name, short_name, siiir_code, locality_id, ownership_type, unit_type, education_level, number_of_students)`

#### 1.5 Important technical notes

- `county_name` is populated from an internal mapping (`COUNTY_MAP`) using county code.
- `siiir_code` is normalized with `zfill(10)` to preserve leading zeros.
- The logical join between the two Excel files is:
  - `Cod SIIIR PJ` (school network file)
  - `Cod unitate PJ` (student file)
- `number_of_students` is aggregated only for `unit_type = 'PJ'`.
- For `AR`, `number_of_students` and `education_level` are typically `NULL`.
- `education_level` may contain multiple concatenated values, so use `LIKE` for filtering.

#### 1.6 Statistics (as reported by the team run)

- Input:
  - school network rows: 18,200
  - enrolled students rows: 133,838
- Output:
  - counties: 42
  - unique localities: 7,284
  - school units (PJ + AR): 18,200

### 2. Rail domain (`rail_mers_tren`)

#### 2.1 Required input file

The script expects this local filename:

- `trenuri-2025-2026_interregional-calator.xml`

Source dataset: https://data.gov.ro/dataset/mers-tren-interregional-calatori

Note: if the downloaded file has a different name, rename it to the expected one or update the script.

#### 2.2 Dependencies

- Python 3.12+
- standard library only (`xml.etree.ElementTree`)

#### 2.3 Run

```bash
python curatare_trenuri.py
```

Output: `rail_mers_tren.sql` (`CREATE TABLE` + batch `INSERT INTO` statements).

#### 2.4 Database schema

- `stations(station_id, station_number, station_name, county)`
- `trains(train_id, train_number, operator_name, category)`
- `timetables(timetable_id, train_id, station_id, arrival_time, departure_time, service_category, day_type)`

#### 2.5 Important technical notes

- `station_name` comes from `DenStaDestinatie`.
- `county` is assigned heuristically from station names; unmatched stations become `Alte Judete`.
- `train_number` comes from XML attribute `Numar`.
- `operator_name` comes from XML attribute `Operator`.
- `arrival_time` and `departure_time` are converted from raw seconds to `HH:MM`.
- `day_type` is decoded from the `Zile` bitmask (for example `Zilnic`, `Luni - Vineri`).

### Generated files

- `edu_reteaua_scolara.sql`
- `rail_mers_tren.sql`
