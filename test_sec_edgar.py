import urllib.request
import json

def test_sec_edgar(ticker="AAPL"):
    headers = {"User-Agent": "MacroDashboard contact@example.com"}
    
    # 1. Get CIK mapping
    req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=headers)
    with urllib.request.urlopen(req) as r:
        sec_data = json.loads(r.read())
        
    cik = None
    for item in sec_data.values():
        if item.get("ticker", "").upper() == ticker.upper():
            cik = str(item.get("cik_str")).zfill(10)
            break
            
    if not cik:
        return
        
    # 2. Get Company Facts
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = urllib.request.Request(url, headers=headers)
    with open('c:/Projekte_Coding/MacroDashboard/sec_output.txt', 'w', encoding='utf-8') as f:
        try:
            with urllib.request.urlopen(req) as r:
                facts = json.loads(r.read())
                
            us_gaap = facts.get("facts", {}).get("us-gaap", {})
            
            # Revenue
            rev_keys = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]
            rev_data = None
            for k in rev_keys:
                if k in us_gaap:
                    f.write(f"Using key: {k} for revenue\n")
                    rev_data = us_gaap[k].get("units", {}).get("USD", [])
                    if rev_data:
                        break
                        
            f.write(f"Total revenue records: {len(rev_data) if rev_data else 0}\n")
            if rev_data:
                f.write("Sample records (last 20):\n")
                for r in rev_data[-20:]:
                    f.write(json.dumps(r) + "\n")
                    
            # Net Income
            ni_keys = ["NetIncomeLoss"]
            for k in ni_keys:
                if k in us_gaap:
                    f.write(f"\nUsing key: {k} for Net Income\n")
                    ni_data = us_gaap[k].get("units", {}).get("USD", [])
                    if ni_data:
                        f.write(f"Total NI records: {len(ni_data)}\n")
                        for r in ni_data[-20:]:
                            f.write(json.dumps(r) + "\n")
                        break
                        
        except Exception as e:
            f.write(f"Error fetching facts: {e}\n")

if __name__ == "__main__":
    test_sec_edgar()
