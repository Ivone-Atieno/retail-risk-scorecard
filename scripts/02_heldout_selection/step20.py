# ===== STEP 20: pilot / go-no-go. EXTRACTION QA ONLY: no scores are computed anywhere in this cell. =====
import json, re
import numpy as np, pandas as pd
from pathlib import Path

for nm in ["BASE", "RAW", "companies"]:
    if nm not in globals():
        raise NameError(f"{nm} is not defined: run your start-of-session cell first")
HO = BASE / "heldout"
START = "2014-01-01"          # the new history start (the old helper used 2019-01-01)

# ---------- reading one company's facts ----------
def facts_of(path):
    return json.load(open(path))["facts"]["us-gaap"]

def recs(facts, tag, start=START):
    r = facts.get(tag, {}).get("units", {}).get("USD", [])
    if not r:
        return pd.DataFrame(columns=["start", "end", "val", "filed", "days"])
    d = pd.DataFrame(r)
    if "start" not in d: d["start"] = np.nan
    for c in ["start", "end", "filed"]: d[c] = pd.to_datetime(d[c])
    d["days"] = (d["end"] - d["start"]).dt.days
    return d[d["end"] >= start]

def inst(facts, tag, start=START):
    """Balance-sheet (instant) values of one tag, earliest-filed value per period end."""
    d = recs(facts, tag, start)
    d = d[d["days"].isna()]
    return d.sort_values("filed").drop_duplicates("end", keep="first").set_index("end")["val"]

# ---------- debt definitions (simple, tag-based) ----------
LT_TOTAL  = ["LongTermDebt"]
LT_NONCUR = ["LongTermDebtNoncurrent"]
LT_CUR    = ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]
SHORT     = ["ShortTermBorrowings", "LineOfCredit", "CommercialPaper", "NotesPayableCurrent", "ShortTermBankLoansAndNotesPayable"]
OTHER_LT  = ["LongTermNotesPayable", "SeniorNotesNoncurrent", "SeniorLongTermNotes", "ConvertibleNotesPayable", "ConvertibleDebtNoncurrent",
             "SecuredDebt", "NotesPayable", "LongTermLineOfCredit", "LongTermDebtAndCapitalLeaseObligations", "ConvertibleDebt"]
ALL_DEBT_TAGS = LT_TOTAL + LT_NONCUR + LT_CUR + SHORT + OTHER_LT

def first_avail(facts, tags):
    s = [inst(facts, t) for t in tags]
    s = [x for x in s if len(x)]
    return pd.concat(s, axis=1).bfill(axis=1).iloc[:, 0] if s else pd.Series(dtype=float)

def debt_defs(facts):
    """A: LongTermDebt if present, else noncurrent + current.  B: A + short-term borrowings / revolver.  Missing pieces count as 0 only when
    at least one long-term piece exists for that period end."""
    tot, non, cur = first_avail(facts, LT_TOTAL), first_avail(facts, LT_NONCUR), first_avail(facts, LT_CUR)
    sh = first_avail(facts, SHORT)
    idx = pd.DatetimeIndex(list(tot.index) + list(non.index) + list(cur.index)).unique()
    A = pd.Series(index=idx, dtype=float)
    for e in idx:
        if e in tot.index: A[e] = tot[e]
        elif e in non.index: A[e] = non[e] + (cur[e] if e in cur.index else 0.0)
        elif e in cur.index: A[e] = cur[e]
    B = A.copy()
    for e in pd.DatetimeIndex(list(sh.index) + list(A.index)).unique():
        B[e] = (A[e] if e in A.index and pd.notna(A[e]) else 0.0) + (sh[e] if e in sh.index else 0.0)
    A.index = pd.DatetimeIndex(A.index); B.index = pd.DatetimeIndex(B.index)
    return A.sort_index(), B.sort_index()

# ======================================================================
# PART A. Facts layer: is the older history clean for the 20 design companies?
# ======================================================================
print("PART A: design companies, facts from", START[:4], "onward (checks only; nothing is scored)\n")
tick_all = list(companies["ticker"])
cik_of = dict(zip(companies["ticker"], companies["cik"].astype(int)))
rowsA = []
for tk in tick_all:
    f = facts_of(RAW / f"{cik_of[tk]:010d}.json")
    rv = None
    for t in ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet"]:
        d = recs(f, t)
        if len(d): rv = d if rv is None else pd.concat([rv, d])
    old = rv[rv["end"] >= "2019-01-01"] if rv is not None else None
    qdur = rv[(rv["days"] >= 80) & (rv["days"] <= 105)] if rv is not None else None
    inv = inst(f, "InventoryNet")
    by_year = inv.groupby(inv.index.year).size() if len(inv) else pd.Series(dtype=int)
    rowsA.append(dict(ticker=tk,
                      rev_rows_all=0 if rv is None else len(rv),
                      rev_rows_2019plus=0 if old is None else len(old),
                      rev_rows_gained=0 if rv is None else len(rv) - len(old),
                      rev_quarter_periods_2014_18=0 if qdur is None else qdur[qdur["end"] < "2019-01-01"]["end"].nunique(),
                      inv_ends_2014_18=int(by_year[by_year.index < 2019].sum()) if len(by_year) else 0))
A = pd.DataFrame(rowsA)
print("A1. rows gained by moving the start, and quarterly revenue periods and inventory period ends in 2014-2018 (a full 5 years = about 15-20):")
print(A.to_string(index=False), "\n")
bad = A[(A.rev_quarter_periods_2014_18 < 10) | (A.inv_ends_2014_18 < 12)]
print("A2. design companies with thin 2014-2018 data (fewer than 10 quarterly revenue periods or 12 inventory ends):", list(bad.ticker) or "none", "\n")

# ======================================================================
# PART B. Debt calibration on the design companies (2019+): which simple definition reproduces the design Debt?
# ======================================================================
print("PART B: do the simple tag-based definitions A and B reproduce the design pipeline's Debt (debt_quarterly_final.csv) for 2019 onward?")
dq = pd.read_csv(BASE / "debt_quarterly_final.csv", parse_dates=["end"])
rowsB = []
for tk in tick_all:
    f = facts_of(RAW / f"{cik_of[tk]:010d}.json")
    A_, B_ = debt_defs(f)
    ref = dq[(dq.ticker == tk) & dq.total_m.notna() & (dq.end >= "2019-01-01")].copy()
    if ref.empty:
        rowsB.append(dict(ticker=tk, n_ref=0)); continue
    out = dict(ticker=tk, n_ref=len(ref))
    for nm, S in [("A", A_), ("B", B_)]:
        errs = []
        for _, r in ref.iterrows():
            if not len(S): continue
            j = S.index[np.abs((S.index - r.end).days) <= 5]
            if len(j) == 0: continue
            v = S.loc[j[0]]
            errs.append(abs(v / 1e6 - r.total_m) / max(abs(r.total_m), 1.0))
        out[f"{nm}_matched"] = len(errs)
        out[f"{nm}_within5pct"] = round(float(np.mean(np.array(errs) <= 0.05)), 2) if errs else np.nan
    rowsB.append(out)
B = pd.DataFrame(rowsB)
print(B.to_string(index=False))
print("\nReading: 'within5pct' = share of matched quarters where the simple definition is within 5% of the design Debt (for tiny debt amounts the error is measured against 1m).")
print("Companies where neither definition matches are exactly where the design pipeline used a formula or manual override, so the held-out versions of those companies need a closer look.\n")

# ======================================================================
# PART C. Held-out failed companies: debt coverage 2014 to the event, and what debt-like tags exist
# ======================================================================
print("PART C: held-out failed companies (extraction QA, no scores)")
ev = pd.read_csv(HO / "failed_events_checked.csv")
ev = ev[ev["event_8k_date"].notna()].copy()
ev["event_8k_date"] = pd.to_datetime(ev["event_8k_date"])
skip_name = ("Container Store",)
rowsC, probes = [], {}
for _, r in ev.iterrows():
    if any(s in str(r["name"]) for s in skip_name): continue
    p = HO / "raw" / f"{int(r['cik']):010d}.json"
    if not p.exists():
        rowsC.append(dict(name=r["name"], note="no raw file")); continue
    f = facts_of(p)
    A_, B_ = debt_defs(f)
    e0 = r["event_8k_date"]
    pre = lambda S: S[(S.index < e0)] if len(S) else S
    Ap, Bp = pre(A_), pre(B_)
    inv = pre(inst(f, "InventoryNet"))
    tags_present = {t: len(inst(f, t)) for t in ALL_DEBT_TAGS if len(inst(f, t))}
    # any other tag that looks like debt
    extra = {k: len(inst(f, k)) for k in f if re.search(r"Debt|Borrow|Revolv|CreditFacility|NotesPayable|TermLoan|Loan", k) and k not in ALL_DEBT_TAGS}
    extra = {k: v for k, v in sorted(extra.items(), key=lambda x: -x[1]) if v >= 4}
    probes[r["name"]] = (tags_present, dict(list(extra.items())[:6]))
    rowsC.append(dict(name=r["name"], event=str(e0.date()),
                      inv_ends_pre_event=len(inv),
                      debtA_ends=int(Ap.notna().sum()) if len(Ap) else 0,
                      debtB_ends=int(Bp.notna().sum()) if len(Bp) else 0,
                      debtB_nonzero=int((Bp.fillna(0) > 0).sum()) if len(Bp) else 0,
                      first_debt_end=str(Bp.dropna().index.min().date()) if len(Bp.dropna()) else "none"))
C = pd.DataFrame(rowsC)
C["verdict"] = np.where(C.get("debtB_ends", 0) >= 8, "OK (>=8 debt ends)",
                np.where(C.get("inv_ends_pre_event", 0) >= 8, "CHECK DEBT BY HAND", "THIN"))
print(C.to_string(index=False), "\n")
print("Debt-like tags found for companies not marked OK (tag: number of period ends); 'other' tags are not in my definitions yet:")
for nm in C[C.verdict != "OK (>=8 debt ends)"]["name"]:
    print(f"  {nm}: defined tags {probes[nm][0]} | other tags {probes[nm][1]}")

A.to_csv(HO / "pilot_A_facts_layer.csv", index=False); B.to_csv(HO / "pilot_B_debt_calibration.csv", index=False); C.to_csv(HO / "pilot_C_heldout_debt.csv", index=False)
n_ok = int((C.verdict == "OK (>=8 debt ends)").sum())
print(f"\nGO/NO-GO INPUT: {n_ok} held-out failed companies have at least 8 debt period ends before the event on the simple definition B (need 12 after hand checks).")
print("saved: pilot_A_facts_layer.csv, pilot_B_debt_calibration.csv, pilot_C_heldout_debt.csv in", HO)
