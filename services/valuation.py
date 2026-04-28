import pandas as pd
import numpy as np

def _safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except Exception:
        return default

def calc_excess_returns(info: dict) -> dict:
    roe = _safe_float(info.get("returnOnEquity"), 0.0)
    beta = _safe_float(info.get("beta"), 1.0)
    book_value = _safe_float(info.get("bookValue"), 0.0)
    
    # Dynamische Risk-Free Rate (Live 10Y Treasury Yield)
    from services.fundamental import _get_live_risk_free_rate
    risk_free_rate = _get_live_risk_free_rate()
    erp = 0.055
    cost_of_equity = risk_free_rate + (beta * erp)
    
    excess_return_margin = roe - cost_of_equity
    excess_return_value = excess_return_margin * book_value
    
    return {
        "roe": roe,
        "beta": beta,
        "cost_of_equity": cost_of_equity,
        "book_value": book_value,
        "excess_return_margin": excess_return_margin,
        "excess_return_value": excess_return_value,
        "is_undervalued": excess_return_margin > 0
    }

def calc_rule_of_40(info: dict) -> dict:
    rev_growth = _safe_float(info.get("revenueGrowth"), 0.0)
    
    # FCF Margin = Free Cashflow / Total Revenue
    fcf = _safe_float(info.get("freeCashflow"), 0.0)
    total_rev = _safe_float(info.get("totalRevenue"), 1.0) # avoid division by zero
    
    # Fallback to operating margin if FCF is weird or zero
    if total_rev > 1.0 and fcf != 0.0:
        fcf_margin = fcf / total_rev
    else:
        fcf_margin = _safe_float(info.get("operatingMargins"), 0.0)
        
    rule_of_40_score = (rev_growth + fcf_margin) * 100
    
    return {
        "revenue_growth": rev_growth,
        "fcf_margin": fcf_margin,
        "rule_of_40_score": rule_of_40_score,
        "is_healthy": rule_of_40_score >= 40.0
    }

def calc_hardware_cycle(info: dict) -> dict:
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0.0)
    price_to_book = _safe_float(info.get("priceToBook"), 0.0)
    inventory_turnover = _safe_float(info.get("inventoryTurnover"), 0.0)
    
    # Cyclic check: Low EV/EBITDA but high P/B implies earnings are at peak cycle.
    return {
        "ev_ebitda": ev_ebitda,
        "price_to_book": price_to_book,
        "inventory_turnover": inventory_turnover,
        "book_to_bill": "N/A (Spezialdaten)",
        "is_value_trap_warning": ev_ebitda < 8 and price_to_book > 5
    }

def calc_rnpv_proxy(info: dict) -> dict:
    ev = _safe_float(info.get("enterpriseValue"), 0.0)
    revenue = _safe_float(info.get("totalRevenue"), 0.0)
    ev_to_sales = _safe_float(info.get("enterpriseToRevenue"), 0.0)
    
    return {
        "ev": ev,
        "ev_to_sales": ev_to_sales,
        "revenue": revenue,
        "ptrs": "N/A (Klinische Erfolgsraten / Spezialdaten)",
        "rnpv": "Benötigt Pipeline-Modellierung"
    }

def calc_ev_dacf(info: dict) -> dict:
    ev = _safe_float(info.get("enterpriseValue"), 0.0)
    ocf = _safe_float(info.get("operatingCashflow"), 0.0)
    
    # Defaulting DACF to proxy Operating Cashflow if interest expense is unavailable simply
    ev_ocf = (ev / ocf) if ocf > 0 else 0.0
    
    return {
        "ev": ev,
        "operating_cashflow": ocf,
        "ev_to_ocf": ev_ocf,
        "reserves_boe": "N/A (Öl-Reserven / Spezialdaten)",
        "is_attractive": ev_ocf > 0 and ev_ocf < 8
    }

def calc_telecom_metrics(info: dict) -> dict:
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0.0)
    dividend_yield = _safe_float(info.get("dividendYield"), 0.0)
    
    return {
        "ev_ebitda": ev_ebitda,
        "dividend_yield": dividend_yield,
        "arpu": "N/A (Spezialdaten)",
        "churn_rate": "N/A (Spezialdaten)",
        "is_cash_cow": ev_ebitda < 10 and dividend_yield > 0.04
    }

def calc_logistics_metrics(info: dict) -> dict:
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0.0)
    ebitda_margin = _safe_float(info.get("ebitdaMargins"), 0.0)
    
    return {
        "ev_ebitda": ev_ebitda,
        "ebitda_margin": ebitda_margin,
        "ebitdar_proxy": "Proxy: EV/EBITDA",
        "load_factor": "N/A (Flottenauslastung / Spezialdaten)"
    }

def calc_hgb_proxy(info: dict) -> dict:
    roa = _safe_float(info.get("returnOnAssets"), 0.0)
    price_to_book = _safe_float(info.get("priceToBook"), 0.0)
    
    return {
        "roa": roa,
        "price_to_book": price_to_book,
        "stille_reserven": "N/A (HGB-Adjustierung)",
        "is_hidden_champion": roa > 0.05 and price_to_book > 0.0 and price_to_book < 3.0
    }

def calc_csvs(info: dict) -> dict:
    dividend_yield = _safe_float(info.get("dividendYield"), 0.0)
    price_to_book = _safe_float(info.get("priceToBook"), 0.0)
    
    return {
        "dividend_yield": dividend_yield,
        "price_to_book": price_to_book,
        "strategic_importance": "N/A (Manuelle Eingabe / Policy-Analyse)",
        "is_undervalued_soe": dividend_yield > 0.05 and price_to_book > 0.0 and price_to_book < 1.0
    }

def calc_defense_metrics(info: dict) -> dict:
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0.0)
    operating_margin = _safe_float(info.get("operatingMargins"), 0.0)
    
    return {
        "ev_ebitda": ev_ebitda,
        "operating_margin": operating_margin,
        "backlog_to_revenue": "N/A (Manuelle Eingabe / Orderbuch)",
        "is_highly_profitable": ev_ebitda > 0 and ev_ebitda < 15 and operating_margin > 0.10
    }

def calc_auto_metrics(info: dict) -> dict:
    pe_ratio = _safe_float(info.get("trailingPE"), 0.0)
    
    # Asset Turnover = Revenue / Total Assets
    rev = _safe_float(info.get("totalRevenue"), 0.0)
    assets = _safe_float(info.get("totalAssets"), 0.0)
    asset_turnover = (rev / assets) if assets > 0 else 0.0
    
    # ROIC Proxy via ROA
    roa = _safe_float(info.get("returnOnAssets"), 0.0)
    
    return {
        "pe_ratio": pe_ratio,
        "asset_turnover": asset_turnover,
        "roa_proxy_roic": roa,
        "is_efficient_allocator": asset_turnover > 0.5 and roa > 0.05 and pe_ratio < 15 and pe_ratio > 0
    }

def calc_machinery_metrics(info: dict) -> dict:
    ev_ebitda = _safe_float(info.get("enterpriseToEbitda"), 0.0)
    price_to_book = _safe_float(info.get("priceToBook"), 0.0)
    roa = _safe_float(info.get("returnOnAssets"), 0.0)
    
    return {
        "ev_ebitda": ev_ebitda,
        "price_to_book": price_to_book,
        "roa": roa,
        "is_value_trap_warning": ev_ebitda < 8 and ev_ebitda > 0 and price_to_book > 4
    }


def determine_sector_category(stats: dict, details: dict) -> tuple:
    """Bestimmt die Sektor-Kategorie und den Tab-Namen für die Quant-Analyse.

    Extrahiert aus views/sections/analysis_valuation.py — reine Logik, kein UI.
    """
    yfin_sector = stats["sector"].lower() if stats.get("sector") and stats["sector"] != "—" else ""
    yfin_industry = details.get("info", {}).get("industry", "").lower()

    sector_cat = "none"
    tab_name = "📊 Quant-Analyse"

    if "financial" in yfin_sector or "insurance" in yfin_sector:
        sector_cat = "finanzen"
        tab_name = "🏦 Excess Returns (Finanzen)"
    elif "technology" in yfin_sector or "software" in yfin_sector:
        sector_cat = "tech"
        tab_name = "💻 Rule of 40 (Tech/SaaS)"
    elif "semiconductor" in yfin_industry or "hardware" in yfin_industry:
        sector_cat = "hardware"
        tab_name = "🔌 EV/EBITDA-Zyklik (Hardware)"
    elif "healthcare" in yfin_sector or "biotech" in yfin_sector or "pharm" in yfin_sector:
        sector_cat = "pharma"
        tab_name = "🧬 rNPV Proxy (Pharma)"
    elif "energy" in yfin_sector or "oil" in yfin_sector:
        sector_cat = "energie"
        tab_name = "🛢️ EV/DACF (Energie)"
    elif "communication" in yfin_sector or "telecom" in yfin_sector:
        sector_cat = "telekom"
        tab_name = "📡 ARPU-Adj. EV/EBITDA (Telekom)"
    elif "industrial" in yfin_sector or "transportation" in yfin_sector or "consumer cyclical" in yfin_sector:
        if "aerospace" in yfin_industry or "defense" in yfin_industry:
            sector_cat = "defense"
            tab_name = "🛡️ EV/EBITDA & Marge (Rüstung/Luftfahrt)"
        elif "auto" in yfin_industry:
            sector_cat = "auto"
            tab_name = "🚗 Asset Turnover (Automobil)"
        elif "machinery" in yfin_industry or "construction" in yfin_industry or "building" in yfin_industry:
            sector_cat = "maschinenbau"
            tab_name = "🏗️ Zyklus-Proxy (Maschinen-/Bauwesen)"
        elif "freight" in yfin_industry or "logistic" in yfin_industry or "airline" in yfin_industry or "railroad" in yfin_industry or "shipping" in yfin_industry or "transport" in yfin_industry:
            sector_cat = "logistik"
            tab_name = "🚢 EV/EBITDAR (Logistik)"
        else:
            sector_cat = "industrie"
            tab_name = "🏭 Asset-Based (Allg. Industrie)"
    else:
        sector_cat = "csvs"
        tab_name = "🏛️ CSVS (Dividenden & Buchwert)"

    return sector_cat, tab_name

