# Faza 1: Curățare și Generare Baze de Date (Echipa G1)

Acest director conține scripturile Python necesare pentru a procesa seturile de date brute guvernamentale și a genera fișierele `.sql` cu structura și datele pentru cele două domenii ale proiectului: Educație și Transport Feroviar.

---

## 1. Domeniul Educație (`edu_reteaua_scolara`) 

### 1.1. Surse de date necesare
Pentru a rula scriptul, următoarele fișiere trebuie să fie prezente în același director:
* [`retea-scolara-2024-2025.xlsx`](https://data.gov.ro/dataset/retea-scolara)
* [`elevi-inmatriculati-2024-2025.xlsx`](https://data.gov.ro/dataset/elevi-inmatriculati)

### 1.2. Cerințe și Dependințe
Scriptul este scris în Python și folosește biblioteca `openpyxl` pentru a citi și procesa fișierele Excel.
Pentru instalarea dependențelor rulați:
`pip install openpyxl`

### 1.3. Instrucțiuni de rulare
Executați scriptul din terminal:
`python clean_educatie.py`

În urma rulării, se va genera fișierul `edu_reteaua_scolara.sql`, care conține instrucțiunile `CREATE TABLE` și `INSERT INTO` necesare pentru a popula baza de date SQLite.

### 1.4. Structura Bazei de Date și Limitări 

Scriptul generează 3 tabele relaționale. Pentru a scrie interogări SQL corecte, țineți cont de următoarele decizii tehnice luate în timpul curățării datelor:

* **counties** (Județe)
  * Conține lista județelor (ID, cod, nume complet).
  * *Notă:* Deoarece datele sursă conțineau doar codul auto (ex: AB, CJ), numele complet al județului a fost populat printr-o mapare manuală predefinită în script.

* **localities** (Localități)
  * Conține localitățile extrase (ID, nume, mediu rezidență, FK către județ).

* **schools** (Unități Școlare)
  * Conține unitățile (ID, nume, cod SIIIR, FK către localitate, proprietate, statut, niveluri educație, număr total elevi).
  * *Notă school_name:* Pentru unitățile cu statut PJ, preia Denumire PJ. Pentru unitățile arondate (AR), se folosește Denumire lunga unitate, deoarece acestea sunt entități distincte cu nume propriu diferit față de PJ-ul de care aparțin.
  * *Notă siiir_code:* Pentru JOIN-ul logic dintre fișiere, toate codurile au fost normalizate cu `zfill(10)` pentru a preveni pierderea zerourilor inițiale la parsare.
  * *Notă unit_type:* Tabela conține atât unități cu personalitate juridică (PJ) cât și structuri arondate (AR). Interogările care vizează doar unități independente trebuie să filtreze cu `WHERE unit_type = 'PJ'`.
  * *Notă education_level:* O școală cu mai multe niveluri are valorile concatenate alfabetic (ex: "Gimnazial, Liceal, Primar"). Folosiți operatorul `LIKE` pentru filtrări (ex: `education_level LIKE '%Gimnazial%'`), nu egalitatea strictă.
  * *Notă number_of_students:* Valoarea reprezintă suma elevilor, agregată după codul PJ. Pentru structurile arondate (AR), coloana este `NULL`, raportarea fiind centralizată pe PJ.

### 1.5. Statistici Date Extrase
În urma procesării fișierelor oficiale, volumul de date gestionat este:

**Date procesate (Input):**
* Rânduri citite din Rețeaua Școlară: 18.200
* Rânduri citite din Elevi Înmatriculați: 133.838

**Date agregate și deduplicate (Output în DB):**
* **Județe:** 42
* **Localități unice:** 7.284
* **Unități școlare (PJ + AR):** 18.200 (numărul coincide cu inputul deoarece fiecare rând din rețeaua școlară reprezintă o unitate distinctă — deduplicarea a eliminat doar eventualele apariții duplicate ale aceluiași cod SIIIR)

---

## 2. Domeniul Transport Feroviar (`rail_mers_tren`) 

### 2.1. Surse de date necesare
Pentru a rula scriptul, următorul fișier trebuie să fie prezent în același director:
* [`trenuri-2025-2026_interregional-calator.xml`](https://data.gov.ro/dataset/mers-tren-interregional-calatori) 

### 2.2. Cerințe și Dependințe
Scriptul este scris în Python și folosește biblioteca standard `xml.etree.ElementTree` pentru parsarea structurii XML. Nu sunt necesare biblioteci externe suplimentare.

### 2.3. Instrucțiuni de rulare
Executați scriptul din terminal:
`python curatare_trenuri.py`

În urma rulării, se va genera fișierul `rail_mers_tren.sql`. Acesta conține instrucțiunile `CREATE TABLE` și `INSERT INTO` (grupate în batch-uri pentru performanță) necesare pentru a popula baza de date SQLite.

### 2.4. Structura Bazei de Date și Limitări 

* **stations** (Stații) 
  * Conține lista stațiilor (ID, cod, nume, județ).
  * *Notă station_name:* Datele sunt preluate din atributul `DenStaDestinatie`.
  * *Notă county:* Deoarece fișierul XML sursă nu conține informații administrative, județul a fost populat printr-o funcție de detecție euristică/manuală în script. Stațiile neidentificate primesc valoarea 'Alte Județe'.

* **trains** (Trenuri) 
  * Conține detaliile trenurilor (ID, număr, operator, categorie).
  * *Notă train_number:* Preluat din atributul `Numar`.
  * *Notă operator_name:* Preluat din atributul `Operator`.

* **timetables** (Orar de circulație)
  * Conține orele de sosire/plecare și zilele de circulație.
  * *Notă arrival_time / departure_time:* Timpul a fost convertit din secundele brute ale XML-ului în format text **HH:MM** conform formulei de calcul standard.
  * *Notă day_type:* Atributul bitmask `Zile` din `CalendarTren` a fost decodat în script pentru a afișa zilele săptămânii în limbaj natural (ex: 'Zilnic', 'Luni - Vineri'). Folosiți aceste denumiri textuale în filtrări.

### 2.5. Statistici Date Extrase
* **Stații unice:** Extrase pe baza combinației `CodStaDest` și `DenStaDestinatie`. 
* **Trenuri:** Înregistrate cu categoriile aferente (R, IR, R-E). 
* **Orare:** Toate opririle au fost mapate prin chei externe (`train_id`, `station_id`). 

---
**Fișiere rezultate:** `edu_reteaua_scolara.sql` și `rail_mers_tren.sql`.