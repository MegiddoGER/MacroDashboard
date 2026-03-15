import sys
import os

sys.path.append(r"c:\Projekte_Coding\MacroDashboard")

from services.market_data import get_stock_details

def test_fetch(ticker):
    print(f"--- Fetching {ticker} ---")
    data = get_stock_details(ticker)
    if not data:
        print("No data returned!")
        return
        
    fin = data.get("financials", [])
    print(f"Found {len(fin)} financial records.")
    for f in fin[:5]:
        print(f)
        
if __name__ == "__main__":
    test_fetch("AAPL")
    print("\n-----------------------\n")
    test_fetch("SAP") # Might be SAP.DE depending on how it's structured, let's try SAP first.
