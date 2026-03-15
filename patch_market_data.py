import sys

with open(r'c:\Projekte_Coding\MacroDashboard\services\market_data.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Insert _get_cik_for_ticker
helper_code = """
_cik_cache = {}

def _get_cik_for_ticker(ticker: str) -> str | None:
    \"\"\"Holt die CIK für einen US-Ticker via SEC EDGAR company_tickers.json.\"\"\"
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

def get_stock_details("""

if "_get_cik_for_ticker" not in content:
    content = content.replace("def get_stock_details(", helper_code)


# 2. Replace financials logic
fin_start_idx = content.find("        # Finanzdaten (Umsatz, EBITDA, Nettogewinn)\n        financials_data = []")
fin_end_idx = content.find("        return {\n            \"info\": info,")

if fin_start_idx == -1 or fin_end_idx == -1:
    print("Could not find financials section to replace.")
    sys.exit(1)

new_fin_code = """        # Finanzdaten (Umsatz, EBITDA, Nettogewinn)
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

"""

content = content[:fin_start_idx] + new_fin_code + content[fin_end_idx:]

with open(r'c:\Projekte_Coding\MacroDashboard\services\market_data.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied successfully.")
