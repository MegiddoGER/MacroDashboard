"""
tests/test_scoring_gate.py — Der Oszillator steuert keine Empfehlung mehr.

Sichert die beiden Entscheidungen, die Score 2.1.0 und 2.2.0 ausmachen:
weder wird eine hohe Confidence ohne Oszillator-Deckung herabgestuft, noch wird
eine niedrige Confidence mit tragendem Oszillator befördert. Beide Zweige sind
entfallen, weil ihr Vorsprung absolut gemessen war und gegen den
Vergleichsindex verschwand (CONTEXT.md §2a/§2b).

Der Test hängt bewusst an `score_label`, nicht an einem Flag: das ist die
Größe, die beim Nutzer als Empfehlung ankommt. Die Flags bleiben gesetzt — die
Konstellationen werden weiter gemessen, sie steuern nur nichts mehr.
"""

from services.scoring import SCORE_VERSION, ScoreResult, _finalize_score


def _ergebnis(trend: int, oszillator: int) -> ScoreResult:
    """Ein ScoreResult mit nur zwei Kategorien, je zur Hälfte gewichtet.

    Damit ist die Confidence direkt steuerbar: trend −1 und oszillator +1
    heben sich auf und ergeben 50, also den Bereich unterhalb von 60, in dem
    die Beförderung früher gegriffen hat.
    """
    return ScoreResult(
        cat_scores={"trend": trend, "oscillator": oszillator},
        cat_max={"trend": 1, "oscillator": 1},
        weights={"trend": 0.5, "oscillator": 0.5},
    )


def _checkliste_indikatoren(result: ScoreResult) -> list:
    return [e.get("Indikator") for e in result.checklist]


# ---------------------------------------------------------------------------
# 2.2.0 — keine Beförderung mehr
# ---------------------------------------------------------------------------

def test_niedrige_confidence_mit_oszillator_wird_nicht_mehr_befoerdert():
    """Die klassische Mean-Reversion-Lage: überverkauft gegen den Trend.

    Bis 2.1.0 wurde daraus "Mean-Reversion-Setup" — eine Empfehlung, die die
    Confidence selbst nicht hergab. Marktbereinigt trägt sie nichts.
    """
    r = _ergebnis(trend=-1, oszillator=1)
    _finalize_score(r)

    assert r.confidence == 50.0
    assert "Mean-Reversion" not in r.score_label
    assert r.score_label == "Neutral "


def test_die_konstellation_wird_weiter_gemessen():
    """Erkannt und angezeigt — nur ohne Wirkung auf die Empfehlung."""
    r = _ergebnis(trend=-1, oszillator=1)
    _finalize_score(r)

    assert r.signals["mean_reversion_setup"] is True
    assert r.signals["mean_reversion_gegen_trend"] is True
    assert r.signals["oscillator_gate_offen"] is True
    assert "Mean-Reversion-Konstellation" in _checkliste_indikatoren(r)


def test_ohne_tragenden_oszillator_keine_konstellation():
    r = _ergebnis(trend=-1, oszillator=-1)
    _finalize_score(r)

    assert r.signals["mean_reversion_setup"] is False
    assert "Mean-Reversion-Konstellation" not in _checkliste_indikatoren(r)


# ---------------------------------------------------------------------------
# 2.1.0 — kein Sperren mehr
# ---------------------------------------------------------------------------

def test_hohe_confidence_ohne_oszillator_wird_nicht_gesperrt():
    """Trend und Volumen allein dürfen eine Kaufempfehlung tragen.

    Bis 2.0.0 wurde hier auf "Kein Einstieg" herabgestuft, ohne dass die
    gesperrte Gruppe je schlechter abgeschnitten hätte.
    """
    r = _ergebnis(trend=1, oszillator=-1)
    r.cat_scores["oscillator"] = -1
    _finalize_score(r)

    assert r.confidence == 50.0
    assert r.score_label != "Kein Einstieg"


def test_fehlende_oszillator_deckung_bleibt_als_hinweis_sichtbar():
    """Bei hoher Confidence ohne Oszillator: Hinweis, keine Herabstufung."""
    r = ScoreResult(
        cat_scores={"trend": 1, "oscillator": 0},
        cat_max={"trend": 1, "oscillator": 1},
        weights={"trend": 0.9, "oscillator": 0.1},
    )
    _finalize_score(r)

    assert r.confidence >= 60
    assert r.signals["oscillator_gate_offen"] is False
    assert "Oszillator-Deckung" in _checkliste_indikatoren(r)
    assert r.score_label != "Kein Einstieg"


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def test_score_version_ist_erhoeht():
    """Aus denselben Kursdaten entsteht eine andere Empfehlung — das verlangt
    laut Konvention eine neue Score-Version, damit Snapshots zweier
    Bewertungssysteme nicht gemeinsam gemittelt werden."""
    assert SCORE_VERSION == "2.2.0"
