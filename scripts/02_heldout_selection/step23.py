# ===== STEP 23: for the held-out companies with gaps, print the quarter ends and the nearest available period end per input (tests date matching vs real absence). NO SCORES. =====
import json, re
import numpy as np, pandas as pd
for nm in ["BASE"]:
    if nm not in globals(): raise NameError("BASE is not defined: run your start-of-session cell first")
HO = BASE / "heldout"; START = "2014-01-01"
def facts_of(p): return json.load(open(p))["facts"]["us-gaap"]
def usd(f, tag):
    r = f.get(tag, {}).get("units", {}).get("USD", [])
    if not r: return pd.DataFrame(columns=["start", "end", "val", "filed", "days"])
    d = pd.DataFrame(r)
    if "start" not in d: d["start"] = np.nan
    for c in ["start", "end", "filed"]: d[c] = pd.to_datetime(d[c])
    d["days"] = (d["end"] - d["start"]).dt.days
    return d[d["end"] >= START]
def ends_of(f, tags, kind):
    S = set()
    for t in tags:
        d = usd(f, t)
        d = d[d["days"].isna()] if kind == "inst" else d[d["days"].notna() & (d["days"] >= 80)]
        S |= set(d["end"])
    return sorted(S)
def nearest(S, e):
    if not S: return None, None
    x = min(S, key=lambda s: abs((s - e).days)); return x, (x - e).days
CLASS = {
 "inv":  (["InventoryNet", "InventoryFinishedGoods", "InventoryFinishedGoodsNetOfReserves", "RetailRelatedInventoryMerchandise", "MerchandiseInventoryNet"], "inst"),
 "rev":  (["Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax"], "flow"),
 "cost": (["CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfRevenue", "GrossProfit", "CostOfMerchandiseSalesBuyingAndOccupancyCosts"], "flow"),
 "debt": (["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "LineOfCredit", "LongTermLineOfCredit", "DebtAndCapitalLeaseObligations",
           "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent", "LinesOfCreditCurrent"], "inst"),
}
WHO = ["Sears Holdings", "Fred's Inc", "Destination Maternity", "RTW Retailwinds", "hhgregg", "Christopher & Banks"]
ev = pd.read_csv(HO / "failed_events_checked.csv"); ev["event_8k_date"] = pd.to_datetime(ev["event_8k_date"])
for who in WHO:
    m = ev[ev["name"].str.contains(who, regex=False)]
    if m.empty: print("not found:", who); continue
    r = m.iloc[0]; e0 = r["event_8k_date"]; f = facts_of(HO / "raw" / f"{int(r['cik']):010d}.json")
    ca = usd(f, "AssetsCurrent"); ca = ca[ca["days"].isna()].sort_values("filed").drop_duplicates("end", keep="first")
    win = ca[[3 <= (e0 - x).days / 30.4 <= 12 for x in ca["filed"]]]
    print(f"\n{r['name']} (event {e0.date()}): quarter ends in the 3-12 month window; for each input the nearest period end and its distance in days (blank = none in the whole file)")
    allends = {k: ends_of(f, *CLASS[k]) for k in CLASS}
    for _, q in win.iterrows():
        e = q["end"]; py = e - pd.Timedelta(days=364)
        line = f"  e={e.date()} filed={q['filed'].date()}"
        for k in CLASS:
            x, g = nearest(allends[k], e); xp, gp = nearest(allends[k], py)
            line += f" | {k}: e {g if g is not None else '-'}d, py {gp if gp is not None else '-'}d"
        print(line)
    print("  all AssetsCurrent ends 2 years around the window:", [str(x.date()) for x in ca["end"] if abs((x - win["end"].min()).days) < 800] if len(win) else "none")
