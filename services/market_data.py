"""
data.py — Datenabruf-Funktionen (yfinance).

Jede Funktion gibt bei Fehlern None zurück und loggt eine Warnung.
"""

import warnings
import os
import pandas as pd
import numpy as np
import yfinance as yf


# ---------------------------------------------------------------------------
# Einzelner Kurs + Vortagesschluss
# ---------------------------------------------------------------------------

def get_quote(ticker: str) -> dict | None:
    """Holt den aktuellen Preis und die tägliche Veränderung.

    Rückgabe: {"price": float, "change_pct": float} oder None.
    """
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d")
        if hist.empty or len(hist) < 2:
            return None
        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        change_pct = ((current - prev) / prev) * 100 if prev else 0.0
        return {"price": round(current, 2), "change_pct": round(change_pct, 2)}
    except Exception as exc:
        warnings.warn(f"get_quote({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Historische Daten (OHLCV)
# ---------------------------------------------------------------------------

def get_history(ticker: str, period: str = "1y") -> pd.DataFrame | None:
    """Gibt ein OHLCV-DataFrame zurück oder None bei Fehler."""
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=period)
        if hist.empty:
            return None
        return hist
    except Exception as exc:
        warnings.warn(f"get_history({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Batch-Download für Watchlist
# ---------------------------------------------------------------------------

def get_multi_quotes(tickers: list[str]) -> pd.DataFrame | None:
    """Lädt Kursdaten für mehrere Ticker und fasst sie zusammen.

    Rückgabe: DataFrame mit Spalten [Ticker, Kurs (€), Veränderung %, RSI (14)].
    """
    try:
        records = []
        from services.technical import calc_rsi

        for t in tickers:
            t = t.strip().upper()
            if not t:
                continue
            hist = get_history(t, period="6mo")
            if hist is None or hist.empty or len(hist) < 2:
                records.append({"Ticker": t, "Kurs (€)": None,
                                "Veränderung %": None, "RSI (14)": None})
                continue
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            chg = round(((current - prev) / prev) * 100, 2) if prev else 0.0
            rsi_series = calc_rsi(hist["Close"], 14)
            rsi_val = (round(float(rsi_series.dropna().iloc[-1]), 1)
                       if rsi_series is not None and not rsi_series.dropna().empty
                       else None)
            records.append({
                "Ticker": t,
                "Kurs (€)": round(current, 2),
                "Veränderung %": chg,
                "RSI (14)": rsi_val,
            })
        if not records:
            return None
        return pd.DataFrame(records)
    except Exception as exc:
        warnings.warn(f"get_multi_quotes: {exc}")
        return None


# ---------------------------------------------------------------------------
# Detail-Daten für Aktien-Analyse
# ---------------------------------------------------------------------------


_cik_cache = {}

def _get_cik_for_ticker(ticker: str) -> str | None:
    """Holt die CIK für einen US-Ticker via SEC EDGAR company_tickers.json."""
    t = ticker.upper()
    if t in _cik_cache:
        return _cik_cache[t]
        
    import urllib.request
    import json
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "MacroDashboard contact@example.com"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            
        for item in data.values():
            sym = item.get("ticker", "").upper()
            cik = str(item.get("cik_str")).zfill(10)
            _cik_cache[sym] = cik
            
        return _cik_cache.get(t)
    except Exception as exc:
        import warnings
        warnings.warn(f"_get_cik_for_ticker({ticker}): {exc}")
        return None

def get_stock_details(ticker: str) -> dict | None:
    """Sammelt umfangreiche Daten für die Einzelaktien-Analyse.

    Rückgabe: Dict mit keys: info, hist_1y, hist_5y, oder None.
    """
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        # Verschiedene Zeiträume für die UI-Filter laden
        hist_1d = tk.history(period="1d", interval="5m")
        hist_1w = tk.history(period="5d", interval="15m")
        hist_1m = tk.history(period="1mo", interval="1h")
        hist_ytd = tk.history(period="ytd", interval="1d")
        hist_1y = tk.history(period="1y", interval="1d")
        hist_5y = tk.history(period="5y", interval="1d")
        hist_max = tk.history(period="max", interval="1wk")
        hist_monthly = tk.history(period="max", interval="1mo")
        
        if hist_1y.empty:
            return None

        # Statistiken berechnen
        from services.technical import calc_rsi
        close = hist_1y["Close"]
        rsi = calc_rsi(close, 14)

        # Gleitende Durchschnitte
        sma_20 = close.rolling(20).mean()
        sma_50 = close.rolling(50).mean()
        sma_200 = close.rolling(200).mean()

        # Volatilität (annualisiert)
        returns = close.pct_change().dropna()
        volatility = float(returns.std() * np.sqrt(252) * 100) if len(returns) > 1 else 0.0

        # 52-Wochen-Range
        high_52w = float(close.max())
        low_52w = float(close.min())
        current_price = float(close.iloc[-1])

        stats = {
            "current_price": round(current_price, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "volatility": round(volatility, 1),
            "rsi": round(float(rsi.dropna().iloc[-1]), 1) if rsi is not None and not rsi.dropna().empty else None,
            "sma_20": round(float(sma_20.dropna().iloc[-1]), 2) if not sma_20.dropna().empty else None,
            "sma_50": round(float(sma_50.dropna().iloc[-1]), 2) if not sma_50.dropna().empty else None,
            "sma_200": round(float(sma_200.dropna().iloc[-1]), 2) if not sma_200.dropna().empty else None,
            "avg_volume": int(hist_1y["Volume"].mean()) if "Volume" in hist_1y.columns else 0,
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "—"),
            "market_cap": info.get("marketCap", None),
            "pe_ratio": info.get("trailingPE", None),
            "dividend_yield": info.get("dividendYield", None),
        }

        # Nächste Quartalszahlen (Earnings Date)
        try:
            cal = tk.calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                ed = cal["Earnings Date"]
                if isinstance(ed, list) and ed:
                    stats["earnings_date"] = str(ed[0])
                elif ed is not None:
                    stats["earnings_date"] = str(ed)
                else:
                    stats["earnings_date"] = None
            else:
                stats["earnings_date"] = None
        except Exception:
            stats["earnings_date"] = None

        # Finanzdaten (Umsatz, EBITDA, Nettogewinn)
        financials_data = []
        try:
            import urllib.request
            import json
            import datetime
            
            cik = _get_cik_for_ticker(ticker)
            sec_data_found = False
            
            if cik:
                # Versuch über SEC EDGAR
                url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
                req = urllib.request.Request(url, headers={"User-Agent": "MacroDashboard contact@example.com"})
                try:
                    with urllib.request.urlopen(req, timeout=15) as r:
                        facts = json.loads(r.read())
                        
                    us_gaap = facts.get("facts", {}).get("us-gaap", {})
                    
                    # Revenue
                    rev_keys = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]
                    rev_data = []
                    for k in rev_keys:
                        if k in us_gaap:
                            rev_data = us_gaap[k].get("units", {}).get("USD", [])
                            if rev_data:
                                break
                                
                    # Net Income
                    ni_keys = ["NetIncomeLoss"]
                    ni_data = []
                    for k in ni_keys:
                        if k in us_gaap:
                            ni_data = us_gaap[k].get("units", {}).get("USD", [])
                            if ni_data:
                                break
                                
                    # Quartalszahlen extrahieren (nur solche mit frame z.B. CY2024Q1)
                    q_rev = {r.get("frame"): r for r in rev_data if r.get("frame") and len(r.get("frame")) == 8 and r.get("frame").startswith("CY") and "Q" in r.get("frame")}
                    q_ni = {r.get("frame"): r for r in ni_data if r.get("frame") and len(r.get("frame")) == 8 and r.get("frame").startswith("CY") and "Q" in r.get("frame")}
                    
                    # Kombinieren nach Frame
                    frames = sorted(list(set(q_rev.keys()) | set(q_ni.keys())))
                    
                    extracted_data = {}
                    for f in frames:
                        r_val = q_rev.get(f, {}).get("val")
                        ni_val = q_ni.get(f, {}).get("val")
                        end_date_str = q_rev.get(f, {}).get("end") or q_ni.get(f, {}).get("end")
                        if end_date_str:
                            try:
                                end_date = datetime.date.fromisoformat(end_date_str)
                                extracted_data[f] = {
                                    "frame": f,
                                    "date": pd.Timestamp(end_date),
                                    "year": f, # We use frame notation like CY2024Q1 as the 'year' indicator for UI
                                    "revenue": r_val,
                                    "net_income": ni_val,
                                    "ebitda": None # SEC usually doesn't provide standard EBITDA
                                }
                            except ValueError:
                                pass
                                
                    # Nach Datum sortieren (älteste zuerst für YoY)
                    sorted_frames = sorted(extracted_data.keys(), key=lambda x: extracted_data[x]["date"])
                    
                    # YoY berechnen
                    for i, f in enumerate(sorted_frames):
                        # Finde das Frame aus dem Vorjahr: CY2024Q1 -> CY2023Q1
                        year = int(f[2:6])
                        q = f[6:]
                        prev_f = f"CY{year-1}{q}"
                        
                        curr = extracted_data[f]
                        prev = extracted_data.get(prev_f)
                        
                        rev_yoy = None
                        ni_yoy = None
                        
                        if prev:
                            if curr["revenue"] is not None and prev["revenue"] and prev["revenue"] != 0:
                                rev_yoy = ((curr["revenue"] - prev["revenue"]) / abs(prev["revenue"])) * 100
                            if curr["net_income"] is not None and prev["net_income"] and prev["net_income"] != 0:
                                ni_yoy = ((curr["net_income"] - prev["net_income"]) / abs(prev["net_income"])) * 100
                                
                        curr["revenue_yoy"] = rev_yoy
                        curr["net_income_yoy"] = ni_yoy
                        curr["ebitda_yoy"] = None
                        
                        financials_data.append(curr)
                        
                    if financials_data:
                        # Für die Anzeige umdrehen (neueste zuerst)
                        financials_data.reverse()
                        sec_data_found = True
                        
                except Exception as sec_exc:
                    warnings.warn(f"SEC EDGAR Fehler für {ticker}: {sec_exc}")
            
            # Fallback auf yfinance quarterly_financials
            if not sec_data_found:
                fin = tk.quarterly_financials
                if not fin.empty:
                    cols = list(fin.columns)
                    cols.sort() # Älteste zuerst
                    
                    prev_data = {} # Q -> (revenue, ebitda, ni)
                    
                    for col in cols:
                        col_data = fin[col]
                        
                        rev = float(col_data.get("Total Revenue", 0)) if "Total Revenue" in col_data and not pd.isna(col_data.get("Total Revenue")) else None
                        ebitda = float(col_data.get("EBITDA", 0)) if "EBITDA" in col_data and not pd.isna(col_data.get("EBITDA")) else None
                        ni = float(col_data.get("Net Income", 0)) if "Net Income" in col_data and not pd.isna(col_data.get("Net Income")) else None
                        
                        year = col.year if hasattr(col, "year") else str(col)[:4]
                        month = col.month if hasattr(col, "month") else 1
                        q = (month - 1) // 3 + 1
                        q_str = f"Q{q}"
                        
                        prev_rev, prev_ebitda, prev_ni = prev_data.get(q_str, (None, None, None))
                        
                        rev_yoy = ((rev - prev_rev) / abs(prev_rev) * 100) if rev is not None and prev_rev else None
                        ebitda_yoy = ((ebitda - prev_ebitda) / abs(prev_ebitda) * 100) if ebitda is not None and prev_ebitda else None
                        ni_yoy = ((ni - prev_ni) / abs(prev_ni) * 100) if ni is not None and prev_ni else None
                        
                        financials_data.append({
                            "year": f"{year} {q_str}", # Anzeige z.B. 2024 Q1
                            "date": col,
                            "revenue": rev,
                            "revenue_yoy": rev_yoy,
                            "ebitda": ebitda,
                            "ebitda_yoy": ebitda_yoy,
                            "net_income": ni,
                            "net_income_yoy": ni_yoy,
                        })
                        
                        prev_data[q_str] = (rev, ebitda, ni)
                        
                    # Für die Anzeige umdrehen (neueste zuerst)
                    financials_data.reverse()

        except Exception as exc:
            warnings.warn(f"get_stock_details/financials({ticker}): {exc}")

        return {
            "info": info,
            "stats": stats,
            "hist_1d": hist_1d,
            "hist_1w": hist_1w,
            "hist_1m": hist_1m,
            "hist_ytd": hist_ytd,
            "hist_1y": hist_1y,
            "hist_5y": hist_5y,
            "hist_max": hist_max,
            "hist_monthly": hist_monthly,
            "rsi_series": rsi,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "returns": returns,
            "financials": financials_data,
        }
    except Exception as exc:
        warnings.warn(f"get_stock_details({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Yield-Curve-Spread (10Y – Short)
# ---------------------------------------------------------------------------

def get_yield_spread(period: str = "2y") -> pd.DataFrame | None:
    """Berechnet den 10Y-Short-Yield-Spread."""
    try:
        tnx = yf.Ticker("^TNX").history(period=period)
        irx = yf.Ticker("^IRX").history(period=period)
        if tnx.empty or irx.empty:
            return None
        spread = pd.DataFrame({
            "10Y": tnx["Close"],
            "Short": irx["Close"],
        }).dropna()
        spread["Spread"] = spread["10Y"] - spread["Short"]
        return spread
    except Exception as exc:
        warnings.warn(f"get_yield_spread: {exc}")
        return None


# ---------------------------------------------------------------------------
# VIX + S&P 500 (für Fear & Greed)
# ---------------------------------------------------------------------------

def get_vix_value() -> float | None:
    """Gibt den aktuellen VIX-Schlusskurs zurück."""
    try:
        hist = yf.Ticker("^VIX").history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as exc:
        warnings.warn(f"get_vix_value: {exc}")
        return None


def get_sp500_close_series(period: str = "2y") -> pd.Series | None:
    """Gibt die S&P-500-Schlusskurse zurück (^GSPC)."""
    try:
        hist = yf.Ticker("^GSPC").history(period=period)
        if hist.empty:
            return None
        return hist["Close"]
    except Exception as exc:
        warnings.warn(f"get_sp500_close_series: {exc}")
        return None


def get_gold_close_series(period: str = "2y") -> pd.Series | None:
    """Gibt die Gold-Schlusskurse zurück (GC=F)."""
    try:
        hist = yf.Ticker("GC=F").history(period=period)
        if hist.empty:
            return None
        return hist["Close"]
    except Exception as exc:
        warnings.warn(f"get_gold_close_series: {exc}")
        return None


# ---------------------------------------------------------------------------
# Deutsche Inflationsrate (FRED: FPCPITOTLZGDEU)
# ---------------------------------------------------------------------------

def get_german_inflation() -> pd.DataFrame | None:
    """Holt die deutsche Inflationsrate (HVPI) von Eurostat.

    Quelle: Eurostat HICP — monatliche Änderungsrate ggü. Vorjahr.
    Daten stammen vom Statistischen Bundesamt (Destatis),
    bereitgestellt über die Eurostat-API.
    Fallback: FRED (ältere Daten).
    """
    # 1. Eurostat SDMX API (aktuellste Daten)
    try:
        import urllib.request
        import json

        url = ("https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/"
               "data/prc_hicp_manr/M.RCH_A.CP00.DE?format=JSON&lang=de")
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        times = data["dimension"]["time"]["category"]["index"]
        values = data["value"]

        records = []
        for time_str, idx in times.items():
            val = values.get(str(idx))
            if val is not None:
                records.append({"Datum": pd.to_datetime(time_str, format="%Y-%m"),
                                "Inflation %": float(val)})
        if records:
            df = pd.DataFrame(records).set_index("Datum").sort_index()
            # Nur Daten ab 2015 für bessere Lesbarkeit
            return df[df.index >= "2015-01-01"]
    except Exception as exc:
        warnings.warn(f"Eurostat-API fehlgeschlagen: {exc}")

    # 2. Fallback: FRED
    try:
        from pandas_datareader import data as pdr
        df = pdr.DataReader("FPCPITOTLZGDEU", "fred", start="2015-01-01")
        if not df.empty:
            df.columns = ["Inflation %"]
            return df
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Aktienverzeichnis (NASDAQ FTP + SEC EDGAR + lokaler Cache)
# ---------------------------------------------------------------------------

def get_stock_listings() -> pd.DataFrame | None:
    """Lädt alle handelbaren Aktien (NASDAQ, NYSE, AMEX, OTC).

    Quellen: nasdaqtrader.com FTP + SEC EDGAR.
    Cached das Ergebnis als lokale CSV-Datei (Refresh alle 24h).
    Rückgabe: DataFrame mit Spalten [Kürzel, Name, Börse].
    """
    import urllib.request
    import urllib.error
    import json

    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(_project_root, "data", "stock_listings.csv")

    # Nur neu laden falls Cache älter als 24h oder nicht vorhanden
    cache_fresh = False
    if os.path.exists(csv_path):
        import time
        age_hours = (time.time() - os.path.getmtime(csv_path)) / 3600
        cache_fresh = age_hours < 24

    if not cache_fresh:
        try:
            records = {}  # sym -> (name, exchange)
            headers = {"User-Agent": "Mozilla/5.0"}

            # 1. NASDAQ-gelistete Aktien
            req = urllib.request.Request(
                "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                headers=headers,
            )
            r = urllib.request.urlopen(req, timeout=15)
            for line in r.read().decode("utf-8").strip().split("\n")[1:]:
                parts = line.split("|")
                if len(parts) >= 2:
                    sym = parts[0].strip()
                    name = parts[1].strip()
                    if sym and name and "File Creation" not in sym:
                        records[sym] = (name, "NASDAQ")

            # 2. NYSE/AMEX-gelistete Aktien
            req = urllib.request.Request(
                "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
                headers=headers,
            )
            r = urllib.request.urlopen(req, timeout=15)
            ex_map = {"A": "AMEX", "N": "NYSE", "P": "NYSE ARCA",
                      "Z": "BATS", "V": "IEX"}
            for line in r.read().decode("utf-8").strip().split("\n")[1:]:
                parts = line.split("|")
                if len(parts) >= 3:
                    sym = parts[0].strip()
                    name = parts[1].strip()
                    ex = ex_map.get(parts[2].strip(), parts[2].strip())
                    if sym and name and "File Creation" not in sym and sym not in records:
                        records[sym] = (name, ex)

            # 3. OTC-gelistete Aktien (NASDAQ FTP)
            try:
                req = urllib.request.Request(
                    "https://www.nasdaqtrader.com/dynamic/SymDir/otclist.txt",
                    headers=headers,
                )
                r = urllib.request.urlopen(req, timeout=15)
                for line in r.read().decode("utf-8").strip().split("\n")[1:]:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        sym = parts[0].strip()
                        name = parts[1].strip()
                        if sym and name and "File Creation" not in sym and sym not in records:
                            records[sym] = (name, "OTC")
            except Exception:
                pass

            # 4. SEC EDGAR — ergänzt OTC/Pink-Sheet-Titel
            try:
                req = urllib.request.Request(
                    "https://www.sec.gov/files/company_tickers.json",
                    headers={"User-Agent": "MacroDashboard contact@example.com"},
                )
                r = urllib.request.urlopen(req, timeout=15)
                sec_data = json.loads(r.read())
                for entry in sec_data.values():
                    sym = entry.get("ticker", "").strip()
                    name = entry.get("title", "").strip()
                    if sym and name and sym not in records:
                        records[sym] = (name, "OTC")
            except Exception:
                pass

            if records:
                rows = [{"Kürzel": s, "Name": n, "Börse": e}
                        for s, (n, e) in sorted(records.items())]
                df = pd.DataFrame(rows).reset_index(drop=True)
                try:
                    df.to_csv(csv_path, index=False, encoding="utf-8")
                except Exception:
                    pass
                return df
        except Exception as exc:
            warnings.warn(f"get_stock_listings: {exc}")

    # Fallback: lokaler Cache
    if os.path.exists(csv_path):
        try:
            return pd.read_csv(csv_path, encoding="utf-8")
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Korrelationsmatrix (für Analyse-Seite)
# ---------------------------------------------------------------------------

# S&P 500 Sektor-ETFs (US)
SECTOR_ETFS_US = {
    "XLK": "Technologie",
    "XLF": "Finanzen",
    "XLE": "Energie",
    "XLV": "Gesundheit",
    "XLY": "Zyklischer Konsum",
    "XLP": "Basiskonsum",
    "XLI": "Industrie",
    "XLB": "Grundstoffe",
    "XLRE": "Immobilien",
    "XLC": "Kommunikation",
    "XLU": "Versorger",
    "ITA": "Rüstung & Luftfahrt",
}

# STOXX Europe 600 Sektor-ETFs (EU)
SECTOR_ETFS_EU = {
    "EXV8.DE": "Technologie",
    "EXV1.DE": "Finanzen",
    "EXH1.DE": "Energie",
    "EXV4.DE": "Gesundheit",
    "EXV5.DE": "Industrie",
    "EXV6.DE": "Versorger",
    "EXH4.DE": "Basiskonsum",
    "EXH8.DE": "Grundstoffe",
    "EXV3.DE": "Zyklischer Konsum",
    "EXV2.DE": "Telekommunikation",
    "EXI5.DE": "Immobilien",
}

# Rückwärtskompatibel
SECTOR_ETFS = SECTOR_ETFS_US


def get_correlation_matrix(tickers: list[str], labels: list[str] | None = None,
                           period: str = "1y") -> pd.DataFrame | None:
    """Berechnet die Korrelationsmatrix für eine Liste von Tickern.

    Rückgabe: DataFrame (symmetrisch, Diagonale = 1.0) oder None.
    """
    try:
        closes = {}
        for t in tickers:
            hist = yf.Ticker(t).history(period=period)
            if hist is not None and not hist.empty:
                # Zeitzonen entfernen, damit verschiedene Börsen kombinierbar sind
                idx = hist.index.tz_localize(None) if hist.index.tz else hist.index
                closes[t] = pd.Series(hist["Close"].values, index=idx, name=t)
        if len(closes) < 2:
            return None
        # Forward-Fill: Lücken durch unterschiedliche Handelstage auffüllen
        df = pd.DataFrame(closes)
        df = df.ffill().bfill().dropna()
        if df.empty or len(df) < 10:
            return None
        corr = df.pct_change().dropna().corr()
        # Labels zuordnen (nur für erfolgreich geladene Ticker)
        if labels:
            # Mapping: Ticker → Label
            ticker_to_label = dict(zip(tickers, labels))
            new_labels = [ticker_to_label.get(c, c) for c in corr.columns]
            corr.index = new_labels
            corr.columns = new_labels
        return corr
    except Exception as exc:
        warnings.warn(f"get_correlation_matrix: {exc}")
        return None


# ---------------------------------------------------------------------------
# Sektor-Performance (für Sektoren-Heatmap)
# ---------------------------------------------------------------------------

def get_sector_performance(period: str = "1d", region: str = "us") -> pd.DataFrame | None:
    """Lädt die Sektor-Performance via ETFs.

    region: 'us' = S&P 500 Sektoren, 'eu' = STOXX Europe 600 Sektoren.
    Rückgabe: DataFrame mit Spalten [Sektor, Ticker, Veränderung %, Kurs].
    """
    etf_map = SECTOR_ETFS_US if region == "us" else SECTOR_ETFS_EU
    currency = "$" if region == "us" else "€"
    try:
        records = []
        for etf_ticker, sector_name in etf_map.items():
            hist = yf.Ticker(etf_ticker).history(period="1y")
            if hist is None or hist.empty or len(hist) < 2:
                continue
            current = float(hist["Close"].iloc[-1])

            # Performance je nach gewähltem Zeitraum berechnen
            if period == "1d":
                prev = float(hist["Close"].iloc[-2])
            elif period == "1w":
                prev = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else float(hist["Close"].iloc[0])
            elif period == "1m":
                prev = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else float(hist["Close"].iloc[0])
            elif period == "3m":
                prev = float(hist["Close"].iloc[-66]) if len(hist) >= 66 else float(hist["Close"].iloc[0])
            elif period == "ytd":
                # Ersten Handelstag des Jahres
                import datetime
                year_start = datetime.date(datetime.date.today().year, 1, 1)
                ytd_data = hist[hist.index >= pd.Timestamp(year_start, tz=hist.index.tz)]
                prev = float(ytd_data["Close"].iloc[0]) if not ytd_data.empty else float(hist["Close"].iloc[0])
            elif period == "1y":
                prev = float(hist["Close"].iloc[0])
            else:
                prev = float(hist["Close"].iloc[-2])

            change_pct = ((current - prev) / prev) * 100 if prev else 0.0

            records.append({
                "Sektor": sector_name,
                "Ticker": etf_ticker,
                "Veränderung %": round(change_pct, 2),
                "Kurs": round(current, 2),
            })
        if not records:
            return None
        return pd.DataFrame(records).sort_values("Veränderung %", ascending=False).reset_index(drop=True)
    except Exception as exc:
        warnings.warn(f"get_sector_performance: {exc}")
        return None


# ---------------------------------------------------------------------------
# Nachrichten — Regionale Macro-News (RSS-Feeds)
# ---------------------------------------------------------------------------

# Kuratierte RSS-Feed-URLs nach Region
_RSS_FEEDS = {
    "europa": [
        ("Tagesschau",    "https://www.tagesschau.de/wirtschaft/konjunktur/index~rss2.xml"),
        ("Handelsblatt",  "https://www.handelsblatt.com/contentexport/feed/schlagzeilen"),
    ],
    "usa": [
        ("CNBC",          "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ],
    "asien": [
        ("Nikkei Asia",   "https://asia.nikkei.com/rss/feed/nar"),
        ("CNBC Asia",     "https://www.cnbc.com/id/19832390/device/rss/rss.html"),
    ],
}


def get_regional_news(region: str, max_items: int = 15) -> list[dict] | None:
    """Lädt Macro-Nachrichten für eine Region via RSS-Feeds.

    region: 'europa', 'usa' oder 'asien'.
    Rückgabe: Liste von Dicts [{title, link, published, source}, ...],
              sortiert nach Datum (neueste zuerst), oder None bei Fehler.
    """
    import feedparser
    from datetime import datetime
    from time import mktime

    feeds = _RSS_FEEDS.get(region.lower())
    if not feeds:
        warnings.warn(f"get_regional_news: unbekannte Region '{region}'")
        return None

    articles = []
    seen_titles = set()

    for source_name, feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                link = entry.get("link", "")
                # Datum parsen
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime.fromtimestamp(mktime(entry.published_parsed))
                    except Exception:
                        pass
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    try:
                        published = datetime.fromtimestamp(mktime(entry.updated_parsed))
                    except Exception:
                        pass

                # Zusammenfassung (Kernaussage) aus RSS-Feed
                summary = ""
                raw_summary = entry.get("summary", "") or entry.get("description", "")
                if raw_summary:
                    # HTML-Tags entfernen (einfach)
                    import re
                    summary = re.sub(r"<[^>]+>", "", raw_summary).strip()
                    # Auf sinnvolle Länge kürzen
                    if len(summary) > 200:
                        summary = summary[:197] + "…"

                articles.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "source": source_name,
                    "summary": summary,
                })
        except Exception as exc:
            warnings.warn(f"RSS-Feed {source_name} ({feed_url}): {exc}")
            continue

    if not articles:
        return None

    # Nach Datum sortieren (neueste zuerst), Einträge ohne Datum ans Ende
    articles.sort(
        key=lambda a: a["published"] or datetime.min,
        reverse=True,
    )
    return articles[:max_items]


# ---------------------------------------------------------------------------
# Nachrichten — Unternehmens-News (yfinance)
# ---------------------------------------------------------------------------

def get_company_news(ticker: str, max_items: int = 10) -> list[dict] | None:
    """Lädt ticker-spezifische Nachrichten via yfinance.

    Rückgabe: Liste von Dicts [{title, link, published, source}, ...],
              oder None bei Fehler.
    """
    try:
        tk = yf.Ticker(ticker)
        raw_news = tk.news
        if not raw_news:
            return None

        articles = []
        for item in raw_news[:max_items]:
            content = item.get("content", {})
            if not content:
                continue

            title = content.get("title", "").strip()
            if not title:
                continue

            # Publisher
            provider = content.get("provider", {})
            source = provider.get("displayName", "Yahoo Finance") if provider else "Yahoo Finance"

            # Link
            click_url = content.get("clickThroughUrl", {})
            link = ""
            if click_url:
                link = click_url.get("url", "")
            if not link:
                canonical = content.get("canonicalUrl", {})
                link = canonical.get("url", "") if canonical else ""

            # Datum
            published = None
            pub_date = content.get("pubDate")
            if pub_date:
                try:
                    from datetime import datetime
                    # yfinance liefert ISO-Format
                    published = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            # Zusammenfassung (Kernaussage) — direkt von Yahoo geliefert
            summary = content.get("summary", "").strip()

            articles.append({
                "title": title,
                "link": link,
                "published": published,
                "source": source,
                "summary": summary,
            })

        return articles if articles else None
    except Exception as exc:
        warnings.warn(f"get_company_news({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Earnings-Termine für Watchlist
# ---------------------------------------------------------------------------

def get_earnings_dates(tickers: list[str],
                       names: dict[str, str] | None = None) -> pd.DataFrame | None:
    """Lädt die nächsten Quartalszahlen-Termine für eine Liste von Tickern.

    Bei Xetra-Tickern (.DE) wird automatisch der US-Ursprungsticker
    für die Earnings-Abfrage verwendet (Xetra liefert oft keine Daten).

    Rückgabe: DataFrame mit Spalten [Ticker, Name, Quartalszahlen]
              sortiert nach Datum (nächster Termin zuerst), oder None.
    """
    import datetime as _dt

    def _extract_date(raw):
        """Extrahiert ein einzelnes datetime.date aus verschiedenen Formaten."""
        if raw is None:
            return None
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        if raw is None:
            return None
        if isinstance(raw, _dt.datetime):
            return raw.date()
        if isinstance(raw, _dt.date):
            return raw
        try:
            return _dt.date.fromisoformat(str(raw).split(" ")[0])
        except Exception:
            return None

    def _get_earnings(ticker_str):
        """Versucht Earnings-Datum für einen Ticker zu holen."""
        try:
            tk = yf.Ticker(ticker_str)
            cal = tk.calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                return _extract_date(cal["Earnings Date"])
        except Exception:
            pass
        return None

    records = []
    for t in tickers:
        t = t.strip()
        if not t:
            continue

        ed = _get_earnings(t)

        # Fallback für Xetra-Ticker: US-Ticker per Namenssuche finden
        if ed is None and t.upper().endswith(".DE"):
            try:
                company = (names or {}).get(t, "")
                if company and company != t:
                    search = yf.Search(company, max_results=5)
                    for q in (search.quotes or []):
                        sym = q.get("symbol", "")
                        exchange = q.get("exchange", "")
                        # Nur US-Börsen nehmen (NYQ, NMS, NGM = NYSE/NASDAQ)
                        if sym and exchange in ("NYQ", "NMS", "NGM", "NYSE", "NASDAQ"):
                            ed = _get_earnings(sym)
                            if ed is not None:
                                break
            except Exception:
                pass

        name = (names or {}).get(t, t)
        records.append({"Ticker": t, "Name": name, "Quartalszahlen": ed})

    if not records:
        return None

    df = pd.DataFrame(records)
    sentinel = _dt.date(9999, 12, 31)
    df["_sort"] = df["Quartalszahlen"].apply(lambda x: x if isinstance(x, _dt.date) else sentinel)
    df = df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    return df

# ---------------------------------------------------------------------------
# S&P 500 Komponenten für Sektoren Drilldown
# ---------------------------------------------------------------------------

def get_sp500_components() -> pd.DataFrame | None:
    """Lädt die Liste aller S&P 500 Aktien von Wikipedia."""
    try:
        import requests
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=headers).text
        tables = pd.read_html(html)
        df = tables[0]
        # Symbole in yfinance Format bringen (z.B. BRK.B -> BRK-B)
        df['Symbol'] = df['Symbol'].str.replace('.', '-')
        return df[['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry']]
    except Exception as exc:
        warnings.warn(f"get_sp500_components: {exc}")
        return None

def get_components_performance(tickers: list[str], period: str) -> pd.DataFrame | None:
    """Berechnet die Performance für eine Liste von Aktien über den gewünschten Zeitraum."""
    try:
        if not tickers:
            return None
            
        p_map = {
            "1d": "5d", "1w": "1mo", "1m": "3mo", "3m": "6mo", "ytd": "ytd", "1y": "1y"
        }
        yf_period = p_map.get(period, "1y")
        
        data = yf.download(tickers, period=yf_period, auto_adjust=True, progress=False)
        if data.empty or 'Close' not in data:
            return None
            
        closes = data['Close']
        if isinstance(closes, pd.Series):
            closes = pd.DataFrame({tickers[0]: closes})

        if len(closes) < 2:
            return None
            
        records = []
        for ticker in tickers:
            if ticker in closes.columns:
                series = closes[ticker].dropna()
                if len(series) < 2:
                    continue
                current = float(series.iloc[-1])
                
                if period == "1d":
                    prev = float(series.iloc[-2])
                elif period == "1w":
                    prev = float(series.iloc[-6]) if len(series) >= 6 else float(series.iloc[0])
                elif period == "1m":
                    prev = float(series.iloc[-22]) if len(series) >= 22 else float(series.iloc[0])
                elif period == "3m":
                    prev = float(series.iloc[-66]) if len(series) >= 66 else float(series.iloc[0])
                elif period == "ytd" or period == "1y":
                    prev = float(series.iloc[0])
                else:
                    prev = float(series.iloc[0])
                    
                change_pct = ((current - prev) / prev) * 100 if prev else 0.0
                records.append({
                    "Ticker": ticker,
                    "Veränderung %": round(change_pct, 2),
                    "Kurs": round(current, 2)
                })
        
        if not records:
            return None
        return pd.DataFrame(records).sort_values("Veränderung %", ascending=False)
    except Exception as exc:
        warnings.warn(f"get_components_performance: {exc}")
        return None
