
# RoGov-SQL – Interogare Bilingvă (RO/EN) peste Date Guvernamentale 

## 1. Obiectiv

Vom construi un **benchmark bilingv NL→SQL** (întrebare în română/engleză → interogare SQL) peste două baze de date relaționale obținute din **date guvernamentale deschise** (https://data.gov.ro/dataset):

- Domeniul **Educație** – “Rețeaua școlară” + (opțional) alte date de elevi/rezultate.
- Domeniul **Transport feroviar** – “Mersul trenurilor de călători”.

Scop: un corpus reutilizabil pentru cercetare (NL→SQL, LLM-uri, educație) și un articol științific.

---

## 2. Baze de date (DB) – nivel minim

### 2.1. Educație – `edu_reteaua_scolara`

Schemă minimă recomandată (ajustați după datele reale):

- `counties(county_id, county_name)`
- `localities(locality_id, locality_name, county_id)`
- `schools(school_id, name, locality_id, education_level, environment, ownership_type, nr_students)`

### 2.2. Trenuri – `rail_mers_tren`

Schemă minimă recomandată:

- `stations(station_id, station_name, county_id)`
- `trains(train_id, train_number, operator_name, category)`
- `timetable(id, train_id, station_id, arrival_time, departure_time, day_type)`

---

## 3. Structura corpusului NL→SQL (RoGov-SQL)

Format recomandat: **JSON Lines** (1 obiect/linie).

Câmpuri obligatorii:

    {
      "id": "edu_001",
      "domain": "education",          // "education" sau "trains"
      "db_id": "edu_reteaua_scolara", // sau "rail_mers_tren"
      "question_ro": "...",
      "question_en": "...",
      "sql": "...",
      "difficulty": 1,                // 1=uşor, 2=mediu, 3=avansat
      "query_type": ["SELECT","JOIN"],
      "tables": ["schools","localities","counties"],
      "expected_result_description_en": "Short English description"
    }

---

## 4. Organizarea echipelor și livrabile

### 4.1. Grupuri (20 studenți ≈ 4 × 5)

- **G1 – Edu Schema & Data**
  - Curățare date educație, definire și populare schema `edu_reteaua_scolara`.
- **G2 – Rail Schema & Data**
  - Curățare date trenuri, definire și populare schema `rail_mers_tren`.
- **G3 – NL→SQL Edu**
  - Generare întrebări + SQL pentru domeniul Educație (≈200–300 intrări).
- **G4 – NL→SQL Rail**
  - Generare întrebări + SQL pentru domeniul Trenuri (≈200–300 intrări).

### 4.2. Faze

1. **Faza 0 – Specificații**
   - Nume finale tabele/coloane, format JSON, stil întrebări, convenții.

2. **Faza 1 – Baze de date (G1, G2)**
   - Scripturi Python pentru curățare CSV/XLSX.
   - Fișier `.sql` (schema + insert-uri) sau CSV-uri + script de încărcare.

3. **Faza 2 – Corpus NL→SQL (G3, G4)**
   - Instanțiați template-urile de mai jos cu valori reale.
   - Pentru fiecare intrare:
     - `question_ro`, `question_en`
     - `sql` verificat (rulează, rezultat nevid)
     - `difficulty`, `query_type`, `tables`
     - `expected_result_description_en`.

4. **Faza 3 – Validare**
   - Cross-review: G3 verifică intrările G4 și invers.
   - Se rezolvă duplicări, erori SQL, formulări neclare.

5. **Faza 4 – Cod & Documentație**
   - Scripturi Python pentru:
     - încărcare DB + rulare SQL;
     - validare corpus.
   - README cu:
     - descriere domenii, tabele, statistici;
     - instrucțiuni de rulare.

### 4.3. Livrabile

- `edu_reteaua_scolara.sql` și `rail_mers_tren.sql` (sau echivalent).
- `rogov_sql.jsonl` (≈400–600 intrări curate).
- Scripturi de validare și README.

---

## 5. Template-uri de întrebări NL→SQL

Scop: **NU inventați de la zero**, ci instanțiați template-uri cu valori reale (nume județe, localități, operatori, ore etc.).

### 5.1. Educație – Nivel 1 (ușor)

**E1.1 – SELECT simplu + filtrare pe județ și tip**

- RO: `Listează toate [TIP_UNITATE] din județul [NUME_JUDET].`
- EN: `List all [SCHOOL_TYPE] in [COUNTY_NAME] county.`
- Tabele: `schools`, `localities`, `counties`.

**E1.2 – SELECT simplu + mediu**

- RO: `Listează toate școlile din mediul [MEDIU] din județul [NUME_JUDET].`
- EN: `List all schools located in [ENVIRONMENT] areas in [COUNTY_NAME] county.`
- Tabele: `schools`, `localities`, `counties`.

**E1.3 – Filtrare pe ownership**

- RO: `Listează toate școlile [TIP_PROPRIETATE] din localitatea [NUME_LOCALITATE].`
- EN: `List all [OWNERSHIP_TYPE] schools in [LOCALITY_NAME].`
- Tabele: `schools`, `localities`.

---

### 5.2. Educație – Nivel 2 (mediu)

**E2.1 – JOIN + mediu + tip**

- RO: `Listează toate [TIP_UNITATE] din județul [NUME_JUDET] care sunt în mediul [MEDIU].`
- EN: `List all [SCHOOL_TYPE] in [COUNTY_NAME] county that are located in [ENVIRONMENT] areas.`
- Tabele: `schools`, `localities`, `counties`.

Exemplu SQL (Cluj, liceu, urban):

    SELECT s.school_id, s.name, l.locality_name
    FROM schools s
    JOIN localities l ON s.locality_id = l.locality_id
    JOIN counties c ON l.county_id = c.county_id
    WHERE c.county_name = 'Cluj'
      AND s.education_level = 'liceu'
      AND s.environment = 'urban';

**E2.2 – SUM pe nr_students**

- RO: `Care este numărul total de elevi înscriși în [TIP_UNITATE] din județul [NUME_JUDET]?`
- EN: `What is the total number of students enrolled in [SCHOOL_TYPE] in [COUNTY_NAME] county?`

**E2.3 – GROUP BY localitate**

- RO: `Afișează, pentru județul [NUME_JUDET], numărul total de elevi pe fiecare localitate.`
- EN: `For [COUNTY_NAME] county, show the total number of students per locality.`

---

### 5.3. Educație – Nivel 3 (avansat)

**E3.1 – Top k localități**

- RO: `Afișează primele [K] localități din județul [NUME_JUDET] după numărul total de elevi.`
- EN: `Show the top [K] localities in [COUNTY_NAME] county by total number of students.`

**E3.2 – HAVING (minim elevi)**

- RO: `Listează localitățile din județul [NUME_JUDET] care au în total peste [N] elevi.`
- EN: `List the localities in [COUNTY_NAME] county that have more than [N] students in total.`

**E3.3 – Subinterogare (peste media județului)**

- RO: `Listează școlile din județul [NUME_JUDET] al căror număr de elevi este peste media județului.`
- EN: `List the schools in [COUNTY_NAME] county whose number of students is above the county average.`

---

### 5.4. Trenuri – Nivel 1 (ușor)

**T1.1 – Trenuri dintr-o stație**

- RO: `Listează toate trenurile care pleacă din stația [STAȚIE].`
- EN: `List all trains departing from [STATION_NAME].`

**T1.2 – Trenuri ale unui operator**

- RO: `Listează toate trenurile operate de [OPERATOR].`
- EN: `List all trains operated by [OPERATOR].`

**T1.3 – Stații într-un județ**

- RO: `Listează toate stațiile de tren din județul [NUME_JUDET].`
- EN: `List all train stations in [COUNTY_NAME] county.`

---

### 5.5. Trenuri – Nivel 2 (mediu)

**T2.1 – Plecări între interval orar**

- RO: `Listează toate trenurile care pleacă din [STAȚIE] între orele [ORA_START] și [ORA_END], ordonate după ora de plecare.`
- EN: `List all trains that depart from [STATION_NAME] between [TIME_START] and [TIME_END], ordered by departure time.`

**T2.2 – Trenuri către destinație**

- RO: `Listează trenurile care pleacă din [STAȚIE_PLECARE] și ajung în [STAȚIE_SOSIRE].`
- EN: `List the trains that depart from [DEPARTURE_STATION] and arrive at [ARRIVAL_STATION].`

**T2.3 – COUNT per operator într-o stație**

- RO: `Pentru stația [STAȚIE], afișează numărul de trenuri pe fiecare operator.`
- EN: `For station [STATION_NAME], show the number of trains per operator.`

---

### 5.6. Trenuri – Nivel 3 (avansat)

**T3.1 – Operator + interval orar + destinație**

- RO: `Ce trenuri operate de [OPERATOR] pleacă din stația [STAȚIE_PLECARE] către [STAȚIE_SOSIRE] după ora [ORA]?`
- EN: `Which trains operated by [OPERATOR] depart from [DEPARTURE_STATION] to [ARRIVAL_STATION] after [TIME]?`

Exemplu SQL (CFR Călători, București Nord → Brașov, după 18:00):

    SELECT DISTINCT t.train_number, t.category, dep.departure_time
    FROM trains t
    JOIN timetable dep ON t.train_id = dep.train_id
    JOIN stations s_dep ON dep.station_id = s_dep.station_id
    JOIN timetable arr ON t.train_id = arr.train_id
    JOIN stations s_arr ON arr.station_id = s_arr.station_id
    WHERE t.operator_name = 'CFR Călători'
      AND s_dep.station_name = 'București Nord'
      AND s_arr.station_name = 'Brașov'
      AND dep.departure_time > '18:00';

**T3.2 – COUNT cu tip de zi**

- RO: `Pentru fiecare operator, afișează numărul de trenuri care opresc în stația [STAȚIE] într-o zi de tip [TIP_ZI].`
- EN: `For each operator, show the number of trains that stop at [STATION_NAME] on [DAY_TYPE] days.`

**T3.3 – Traseu cu două stații (ordine)**

- RO: `Listează trenurile care trec atât prin [STAȚIE_A], cât și prin [STAȚIE_B], în această ordine.`
- EN: `List the trains that pass through both [STATION_A] and [STATION_B], in that order.`

---

## 6. Exemple complete (orientare)

### 6.1. Educație – exemplu

    {
      "id": "edu_001",
      "domain": "education",
      "db_id": "edu_reteaua_scolara",
      "question_ro": "Listează toate liceele din județul Cluj care sunt în mediul urban.",
      "question_en": "List all high schools in Cluj county that are located in urban areas.",
      "sql": "SELECT s.school_id, s.name, l.locality_name\nFROM schools s\nJOIN localities l ON s.locality_id = l.locality_id\nJOIN counties c ON l.county_id = c.county_id\nWHERE c.county_name = 'Cluj'\n  AND s.education_level = 'liceu'\n  AND s.environment = 'urban';",
      "difficulty": 2,
      "query_type": ["SELECT", "JOIN", "FILTER"],
      "tables": ["schools", "localities", "counties"],
      "expected_result_description_en": "Returns IDs, names, and localities of all schools classified as high schools (liceu) in Cluj county with environment = urban."
    }

### 6.2. Trenuri – exemplu

    {
      "id": "rail_103",
      "domain": "trains",
      "db_id": "rail_mers_tren",
      "question_ro": "Ce trenuri operate de CFR Călători pleacă din stația București Nord către Brașov după ora 18:00?",
      "question_en": "Which trains operated by CFR Călători depart from București Nord station to Brașov after 18:00?",
      "sql": "SELECT DISTINCT t.train_number, t.category, dep.departure_time\nFROM trains t\nJOIN timetable dep ON t.train_id = dep.train_id\nJOIN stations s_dep ON dep.station_id = s_dep.station_id\nJOIN timetable arr ON t.train_id = arr.train_id\nJOIN stations s_arr ON arr.station_id = s_arr.station_id\nWHERE t.operator_name = 'CFR Călători'\n  AND s_dep.station_name = 'București Nord'\n  AND s_arr.station_name = 'Brașov'\n  AND dep.departure_time > '18:00';",
      "difficulty": 3,
      "query_type": ["SELECT", "JOIN", "FILTER", "DISTINCT"],
      "tables": ["trains", "timetable", "stations"],
      "expected_result_description_en": "Returns distinct train numbers, categories, and departure times for CFR Călători trains from București Nord to Brașov departing after 18:00."
    }
