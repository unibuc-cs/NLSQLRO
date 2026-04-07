"""Local deterministic provider for offline development/testing.

It emits schema-aware SQL/question pairs without external model calls.
"""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional

from dataset_gen.providers.base import AgenticProvider
from dataset_gen.schema import SchemaSnapshot
from dataset_gen.types import QueryCandidate


def _sql_lit(value: str) -> str:
    """Escape single quotes for SQL string literals."""
    return "'" + str(value).replace("'", "''") + "'"


def _pick(values: List[str], fallback: str, rng: random.Random) -> str:
    """Pick random non-empty value or fallback when hints are unavailable."""
    clean = [x for x in values if x]
    if not clean:
        return fallback
    return rng.choice(clean)


class MockProvider(AgenticProvider):
    """
    Deterministic local provider for development and CI.
    Generates schema-valid candidates without external APIs.
    """

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def generate_candidate(
        self,
        domain: str,
        snapshot: SchemaSnapshot,
        difficulty: int,
        min_rows: int,
        strict_non_empty: bool,
        feedback: List[str],
    ) -> QueryCandidate:
        """Generate candidate by domain-specific template families."""
        if domain == "education":
            return self._gen_education(snapshot, difficulty)
        return self._gen_trains(snapshot, difficulty)

    def repair_candidate(
        self,
        domain: str,
        snapshot: SchemaSnapshot,
        previous: QueryCandidate,
        error_message: str,
        min_rows: int,
        strict_non_empty: bool,
    ) -> QueryCandidate:
        # Local fallback strategy: regenerate a fresh candidate at same difficulty.
        return self.generate_candidate(
            domain=domain,
            snapshot=snapshot,
            difficulty=previous.difficulty,
            min_rows=min_rows,
            strict_non_empty=strict_non_empty,
            feedback=[error_message],
        )

    def translate_to_romanian(
        self, question_en: str, domain: str, question_ro_hint: Optional[str] = None
    ) -> str:
        """Return hint if available, otherwise apply simple heuristic translation."""
        if question_ro_hint:
            return question_ro_hint
        replacements = [
            ("List all schools in ", "Listeaza toate scolile din judetul "),
            ("List all trains operated by ", "Listeaza toate trenurile operate de "),
            ("How many schools are in each county?", "Cate scoli sunt in fiecare judet?"),
            ("Show", "Afiseaza"),
            ("List", "Listeaza"),
            ("county", "judet"),
            ("schools", "scoli"),
            ("trains", "trenuri"),
            ("station", "statie"),
            ("operator", "operator"),
        ]
        out = question_en
        for src, dst in replacements:
            out = out.replace(src, dst)
        return out

    def _gen_education(self, snapshot: SchemaSnapshot, difficulty: int) -> QueryCandidate:
        """Education domain template pool split by difficulty."""
        counties = snapshot.value_hints.get("counties.county_name", [])
        areas = snapshot.value_hints.get("localities.residency_area", ["URBAN", "RURAL"])
        county = _pick(counties, "Cluj", self.rng)
        area = _pick(areas, "URBAN", self.rng)
        n = self.rng.choice([500, 1000, 3000, 5000, 7000])
        k = self.rng.choice([5, 10, 15])

        easy: List[Callable[[], QueryCandidate]] = [
            lambda: QueryCandidate(
                question_en=f"List all schools in {county} county.",
                question_ro_hint=f"Listeaza toate scolile din judetul {county}.",
                sql=(
                    "SELECT s.school_id, s.school_name, l.locality_name "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    f"WHERE c.county_name = {_sql_lit(county)} "
                    "ORDER BY s.school_name "
                    "LIMIT 100;"
                ),
                difficulty=1,
                query_type=["SELECT", "JOIN", "FILTER", "ORDER_BY", "LIMIT"],
                tables=["schools", "localities", "counties"],
            ),
            lambda: QueryCandidate(
                question_en="How many schools are in each county?",
                question_ro_hint="Cate scoli sunt in fiecare judet?",
                sql=(
                    "SELECT c.county_name, COUNT(*) AS school_count "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    "GROUP BY c.county_name "
                    "ORDER BY school_count DESC;"
                ),
                difficulty=1,
                query_type=["SELECT", "JOIN", "COUNT", "GROUP_BY", "ORDER_BY"],
                tables=["schools", "localities", "counties"],
            ),
            lambda: QueryCandidate(
                question_en="List schools that include both primary and lower-secondary levels.",
                question_ro_hint="Listeaza scolile care includ atat nivel primar, cat si gimnazial.",
                sql=(
                    "SELECT s.school_id, s.school_name, s.education_level "
                    "FROM schools s "
                    "WHERE s.education_level LIKE '%Primar%' "
                    "AND s.education_level LIKE '%Gimnazial%' "
                    "ORDER BY s.school_name;"
                ),
                difficulty=1,
                query_type=["SELECT", "FILTER", "LIKE", "ORDER_BY"],
                tables=["schools"],
            ),
        ]

        medium: List[Callable[[], QueryCandidate]] = [
            lambda: QueryCandidate(
                question_en=f"Show localities in {county} county with more than {n} students in PJ schools.",
                question_ro_hint=(
                    f"Afiseaza localitatile din judetul {county} care au peste {n} elevi in scolile PJ."
                ),
                sql=(
                    "SELECT l.locality_name, SUM(s.number_of_students) AS total_students "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    f"WHERE c.county_name = {_sql_lit(county)} "
                    "AND s.unit_type = 'PJ' "
                    "GROUP BY l.locality_name "
                    f"HAVING SUM(s.number_of_students) > {n} "
                    "ORDER BY total_students DESC;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "SUM", "GROUP_BY", "HAVING", "ORDER_BY"],
                tables=["schools", "localities", "counties"],
            ),
            lambda: QueryCandidate(
                question_en=(
                    f"List PJ schools in {area} localities from {county} county that include high-school level."
                ),
                question_ro_hint=(
                    f"Listeaza scolile PJ din mediul {area} din judetul {county} care au nivel liceal."
                ),
                sql=(
                    "SELECT s.school_name, l.locality_name "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    f"WHERE c.county_name = {_sql_lit(county)} "
                    "AND s.unit_type = 'PJ' "
                    f"AND l.residency_area = {_sql_lit(area)} "
                    "AND s.education_level LIKE '%Liceal%' "
                    "ORDER BY s.school_name;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "FILTER", "LIKE", "ORDER_BY"],
                tables=["schools", "localities", "counties"],
            ),
            lambda: QueryCandidate(
                question_en=f"Show the top {k} localities in {county} county by number of PJ schools.",
                question_ro_hint=f"Afiseaza top {k} localitati din judetul {county} dupa numarul de scoli PJ.",
                sql=(
                    "SELECT l.locality_name, COUNT(*) AS pj_school_count "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    f"WHERE c.county_name = {_sql_lit(county)} "
                    "AND s.unit_type = 'PJ' "
                    "GROUP BY l.locality_name "
                    "ORDER BY pj_school_count DESC, l.locality_name "
                    f"LIMIT {k};"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "COUNT", "GROUP_BY", "ORDER_BY", "LIMIT"],
                tables=["schools", "localities", "counties"],
            ),
        ]

        hard: List[Callable[[], QueryCandidate]] = [
            lambda: QueryCandidate(
                question_en=f"List PJ schools in {county} county with student counts above county average.",
                question_ro_hint=(
                    f"Listeaza scolile PJ din judetul {county} care au numar de elevi peste media judetului."
                ),
                sql=(
                    "SELECT s.school_name, s.number_of_students "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    f"WHERE c.county_name = {_sql_lit(county)} "
                    "AND s.unit_type = 'PJ' "
                    "AND s.number_of_students IS NOT NULL "
                    "AND s.number_of_students > ("
                    "  SELECT AVG(s2.number_of_students) "
                    "  FROM schools s2 "
                    "  JOIN localities l2 ON s2.locality_id = l2.locality_id "
                    "  JOIN counties c2 ON l2.county_id = c2.county_id "
                    f"  WHERE c2.county_name = {_sql_lit(county)} "
                    "  AND s2.unit_type = 'PJ' "
                    "  AND s2.number_of_students IS NOT NULL"
                    ") "
                    "ORDER BY s.number_of_students DESC;"
                ),
                difficulty=3,
                query_type=["SELECT", "JOIN", "FILTER", "SUBQUERY", "AVG", "ORDER_BY"],
                tables=["schools", "localities", "counties"],
            ),
            lambda: QueryCandidate(
                question_en="Which counties have at least one private school?",
                question_ro_hint="Ce judete au cel putin o scoala privata?",
                sql=(
                    "SELECT DISTINCT c.county_name "
                    "FROM counties c "
                    "WHERE EXISTS ("
                    "  SELECT 1 "
                    "  FROM localities l "
                    "  JOIN schools s ON s.locality_id = l.locality_id "
                    "  WHERE l.county_id = c.county_id "
                    "  AND s.ownership_type IS NOT NULL "
                    "  AND LOWER(s.ownership_type) LIKE '%priv%'"
                    ") "
                    "ORDER BY c.county_name;"
                ),
                difficulty=3,
                query_type=["SELECT", "EXISTS", "JOIN", "DISTINCT", "LIKE", "ORDER_BY"],
                tables=["counties", "localities", "schools"],
            ),
            lambda: QueryCandidate(
                question_en="Show counties with at least 50 PJ schools and average students above 250.",
                question_ro_hint=(
                    "Afiseaza judetele care au cel putin 50 de scoli PJ si media elevilor peste 250."
                ),
                sql=(
                    "SELECT c.county_name, COUNT(s.school_id) AS pj_schools, "
                    "AVG(s.number_of_students) AS avg_students "
                    "FROM schools s "
                    "JOIN localities l ON s.locality_id = l.locality_id "
                    "JOIN counties c ON l.county_id = c.county_id "
                    "WHERE s.unit_type = 'PJ' AND s.number_of_students IS NOT NULL "
                    "GROUP BY c.county_name "
                    "HAVING COUNT(s.school_id) >= 50 AND AVG(s.number_of_students) > 250 "
                    "ORDER BY avg_students DESC;"
                ),
                difficulty=3,
                query_type=["SELECT", "JOIN", "COUNT", "AVG", "GROUP_BY", "HAVING"],
                tables=["schools", "localities", "counties"],
            ),
        ]

        if difficulty <= 1:
            return self.rng.choice(easy)()
        if difficulty == 2:
            return self.rng.choice(medium)()
        return self.rng.choice(hard)()

    def _gen_trains(self, snapshot: SchemaSnapshot, difficulty: int) -> QueryCandidate:
        """Rail domain template pool split by difficulty."""
        ops = snapshot.value_hints.get("trains.operator_name", [])
        stations = snapshot.value_hints.get("stations.station_name", [])
        top_stations = snapshot.value_hints.get("stations.top_station_names", []) or stations
        day_types = snapshot.value_hints.get("timetables.day_type", [])

        operator = _pick(ops, "CFR Calatori", self.rng)
        station_a = _pick(top_stations, "Cluj Napoca", self.rng)
        station_b = _pick(top_stations, "Apahida Hm.", self.rng)
        station_c = _pick(stations, "Cluj Napoca Est", self.rng)
        day_type = _pick(day_types, "Zilnic", self.rng)
        hour_start = self.rng.randint(0, 20)
        span = self.rng.randint(2, 6)
        hour_end = min(23, hour_start + span)
        t_start = f"{hour_start:02d}:00"
        t_end = f"{hour_end:02d}:59"
        threshold = self.rng.randint(5, 120)
        limit_n = self.rng.randint(5, 40)

        easy: List[Callable[[], QueryCandidate]] = [
            lambda: QueryCandidate(
                question_en=f"List all trains operated by {operator}.",
                question_ro_hint=f"Listeaza toate trenurile operate de {operator}.",
                sql=(
                    "SELECT t.train_id, t.train_number, t.category "
                    "FROM trains t "
                    f"WHERE t.operator_name = {_sql_lit(operator)} "
                    "ORDER BY t.train_number;"
                ),
                difficulty=1,
                query_type=["SELECT", "FILTER", "ORDER_BY"],
                tables=["trains"],
            ),
            lambda: QueryCandidate(
                question_en=f"List up to {limit_n} departures from {station_a}.",
                question_ro_hint=f"Listeaza pana la {limit_n} plecari din {station_a}.",
                sql=(
                    "SELECT t.train_number, tt.departure_time "
                    "FROM trains t "
                    "JOIN timetables tt ON t.train_id = tt.train_id "
                    "JOIN stations s ON tt.station_id = s.station_id "
                    f"WHERE s.station_name = {_sql_lit(station_a)} "
                    "AND tt.departure_time IS NOT NULL "
                    "ORDER BY tt.departure_time, t.train_number "
                    f"LIMIT {limit_n};"
                ),
                difficulty=1,
                query_type=["SELECT", "JOIN", "FILTER", "ORDER_BY", "LIMIT"],
                tables=["trains", "timetables", "stations"],
            ),
            lambda: QueryCandidate(
                question_en="How many distinct trains run for each day type?",
                question_ro_hint="Cate trenuri distincte circula pentru fiecare tip de zi?",
                sql=(
                    "SELECT tt.day_type, COUNT(DISTINCT tt.train_id) AS trains_running "
                    "FROM timetables tt "
                    "GROUP BY tt.day_type "
                    "ORDER BY trains_running DESC;"
                ),
                difficulty=1,
                query_type=["SELECT", "COUNT", "DISTINCT", "GROUP_BY", "ORDER_BY"],
                tables=["timetables"],
            ),
            lambda: QueryCandidate(
                question_en="Show the top 15 stations by total number of stops.",
                question_ro_hint="Afiseaza primele 15 statii dupa numarul total de opriri.",
                sql=(
                    "SELECT s.station_name, COUNT(*) AS stop_count "
                    "FROM timetables tt "
                    "JOIN stations s ON tt.station_id = s.station_id "
                    "GROUP BY s.station_id, s.station_name "
                    "ORDER BY stop_count DESC "
                    "LIMIT 15;"
                ),
                difficulty=1,
                query_type=["SELECT", "JOIN", "COUNT", "GROUP_BY", "ORDER_BY", "LIMIT"],
                tables=["timetables", "stations"],
            ),
            lambda: QueryCandidate(
                question_en=f"Show distinct train count for station {station_c}.",
                question_ro_hint=f"Afiseaza numarul de trenuri distincte pentru statia {station_c}.",
                sql=(
                    "SELECT s.station_name, COUNT(DISTINCT tt.train_id) AS distinct_trains "
                    "FROM stations s "
                    "JOIN timetables tt ON s.station_id = tt.station_id "
                    f"WHERE s.station_name = {_sql_lit(station_c)} "
                    "GROUP BY s.station_name;"
                ),
                difficulty=1,
                query_type=["SELECT", "JOIN", "COUNT", "DISTINCT", "GROUP_BY", "FILTER"],
                tables=["stations", "timetables"],
            ),
        ]

        medium: List[Callable[[], QueryCandidate]] = [
            lambda: QueryCandidate(
                question_en=(
                    f"List trains departing from {station_a} between {t_start} and {t_end}."
                ),
                question_ro_hint=(
                    f"Listeaza trenurile care pleaca din {station_a} intre {t_start} si {t_end}."
                ),
                sql=(
                    "SELECT DISTINCT t.train_number, t.operator_name, tt.departure_time "
                    "FROM trains t "
                    "JOIN timetables tt ON t.train_id = tt.train_id "
                    "JOIN stations s ON tt.station_id = s.station_id "
                    f"WHERE s.station_name = {_sql_lit(station_a)} "
                    f"AND tt.departure_time BETWEEN {_sql_lit(t_start)} AND {_sql_lit(t_end)} "
                    "ORDER BY tt.departure_time, t.train_number;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "DISTINCT", "FILTER", "BETWEEN", "ORDER_BY"],
                tables=["trains", "timetables", "stations"],
            ),
            lambda: QueryCandidate(
                question_en=f"For station {station_a}, show number of trains per operator.",
                question_ro_hint=f"Pentru statia {station_a}, afiseaza numarul de trenuri pe operator.",
                sql=(
                    "SELECT t.operator_name, COUNT(DISTINCT t.train_id) AS train_count "
                    "FROM trains t "
                    "JOIN timetables tt ON t.train_id = tt.train_id "
                    "JOIN stations s ON tt.station_id = s.station_id "
                    f"WHERE s.station_name = {_sql_lit(station_a)} "
                    "GROUP BY t.operator_name "
                    "ORDER BY train_count DESC;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "COUNT", "DISTINCT", "GROUP_BY", "ORDER_BY"],
                tables=["trains", "timetables", "stations"],
            ),
            lambda: QueryCandidate(
                question_en=f"For day type {day_type}, show number of trains per operator.",
                question_ro_hint=f"Pentru tipul de zi {day_type}, afiseaza numarul de trenuri pe operator.",
                sql=(
                    "SELECT t.operator_name, COUNT(DISTINCT t.train_id) AS train_count "
                    "FROM trains t "
                    "JOIN timetables tt ON t.train_id = tt.train_id "
                    f"WHERE tt.day_type = {_sql_lit(day_type)} "
                    "GROUP BY t.operator_name "
                    "ORDER BY train_count DESC;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "COUNT", "DISTINCT", "GROUP_BY", "ORDER_BY"],
                tables=["trains", "timetables"],
            ),
            lambda: QueryCandidate(
                question_en=f"List stations through which more than {threshold} distinct trains pass.",
                question_ro_hint=(
                    f"Listeaza statiile prin care trec mai mult de {threshold} trenuri distincte."
                ),
                sql=(
                    "SELECT s.station_name, COUNT(DISTINCT tt.train_id) AS distinct_trains "
                    "FROM stations s "
                    "JOIN timetables tt ON s.station_id = tt.station_id "
                    "GROUP BY s.station_id, s.station_name "
                    f"HAVING COUNT(DISTINCT tt.train_id) > {threshold} "
                    "ORDER BY distinct_trains DESC;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "COUNT", "DISTINCT", "GROUP_BY", "HAVING"],
                tables=["stations", "timetables"],
            ),
            lambda: QueryCandidate(
                question_en=f"List stations with more than {threshold} total stops.",
                question_ro_hint=f"Listeaza statiile cu peste {threshold} opriri totale.",
                sql=(
                    "SELECT s.station_name, COUNT(*) AS stop_count "
                    "FROM stations s "
                    "JOIN timetables tt ON s.station_id = tt.station_id "
                    "GROUP BY s.station_id, s.station_name "
                    f"HAVING COUNT(*) > {threshold} "
                    "ORDER BY stop_count DESC;"
                ),
                difficulty=2,
                query_type=["SELECT", "JOIN", "COUNT", "GROUP_BY", "HAVING", "ORDER_BY"],
                tables=["stations", "timetables"],
            ),
        ]

        hard: List[Callable[[], QueryCandidate]] = [
            lambda: QueryCandidate(
                question_en=f"List trains that pass through {station_a} and then {station_b}.",
                question_ro_hint=f"Listeaza trenurile care trec prin {station_a} si apoi prin {station_b}.",
                sql=(
                    "SELECT DISTINCT t.train_number, t.operator_name "
                    "FROM trains t "
                    "JOIN timetables ta ON t.train_id = ta.train_id "
                    "JOIN stations sa ON ta.station_id = sa.station_id "
                    "JOIN timetables tb ON t.train_id = tb.train_id "
                    "JOIN stations sb ON tb.station_id = sb.station_id "
                    f"WHERE sa.station_name = {_sql_lit(station_a)} "
                    f"AND sb.station_name = {_sql_lit(station_b)} "
                    "AND ta.timetable_id < tb.timetable_id "
                    "ORDER BY t.train_number;"
                ),
                difficulty=3,
                query_type=["SELECT", "JOIN", "DISTINCT", "SELF_JOIN", "FILTER", "ORDER_BY"],
                tables=["trains", "timetables", "stations"],
            ),
            lambda: QueryCandidate(
                question_en="What is the average number of stops per train for each operator?",
                question_ro_hint=(
                    "Care este media numarului de opriri pe tren pentru fiecare operator?"
                ),
                sql=(
                    "SELECT t.operator_name, AVG(x.stop_count) AS avg_stops_per_train "
                    "FROM ("
                    "  SELECT tt.train_id, COUNT(*) AS stop_count "
                    "  FROM timetables tt "
                    "  GROUP BY tt.train_id"
                    ") x "
                    "JOIN trains t ON t.train_id = x.train_id "
                    "GROUP BY t.operator_name "
                    "ORDER BY avg_stops_per_train DESC;"
                ),
                difficulty=3,
                query_type=["SELECT", "SUBQUERY", "JOIN", "AVG", "COUNT", "GROUP_BY"],
                tables=["trains", "timetables"],
            ),
            lambda: QueryCandidate(
                question_en=f"For station {station_b}, show first and last departure by operator.",
                question_ro_hint=f"Pentru statia {station_b}, afiseaza prima si ultima plecare pe operator.",
                sql=(
                    "SELECT t.operator_name, MIN(tt.departure_time) AS first_departure, "
                    "MAX(tt.departure_time) AS last_departure "
                    "FROM trains t "
                    "JOIN timetables tt ON t.train_id = tt.train_id "
                    "JOIN stations s ON tt.station_id = s.station_id "
                    f"WHERE s.station_name = {_sql_lit(station_b)} "
                    "AND tt.departure_time IS NOT NULL "
                    "GROUP BY t.operator_name "
                    "ORDER BY t.operator_name;"
                ),
                difficulty=3,
                query_type=["SELECT", "JOIN", "MIN", "MAX", "GROUP_BY", "FILTER", "ORDER_BY"],
                tables=["trains", "timetables", "stations"],
            ),
            lambda: QueryCandidate(
                question_en=(
                    f"Which trains depart after {t_start} from {station_a} and also reach {station_b}?"
                ),
                question_ro_hint=(
                    f"Ce trenuri pleaca dupa {t_start} din {station_a} si ajung in {station_b}?"
                ),
                sql=(
                    "WITH departures AS ("
                    "  SELECT tt.train_id, tt.departure_time "
                    "  FROM timetables tt "
                    "  JOIN stations s ON tt.station_id = s.station_id "
                    f"  WHERE s.station_name = {_sql_lit(station_a)} "
                    f"  AND tt.departure_time >= {_sql_lit(t_start)}"
                    "), arrivals AS ("
                    "  SELECT DISTINCT tt.train_id "
                    "  FROM timetables tt "
                    "  JOIN stations s ON tt.station_id = s.station_id "
                    f"  WHERE s.station_name = {_sql_lit(station_b)}"
                    ") "
                    "SELECT DISTINCT t.train_number, t.operator_name, d.departure_time "
                    "FROM departures d "
                    "JOIN arrivals a ON d.train_id = a.train_id "
                    "JOIN trains t ON t.train_id = d.train_id "
                    "ORDER BY d.departure_time, t.train_number;"
                ),
                difficulty=3,
                query_type=["WITH", "SELECT", "JOIN", "DISTINCT", "FILTER", "ORDER_BY"],
                tables=["timetables", "stations", "trains"],
            ),
            lambda: QueryCandidate(
                question_en=f"List operators having at least {threshold} distinct trains.",
                question_ro_hint=f"Listeaza operatorii care au cel putin {threshold} trenuri distincte.",
                sql=(
                    "SELECT t.operator_name, COUNT(DISTINCT t.train_id) AS train_count "
                    "FROM trains t "
                    "GROUP BY t.operator_name "
                    f"HAVING COUNT(DISTINCT t.train_id) >= {threshold} "
                    "ORDER BY train_count DESC;"
                ),
                difficulty=3,
                query_type=["SELECT", "COUNT", "DISTINCT", "GROUP_BY", "HAVING", "ORDER_BY"],
                tables=["trains"],
            ),
        ]

        if difficulty <= 1:
            return self.rng.choice(easy)()
        if difficulty == 2:
            return self.rng.choice(medium)()
        return self.rng.choice(hard)()
