"""
services/kurshistorie.py — Die Kursreihe als eigener Bestand (BC-04, Schritt 1).

**Warum.** Der Backfill lädt je Ticker eine OHLCV-Reihe, spielt sie ab und
verwirft sie. Was im Snapshot landet, ist nur die *Deutung* der Reihe: +1 oder
−1 je Indikatorrichtung. Damit war jede spätere Frage, die eine andere
Auflösung oder eine andere Kennzahl braucht, ein neuer Durchlauf mit neuen
Abrufen — und deshalb ließen sich von acht Instrumenten der Einstiegsanalyse
nur zwei nachträglich stetig auswerten (§2h).

Dieses Modul hält die Reihe fest. Danach ist eine andere Schwelle, ein neuer
Indikator, echtes Volumen oder eine Tagesspanne eine *Abfrage* — kein Backfill.

**Reihen werden immer als Ganzes geschrieben, nie zeilenweise ergänzt.**
Das ist die zentrale Entscheidung dieses Moduls und kein Implementierungsdetail.
yfinance liefert split- und dividendenbereinigte Kurse, und die Bereinigung
bezieht sich auf den Zeitpunkt des Abrufs: nach einem späteren Split trägt
dieselbe historische Zeile einen anderen Wert. Zwei Zeilen aus verschiedenen
Abrufen sind damit nicht vergleichbar, und ein Verhältnis zwischen ihnen ist
kein Kursverhältnis, sondern ein Split-Artefakt.

`reihe_speichern()` ersetzt deshalb den vorhandenen Bestand eines Tickers
vollständig. Eine gespeicherte Reihe trägt genau eine Anpassungsbasis, und
`geladen_am` sagt, welche. Genau diese Eigenschaft mussten
`auswertung/momentum.py` und `services/stetige_indikatoren.py` bisher aus der
gemeinsamen Herkunft der Snapshot-Kurse *herleiten* — hier ist sie zugesichert.

**Keine Abrufe.** Dieses Modul lädt nichts. Es bekommt die Reihe von dem, der
sie ohnehin schon geholt hat (der Backfill), und legt sie ab. Damit kostet der
Nachtrag keine einzige zusätzliche Anfrage.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import KursHistorie

logger = logging.getLogger(__name__)


# Spaltennamen, wie yfinance / pandas_datareader sie liefern.
_SPALTEN = ("Open", "High", "Low", "Close", "Volume")


def _naiv(zeitpunkt) -> Optional[datetime]:
    """Wandelt einen Zeitstempel in ein zeitzonenloses `datetime`.

    SQLite speichert keine Zeitzone. Eine tz-bewusste Reihe (yfinance liefert
    US-Ticker in `America/New_York`) und eine naive würden sonst beim Vergleich
    mit `snapshot_zeitpunkt` um Stunden auseinanderliegen — bei einem Fenster
    von 280 Tagen fällt das nicht auf, bei einem Tagesabstand schon.
    """
    if zeitpunkt is None:
        return None
    try:
        wert = (zeitpunkt.to_pydatetime()
                if hasattr(zeitpunkt, "to_pydatetime") else zeitpunkt)
    except Exception:
        return None
    if not isinstance(wert, datetime):
        return None
    return wert.replace(tzinfo=None) if wert.tzinfo is not None else wert


def _zahl(wert) -> Optional[float]:
    """Float oder None. NaN zählt als None — nicht als Wert null."""
    if wert is None:
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if zahl != zahl else zahl  # NaN != NaN


def zeilen_aus_dataframe(hist) -> list[tuple]:
    """Zerlegt einen OHLCV-DataFrame in (datum, o, h, l, c, v)-Tupel.

    Zeilen ohne Schlusskurs entfallen: ohne Kurs ist es keine Beobachtung, und
    `schluss` ist die einzige nicht-nullbare Spalte der Tabelle. Fehlende
    Einzelwerte in O/H/L/V bleiben dagegen erhalten — ein Handelsplatz ohne
    Volumenmeldung ist ein Normalfall, kein Fehler.
    """
    if hist is None or getattr(hist, "empty", True):
        return []

    vorhanden = {s: (s in hist.columns) for s in _SPALTEN}
    if not vorhanden.get("Close"):
        logger.warning("Kurshistorie: DataFrame ohne Spalte 'Close' — übersprungen.")
        return []

    zeilen: list[tuple] = []
    for index, reihe in hist.iterrows():
        datum = _naiv(index)
        schluss = _zahl(reihe.get("Close"))
        if datum is None or schluss is None:
            continue
        zeilen.append((
            datum,
            _zahl(reihe.get("Open")) if vorhanden.get("Open") else None,
            _zahl(reihe.get("High")) if vorhanden.get("High") else None,
            _zahl(reihe.get("Low")) if vorhanden.get("Low") else None,
            schluss,
            _zahl(reihe.get("Volume")) if vorhanden.get("Volume") else None,
        ))
    return zeilen


def zeilen_speichern(db: Session, ticker: str, zeilen: Sequence[tuple],
                     angepasst: bool = True, quelle: str = "yfinance",
                     geladen_am: Optional[datetime] = None) -> int:
    """Ersetzt die gespeicherte Reihe eines Tickers vollständig.

    Args:
        zeilen: (datum, eroeffnung, hoch, tief, schluss, volumen)-Tupel.
        angepasst: ob die Kurse split-/dividendenbereinigt sind.

    Warum ersetzen und nicht ergänzen: siehe Modul-Docstring. Ein Mischbestand
    aus zwei Abrufen trüge zwei Anpassungsbasen, und das wäre von außen nicht
    mehr erkennbar.

    Eine leere `zeilen`-Folge löscht **nicht**. Ein fehlgeschlagener Abruf
    würde sonst einen vorhandenen Bestand vernichten — der teuerste denkbare
    Ausgang, und er darf nicht der stille Normalfall eines leeren Ergebnisses
    sein.

    Returns:
        Anzahl geschriebener Zeilen.
    """
    if not ticker:
        return 0
    if not zeilen:
        logger.info("Kurshistorie %s: keine Zeilen übergeben — Bestand bleibt.",
                    ticker)
        return 0

    zeitpunkt = geladen_am or datetime.utcnow()

    db.query(KursHistorie).filter(KursHistorie.ticker == ticker).delete(
        synchronize_session=False)

    # Doppelte Handelstage kommen vor (Zeitzonenwechsel, doppelte Zeilen aus
    # dem Abruf); die Unique-Bedingung würde den ganzen Block zurückrollen.
    # Der letzte Wert je Tag gewinnt.
    je_datum: dict[datetime, tuple] = {z[0]: z for z in zeilen}

    db.bulk_insert_mappings(KursHistorie, [
        {
            "ticker": ticker,
            "datum": datum,
            "eroeffnung": eroeffnung,
            "hoch": hoch,
            "tief": tief,
            "schluss": schluss,
            "volumen": volumen,
            "angepasst": angepasst,
            "quelle": quelle,
            "geladen_am": zeitpunkt,
        }
        for datum, eroeffnung, hoch, tief, schluss, volumen
        in sorted(je_datum.values(), key=lambda z: z[0])
    ])
    return len(je_datum)


def reihe_speichern(db: Session, ticker: str, hist,
                    angepasst: bool = True, quelle: str = "yfinance") -> int:
    """Speichert einen OHLCV-DataFrame als Reihe. Siehe `zeilen_speichern`."""
    return zeilen_speichern(db, ticker, zeilen_aus_dataframe(hist),
                            angepasst=angepasst, quelle=quelle)


def reihe_lesen(db: Session, ticker: str, von: Optional[datetime] = None,
                bis: Optional[datetime] = None) -> list[KursHistorie]:
    """Die Reihe eines Tickers, nach Datum aufsteigend.

    `bis` ist einschließend: der Kurs des Stichtags selbst ist zu diesem
    Zeitpunkt bekannt und gehört in jedes rückblickende Fenster. Dieselbe
    Festlegung wie in `services/stetige_indikatoren.py`.
    """
    query = db.query(KursHistorie).filter(KursHistorie.ticker == ticker)
    if von is not None:
        query = query.filter(KursHistorie.datum >= von)
    if bis is not None:
        query = query.filter(KursHistorie.datum <= bis)
    return query.order_by(KursHistorie.datum.asc()).all()


def schlusskurs_paare(db: Session, ticker: str,
                      bis: Optional[datetime] = None) -> list[tuple[datetime, float]]:
    """(Zeitpunkt, Schlusskurs)-Paare, aufsteigend.

    Genau die Form, die `services/stetige_indikatoren.gleitender_mittelwert()`
    erwartet. Der Unterschied zur bisherigen Quelle ist die Auflösung: dort
    stammten die Stützstellen aus den Snapshots selbst — im Median acht Tage
    Abstand, rund 35 Punkte in einem 280-Tage-Fenster statt 200. Hier ist jeder
    Handelstag vorhanden, die genäherte SMA wird zur exakten.
    """
    return [(z.datum, z.schluss) for z in reihe_lesen(db, ticker, bis=bis)]


def bestand(db: Session, ticker: Optional[str] = None) -> dict:
    """Abdeckung des Kursbestands — Zeilen, Ticker, Zeitraum.

    Ohne `ticker` über den gesamten Bestand. Gedacht als Kontrollblick nach
    einem Durchlauf: eine Lücke ist hier sichtbar, bevor eine Auswertung
    darauf aufsetzt.
    """
    query = db.query(
        func.count(KursHistorie.id),
        func.count(func.distinct(KursHistorie.ticker)),
        func.min(KursHistorie.datum),
        func.max(KursHistorie.datum),
    )
    if ticker:
        query = query.filter(KursHistorie.ticker == ticker)
    zeilen, tickers, von, bis = query.one()
    return {
        "zeilen": zeilen or 0,
        "ticker": tickers or 0,
        "von": von,
        "bis": bis,
    }


def fehlende_ticker(db: Session, tickers: Iterable[str]) -> list[str]:
    """Welche der übergebenen Ticker (noch) keine Reihe im Bestand haben."""
    gewuenscht = [t for t in tickers if t]
    if not gewuenscht:
        return []
    vorhanden = {
        t for (t,) in db.query(KursHistorie.ticker)
        .filter(KursHistorie.ticker.in_(gewuenscht))
        .distinct().all()
    }
    return [t for t in gewuenscht if t not in vorhanden]
