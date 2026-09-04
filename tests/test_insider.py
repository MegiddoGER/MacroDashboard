"""
tests/test_insider.py — Offene Insidergeschäfte aus SEC Form 4 (Auftrag B).

Geprüft wird das, was diesen Befund still wertlos machen würde: eine Datierung
auf den Handelstag statt auf die Einreichung (in den Daten der SEC liegen
dazwischen im Extremfall 2.332 Tage); ein `"false"`, das als True gelesen wird;
eine Berichtigung, die dasselbe Geschäft ein zweites Mal zählt; eine
Optionsausübung, die als Kauf durchgeht; eine Person, die durch eine verspätet
gemeldete Vorjahrestransaktion **rückwirkend** zur Routine wird; und ein
Vorzeichen, das die Hypothese zur Widerlegung macht.

Die Rohdaten der Tests sind der Form nachgebaut, die am 2026-09-04 gegen den
echten Datensatz 2024Q1 geprüft wurde — Spaltennamen, Datumsformat
(`31-JAN-2024`) und die vier Schreibweisen des 10b5-1-Hakens eingeschlossen.
"""

import io
import zipfile
from datetime import date, datetime

import pytest

from services.insider import (
    FENSTER_TAGE, KAUF, MIN_ABSTAND_TAGE, VERKAUF, _wahrheit,
    geschaefte_aus_archiv, ist_routine, kennzahl_vor, quartale,
    routine_kalender,
)
from snapshot_engine.auswertung.insider import (
    CLUSTER_AB, GRUPPE_CLUSTER, GRUPPE_EIN_KAUF, GRUPPE_KEIN_KAUF, QUANTILE,
    _cluster_vorsprung, _spread, kaeufergruppe, quintil,
)


# ---------------------------------------------------------------------------
# Ein Archiv nach dem Vorbild des echten Datensatzes
# ---------------------------------------------------------------------------

SUBMISSION_SPALTEN = [
    "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB",
    "NO_SECURITIES_OWNED", "NOT_SUBJECT_SEC16", "FORM3_HOLDINGS_REPORTED",
    "FORM4_TRANS_REPORTED", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME",
    "ISSUERTRADINGSYMBOL", "REMARKS", "AFF10B5ONE",
]
OWNER_SPALTEN = [
    "ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP",
    "RPTOWNER_TITLE", "RPTOWNER_TXT", "RPTOWNER_STREET1", "RPTOWNER_STREET2",
    "RPTOWNER_CITY", "RPTOWNER_STATE", "RPTOWNER_ZIPCODE",
    "RPTOWNER_STATE_DESC", "FILE_NUMBER",
]
TRANS_SPALTEN = [
    "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "SECURITY_TITLE",
    "SECURITY_TITLE_FN", "TRANS_DATE", "TRANS_DATE_FN",
    "DEEMED_EXECUTION_DATE", "DEEMED_EXECUTION_DATE_FN", "TRANS_FORM_TYPE",
    "TRANS_CODE", "EQUITY_SWAP_INVOLVED", "EQUITY_SWAP_TRANS_CD_FN",
    "TRANS_TIMELINESS", "TRANS_TIMELINESS_FN", "TRANS_SHARES",
    "TRANS_SHARES_FN", "TRANS_PRICEPERSHARE", "TRANS_PRICEPERSHARE_FN",
    "TRANS_ACQUIRED_DISP_CD", "TRANS_ACQUIRED_DISP_CD_FN",
    "SHRS_OWND_FOLWNG_TRANS", "SHRS_OWND_FOLWNG_TRANS_FN",
    "VALU_OWND_FOLWNG_TRANS", "VALU_OWND_FOLWNG_TRANS_FN",
    "DIRECT_INDIRECT_OWNERSHIP", "DIRECT_INDIRECT_OWNERSHIP_FN",
    "NATURE_OF_OWNERSHIP", "NATURE_OF_OWNERSHIP_FN",
]


def _tsv(spalten, zeilen):
    ausgabe = ["\t".join(spalten)]
    for zeile in zeilen:
        ausgabe.append("\t".join(str(zeile.get(s, "")) for s in spalten))
    return "\n".join(ausgabe) + "\n"


def _archiv(einreichungen, meldende, geschaefte) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("SUBMISSION.tsv", _tsv(SUBMISSION_SPALTEN, einreichungen))
        z.writestr("REPORTINGOWNER.tsv", _tsv(OWNER_SPALTEN, meldende))
        z.writestr("NONDERIV_TRANS.tsv", _tsv(TRANS_SPALTEN, geschaefte))
    return puffer.getvalue()


def _einreichung(nummer="0000000000-24-000001", eingereicht="31-JAN-2024",
                 typ="4", ticker="AAPL", plan="0"):
    return {"ACCESSION_NUMBER": nummer, "FILING_DATE": eingereicht,
            "DOCUMENT_TYPE": typ, "ISSUERCIK": "0000320193",
            "ISSUERNAME": "APPLE INC", "ISSUERTRADINGSYMBOL": ticker,
            "AFF10B5ONE": plan}


def _meldender(nummer="0000000000-24-000001", cik="0001111111",
               name="MUSTER MAX", beziehung="Officer"):
    return {"ACCESSION_NUMBER": nummer, "RPTOWNERCIK": cik,
            "RPTOWNERNAME": name, "RPTOWNER_RELATIONSHIP": beziehung}


def _geschaeft(nummer="0000000000-24-000001", sk="1", gehandelt="29-JAN-2024",
               code="P", ad=None, stueck="100", kurs="10"):
    return {"ACCESSION_NUMBER": nummer, "NONDERIV_TRANS_SK": sk,
            "TRANS_DATE": gehandelt, "TRANS_CODE": code,
            "TRANS_ACQUIRED_DISP_CD": ad if ad is not None
            else ("A" if code == "P" else "D"),
            "TRANS_SHARES": stueck, "TRANS_PRICEPERSHARE": kurs}


# ---------------------------------------------------------------------------
# Punkt-in-Zeit: das Einreichungsdatum, nicht der Handelstag
# ---------------------------------------------------------------------------

def test_bekannt_ab_ist_das_einreichungsdatum():
    """Der Kern der Punkt-in-Zeit-Datierung dieser Familie.

    Der Meldeverzug liegt im Median bei zwei Tagen — der größte in 2024Q1
    gemessene Wert aber bei 2.332. Ein Geschäft aus dem November 2022, das im
    Januar 2024 gemeldet wird, war bis zur Meldung nicht öffentlich. Nach
    `trans_datum` datiert wäre das Look-ahead um vierzehn Monate.
    """
    daten = _archiv(
        [_einreichung(eingereicht="31-JAN-2024")],
        [_meldender()],
        [_geschaeft(gehandelt="15-NOV-2022")])
    (zeile,) = geschaefte_aus_archiv(daten)
    assert zeile["bekannt_ab"] == datetime(2024, 1, 31)
    assert zeile["trans_datum"] == datetime(2022, 11, 15)


def test_der_handelstag_bleibt_erhalten():
    """Er wird nicht zur Datierung gebraucht, aber zur Routine-Erkennung: die
    Kalendertreue nach Cohen/Malloy/Pomorski bemisst sich am HANDELSmonat."""
    daten = _archiv([_einreichung()], [_meldender()],
                    [_geschaeft(gehandelt="29-JAN-2024")])
    (zeile,) = geschaefte_aus_archiv(daten)
    assert zeile["trans_datum"].month == 1


# ---------------------------------------------------------------------------
# Was nicht in den Bestand gehört
# ---------------------------------------------------------------------------

def test_nur_form_4_keine_berichtigungen():
    """`4/A` stellt eine frühere Meldung richtig. Ohne Abgleich zählte
    dasselbe Geschäft zweimal — und ein Käufer würde zu zweien."""
    daten = _archiv(
        [_einreichung(nummer="A-1", typ="4"),
         _einreichung(nummer="A-2", typ="4/A"),
         _einreichung(nummer="A-3", typ="5")],
        [_meldender(nummer="A-1"), _meldender(nummer="A-2"),
         _meldender(nummer="A-3")],
        [_geschaeft(nummer="A-1", sk="1"), _geschaeft(nummer="A-2", sk="2"),
         _geschaeft(nummer="A-3", sk="3")])
    assert [z["accession"] for z in geschaefte_aus_archiv(daten)] == ["A-1"]


@pytest.mark.parametrize("code", ["A", "M", "F", "G", "C", "J"])
def test_nur_marktgeschaefte_zaehlen(code):
    """Eine Zuteilung (A), eine Optionsausübung (M) oder ein Steuereinbehalt
    (F) ist keine Entscheidung, zu diesem Kurs zu handeln. In 2024Q1 sind das
    zusammen mehr Zeilen als Käufe und Verkäufe zusammen."""
    daten = _archiv([_einreichung()], [_meldender()],
                    [_geschaeft(code=code, ad="A")])
    assert geschaefte_aus_archiv(daten) == []


def test_widerspruechliche_erwerbskennung_wird_verworfen():
    """Ein Kauf, der als Veräußerung ausgezeichnet ist. 61 von 32.354 Zeilen
    in 2024Q1. Welche der beiden Angaben stimmt, ist von außen nicht
    entscheidbar — also zählt die Zeile nicht."""
    daten = _archiv(
        [_einreichung(nummer="A-1"), _einreichung(nummer="A-2")],
        [_meldender(nummer="A-1"), _meldender(nummer="A-2")],
        [_geschaeft(nummer="A-1", sk="1", code="P", ad="D"),
         _geschaeft(nummer="A-2", sk="2", code="P", ad="A")])
    assert [z["accession"] for z in geschaefte_aus_archiv(daten)] == ["A-2"]


def test_universumsfilter_greift_vor_dem_aufbau():
    daten = _archiv(
        [_einreichung(nummer="A-1", ticker="AAPL"),
         _einreichung(nummer="A-2", ticker="ZZZZ")],
        [_meldender(nummer="A-1"), _meldender(nummer="A-2")],
        [_geschaeft(nummer="A-1", sk="1"), _geschaeft(nummer="A-2", sk="2")])
    assert [z["ticker"] for z in geschaefte_aus_archiv(daten, {"AAPL"})] == ["AAPL"]


# ---------------------------------------------------------------------------
# Der 10b5-1-Haken und seine vier Schreibweisen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,erwartet", [
    ("1", True), ("true", True), ("TRUE", True),
    ("0", False), ("false", False), ("False", False),
    ("", None), ("   ", None), ("vielleicht", None),
])
def test_der_10b5_1_haken_kennt_vier_schreibweisen(text, erwartet):
    """`0`, `1`, `false` und `true` stehen in denselben Daten nebeneinander —
    die SEC hat die Kodierung zwischen den Jahrgängen gewechselt. Ein
    `bool("false")` ist True und würde die Spalte still umdrehen."""
    assert _wahrheit(text) is erwartet


def test_der_haken_erreicht_das_geschaeft():
    daten = _archiv([_einreichung(plan="false")], [_meldender()],
                    [_geschaeft()])
    (zeile,) = geschaefte_aus_archiv(daten)
    assert zeile["plan_10b5_1"] is False


# ---------------------------------------------------------------------------
# Gemeinschaftsmeldungen
# ---------------------------------------------------------------------------

def test_gemeinschaftsmeldung_bleibt_eine_zeile():
    """2,2 % der Einreichungen tragen mehrere Meldende (gemessen: 1.473 von
    67.671). Je Meldendem eine Zeile anzulegen würde die Stückzahl
    vervielfachen und aus einem Käufer mehrere machen."""
    daten = _archiv(
        [_einreichung()],
        [_meldender(cik="0002222222", name="ZWEITER"),
         _meldender(cik="0001111111", name="ERSTER")],
        [_geschaeft()])
    (zeile,) = geschaefte_aus_archiv(daten)
    assert zeile["mehrere_meldende"] is True
    # Deterministisch die kleinste CIK, damit derselbe Bestand zweimal
    # aufgebaut dieselbe Person trägt.
    assert zeile["owner_cik"] == "0001111111"


# ---------------------------------------------------------------------------
# Quartalsabgrenzung
# ---------------------------------------------------------------------------

def test_quartale_umfassen_beide_raender():
    assert quartale(date(2024, 2, 1), date(2024, 7, 1)) == [
        (2024, 1), (2024, 2), (2024, 3)]


def test_quartale_beginnen_nicht_vor_dem_ersten_datensatz():
    """Vor 2006Q1 führt die SEC den Datensatz nicht. Abrufe davor wären
    vierzig 404er ohne Erkenntnis."""
    assert quartale(date(1999, 1, 1), date(2006, 6, 1))[0] == (2006, 1)


def test_quartale_laufen_ueber_den_jahreswechsel():
    assert quartale(date(2023, 12, 1), date(2024, 2, 1)) == [
        (2023, 4), (2024, 1)]


# ---------------------------------------------------------------------------
# Routine gegen opportunistisch — und zwar punkt-in-zeit
# ---------------------------------------------------------------------------

def _reihe(*eintraege):
    """(bekannt_ab, trans_datum, owner, code, wert) aus knapperen Angaben."""
    return [(bekannt, gehandelt, owner, code, wert)
            for bekannt, gehandelt, owner, code, wert in eintraege]


def test_drei_gleiche_monate_machen_eine_routine():
    """Cohen/Malloy/Pomorski: gleiche Person, gleicher Kalendermonat, drei
    aufeinanderfolgende Vorjahre. Solche Geschäfte tragen null."""
    reihen = {"AAPL": _reihe(
        (datetime(2021, 3, 5), datetime(2021, 3, 1), "P1", KAUF, 100.0),
        (datetime(2022, 3, 5), datetime(2022, 3, 1), "P1", KAUF, 100.0),
        (datetime(2023, 3, 5), datetime(2023, 3, 1), "P1", KAUF, 100.0),
    )}
    kalender = routine_kalender(reihen)
    assert ist_routine(kalender, "P1", datetime(2024, 3, 1),
                       datetime(2024, 3, 10)) is True


def test_ein_fehlendes_jahr_beendet_die_routine():
    reihen = {"AAPL": _reihe(
        (datetime(2021, 3, 5), datetime(2021, 3, 1), "P1", KAUF, 100.0),
        (datetime(2023, 3, 5), datetime(2023, 3, 1), "P1", KAUF, 100.0),
    )}
    assert ist_routine(routine_kalender(reihen), "P1", datetime(2024, 3, 1),
                       datetime(2024, 3, 10)) is False


def test_ein_anderer_monat_ist_keine_routine():
    """Die Kalendertreue ist der ganze Punkt. Wer jedes Jahr handelt, aber in
    wechselnden Monaten, handelt nach Anlass."""
    reihen = {"AAPL": _reihe(
        (datetime(2021, 3, 5), datetime(2021, 3, 1), "P1", KAUF, 100.0),
        (datetime(2022, 7, 5), datetime(2022, 7, 1), "P1", KAUF, 100.0),
        (datetime(2023, 3, 5), datetime(2023, 3, 1), "P1", KAUF, 100.0),
    )}
    assert ist_routine(routine_kalender(reihen), "P1", datetime(2024, 3, 1),
                       datetime(2024, 3, 10)) is False


def test_eine_verspaetete_meldung_macht_niemanden_rueckwirkend_zur_routine():
    """**Der Look-ahead-Test dieser Familie.**

    Alle drei Vorjahresgeschäfte liegen im richtigen Monat — aber das von
    2023 wurde erst 2025 gemeldet. Zum Auswertungszeitpunkt im März 2024 war
    es nicht bekannt, also war die Person damals nicht als Routine erkennbar.
    Wer den Kalender ohne diese Bedingung liest, verschiebt Geschäfte
    rückwirkend aus dem opportunistischen Topf — mit Wissen aus der Zukunft.
    """
    reihen = {"AAPL": _reihe(
        (datetime(2021, 3, 5), datetime(2021, 3, 1), "P1", KAUF, 100.0),
        (datetime(2022, 3, 5), datetime(2022, 3, 1), "P1", KAUF, 100.0),
        (datetime(2025, 6, 1), datetime(2023, 3, 1), "P1", KAUF, 100.0),
    )}
    kalender = routine_kalender(reihen)
    assert ist_routine(kalender, "P1", datetime(2024, 3, 1),
                       datetime(2024, 3, 10)) is False
    # DASSELBE Geschäft, später ausgewertet: jetzt liegt die Meldung von 2023
    # vor, und die Person ist als Routine erkennbar. Dass eine Einstufung vom
    # Auswertungszeitpunkt abhängt, ist kein Mangel — es IST die
    # Punkt-in-Zeit-Eigenschaft.
    assert ist_routine(kalender, "P1", datetime(2024, 3, 1),
                       datetime(2025, 7, 1)) is True


def test_ohne_person_gilt_nicht_als_routine():
    """Die vorsichtige Richtung: Nichtklassifizierbarkeit ist kein Beleg für
    Kalendertreue. So bleibt Rauschen im opportunistischen Topf, statt ein
    echtes Geschäft aus ihm zu entfernen."""
    assert ist_routine({}, None, datetime(2024, 3, 1),
                       datetime(2024, 3, 10)) is False


# ---------------------------------------------------------------------------
# Die Firmenkennzahl
# ---------------------------------------------------------------------------

def test_personen_werden_gezaehlt_nicht_geschaefte():
    """Wer im Fenster dreimal nachkauft, ist EIN Käufer. Sonst entschiede die
    Stückelung einer Order über die Kennzahl — das ist die Konstruktion von
    Lakonishok/Lee."""
    reihe = _reihe(
        (datetime(2024, 1, 5), datetime(2024, 1, 3), "P1", KAUF, 100.0),
        (datetime(2024, 1, 6), datetime(2024, 1, 4), "P1", KAUF, 100.0),
        (datetime(2024, 1, 7), datetime(2024, 1, 5), "P1", KAUF, 100.0),
    )
    kennzahl = kennzahl_vor(reihe, datetime(2024, 2, 1))
    assert kennzahl["kaeufer"] == 1
    assert kennzahl["n_geschaefte"] == 3
    assert kennzahl["npr"] == 1.0


def test_npr_ist_positiv_wenn_gekauft_wird():
    """Das Vorzeichen dieser Familie: oben ist gut. Anders als bei den
    Accruals (§2g), wo Sloans Hypothese hohe Werte als schlecht erwartet."""
    nur_kauf = kennzahl_vor(_reihe(
        (datetime(2024, 1, 5), datetime(2024, 1, 3), "P1", KAUF, 100.0),
    ), datetime(2024, 2, 1))
    nur_verkauf = kennzahl_vor(_reihe(
        (datetime(2024, 1, 5), datetime(2024, 1, 3), "P1", VERKAUF, 100.0),
    ), datetime(2024, 2, 1))
    assert nur_kauf["npr"] == 1.0
    assert nur_verkauf["npr"] == -1.0


def test_das_fenster_schliesst_vor_dem_snapshot():
    """`MIN_ABSTAND_TAGE`, aus demselben Grund wie in §2e und §2g: das
    Einreichungsdatum trägt keine Uhrzeit. Eine Meldung vom Snapshot-Tag
    könnte nach dem Kursstand liegen."""
    zeitpunkt = datetime(2024, 2, 1)
    am_selben_tag = _reihe(
        (zeitpunkt, datetime(2024, 1, 30), "P1", KAUF, 100.0))
    assert kennzahl_vor(am_selben_tag, zeitpunkt,
                        min_abstand_tage=MIN_ABSTAND_TAGE) is None


def test_alte_meldungen_fallen_aus_dem_fenster():
    zeitpunkt = datetime(2024, 7, 1)
    alt = _reihe((datetime(2023, 1, 1), datetime(2023, 1, 1), "P1", KAUF, 1.0))
    assert kennzahl_vor(alt, zeitpunkt, fenster_tage=FENSTER_TAGE) is None


def test_ohne_meldung_gibt_es_keine_kennzahl():
    """Ein Titel, über den nichts gemeldet wurde, ist NICHT dasselbe wie
    einer, bei dem Insider verkauft und nicht gekauft haben. Als „null
    Käufer" gezählt landete er in derselben Gruppe."""
    assert kennzahl_vor([], datetime(2024, 2, 1)) is None
    assert kennzahl_vor(None, datetime(2024, 2, 1)) is None


def test_die_opportunistische_zaehlung_laesst_routine_weg():
    """Drei Vorjahre im selben Monat: der Käufer zählt, aber nicht als
    opportunistisch. Ohne diese Trennung misst man laut
    Cohen/Malloy/Pomorski überwiegend Rauschen."""
    reihe = _reihe(
        (datetime(2021, 3, 5), datetime(2021, 3, 1), "P1", KAUF, 100.0),
        (datetime(2022, 3, 5), datetime(2022, 3, 1), "P1", KAUF, 100.0),
        (datetime(2023, 3, 5), datetime(2023, 3, 1), "P1", KAUF, 100.0),
        (datetime(2024, 3, 5), datetime(2024, 3, 1), "P1", KAUF, 100.0),
    )
    kalender = routine_kalender({"AAPL": reihe})
    kennzahl = kennzahl_vor(reihe, datetime(2024, 4, 1), kalender)
    assert kennzahl["kaeufer"] == 1
    assert kennzahl["opportunistische_kaeufer"] == 0


# ---------------------------------------------------------------------------
# Gruppen und Vorzeichen der Auswertung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("anzahl,erwartet", [
    (0, GRUPPE_KEIN_KAUF), (1, GRUPPE_EIN_KAUF),
    (CLUSTER_AB, GRUPPE_CLUSTER), (9, GRUPPE_CLUSTER),
])
def test_kaeufergruppen(anzahl, erwartet):
    assert kaeufergruppe(anzahl) == erwartet


@pytest.mark.parametrize("rang,erwartet", [
    (0.0, 1), (19.9, 1), (20.0, 2), (99.9, QUANTILE), (100.0, QUANTILE),
])
def test_quintilgrenzen(rang, erwartet):
    assert quintil(rang) == erwartet


def test_der_spread_ist_q5_minus_q1():
    """**Umgekehrt zu §2g.** Dort ist unten gut (Sloan), hier oben. Ein
    verwechseltes Vorzeichen liest einen bestätigten Befund als Widerlegung —
    genau die Fußangel, vor der `accruals._spread` warnt."""
    zeilen = [{"quintil": 1, "markt_trefferquote": 45.0},
              {"quintil": QUANTILE, "markt_trefferquote": 52.0}]
    assert _spread(zeilen) == 7.0


def test_der_cluster_vorsprung_ist_cluster_minus_kein_kauf():
    zeilen = [{"gruppe": GRUPPE_KEIN_KAUF, "markt_trefferquote": 47.0},
              {"gruppe": GRUPPE_EIN_KAUF, "markt_trefferquote": 48.0},
              {"gruppe": GRUPPE_CLUSTER, "markt_trefferquote": 53.0}]
    assert _cluster_vorsprung(zeilen) == 6.0


def test_fehlende_gruppen_ergeben_keinen_vorsprung():
    """Eine Gruppe unter `MIN_STICHPROBE` trägt keine Trefferquote. Dann darf
    auch kein Spread entstehen — eine Zahl gegen None wäre eine Aussage ohne
    Deckung."""
    assert _cluster_vorsprung(
        [{"gruppe": GRUPPE_KEIN_KAUF, "markt_trefferquote": 47.0},
         {"gruppe": GRUPPE_CLUSTER, "markt_trefferquote": None}]) is None
    assert _spread([{"quintil": 1, "markt_trefferquote": 45.0}]) is None
