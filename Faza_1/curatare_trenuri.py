"""
RoGov-SQL – Faza 1: Curățare date feroviare (Trenuri)
Sursa: trenuri-2025-2026_interregional-calatori.xml
Output: rail_mers_tren.sql (schema + INSERT-uri)
"""
import os
import xml.etree.ElementTree as ET

# 0. Functii de decodare si curatare


def decode_zile(cod_str):
    """transform mastile binare (799, 319, 16767 etc.) in text clar."""
    if not cod_str: return "Zilnic"
    try:
        cod = int(cod_str)
        pattern = cod % 128
        if pattern == 127: return "Zilnic"
        if pattern == 31:  return "Luni - Vineri"
        if pattern == 96:  return "Sâmbătă - Duminică"
        if pattern == 63:  return "Luni - Sâmbătă"
        if pattern == 95:  return "Luni - Vineri și Duminică"
        
        zile = []
        nume_zile = ["Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"]
        for i in range(7):
            if (pattern >> i) & 1: zile.append(nume_zile[i])
        return ", ".join(zile) if zile else "Zilnic"
    except: return "Zilnic"

def detecteaza_judetul(nume_statie):
    """
    judetele bazate pe numele statiilor
    """
    n = nume_statie.upper()
    
    # TIMIȘ
    if any(x in n for x in ["TIMIŞOARA", "RONAT", "SÂNANDREI", "CALACEA", "ORŢIŞOARA"]): return "Timiș"
    
    # ARAD
    if any(x in n for x in ["ARAD", "VINGA", "ŞAG", "Valea Viilor", "GLOGOVĂŢ", "GHIOROC", "PAULIS", "RADNA", "MILOVA", "BÂRZAVA", "BATA", "VĂRĂDIA", "SĂVĂRŞIN"]): return "Arad"
    
    # HUNEDOARA
    if any(x in n for x in ["ILTEU", "ZAM", "SURDUC", "ILIA", "MINTIA", "DEVA", "SIMERIA", "ORĂŞTIE", "AUREL VLAICU", "ŞIBOT"]): return "Hunedoara"
    
    # ALBA
    if any(x in n for x in ["BLANDIANA", "VINŢU", "ALBA IULIA", "BĂRĂBANŢ", "SÂNTIMBRU", "COŞLARIU", "TEIUŞ", "AIUD", "UNIREA", "RĂZBOIENI"]): return "Alba"
    
    # CLUJ
    if any(x in n for x in ["CLUJ", "BACIU", "APAHIDA", "JUCU", "DEZMIR", "COJOCNA", "BONŢIDA", "GHERLA", "DEJ", "ICLOD", "RĂSCRUCI", "AGHIREŞ", "GÂRBĂU", "MERA", "NĂDĂŞEL", "BOJU", "CÂMPIA TURZII", "TURDA", "HUEDIN", "GĂLĂŞENI"]): return "Cluj"
    
    # SĂLAJ
    if any(x in n for x in ["JIBOU", "VAR H.", "SURDUC SĂLAJ", "CIOCMANI", "BĂBUŢENI", "CUCIULAT", "LETCA", "JEBUC", "STANA"]): return "Sălaj"
    
    # BISTRIȚA-NĂSĂUD
    if any(x in n for x in ["BISTRIŢA", "BECLEAN", "SĂRĂŢEL", "RETEAG", "CICEU", "COLDĂU", "ŞINTEREAG", "MĂGHERUŞ", "BÂRGĂU", "PRUNDU"]): return "Bistrița-Năsăud"
    
    # PRAHOVA
    if any(x in n for x in ["PLOIEŞTI", "BRAZI", "MIZIL", "INOTEŞTI", "CRICOV", "VALEA CĂLUGĂREASCĂ", "CRIVINA", "SCROVIŞTEA", "BUDA", "FLOREŞTI", "CÂMPINA", "COMARNIC", "SINAIA", "BUŞTENI", "AZUGA"]): return "Prahova"
    
    # BRAȘOV
    if any(x in n for x in ["BRAŞOV", "PREDEAL", "TIMIŞU DE SUS", "DÂRSTE"]): return "Brașov"
    
    # VRANCEA
    if any(x in n for x in ["FOCŞANI", "MĂRĂŞEŞTI", "ADJUD", "GUGEŞTI", "COTEŞTI", "SIHLEA", "PUFEŞTI", "PUTNA SEACĂ", "PĂDURENI"]): return "Vrancea"
    
    # BUZĂU
    if any(x in n for x in ["BUZĂU", "RÂMNICU SĂRAT", "ULMENI", "BOBOC", "ZOITA", "SAHATENI"]): return "Buzău"
    
    # BIHOR
    if any(x in n for x in ["ORADEA", "ALEŞD", "BRATCA", "TILEAGD", "VADU CRIŞULUI"]): return "Bihor"

    return "Alte Județe"

def converteste_timpul(secunde_str):
    """converteste secundele în HH:MM"""
    if not secunde_str: return None
    try:
        sec = int(secunde_str)
        return f"{(sec // 3600) % 24:02d}:{(sec % 3600) // 60:02d}"
    except: return None

def esc(val):
    if val is None: return "NULL"
    val_curatat = str(val).replace("'", "''")
    return f"'{val_curatat}'"


# 1. Citire si Parsare XML

print("Deschidere fișier XML...")
try:
    try:
        tree = ET.parse('trenuri-2025-2026_interregional-calatori.xml')
    except FileNotFoundError:
        # print all the files in the current directory for debugging
        print(os.listdir("."))
        print("=================================")
        print(os.listdir(".."))
        print(os.path.exists("trenuri-2025-2026_interregional-calatori.xml"))
        tree = ET.parse(os.path.join('../trenuri-2025-2026_interregional-calator.xml'))
    root = tree.getroot()
except Exception as e:
    print(f"Eroare la citirea XML: {e}")
    exit(1)

stations_dict, stations_list = {}, []
trains_list, timetable_list = [], []
stat_idx, train_idx, tt_idx = 1, 1, 1

trenuri = root.findall('.//Tren')
print(f"S-au găsit {len(trenuri)} trenuri. Procesare...")


# 2. Procesare date in memorie

for tren in trenuri:
    numar = tren.get('Numar')
    if not numar: continue

    cal_tren = tren.find('.//CalendarTren')
    day_type_tren = decode_zile(cal_tren.get('Zile') if cal_tren is not None else "16767")

    trains_list.append({
        'train_id': train_idx, 'train_number': numar,
        'operator_name': tren.get('Operator'), 'category': tren.get('CategorieTren')
    })

    for trasa in tren.findall('.//ElementTrasa'):
        s_cod = trasa.get('CodStaDest')
        s_nume = trasa.get('DenStaDestinatie', '').strip()
        if not s_nume: continue

        s_key = (s_cod, s_nume.upper())
        if s_key not in stations_dict:
            stations_dict[s_key] = stat_idx
            stations_list.append({
                'station_id': stat_idx, 'station_number': s_cod,
                'station_name': s_nume, 'county': detecteaza_judetul(s_nume)
            })
            stat_idx += 1

        cal_trasa = trasa.find('.//CalendarTren')
        dt_final = decode_zile(cal_trasa.get('Zile')) if cal_trasa is not None else day_type_tren

        timetable_list.append({
            'tt_id': tt_idx, 't_id': train_idx, 's_id': stations_dict[s_key],
            'arr': converteste_timpul(trasa.get('OraS')),
            'dep': converteste_timpul(trasa.get('OraP')),
            'rci': trasa.get('Rci'), 'dt': dt_final
        })
        tt_idx += 1
    train_idx += 1


# 3. Generare SQL 

print("Generare rail_mers_tren.sql ...")

lines = []
lines.append("-- ============================================================")
lines.append("-- RoGov-SQL – rail_mers_tren")
lines.append("-- Generat din: trenuri-2025-2026_interregional-calatori.xml")
lines.append("-- An școlar: 2025-2026")
lines.append("-- ============================================================\n")

lines.append("PRAGMA foreign_keys = ON;\n")
lines.append("BEGIN TRANSACTION;\n")

lines.append("-- ─────────────────── SCHEMA ───────────────────\n")

lines.append("""CREATE TABLE IF NOT EXISTS stations (
    station_id     INTEGER PRIMARY KEY,
    station_number INTEGER,
    station_name   VARCHAR(200) NOT NULL,
    county         VARCHAR(100)
);\n""")

lines.append("""CREATE TABLE IF NOT EXISTS trains (
    train_id      INTEGER PRIMARY KEY,
    train_number  VARCHAR(50) NOT NULL,
    operator_name VARCHAR(100),
    category      VARCHAR(50)
);\n""")

lines.append("""CREATE TABLE IF NOT EXISTS timetables (
    timetable_id     INTEGER PRIMARY KEY,
    train_id         INTEGER NOT NULL,
    station_id       INTEGER NOT NULL,
    arrival_time     VARCHAR(10),
    departure_time   VARCHAR(10),
    service_category VARCHAR(50),
    day_type         VARCHAR(200),
    FOREIGN KEY (train_id) REFERENCES trains(train_id),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);\n""")

def build_batch_inserts(table_name, columns, data_list, keys):
    if not data_list: return
    lines.append(f"-- ─────────────────── {table_name.upper()} ───────────────────\n")
    BATCH = 500
    for i in range(0, len(data_list), BATCH):
        batch = data_list[i:i+BATCH]
        lines.append(f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES")
        rows = []
        for d in batch:
            vals = [str(d[k]) if isinstance(d[k], int) else esc(d[k]) for k in keys]
            rows.append("  (" + ", ".join(vals) + ")")
        lines.append(",\n".join(rows) + ";\n")

build_batch_inserts('stations', ['station_id', 'station_number', 'station_name', 'county'], stations_list, ['station_id', 'station_number', 'station_name', 'county'])
build_batch_inserts('trains', ['train_id', 'train_number', 'operator_name', 'category'], trains_list, ['train_id', 'train_number', 'operator_name', 'category'])
build_batch_inserts('timetables', ['timetable_id', 'train_id', 'station_id', 'arrival_time', 'departure_time', 'service_category', 'day_type'], timetable_list, ['tt_id', 't_id', 's_id', 'arr', 'dep', 'rci', 'dt'])

lines.append("COMMIT;")

with open('rail_mers_tren.sql', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print(f"\nSucces! Fișier generat cu {len(stations_list)} stații și {len(trains_list)} trenuri.")