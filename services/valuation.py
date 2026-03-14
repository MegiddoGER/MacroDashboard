import pandas as pd
import numpy as np

def _safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val):
            return default
        return float(val)
    except:
        return default

def calc_excess_returns(info: dict) -> dict:
    roe = _safe_float(info.get("returnOnEquity"), 0.0)
    beta = _safe_float(info.get("beta"), 1.0)
    book_value = _safe_float(info.get("bookValue"), 0.0)
    
    # Assume Risk-Free Rate of 3% and Equity Risk Premium of 5.5%
    risk_free_rate = 0.03
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

