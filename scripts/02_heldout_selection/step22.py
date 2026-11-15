# ===== STEP 22: why do some held-out failures lack inputs, and which design reference companies are thin before 2019? NO SCORES. =====
import json, re
import numpy as np, pandas as pd
for nm in ["BASE", "RAW", "companies"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run your start-of-session cell first")
HO = BASE / "heldout"; START = "2014-01-01"
cik_of = dict(zip(companies["ticker"], companies["cik"].astype(int)))
def facts_of(p): return json.load(open(p))["facts"]["us-gaap"]
def usd(f, tag):
    r = f.get(tag, {}).get("units", {}).get("USD", [])
    if not r: return pd.DataFrame(columns=["start", "end", "val", "filed", "days"])
    d = pd.DataFrame(r)
    if "start" not in d: d["start"] = np.nan
    for c in ["start", "end", "filed"]: d[c] = pd.to_datetime(d[c])
    d["days"] = (d["end"] - d["start"]).dt.days
    return d[d["end"] >= START]
def inst_ends(f, tag):
    d = usd(f, tag); return set(d[d["days"].isna()]["end"])
def flow_ends(f, tag):
    d = usd(f, tag); return set(d[d["days"].notna() & (d["days"] >= 80)]["end"])
def near(S, e, tol=6): return any(abs((x - e).days) <= tol for x in S)
def tag_table(f, pattern, kind, lo, hi, top=5):
    out = []
    for k in f:
        if re.search(pattern, k):
            ends = inst_ends(f, k) if kind == "inst" else flow_ends(f, k)
            n = len([e for e in ends if lo <= e <= hi])
            if n: out.append((n, k))
    return [f"{k}:{n}" for n, k in sorted(out, reverse=True)[:top]]

# ---------- PART A: thin design reference companies before 2019 ----------
defs = pd.read_csv(BASE / "debt_definition.csv").fillna("")
print("PART A: design reference companies with thin 2014-2018 debt: period ends per calendar year, and debt-like tags that exist in those years\n")
for tk in ["TGT", "ROST", "DBI", "PLCE", "BGFV", "WOOF"]:
    if tk not in cik_of or tk not in set(defs.ticker): continue
    f = facts_of(RAW / f"{cik_of[tk]:010d}.json")
    formula = defs.loc[defs.ticker == tk, "formula"].iloc[0]
    tags = [x.rstrip("?") for t in formula.split("+") for x in t.split("|")]
    per_year = {}
    for t in tags:
        for e in inst_ends(f, t):
            if e.year <= 2018: per_year.setdefault(t, {}).setdefault(e.year, 0); per_year[t][e.year] += 1
    print(f"{tk}: formula tags and ends per year 2014-2018: {per_year}")
    print(f"     debt-like tags with ends in 2014-2018: {tag_table(f, r'Debt|Borrow|Credit|Notes|Loan', 'inst', pd.Timestamp('2014-01-01'), pd.Timestamp('2018-12-31'), 8)}")
print()

# ---------- PART B: held-out companies with missing inputs ----------
print("PART B: for each held-out failed company with fewer than 2 usable observations, which input is missing at the quarter ends in its 3-12 month window")
print("(columns count quarter ends, of those in the window, where the input is missing at the quarter end 'e' or the same quarter a year earlier 'py')\n")
INV  = r"Inventor"; REV = r"Revenue|Sales"; COST = r"CostOf|CostsAndExpenses|GrossProfit"; DEBT = r"Debt|Borrow|Credit|Notes|Loan"
INVT  = ["InventoryNet", "InventoryFinishedGoodsNetOfReserves", "RetailRelatedInventoryMerchandise", "InventoryFinishedGoods", "MerchandiseInventoryNet"]
REVT  = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]
COSTT = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "GrossProfit"]
DEBTT = ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "LineOfCredit", "LongTermLineOfCredit", "DebtAndCapitalLeaseObligations",
         "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent", "SecuredDebt", "ConvertibleNotesPayable", "NotesPayable", "LinesOfCreditCurrent"]
U = pd.read_csv(HO / "pilot_B_usable_observations.csv")
need = list(U[U.usable_3_12m - U.of_which_no_prior_debt < 2]["name"])
ev = pd.read_csv(HO / "failed_events_checked.csv"); ev["event_8k_date"] = pd.to_datetime(ev["event_8k_date"])
rows = []
for nm in need:
    r = ev[ev["name"] == nm].iloc[0]; e0 = r["event_8k_date"]
    f = facts_of(HO / "raw" / f"{int(r['cik']):010d}.json")
    inv = set().union(*[inst_ends(f, t) for t in INVT]); rev = set().union(*[flow_ends(f, t) for t in REVT])
    cost = set().union(*[flow_ends(f, t) for t in COSTT]); debt = set().union(*[inst_ends(f, t) for t in DEBTT])
    ca = usd(f, "AssetsCurrent"); ca = ca[ca["days"].isna()].sort_values("filed").drop_duplicates("end", keep="first")
    win = ca[[(e0 - x).days / 30.4 >= 3 and (e0 - x).days / 30.4 <= 12 for x in ca["filed"]]]
    c = dict(name=nm, event=str(e0.date()), window_quarters=len(win))
    for lab, S in [("inv", inv), ("rev", rev), ("cost", cost), ("debt", debt)]:
        c[f"{lab}_miss_e"] = sum(not near(S, e) for e in win["end"])
        c[f"{lab}_miss_py"] = sum(not near(S, e - pd.Timedelta(days=364)) for e in win["end"])
    rows.append(c)
    lo, hi = (e0 - pd.Timedelta(days=int(27 * 30.4)) - pd.Timedelta(days=370)), e0
    print(f"{nm}: top tags in {lo.date()}..{hi.date()}")
    print("   inventory:", tag_table(f, INV, "inst", lo, hi, 4))
    print("   revenue  :", tag_table(f, REV, "flow", lo, hi, 4))
    print("   cost     :", tag_table(f, COST, "flow", lo, hi, 4))
    print("   debt     :", tag_table(f, DEBT, "inst", lo, hi, 5))
M = pd.DataFrame(rows)
print("\n", M.to_string(index=False))
M.to_csv(HO / "pilot_C_missing_inputs.csv", index=False)
print("\nsaved pilot_C_missing_inputs.csv in", HO)
