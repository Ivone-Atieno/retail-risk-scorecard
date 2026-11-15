# ===== HELPERS (run once per session, after your start-of-session cell) =====
import numpy as np
tm = pd.DataFrame(columns=["ticker","metric","primary_tag"])

FLOW = ["Revenue", "CostOfGoods", "GrossProfit", "NetIncome", "OpCashFlow", "Capex"]
BAL = ["Inventory", "CurrAssets", "CurrLiab", "Equity"]

def load_facts(ticker):
    cik = int(companies.loc[companies["ticker"] == ticker, "cik"].iloc[0])
    return json.load(open(RAW / f"{cik:010d}.json"))["facts"]["us-gaap"]

def recs_df(facts, tag):
    """All USD records of one tag as a table with period length in days (NaN for balance-sheet facts)."""
    recs = facts.get(tag, {}).get("units", {}).get("USD", [])
    if not recs:
        return pd.DataFrame(columns=["start", "end", "val", "filed", "days"])
    d = pd.DataFrame(recs)
    if "start" not in d:
        d["start"] = np.nan
    d["start"] = pd.to_datetime(d["start"]); d["end"] = pd.to_datetime(d["end"]); d["filed"] = pd.to_datetime(d["filed"])
    d["days"] = (d["end"] - d["start"]).dt.days
    return d[d["end"] >= "2019-01-01"]

def ptype(days):
    if days != days: return "I"          # instant (balance sheet)
    if 80 <= days <= 105: return "Q"     # one quarter
    if 150 <= days <= 300: return "YTD"  # 6 or 9 months year-to-date
    if 340 <= days <= 380: return "A"    # full year
    return "other"

def primary(ticker, metric):
    r = tm[(tm["ticker"] == ticker) & (tm["metric"] == metric)]
    return r["primary_tag"].iloc[0] if len(r) else ""

def earliest(d):
    """One record per (start, end): the earliest-filed one."""
    return d.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
print("helpers ready:", len(tm), "tag-map rows,", len(cov), "coverage rows")
