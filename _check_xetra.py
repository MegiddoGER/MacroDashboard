"""Einmal-Script: Überprüft xetra_stocks.csv auf Duplikate und Vollständigkeit."""
import sys
import csv
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

entries = []
with open(r"data\xetra_stocks.csv", "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        entries.append({
            "ticker": row.get("Kürzel", "").strip(),
            "name": row.get("Name", "").strip(),
            "index": row.get("Index", "").strip(),
        })

print(f"=== GESAMT: {len(entries)} Zeilen ===\n")

# 1. Exakte Duplikate (gleicher Ticker + gleicher Index)
pairs = [(e["index"], e["ticker"]) for e in entries]
exact_dupes = [(idx, t) for (idx, t), c in Counter(pairs).items() if c > 1]
print(f"1) EXAKTE DUPLIKATE (gleicher Ticker im gleichen Index): {len(exact_dupes)}")
for idx, t in exact_dupes:
    print(f"   ❌ {t} doppelt in '{idx}'")

# 2. Cross-Index Ticker (gleicher Ticker in mehreren Indizes)
t2i = {}
for e in entries:
    t2i.setdefault(e["ticker"], set()).add(e["index"])
multi = {t: sorted(i) for t, i in t2i.items() if len(i) > 1}
print(f"\n2) CROSS-INDEX TICKER (Ticker in mehreren Indizes): {len(multi)}")
for t, indices in sorted(multi.items()):
    name = next((e["name"] for e in entries if e["ticker"] == t), "?")
    print(f"   ⚠️  {t} ({name}) → {', '.join(indices)}")

# 3. Counts pro Index
print(f"\n3) TICKER PRO INDEX:")
for idx in sorted(set(e["index"] for e in entries)):
    tickers = set(e["ticker"] for e in entries if e["index"] == idx)
    rows = sum(1 for e in entries if e["index"] == idx)
    dupe_count = rows - len(tickers)
    status = f" (⚠️ {dupe_count} Duplikate!)" if dupe_count > 0 else ""
    print(f"   {idx}: {len(tickers)} Ticker ({rows} Zeilen){status}")

# 4. Potenzielle DAX-Lücken prüfen (aktueller DAX 40)
dax_tickers = set(e["ticker"] for e in entries if e["index"] == "DAX")
print(f"\n4) DAX CHECK: {len(dax_tickers)} von 40 Aktien enthalten")
if len(dax_tickers) < 40:
    print(f"   ⚠️  Es fehlen {40 - len(dax_tickers)} DAX-Aktien!")

# 5. US-Backtesting-Presets vs Xetra International Overlap
us_presets = {"AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","JPM","V","JNJ",
              "WMT","PG","MA","UNH","HD","DIS","NFLX","KO","PEP","MCD",
              "COST","ABBV","CRM","AMD","INTC","BA","GS","CAT","XOM","CVX"}

# Welche Xetra International Ticker mappen auf die gleichen Unternehmen?
xi_names = {e["name"].lower(): e["ticker"] for e in entries if e["index"] == "XETRA International"}
print(f"\n5) XETRA INTERNATIONAL vs US PRESETS:")
overlap_companies = []
for e in entries:
    if e["index"] != "XETRA International":
        continue
    name_l = e["name"].lower()
    for us in us_presets:
        us_l = us.lower()
        if us_l in name_l or us_l.replace(".", "") in name_l:
            overlap_companies.append((e["ticker"], e["name"], us))
# Check by company name fragments
name_map = {
    "apple": "AAPL", "microsoft": "MSFT", "amazon": "AMZN", "alphabet": "GOOGL",
    "meta platforms": "META", "nvidia": "NVDA", "tesla": "TSLA", "jpmorgan": "JPM",
    "visa": "V", "johnson": "JNJ", "walmart": "WMT", "procter": "PG",
    "mastercard": "MA", "unitedhealth": "UNH", "home depot": "HD",
    "disney": "DIS", "netflix": "NFLX", "coca-cola": "KO", "pepsico": "PEP",
    "mcdonald": "MCD", "costco": "COST", "abbvie": "ABBV", "salesforce": "CRM",
    "advanced micro": "AMD", "intel": "INTC", "boeing": "BA", "goldman": "GS",
    "caterpillar": "CAT", "exxon": "XOM", "chevron": "CVX",
}
print("   Xetra Int. Ticker die das gleiche Unternehmen wie ein US-Preset sind:")
found_overlaps = []
for e in entries:
    if e["index"] != "XETRA International":
        continue
    for frag, us_sym in name_map.items():
        if frag in e["name"].lower():
            found_overlaps.append((e["ticker"], e["name"], us_sym))
            print(f"   📎 {e['ticker']} ({e['name']}) ↔ US: {us_sym}")
if not found_overlaps:
    print("   ✅ Kein Overlap gefunden")
else:
    print(f"   → {len(found_overlaps)} Überlappungen (Xetra .DE Version des gleichen US-Unternehmens)")

print("\n=== FERTIG ===")
