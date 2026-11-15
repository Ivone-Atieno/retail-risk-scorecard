# ===== STEP 21: (A) design Debt formulas on 2014+ filings, (B) usable-observation count for held-out failures. NO SCORES. =====
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
def inst(f, tag):
    d = usd(f, tag); d = d[d["days"].isna()]
    return d.sort_values("filed").drop_duplicates("end", keep="first").set_index("end")[["val", "filed"]]

# ---------- the design formula language: '+' adds terms, '|' takes the first available tag, '?' marks optional ----------
def eval_formula(f, formula):
    terms = [t.strip() for t in str(formula).split("+") if t.strip()]
    parts, optional = [], []
    for t in terms:
        alts = [a.strip() for a in t.split("|")]
        opt = any(a.endswith("?") for a in alts)
        ser = [inst(f, a.rstrip("?"))["val"] for a in alts]
        ser = [s for s in ser if len(s)]
        parts.append(pd.concat(ser, axis=1).bfill(axis=1).iloc[:, 0] if ser else pd.Series(dtype=float)); optional.append(opt)
    if not parts: return pd.Series(dtype=float)
    ends = sorted(set().union(*[set(p.index) for p in parts]))
    out = {}
    for e in ends:
        tot, ok = 0.0, True
        for p, o in zip(parts, optional):
            if e in p.index and pd.notna(p[e]): tot += p[e]
            elif not o: ok = False; break
        if ok: out[e] = tot
    return pd.Series(out, dtype=float).sort_index()

# ======================================================================
# PART A. Apply the design debt_definition.csv formulas to filings from 2014 and compare with debt_quarterly_final.csv (2019+)
# ======================================================================
defs = pd.read_csv(BASE / "debt_definition.csv").fillna("")
print("PART A: design debt definitions (from debt_definition.csv)\n")
print(defs[[c for c in ["ticker", "formula", "basis", "includes_leases", "confidence"] if c in defs.columns]].to_string(index=False), "\n")
dq = pd.read_csv(BASE / "debt_quarterly_final.csv", parse_dates=["end"])
rows, newdebt = [], {}
for _, r in defs.iterrows():
    tk = r["ticker"]
    f = facts_of(RAW / f"{cik_of[tk]:010d}.json")
    S = eval_formula(f, r["formula"]) / 1e6
    newdebt[tk] = S
    ref = dq[(dq.ticker == tk) & dq.total_m.notna() & (dq.end >= "2019-01-01")]
    errs, bad = [], []
    for _, q in ref.iterrows():
        j = S.index[np.abs((S.index - q.end).days) <= 5] if len(S) else []
        if len(j) == 0: continue
        e = abs(S[j[0]] - q.total_m) / max(abs(q.total_m), 1.0); errs.append(e)
        if e > 0.005: bad.append((str(q.end.date()), round(q.total_m, 1), round(S[j[0]], 1), q["flag"]))
    pre = S[(S.index < "2019-01-01")]
    rows.append(dict(ticker=tk, n_design_2019plus=len(ref), n_matched=len(errs), share_exact=round(float(np.mean(np.array(errs) <= 0.005)), 2) if errs else np.nan,
                     n_mismatch=len(bad), first_mismatches=bad[:3], ends_2014_18=len(pre), nonzero_2014_18=int((pre > 0).sum())))
A = pd.DataFrame(rows)
print("A1. formula reproduces the design Debt? share_exact = quarters equal within 0.5%; mismatches are expected only where the design used a MANUAL override or a tag with no formula term\n")
print(A.to_string(index=False), "\n")
pd.to_pickle(newdebt, HO / "design_debt_2014.pkl")

# ======================================================================
# PART B. Held-out failures: approximate count of usable observations in the primary window (3-12 months), after COVID blanking
# ======================================================================
print("PART B: held-out failed companies, usable observations (approximate: input availability at period ends, no scores)")
INV  = ["InventoryNet", "InventoryFinishedGoodsNetOfReserves", "RetailRelatedInventoryMerchandise", "InventoryFinishedGoods", "MerchandiseInventoryNet"]
REV  = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]
COST = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "GrossProfit"]
DEBTB = "LongTermDebt|LongTermDebtNoncurrent+LongTermDebtCurrent?+ShortTermBorrowings?+LineOfCredit?+LongTermLineOfCredit?"   # provisional, replaced by hand-checked formulas
def has_flow_end(f, tags):
    ends = set()
    for t in tags:
        d = usd(f, t); d = d[d["days"].notna() & (d["days"] >= 80)]
        ends |= set(d["end"])
    return ends
def has_inst_end(f, tags):
    ends = set()
    for t in tags: ends |= set(inst(f, t).index)
    return ends
def near(ends_set, e, tol=6):
    return any(abs((x - e).days) <= tol for x in ends_set)

WIN = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
ev = pd.read_csv(HO / "failed_events_checked.csv"); ev = ev[ev["event_8k_date"].notna()].copy()
ev["event_8k_date"] = pd.to_datetime(ev["event_8k_date"])
rowsB = []
for _, r in ev.iterrows():
    if "Container Store" in str(r["name"]): continue
    p = HO / "raw" / f"{int(r['cik']):010d}.json"
    if not p.exists(): continue
    f = facts_of(p); e0 = r["event_8k_date"]
    ca = inst(f, "AssetsCurrent")
    invE, revE, costE = has_inst_end(f, INV), has_flow_end(f, REV), has_flow_end(f, COST)
    D = eval_formula(f, DEBTB)
    nzD = D[D > 0]
    n_prim = n_all = n_blank = n_missing = n_nodebt = 0
    for e, row in ca.iterrows():
        h = (e0 - row["filed"]).days / 30.4
        if h < 3 or h > 27: continue
        py = e - pd.Timedelta(days=364)
        ok_inputs = (near(invE, e) and near(invE, py) and near(revE, e) and near(revE, py) and near(costE, e) and near(costE, py)
                     and len(D) and any(abs((x - e).days) <= 6 for x in D.index) and any(abs((x - py).days) <= 6 for x in D.index))
        blank = str((e + pd.Timedelta(days=30)).to_period("Q")) in WIN
        debt_live = len(D) and any(abs((x - py).days) <= 6 for x in nzD.index)       # last year's debt above zero, else lev3 blank and lev2 flat
        if h <= 12:
            if blank: n_blank += 1
            elif not ok_inputs: n_missing += 1
            else:
                n_prim += 1
                if not debt_live: n_nodebt += 1
        n_all += 1 if (ok_inputs and not blank) else 0
    rowsB.append(dict(name=r["name"], event=str(e0.date()), usable_3_12m=n_prim, of_which_no_prior_debt=n_nodebt, blanked_by_covid_3_12m=n_blank,
                      missing_inputs_3_12m=n_missing, usable_3_27m=n_all))
B = pd.DataFrame(rowsB)
print(B.to_string(index=False))
ge2 = int((B.usable_3_12m - B.of_which_no_prior_debt >= 2).sum())
print(f"\nCompanies with at least 2 usable 3-12 month observations that have last-year debt above zero: {ge2} of {len(B)}")
print("Companies with at least 1:", int((B.usable_3_12m >= 1).sum()))
A.to_csv(HO / "pilot_A_design_debt_formula.csv", index=False); B.to_csv(HO / "pilot_B_usable_observations.csv", index=False)
print("saved pilot_A_design_debt_formula.csv, pilot_B_usable_observations.csv, design_debt_2014.pkl in", HO)
