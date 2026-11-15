# ===== STEP 43: held-out inputs + your own cleaning cells (Steps 1-9) re-run from 2014 + regression test. NO SCORES. =====
# HOW TO RUN: upload this file to your retail_risk_project folder in Drive, then in a notebook cell run:
#     exec(open(str(BASE / "heldout_pipeline.py")).read())
# It needs these names from your session: BASE, RAW, companies, cov, tm (the design tables, exactly as printed in your schema check).
# It writes ONLY inside BASE/heldout_pipeline/. Your design files are read, never changed. Each embedded cleaning cell writes its long printout to
# BASE/heldout_pipeline/logs/<cell>.log; this script prints only short summaries. Expect 3-8 minutes.
import json, io, re, contextlib, traceback
from pathlib import Path
import numpy as np, pandas as pd
for _nm in ["BASE", "RAW", "companies", "cov", "tm"]:
    if _nm not in globals(): raise NameError(f"{_nm} is not defined: run your start-of-session cell and load companies, cov and tm first")
START_NEW = "2014-01-01"; DATE_WINDOW = 2; EXTEND_REFERENCE = True; APPLY_OVERLAP_RULE = True; MIN_COVERAGE = 0.85               # DATE_WINDOW = Step 2 merge window in days (verified against your clean_02_dates.csv in Step 42)
BASE_D = Path(BASE); RAW_D = Path(RAW); HO = BASE_D / "heldout"; CT = HO / "controls"; HP = BASE_D / "heldout_pipeline"
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
TICK = {"Sears": "SHLD", "Bon-Ton": "BONT", "Pier 1": "PIR", "Stein Mart": "SMRT", "Stage": "SSI", "Penney": "JCP", "Tailored": "TLRD", "Ascena": "ASNA",
        "francesca": "FRAN", "RTW": "RTW", "GNC": "GNC", "Fred": "FRED", "Destination": "DEST", "hhgregg": "HGG", "Gordmans": "GMAN",
        "Aeropostale": "ARO", "Pacific Sunwear": "PSUN", "LL Flooring": "LL", "iMedia": "IMBI"}     # same mapping as Step 30
BLANKS = [("Duluth", "2017-01-29"), ("Hibbett", "2019-02-02")]                                       # protocol v1.2 section 11: quarter-level blank rule
REVP  = ["RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]   # last one added in v4: it is in your Step 31 coverage list but was missing from the Step 24 list
COSTP = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]
INVP  = ["InventoryNet", "InventoryFinishedGoodsNetOfReserves", "InventoryFinishedGoods", "RetailRelatedInventoryMerchandise", "MerchandiseInventoryNet", "RetailRelatedInventory"]   # last one added in v4 (Sportsman's Warehouse reports its inventory under it)
# (same priority lists as Step 24; they are the lists the held-out failed companies were mapped with)

# ------------------------------------------------------------------ embedded cleaning cells (your own code; patches listed in PATCHES) ------------------------------------------------------------------
SRC = {}
SRC['helpers'] = r'''# ===== HELPERS (run once per session, after your start-of-session cell) =====
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
'''
SRC['step1'] = r'''# ===== STEP 1: flat "long" table of every fact (all tags, all filings) =====
rows = []
want = cov[cov["metric"].isin(FLOW + BAL)]
for tk in companies["ticker"]:
    facts = load_facts(tk)
    for _, r in want[want["ticker"] == tk].iterrows():
        d = recs_df(facts, r["tag"])
        if d.empty:
            continue
        d = d.copy()
        d["ticker"] = tk; d["metric"] = r["metric"]; d["tag"] = r["tag"]
        d["ptype"] = d["days"].map(ptype)
        rows.append(d)

long_df = pd.concat(rows, ignore_index=True)
keep = ["ticker", "metric", "tag", "start", "end", "days", "ptype", "val", "filed", "form", "fy", "fp"]
long_df = (long_df[[c for c in keep if c in long_df.columns]]
           .sort_values(["ticker", "metric", "tag", "end", "start", "filed"])
           .reset_index(drop=True))
long_df.to_csv(BASE / "clean_01_long.csv", index=False)
print("saved clean_01_long.csv:", len(long_df), "rows\n")

# ---- CHECK 1: rows per company ----
c1 = long_df.groupby("ticker").agg(rows=("val", "size"), tags=("tag", "nunique"),
                                   first_end=("end", "min"), last_end=("end", "max"),
                                   last_filed=("filed", "max"))
print("CHECK 1: rows per company"); print(c1.reindex(companies["ticker"]).to_string(), "\n")

# ---- CHECK 2: metric x period type ----
print("CHECK 2: metric x period type (balance metrics should be all I, flow metrics Q/YTD/A)")
print(pd.crosstab(long_df["metric"], long_df["ptype"]).reindex(FLOW + BAL).fillna(0).astype(int).to_string(), "\n")

# ---- CHECK 3: anything that breaks the pattern ----
bad = long_df[(long_df["metric"].isin(BAL) & (long_df["ptype"] != "I")) |
              (long_df["metric"].isin(FLOW) & (long_df["ptype"].isin(["I", "other"])))]
print("CHECK 3: rows that break the pattern:", len(bad))
if len(bad):
    print(bad.groupby(["ticker", "metric", "ptype", "days"]).size().head(30).to_string())
print()

# ---- CHECK 4: tags in tag_coverage that gave no rows from 2019 on ----
got = set(zip(long_df["ticker"], long_df["tag"]))
miss = [(r["ticker"], r["metric"], r["tag"]) for _, r in want.iterrows()
        if (r["ticker"], r["tag"]) not in got and pd.to_datetime(r["last_end"], errors="coerce") >= pd.Timestamp("2019-01-01")]
print("CHECK 4: tags with data after 2019 that gave no rows:", len(miss))
for m in miss[:20]:
    print("  ", m)
'''
SRC['step2'] = r'''# ===== STEP 2 (rebuilt from its description, verified identical to your clean_02_dates.csv in Step 42): merge period-end dates that differ by a day or two =====
L = pd.read_csv(BASE / "clean_01_long.csv", parse_dates=["start", "end", "filed"])
L["end_raw"] = L["end"]; mp = {}; near = []
for tk, g in L.groupby("ticker"):
    cnt = g["end"].value_counts().sort_index(); ds = list(cnt.index); grp = [[ds[0]]] if ds else []
    for d in ds[1:]:
        (grp[-1].append(d) if (d - grp[-1][-1]).days <= DATE_WINDOW else grp.append([d]))
        if DATE_WINDOW < (d - ds[ds.index(d) - 1]).days <= 5: near.append((tk, str(ds[ds.index(d) - 1].date()), str(d.date()), (d - ds[ds.index(d) - 1]).days))
    for gr in grp:
        if len(gr) > 1:
            keep = max(gr, key=lambda d: (cnt[d], d))
            for d in gr: mp[(tk, d)] = keep
L["end"] = [mp.get((t, e), e) for t, e in zip(L["ticker"], L["end"])]
L.to_csv(BASE / "clean_02_dates.csv", index=False)
print("saved clean_02_dates.csv:", len(L), "rows; rows relabelled:", int((L["end"] != L["end_raw"]).sum()))
print("merged date groups (company, dropped date -> kept date):", [(t, str(a.date()), str(k.date())) for (t, a), k in mp.items() if a != k])
print("period-end dates 3 to 5 days apart that were NOT merged (check these by eye):", near)
'''
SRC['step3'] = r'''# ===== STEP 3: one value per period (earliest-filed; DBI gross profit = latest-filed) =====
df = pd.read_csv(BASE / "clean_02_dates.csv", parse_dates=["start", "end", "filed", "end_raw"])
key = ["ticker", "metric", "tag", "end", "ptype"]
n_before = len(df)

df = df.sort_values(key + ["filed"], kind="stable")
first = df.drop_duplicates(key, keep="first").rename(columns={"val": "val_first", "filed": "filed_first"})
last = (df.drop_duplicates(key, keep="last")[key + ["val", "filed"]]
        .rename(columns={"val": "val_last", "filed": "filed_last"}))
nver = df.groupby(key).size().rename("n_versions").reset_index()
out = first.merge(last, on=key).merge(nver, on=key)

use_last = (out["ticker"] == "DBI") & (out["metric"] == "GrossProfit")   # reclassification restatement
out["val"] = out["val_first"].where(~use_last, out["val_last"])
out["filed"] = out["filed_first"].where(~use_last, out["filed_last"])
out["chg_pct"] = np.where(out["val_first"] != 0, (out["val_last"] / out["val_first"] - 1) * 100, np.nan)

cols = ["ticker", "metric", "tag", "start", "end", "days", "ptype", "val", "filed",
        "val_first", "filed_first", "val_last", "filed_last", "n_versions", "chg_pct", "form", "fy", "fp", "end_raw"]
out = out[[c for c in cols if c in out.columns]].sort_values(["ticker", "metric", "tag", "end", "ptype"]).reset_index(drop=True)
out.to_csv(BASE / "clean_03_asof.csv", index=False)

print("saved clean_03_asof.csv: rows", n_before, "->", len(out))
print("duplicate keys left:", int(out.duplicated(key).sum()), "\n")
print("versions per period:"); print(out["n_versions"].value_counts().sort_index().to_string(), "\n")

prim = set(zip(tm["ticker"], tm["metric"], tm["primary_tag"]))
op = out[[(t, m, g) in prim for t, m, g in zip(out["ticker"], out["metric"], out["tag"])]]
chg = op[op["chg_pct"].abs() > 1]
print("PRIMARY-TAG periods that changed more than 1% between first and last filing (count, largest %):")
print(chg.groupby(["ticker", "metric"])["chg_pct"].agg(periods="size", biggest=lambda s: s.loc[s.abs().idxmax()]).round(2).to_string(), "\n")
print("WMT Revenue periods that changed at all:", int((op[(op.ticker == "WMT") & (op.metric == "Revenue")]["chg_pct"].abs() > 0).sum()))
d = out[use_last & (out["n_versions"] > 1)]
print("DBI GrossProfit exception applied: rows", len(d), "| all use latest value:", bool((d["val"] == d["val_last"]).all()))
'''
SRC['step4'] = r'''# ===== STEP 4: one tag per company/metric (stitch by priority) =====
df = pd.read_csv(BASE / "clean_03_asof.csv", parse_dates=["start", "end", "filed", "filed_first", "filed_last", "end_raw"])

STITCH = {
    ("PLCE", "Revenue"):   ["RevenueFromContractWithCustomerExcludingAssessedTax",
                            "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet"],
    ("PRTY", "Revenue"):   ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                            "RevenueFromContractWithCustomerIncludingAssessedTax"],
    ("PLCE", "NetIncome"): ["NetIncomeLoss", "ProfitLoss"],
    ("PLCE", "Capex"):     ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    ("WOOF", "Equity"):    ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
}
DERIVE_ALL = {("COST", "GrossProfit"), ("DBI", "CostOfGoods")}   # always derived (Step 8), reported tag not used

parts, gaps = [], []
for tk in companies["ticker"]:
    for m in FLOW + BAL:
        if (tk, m) in DERIVE_ALL:
            continue
        prio = STITCH.get((tk, m)) or [primary(tk, m)]
        prio = [p for p in prio if p]
        if not prio:
            continue
        sub = df[(df.ticker == tk) & (df.metric == m)]
        use = sub[sub.tag.isin(prio)].copy()
        use["rank"] = use["tag"].map({p: i for i, p in enumerate(prio)})
        use = use.sort_values(["end", "ptype", "rank"]).drop_duplicates(["end", "ptype"], keep="first")
        use["tag_used"] = use["tag"]
        use["stitched"] = use["rank"] > 0
        parts.append(use.drop(columns=["rank"]))
        # periods that exist under some OTHER tag but are empty in the chosen series
        have = set(zip(use["end"], use["ptype"]))
        oth = sub[~sub.tag.isin(prio)]
        miss = oth[[(e, p) not in have for e, p in zip(oth["end"], oth["ptype"])]]
        if len(miss):
            gaps.append(dict(ticker=tk, metric=m, periods=miss[["end", "ptype"]].drop_duplicates().shape[0],
                             other_tags=", ".join(sorted(miss["tag"].unique()))[:80]))

st = pd.concat(parts, ignore_index=True).sort_values(["ticker", "metric", "end", "ptype"]).reset_index(drop=True)
st.to_csv(BASE / "clean_04_stitched.csv", index=False)
print("saved clean_04_stitched.csv:", len(st), "rows (from", len(df), ")")
print("duplicate (company, metric, end, type) keys:", int(st.duplicated(["ticker", "metric", "end", "ptype"]).sum()), "\n")

print("STITCHED SERIES: rows taken from each tag")
for (tk, m) in STITCH:
    print(f"  {tk} {m}:", st[(st.ticker == tk) & (st.metric == m)]["tag_used"].value_counts().to_dict())
print()
print("PERIODS PRESENT UNDER ANOTHER TAG BUT EMPTY IN THE CHOSEN SERIES (possible fills, to review):")
print(pd.DataFrame(gaps).to_string(index=False) if gaps else "  none")
'''
SRC['step4b'] = r'''# ===== STEP 4b: fallback tags for the gaps found in Step 4 =====
df = pd.read_csv(BASE / "clean_03_asof.csv", parse_dates=["start", "end", "filed", "filed_first", "filed_last", "end_raw"])
st = pd.read_csv(BASE / "clean_04_stitched.csv", parse_dates=["start", "end", "filed", "filed_first", "filed_last", "end_raw"])
st["fallback"] = False

PLCE_EQ = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
FALLBACK = {("PLCE", "CostOfGoods"): "CostOfGoodsSold",
            ("PLCE", "Equity"): PLCE_EQ,
            ("DBI", "NetIncome"): "ProfitLoss",
            ("RAD", "Capex"): "PaymentsToAcquireProductiveAssets",
            ("PRTY", "Equity"): PLCE_EQ,
            ("EXPR", "CostOfGoods"): "CostOfGoodsAndServicesSold"}

report, adds = [], []
for (tk, m), alt in FALLBACK.items():
    cur = st[(st.ticker == tk) & (st.metric == m)]
    a = df[(df.ticker == tk) & (df.metric == m) & (df.tag == alt)]
    both = cur.merge(a, on=["end", "ptype"], suffixes=("", "_alt"))
    nover = len(both)
    mx = (((both["val_alt"] / both["val"]) - 1).abs() * 100).max() if nover else np.nan
    have = set(zip(cur["end"], cur["ptype"]))
    cand = a[[(e, p) not in have for e, p in zip(a["end"], a["ptype"])]].copy()
    ok = (nover == 0) or (mx <= 1.0)
    note = ("verified (agrees within 1%)" if nover and mx <= 1.0 else
            "unverified (no overlap to test)" if nover == 0 else "REJECTED (differs by more than 1%)")
    report.append(dict(ticker=tk, metric=m, alt_tag=alt[:45], overlap=nover,
                       max_diff_pct=round(mx, 2) if nover else "", candidates=len(cand), decision=note))
    if ok and len(cand):
        cand["tag_used"] = alt; cand["stitched"] = True; cand["fallback"] = True
        adds.append(cand)

print("FALLBACK DECISIONS:"); print(pd.DataFrame(report).to_string(index=False), "\n")
st2 = pd.concat([st] + adds, ignore_index=True).sort_values(["ticker", "metric", "end", "ptype"]).reset_index(drop=True)
st2.to_csv(BASE / "clean_04b_stitched.csv", index=False)
print("saved clean_04b_stitched.csv:", len(st2), "rows (added", int(st2["fallback"].sum()), "fallback rows)")
print("duplicate keys:", int(st2.duplicated(["ticker", "metric", "end", "ptype"]).sum()))
print("\nFilled periods:")
print(st2[st2["fallback"]][["ticker", "metric", "end", "ptype", "val"]].to_string(index=False))
'''
SRC['step5c'] = r'''# ===== STEP 5c: quarterly values with filing dates, a conflict rule and the DBI basis fix =====
st = pd.read_csv(BASE / "clean_04b_stitched.csv", parse_dates=["start", "end", "filed"])
flows = st[st.metric.isin(FLOW) & st.ptype.isin(["Q", "YTD", "A"])]
DBI_BAD = pd.Timestamp("2023-01-28")     # DBI Q4 FY2022 gross profit: restated annual minus unrestated 9-month = not a real number
DBI_BREAK = pd.Timestamp("2023-04-29")   # first DBI quarter on the restated basis

res, unplaced, recon, dropped = [], [], [], []
for tk in companies["ticker"]:
    grid = sorted(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique())
    if len(grid) < 2:
        continue
    g = pd.DatetimeIndex(grid)

    def gidx(d):
        diff = np.abs((g - d).days); pos = int(diff.argmin())
        return pos if diff[pos] <= 5 else None

    for m in FLOW:
        x = flows[(flows.ticker == tk) & (flows.metric == m)]
        V, VA = {}, {}
        for _, r in x.iterrows():
            i = gidx(r["start"] - pd.Timedelta(days=1)); j = gidx(r["end"])
            if i is None or j is None or j <= i:
                unplaced.append((tk, m, r["ptype"], str(r["start"].date()), str(r["end"].date()))); continue
            V.setdefault((i, j), (r["val"], r["filed"]))
            if r["ptype"] == "A":
                VA.setdefault((i, j), r["val"])
        q = {}

        def cum(a, k):
            if (a, k) in V: return V[(a, k)]
            ks = range(a + 1, k + 1)
            if all(t in q for t in ks):
                return (sum(q[t]["val"] for t in ks), max(q[t]["filed"] for t in ks))
            return None

        for k in range(1, len(g)):
            der = None
            for a in range(k - 2, -1, -1):
                if (a, k) in V:
                    c = cum(a, k - 1)
                    if c is not None:
                        der = (V[(a, k)][0] - c[0], max(V[(a, k)][1], c[1])); break
            rep = V.get((k - 1, k))
            if rep is None and der is None:
                continue
            conflict, other = False, None
            if der is None:
                pick, src = rep, "reported"
            elif rep is None:
                pick, src = der, "derived"
            else:
                pick, src, other = rep, "reported", der
                diff = abs(der[0] - rep[0])
                conflict = (diff > 2e6) and (diff > 0.005 * abs(rep[0]))
                if conflict and not (tk == "DBI" and m == "GrossProfit") and der[1] < rep[1]:
                    pick, src, other = der, "derived (earlier filing wins)", rep
            q[k] = dict(val=pick[0], filed=pick[1], src=src, alt_val=other[0] if other else np.nan,
                        alt_filed=other[1] if other else pd.NaT, conflict=conflict)
        if tk == "DBI" and m == "GrossProfit":
            for k in [k for k in q if g[k] == DBI_BAD]:
                dropped.append((tk, m, str(g[k].date()), round(q[k]["val"] / 1e6, 1))); del q[k]
        for k, v in q.items():
            basis = ("old" if g[k] < DBI_BREAK else "new") if (tk == "DBI" and m == "GrossProfit") else ""
            res.append(dict(ticker=tk, metric=m, end=g[k], val=v["val"], filed=v["filed"], src=v["src"],
                            alt_val=v["alt_val"], alt_filed=v["alt_filed"], conflict=v["conflict"], basis=basis))
        for (a, j), av in VA.items():
            ks = range(a + 1, j + 1)
            if all(t in q for t in ks):
                recon.append(dict(ticker=tk, metric=m, year_end=g[j], annual=av, sum_q=sum(q[t]["val"] for t in ks)))

qdf = pd.DataFrame(res).sort_values(["ticker", "metric", "end"]).reset_index(drop=True)
qdf.to_csv(BASE / "clean_05c_quarters.csv", index=False)
print("saved clean_05c_quarters.csv:", len(qdf), "quarterly values (previous version: 2578)")
print("dropped on purpose:", dropped, "| rows with no filing date:", int(qdf["filed"].isna().sum()), "\n")

print("CHECK 1: source of each quarterly value")
print(pd.crosstab(qdf["metric"], qdf["src"]).reindex(FLOW).fillna(0).astype(int).to_string(), "\n")

cf = qdf[qdf["conflict"]].copy()
print("CHECK 2: reported vs rebuilt disagree by more than 0.5% and $2m:", len(cf))
if len(cf):
    cf["val_m"] = (cf["val"] / 1e6).round(1); cf["other_m"] = (cf["alt_val"] / 1e6).round(1)
    print(cf[["ticker", "metric", "end", "src", "val_m", "other_m", "filed", "alt_filed"]].to_string(index=False))
print()

rc = pd.DataFrame(recon)
if len(rc):
    rc["diff_pct"] = (rc.sum_q - rc.annual).abs() / rc.annual.abs().replace(0, np.nan) * 100
    print("CHECK 3: four quarters vs annual:", len(rc), "years tested; over 0.5%:", int((rc.diff_pct > 0.5).sum()))
    bad = rc[rc.diff_pct > 0.5].sort_values("diff_pct", ascending=False)
    if len(bad):
        print(bad.assign(annual_m=(bad.annual / 1e6).round(1), sum_m=(bad.sum_q / 1e6).round(1), diff_pct=bad.diff_pct.round(2))
              [["ticker", "metric", "year_end", "annual_m", "sum_m", "diff_pct"]].to_string(index=False))
else:
    print("CHECK 3: no complete years to test")
print()

co = pd.read_csv(BASE / "companies.csv", parse_dates=["distress_date"])
rows = []
for _, r in co[co["group"] == "failed"].iterrows():
    z = qdf[qdf.ticker == r.ticker]
    late = z[z.filed > r.distress_date]
    rows.append(dict(ticker=r.ticker, distress=r.distress_date.date(), quarter_values=len(z),
                     filed_after_distress=len(late), quarter_ends_affected=late["end"].nunique(),
                     last_usable_end=z[z.filed <= r.distress_date]["end"].max().date()))
print("CHECK 4: what the as-of filter will remove for the failed companies")
print(pd.DataFrame(rows).to_string(index=False))
print("\nrows that could not be placed on the quarter grid:", len(unplaced), "(reasons were shown in Step 5b)")
'''
SRC['step6'] = r'''# ===== STEP 6: derive gross profit / cost of goods where the agreed rule says so =====
q = pd.read_csv(BASE / "clean_05c_quarters.csv", parse_dates=["end", "filed", "alt_filed"])
q["basis"] = q["basis"].fillna("")
V = q.pivot(index=["ticker", "end"], columns="metric", values="val")
F = q.pivot(index=["ticker", "end"], columns="metric", values="filed")
basis_gp = q[q.metric == "GrossProfit"].set_index(["ticker", "end"])["basis"].to_dict()

DERIVE_GP = ["WMT", "COST", "TGT", "TJX", "ROST", "KSS", "M", "JOAN", "CONN"]   # gross profit = revenue - cost of goods
DERIVE_COGS = ["PLCE", "DBI"]                                                  # cost of goods = revenue - gross profit
add = []
for (tk, end), row in V.iterrows():
    rev, cg, gp = row.get("Revenue"), row.get("CostOfGoods"), row.get("GrossProfit")
    if tk in DERIVE_GP and pd.isna(gp) and pd.notna(rev) and pd.notna(cg):
        add.append(dict(ticker=tk, metric="GrossProfit", end=end, val=rev - cg,
                        filed=max(F.loc[(tk, end), "Revenue"], F.loc[(tk, end), "CostOfGoods"]), src="derived (rule)", basis=""))
    if tk in DERIVE_COGS and pd.isna(cg) and pd.notna(rev) and pd.notna(gp):
        add.append(dict(ticker=tk, metric="CostOfGoods", end=end, val=rev - gp,
                        filed=max(F.loc[(tk, end), "Revenue"], F.loc[(tk, end), "GrossProfit"]), src="derived (rule)",
                        basis=basis_gp.get((tk, end), "")))
a = pd.DataFrame(add)
q2 = pd.concat([q, a], ignore_index=True).sort_values(["ticker", "metric", "end"]).reset_index(drop=True)
q2.to_csv(BASE / "clean_06_quarters.csv", index=False)
print("saved clean_06_quarters.csv:", len(q2), "rows (added", len(a), ")\n")
print("ADDED BY THE RULE:"); print(a.groupby(["ticker", "metric"]).size().to_string(), "\n")

P = q2.pivot(index=["ticker", "end"], columns="metric", values="val")
P["margin"] = P["GrossProfit"] / P["Revenue"] * 100
mt = P["margin"].dropna().reset_index()
print("CHECK 1: gross margin % by company (quarters, min, median, max)")
s = mt.groupby("ticker")["margin"].agg(quarters="size", min="min", median="median", max="max").round(1)
print(s.reindex(companies["ticker"]).to_string(), "\n")

low = mt[mt["margin"] < 10].copy(); low["margin"] = low["margin"].round(1)
print("CHECK 2: quarters with gross margin below 10% (expect the 2020 COVID closures):")
print(low.to_string(index=False), "\n")

gp_rep = q2[(q2.metric == "GrossProfit") & (q2.src != "derived (rule)")].set_index(["ticker", "end"])["val"]
cg_rep = q2[(q2.metric == "CostOfGoods") & (q2.src != "derived (rule)")].set_index(["ticker", "end"])["val"]
chk = pd.concat([gp_rep.rename("gp_reported"), (P["Revenue"] - cg_rep).rename("rev_minus_cogs")], axis=1).dropna()
chk["diff_pct"] = (chk["gp_reported"] - chk["rev_minus_cogs"]).abs() / chk["gp_reported"].abs().replace(0, np.nan) * 100
print("CHECK 3: reported gross profit vs revenue minus cost of goods, where both exist (the rule's own test)")
print(chk.groupby("ticker")["diff_pct"].agg(quarters="size", median="median", biggest="max").round(2).to_string(), "\n")

cnt = q2[q2.metric.isin(["Revenue", "CostOfGoods", "GrossProfit"])].groupby(["ticker", "metric"]).size().unstack().reindex(companies["ticker"]).fillna(0).astype(int)
print("CHECK 4: quarters per company after derivation")
print(cnt.to_string())
'''
SRC['step7'] = r'''# ===== STEP 7: one wide quarterly table (flows + balance sheet + debt) =====
q = pd.read_csv(BASE / "clean_06_quarters.csv", parse_dates=["end", "filed"])
st = pd.read_csv(BASE / "clean_04b_stitched.csv", parse_dates=["start", "end", "filed"])
bal = st[st.metric.isin(BAL) & (st.ptype == "I")]
dbt = pd.read_csv(BASE / "debt_quarterly_final.csv", parse_dates=["end"])

order = list(companies["ticker"])
grid = {tk: pd.DatetimeIndex(sorted(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique())) for tk in order}
W = pd.DataFrame([(tk, e) for tk in order for e in grid[tk]], columns=["ticker", "end"])

for m in FLOW:
    W = W.merge(q[q.metric == m][["ticker", "end", "val", "filed"]].rename(columns={"val": m, "filed": "f_" + m}),
                on=["ticker", "end"], how="left")
for m in BAL:
    W = W.merge(bal[bal.metric == m][["ticker", "end", "val", "filed"]].rename(columns={"val": m, "filed": "f_" + m}),
                on=["ticker", "end"], how="left")

# debt: snap its dates onto the quarter grid (within 5 days), then attach
def snap(tk, d):
    g = grid.get(tk)
    if g is None or len(g) == 0: return pd.NaT
    diff = np.abs((g - d).days); p = int(diff.argmin())
    return g[p] if diff[p] <= 5 else pd.NaT
dbt["end_grid"] = [snap(t, d) for t, d in zip(dbt["ticker"], dbt["end"])]
unmatched = dbt[dbt["end_grid"].isna()]
d2 = dbt.dropna(subset=["end_grid"]).copy()
d2["has"] = d2["total_m"].notna()
d2 = d2.sort_values(["ticker", "end_grid", "has"], ascending=[True, True, False])
n_dup = int(d2.duplicated(["ticker", "end_grid"]).sum())
d2 = d2.drop_duplicates(["ticker", "end_grid"], keep="first")
d2 = d2.rename(columns={"end_grid": "end", "end": "end_raw", "flag": "debt_flag"})
d2["Debt"] = d2["total_m"] * 1e6
W = W.merge(d2[["ticker", "end", "Debt", "debt_flag"]], on=["ticker", "end"], how="left")
W["f_Debt"] = W["f_CurrAssets"].where(W["Debt"].notna())      # debt comes from the same balance sheet filing

V11 = FLOW + BAL + ["Debt"]
W["n_metrics"] = W[V11].notna().sum(axis=1)
W.to_csv(BASE / "clean_07_wide.csv", index=False)
print("saved clean_07_wide.csv:", len(W), "rows x", W.shape[1], "columns\n")

print("CHECK 1: rows per company")
print(W.groupby("ticker").agg(rows=("end", "size"), first=("end", "min"), last=("end", "max")).reindex(order).to_string(), "\n")
print("CHECK 2: how many quarters have a value, per metric")
print(W.groupby("ticker")[V11].count().reindex(order).to_string(), "\n")

W["cur_ratio"] = W["CurrAssets"] / W["CurrLiab"]
W["inv_to_qsales"] = W["Inventory"] / W["Revenue"]
W["debt_to_curr_assets"] = W["Debt"] / W["CurrAssets"]
print("CHECK 3: unit sanity (a unit mistake would show as a 1,000,000x jump)")
s3 = W.groupby("ticker")[["cur_ratio", "inv_to_qsales", "debt_to_curr_assets"]].agg(["min", "median", "max"]).round(2)
print(s3.reindex(order).to_string(), "\n")

print("CHECK 4: debt rows not matched to the grid:", len(unmatched), "| duplicate debt dates merged:", n_dup)
if len(unmatched):
    print(unmatched[["ticker", "end", "total_m", "flag"]].head(15).to_string(index=False))
print(pd.crosstab(W["ticker"], W["debt_flag"].fillna("(no debt row)")).reindex(order).to_string(), "\n")

W["margin"] = W["GrossProfit"] / W["Revenue"] * 100
print("CHECK 5: margin outliers to look at")
t = W[(W.ticker == "TGT") & (W.margin > 31)][["ticker", "end", "Revenue", "CostOfGoods", "GrossProfit", "margin"]].copy()
for c in ["Revenue", "CostOfGoods", "GrossProfit"]: t[c] = (t[c] / 1e6).round(0)
t["margin"] = t["margin"].round(1)
print("TGT quarters above 31%:"); print(t.to_string(index=False) if len(t) else "  none")
dd = W[(W.ticker == "DBI")].tail(6)[["ticker", "end", "Revenue", "GrossProfit", "margin"]].copy()
dd["Revenue"] = (dd["Revenue"] / 1e6).round(0); dd["GrossProfit"] = (dd["GrossProfit"] / 1e6).round(0); dd["margin"] = dd["margin"].round(1)
print("\nDBI latest quarters:"); print(dd.to_string(index=False))
'''
SRC['step8'] = r'''# ===== STEP 8: debt fixes, flags, as-of filter and the final tables =====
V11 = FLOW + BAL + ["Debt"]
FC = ["f_" + m for m in V11]
W = pd.read_csv(BASE / "clean_07_wide.csv", parse_dates=["end"] + FC)

# 1) debt values read directly from the filings (balance sheet, us-gaap, no dimensions)
FIX = [("BIG", "2022-04-30", 270.8, "2022-06-08", "10-Q balance sheet: LongTermDebtNoncurrent (our formula missed this tag)"),
       ("BIG", "2022-07-30", 252.6, "2022-09-07", "10-Q balance sheet: LongTermDebtNoncurrent"),
       ("BIG", "2022-10-29", 459.9, "2022-12-07", "10-Q balance sheet: LongTermDebtNoncurrent"),
       ("BIG", "2023-04-29", 501.6, "2023-06-07", "10-Q balance sheet: LongTermDebtNoncurrent"),
       ("EXPR", "2019-11-02", 0.0, "2019-12-11", "10-Q: current and total liabilities tie out exactly with no borrowings line")]
for tk, d, v, filed, why in FIX:
    m = (W.ticker == tk) & (W.end == pd.Timestamp(d))
    assert m.sum() == 1, (tk, d, "row not found")
    assert W.loc[m, "Debt"].isna().all(), (tk, d, "already has a debt value, not overwriting")
    W.loc[m, "Debt"] = v * 1e6; W.loc[m, "debt_flag"] = "MANUAL (filing)"; W.loc[m, "f_Debt"] = pd.Timestamp(filed)
pd.DataFrame(FIX, columns=["ticker", "end", "debt_m", "filed", "source"]).to_csv(BASE / "debt_gap_overrides.csv", index=False)

# 2) flags
W["tariff_refund_quarter"] = W["end"] >= pd.Timestamp("2026-07-31")      # TGT and ROST verified; others not checked
W["gp_basis"] = np.where(W["ticker"] == "DBI", np.where(W["end"] < pd.Timestamp("2023-04-29"), "old", "new"), "")

# 3) distress dates, quarters relative to failure, as-of filter
co = pd.read_csv(BASE / "companies.csv", parse_dates=["distress_date"])[["ticker", "group", "distress_date"]]
W = W.merge(co, on="ticker", how="left").sort_values(["ticker", "end"]).reset_index(drop=True)
W["pos"] = W.groupby("ticker").cumcount()
last_ok = {}
for tk, g in W.groupby("ticker"):
    dd = g["distress_date"].iloc[0]
    if pd.isna(dd): continue
    ok = g[g["f_CurrAssets"] <= dd]
    last_ok[tk] = int(ok["pos"].max()) if len(ok) else -1
W["q_rel"] = [(p - last_ok[t] - 1) if t in last_ok else np.nan for t, p in zip(W["ticker"], W["pos"])]
W["usable"] = W["q_rel"].isna() | (W["q_rel"] <= -1)

masked = []
for tk, L in last_ok.items():
    dd = W.loc[W.ticker == tk, "distress_date"].iloc[0]
    for m in V11:
        bad = (W.ticker == tk) & W["usable"] & W["f_" + m].notna() & (W["f_" + m] > dd)
        if bad.any():
            masked.append((tk, m, int(bad.sum())))
            W.loc[bad, m] = np.nan; W.loc[bad, "f_" + m] = pd.NaT
W["as_of_date"] = W[FC].max(axis=1)

W.drop(columns=["pos"]).to_csv(BASE / "clean_quarterly_full.csv", index=False)
final = W[W["usable"]].drop(columns=["pos", "usable"]).reset_index(drop=True)
final.to_csv(BASE / "clean_quarterly.csv", index=False)
print("saved clean_quarterly.csv:", len(final), "rows | clean_quarterly_full.csv:", len(W), "rows (all quarters, with flags)\n")

print("CHECK 1: debt values added from the filings")
print(W[(W.ticker == "BIG") & (W.end >= "2022-01-01") & (W.end <= "2023-10-31")][["ticker", "end", "Debt", "debt_flag"]]
      .assign(Debt_m=lambda d: (d["Debt"] / 1e6).round(1)).drop(columns="Debt").to_string(index=False))
print(W[(W.ticker == "EXPR") & (W.end <= "2020-03-01")][["ticker", "end", "Debt", "debt_flag"]]
      .assign(Debt_m=lambda d: (d["Debt"] / 1e6).round(1)).drop(columns="Debt").to_string(index=False), "\n")

EXPECT = {"BBBY (old)": "2022-11-26", "RAD": "2023-06-03", "BIG": "2024-05-04", "PRTY": "2022-09-30",
          "JOAN": "2023-10-28", "EXPR": "2023-10-28", "TUEM": "2022-10-01", "CONN": "2024-01-31"}
rows = []
for tk, exp in EXPECT.items():
    if tk not in set(W.ticker): print("not in data, skipped:", tk); continue
    g = W[(W.ticker == tk) & W["usable"]]
    got = g["end"].max()
    rows.append(dict(ticker=tk, distress=W.loc[W.ticker == tk, "distress_date"].iloc[0].date(), usable_quarters=len(g),
                     dropped_after=int(((W.ticker == tk) & ~W["usable"]).sum()), last_usable=got.date(),
                     matches_earlier_table="PASS" if str(got.date()) == exp else "FAIL (expected " + exp + ")"))
print("CHECK 2: the as-of filter against the usable-history table from Step 1b")
print(pd.DataFrame(rows).to_string(index=False), "\n")
print("CHECK 3: single values removed because they were first filed after the distress date:", masked if masked else "none", "\n")

KEY = ["Revenue", "GrossProfit", "Inventory", "Debt"]
cnt = final.groupby("ticker")[KEY].count()
cnt.insert(0, "quarters", final.groupby("ticker").size())
print("CHECK 4: usable quarters with a value, per company (the 8-quarter minimum applies to each signal)")
print(cnt.reindex(W["ticker"].unique()).to_string())
low = [(t, k, int(cnt.loc[t, k])) for t in cnt.index for k in KEY if cnt.loc[t, k] < 8]
print("below 8:", low if low else "none", "\n")
print("CHECK 5: quarters flagged as tariff-refund quarters:", int(final["tariff_refund_quarter"].sum()),
      "| DBI quarters by gross-profit basis:", final[final.ticker == "DBI"]["gp_basis"].value_counts().to_dict())
'''
SRC['step9'] = r'''# ===== STEP 9: build the quarterly signals (no hypothesis testing yet) =====
Q = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end", "distress_date", "as_of_date", "f_CurrAssets"])
Q = Q.sort_values(["ticker", "end"]).reset_index(drop=True)

# 1) same quarter one year earlier, matched by DATE (not by row position), tolerance 15 days
Q["end_prev"] = Q["end"] - pd.Timedelta(days=364)
cols = ["ticker", "end", "Revenue", "Inventory", "GrossProfit", "Debt", "CurrAssets", "delay_days"]
Q["delay_days"] = (Q["f_CurrAssets"] - Q["end"]).dt.days
P = Q[cols].rename(columns=lambda c: c if c == "ticker" else c + "_py").sort_values("end_py")
Q = pd.merge_asof(Q.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker",
                  tolerance=pd.Timedelta(days=15), direction="nearest").sort_values(["ticker", "end"]).reset_index(drop=True)

# 2) signals
Q["gross_margin"] = Q["GrossProfit"] / Q["Revenue"]
Q["gm_py"] = Q["GrossProfit_py"] / Q["Revenue_py"]
Q["gm_chg_yoy"] = (Q["gross_margin"] - Q["gm_py"]) * 100                      # percentage points
brk = (Q["ticker"] == "DBI") & (Q["end"] >= "2023-04-29") & (Q["end_py"] < "2023-04-29")
Q["basis_break_yoy"] = brk | ((Q["ticker"] == "DBI") & Q["end_py"].isna() & (Q["end"] >= "2023-04-29") & (Q["end"] < "2024-05-01"))
Q.loc[Q["basis_break_yoy"], "gm_chg_yoy"] = np.nan                           # old vs new basis cannot be compared

Q["rev_yoy"] = (Q["Revenue"] / Q["Revenue_py"] - 1) * 100
Q["inv_yoy"] = (Q["Inventory"] / Q["Inventory_py"] - 1) * 100
Q["inv_gap"] = Q["inv_yoy"] - Q["rev_yoy"]                                    # H2: inventory growth minus sales growth
Q["inv_to_rev"] = Q["Inventory"] / Q["Revenue"]

Q["debt_to_ca"] = Q["Debt"] / Q["CurrAssets"]
Q["lev_chg_yoy"] = Q["debt_to_ca"] - Q["Debt_py"] / Q["CurrAssets_py"]
Q["equity_negative"] = Q["Equity"] < 0
Q["debt_to_equity"] = np.where(Q["Equity"] > 0, Q["Debt"] / Q["Equity"], np.nan)
Q["current_ratio"] = Q["CurrAssets"] / Q["CurrLiab"]
Q["ocf_margin"] = Q["OpCashFlow"] / Q["Revenue"] * 100
Q["net_margin"] = Q["NetIncome"] / Q["Revenue"] * 100
Q["delay_chg_yoy"] = Q["delay_days"] - Q["delay_days_py"]                     # H4: filing delay vs same quarter last year
Q["qtd"] = -Q["q_rel"]                                                        # failed companies: 1 = last filed quarter before distress

SIG = ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "current_ratio", "ocf_margin", "delay_chg_yoy"]
keep = ["ticker", "group", "end", "qtd", "distress_date", "tariff_refund_quarter", "gp_basis", "basis_break_yoy", "equity_negative",
        "gross_margin", "gm_chg_yoy", "rev_yoy", "inv_yoy", "inv_gap", "inv_to_rev", "debt_to_ca", "lev_chg_yoy", "debt_to_equity",
        "current_ratio", "ocf_margin", "net_margin", "delay_days", "delay_chg_yoy", "as_of_date"]
F = Q[keep]
F.to_csv(BASE / "features_quarterly.csv", index=False)
print("saved features_quarterly.csv:", len(F), "rows,", F["ticker"].nunique(), "companies\n")

print("CHECK 1: share of rows with a value, by group (a signal needs a prior-year quarter, so each company loses its first year)")
print((F.groupby("group")[SIG].count().div(F.groupby("group").size(), axis=0) * 100).round(0).to_string(), "\n")

print("CHECK 2: ranges, to catch unit errors or extreme values (min / 1st pct / median / 99th pct / max)")
r = F[SIG + ["gross_margin", "debt_to_ca", "inv_to_rev"]].describe(percentiles=[.01, .5, .99]).T[["min", "1%", "50%", "99%", "max"]].round(2)
print(r.to_string(), "\n")

print("CHECK 3: the most extreme single values per signal (verify these before trusting any average)")
for s in ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "current_ratio", "ocf_margin"]:
    x = F.dropna(subset=[s]).reindex(F[s].abs().dropna().sort_values(ascending=False).index).head(3)
    print(s, "->", [(a, str(b.date()), round(c, 2)) for a, b, c in zip(x.ticker, x.end, x[s])])
print()

print("CHECK 4: failed companies, rows with a full set of the five core signals, by quarters before distress")
core = ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "current_ratio", "delay_chg_yoy"]
fl = F[F.group == "failed"].copy(); fl["full"] = fl[core].notna().all(axis=1)
print(fl.groupby("ticker").agg(rows=("end", "size"), full_rows=("full", "sum"), first_full=("end", lambda s: str(s[fl.loc[s.index, "full"]].min().date()) if fl.loc[s.index, "full"].any() else "none")).to_string())
print("\nrows affected by the DBI basis break:", int(F["basis_break_yoy"].sum()), "| negative-equity rows:", int(F["equity_negative"].sum()),
      "| tariff-refund rows:", int(F["tariff_refund_quarter"].sum()))
'''


def _patch(src, old, new, cell):
    assert src.count(old) == 1, f"patch target not found exactly once in {cell}: {old[:60]!r}"
    return src.replace(old, new)
PATCHES = {   # each entry: (cell, text found once in your original cell, replacement). Nothing else in the cells is changed.
    "helpers": [('tm = pd.DataFrame(columns=["ticker","metric","primary_tag"])', 'pass   # PATCH: do not reset tm (it is supplied)'),
                ('return json.load(open(RAW / f"{cik:010d}.json"))["facts"]["us-gaap"]',
                 'return json.load(open(next(p for p in (d / f"{cik:010d}.json" for d in RAWDIRS) if p.exists())))["facts"]["us-gaap"]   # PATCH: several raw folders'),
                ('return d[d["end"] >= "2019-01-01"]', 'return d[d["end"] >= START]   # PATCH: start date is a variable')],
    "step1": [('pd.Timestamp("2019-01-01")', 'pd.Timestamp(START)')],   # PATCH: start date is a variable (only a printed check)
    "step4": [('DERIVE_ALL = {("COST", "GrossProfit"), ("DBI", "CostOfGoods")}', 'DERIVE_ALL = {("COST", "GrossProfit"), ("DBI", "CostOfGoods")}\nSTITCH.update(STITCH_NEW)   # PATCH: priority lists of the added companies'),
              ('use = use.sort_values(["end", "ptype", "rank"]).drop_duplicates(["end", "ptype"], keep="first")',
               'use = use.sort_values((["end", "ptype", "filed", "rank"] if (tk, m) in STITCH_NEW else ["end", "ptype", "rank"])).drop_duplicates(["end", "ptype"], keep="first")   # PATCH v5: for the added companies and the extended reference, the earliest-filed value across the agreeing tags wins (rank only breaks ties)')],
    "step6": [('q2 = pd.concat([q, a], ignore_index=True)', 'GPCHG = []   # PATCH v6: for the added companies, a reported gross profit that equals revenue - cost of goods (within 1%) is public when those two were public, if that is earlier\nfor (tk, end), row in V.iterrows():\n    if tk in NEW_TICKERS and pd.notna(row.get("GrossProfit")) and pd.notna(row.get("Revenue")) and pd.notna(row.get("CostOfGoods")):\n        fd = max(F.loc[(tk, end), "Revenue"], F.loc[(tk, end), "CostOfGoods"]); fg = F.loc[(tk, end), "GrossProfit"]\n        if pd.notna(fd) and pd.notna(fg) and fd < fg and abs(row["GrossProfit"] - (row["Revenue"] - row["CostOfGoods"])) <= 0.01 * abs(row["GrossProfit"]):\n            q.loc[(q.ticker == tk) & (q.end == end) & (q.metric == "GrossProfit"), "filed"] = fd\n            GPCHG.append(dict(ticker=tk, end=str(end.date()), reported_filed=str(fg.date()), now_filed=str(fd.date()), days_earlier=(fg - fd).days))\npd.DataFrame(GPCHG, columns=["ticker", "end", "reported_filed", "now_filed", "days_earlier"]).to_csv(BASE / "gp_earlier_public.csv", index=False)\nq2 = pd.concat([q, a], ignore_index=True)'),
                ('a = pd.DataFrame(add)', 'a = pd.DataFrame(add, columns=["ticker", "metric", "end", "val", "filed", "src", "basis"])'), ('DERIVE_COGS = ["PLCE", "DBI"]', 'DERIVE_COGS = ["PLCE", "DBI"]\nDERIVE_GP = DERIVE_GP + list(NEW_TICKERS)   # PATCH: same rule for the added companies (only fills a missing gross profit)')],
}
ORDER = ["helpers", "step1", "step2", "step3", "step4", "step4b", "step5c", "step6", "step7", "step8", "step9"]

def run_pipeline(outdir, comp, cov_, tm_, start, stitch_new, new_tickers, rawdirs):
    outdir = Path(outdir); (outdir / "logs").mkdir(parents=True, exist_ok=True)
    comp.to_csv(outdir / "companies.csv", index=False)
    ns = dict(pd=pd, np=np, json=json, Path=Path, BASE=outdir, RAW=rawdirs[0], RAWDIRS=rawdirs, START=start, companies=comp.copy(), cov=cov_.copy(), tm=tm_.copy(),
              STITCH_NEW=stitch_new, NEW_TICKERS=list(new_tickers), DATE_WINDOW=DATE_WINDOW)
    for name in ORDER:
        src = SRC[name]
        for old, new in PATCHES.get(name, []): src = _patch(src, old, new, name)
        buf = io.StringIO(); err = None
        try:
            with contextlib.redirect_stdout(buf): exec(compile(src, name, "exec"), ns)
        except Exception: err = traceback.format_exc()
        (outdir / "logs" / f"{name}.log").write_text(buf.getvalue() + ("\n\nERROR\n" + err if err else ""))
        if err: raise RuntimeError(f"cell {name} failed (log: {outdir / 'logs' / (name + '.log')}):\n{err[-1500:]}")
        if name == "helpers": ns["tm"] = tm_.copy()
    return ns

def lev_features(Qc):
    """Steps 13 and 16 (raw parts only): debt / 4-quarter sales and its year-on-year change (lev2), year-on-year % debt growth (lev3)."""
    Qc = Qc.sort_values(["ticker", "end"]).reset_index(drop=True); g = Qc.groupby("ticker")
    Qc["ttm_rev"] = g["Revenue"].transform(lambda s: s.rolling(4, min_periods=4).sum())
    Qc.loc[~(Qc["end"] - g["end"].shift(3)).dt.days.between(240, 300), "ttm_rev"] = np.nan
    Qc["debt_to_sales"] = Qc["Debt"] / Qc["ttm_rev"]
    Qc["end_prev"] = Qc["end"] - pd.Timedelta(days=364)
    P = Qc[["ticker", "end", "debt_to_sales", "Debt"]].rename(columns={"end": "end_py", "debt_to_sales": "ds_py", "Debt": "Debt_py"}).sort_values("end_py")
    Qc = pd.merge_asof(Qc.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker", tolerance=pd.Timedelta(days=15), direction="nearest")
    Qc["lev2_chg_yoy"] = Qc["debt_to_sales"] - Qc["ds_py"]
    Qc["lev3_chg_yoy"] = np.where(Qc["Debt_py"] > 0, (Qc["Debt"] / Qc["Debt_py"] - 1) * 100, np.nan)
    return Qc[["ticker", "end", "ttm_rev", "debt_to_sales", "lev2_chg_yoy", "lev3_chg_yoy"]]

def features_lite(base):
    """features_quarterly.csv (your Step 9) + calendar quarter (Step 10) + leverage signals; raw signals only, no peer adjustment, no COVID blanking (blanking happens at scoring)."""
    F = pd.read_csv(Path(base) / "features_quarterly.csv", parse_dates=["end", "distress_date", "as_of_date"])
    Qc = pd.read_csv(Path(base) / "clean_quarterly.csv", parse_dates=["end"])
    F["cal_q"] = (F["end"] + pd.Timedelta(days=30)).dt.to_period("Q").astype(str)
    F = F.merge(lev_features(Qc), on=["ticker", "end"], how="left")
    F["months_avail"] = (F["distress_date"] - F["as_of_date"]).dt.days / 30.44
    return F

# ------------------------------------------------------------------ PART A: build the inputs ------------------------------------------------------------------
def _usd(f, tag, start):
    r = f.get(tag, {}).get("units", {}).get("USD", [])
    if not r: return pd.DataFrame(columns=["start", "end", "val", "filed", "days"])
    d = pd.DataFrame(r)
    if "start" not in d: d["start"] = np.nan
    for c in ["start", "end", "filed"]: d[c] = pd.to_datetime(d[c])
    d["days"] = (d["end"] - d["start"]).dt.days
    return d[d["end"] >= start]
def _n_ends(f, tag, kind, start, before=None):
    d = _usd(f, tag, start)
    if before is not None: d = d[d["end"] < before]
    d = d[d["days"].isna()] if kind == "inst" else d[d["days"].notna() & (d["days"] >= 80)]
    return d["end"].nunique()
def _facts(cik, rawdirs):
    for d in rawdirs:
        p = Path(d) / f"{int(cik):010d}.json"
        if p.exists(): return json.load(open(p))["facts"]["us-gaap"], p
    return None, None

def _overlap(f, a, b, start, inst=False):
    """periods that exist under both tags (earliest-filed value of each): count and the largest relative difference in percent. inst=True compares balance-sheet dates, else periods (start, end)."""
    def one(t):
        d = _usd(f, t, start); d = d[d["days"].isna()] if inst else d[d["days"].notna()]
        k = ["end"] if inst else ["start", "end"]
        return d.sort_values("filed").drop_duplicates(k, keep="first").set_index(k)["val"]
    x, y = one(a), one(b); j = pd.concat([x, y], axis=1, keys=["a", "b"]).dropna()
    return len(j), (float(((j["a"] - j["b"]).abs() / j["a"].abs().replace(0, np.nan)).max() * 100) if len(j) else 0.0)

def build_inputs(start=START_NEW, rawdirs=None, verbose=True):
    rawdirs = rawdirs or [RAW_D, HO / "raw", CT / "raw"]
    rep = {}
    # --- design tables, unchanged ---
    comp_d = companies.copy(); comp_d["distress_date"] = pd.to_datetime(comp_d["distress_date"], errors="coerce")
    design_tk = list(comp_d["ticker"]); rep["design_tickers"] = len(design_tk)
    # --- held-out failed: tag map v4 (Step 28) ---
    TM4 = pd.read_csv(HO / "tag_map_heldout_v4.csv").fillna("")
    TM4["ticker"] = [[v for k, v in TICK.items() if k in n][0] for n in TM4["name"]]
    DT = pd.read_csv(HO / "debt_quarterly_heldout.csv", parse_dates=["end"])
    assert set(TM4["ticker"]) == set(DT["ticker"]), f"tag map and debt table disagree: {set(TM4['ticker']) ^ set(DT['ticker'])}"
    # --- controls and new failed (Step 38/40 final files) ---
    FR = pd.read_csv(CT / "controls_final.csv"); FR = FR[FR["status"].isin(["CONTROL", "NEW FAILED"])].copy()
    DC = pd.read_csv(CT / "debt_quarterly_controls_final.csv", parse_dates=["end"])
    FR["ticker"] = FR["ticker"].astype(str)
    rows = []   # (ticker, name, cik, group, distress_date, tags dict)
    for _, r in TM4.iterrows():
        rows.append(dict(ticker=r["ticker"], company_name=r["name"], cik=int(r["cik"]), group="ho_failed", distress_date=pd.Timestamp(r["event"]),
                         rev=[t for t in str(r["revenue"]).split(" > ") if t], cost=[t for t in str(r["cost"]).split(" > ") if t],
                         gp=str(r["gross_profit_tag"]), inv=[t for t in str(r["inventory"]).split(" > ") if t], before=pd.Timestamp(r["event"])))
        if "Sears" not in r["name"]:      # Sears' tags were verified against filings
            f_, _p = _facts(r["cik"], rawdirs)
            for key, cand, kind in (("rev", REVP, "flow"), ("inv", INVP, "inst")):
                rows[-1][key] = rows[-1][key] + [t for t in cand if t not in rows[-1][key] and _n_ends(f_, t, kind, start, rows[-1]["before"]) >= 4]
    for _, r in FR.iterrows():
        ev = pd.Timestamp(r["event"]) if isinstance(r["event"], str) and r["event"] else pd.NaT
        f, _p = _facts(r["cik"], rawdirs)
        if f is None: raise FileNotFoundError(f"no raw facts file for {r['ticker']} (CIK {int(r['cik'])}) in {rawdirs}")
        b = ev if pd.notna(ev) else None
        keep = lambda L, k: [t for t in L if _n_ends(f, t, k, start, b) >= 4]
        rows.append(dict(ticker=r["ticker"], company_name=r["name"], cik=int(r["cik"]), group="ho_failed" if r["status"] == "NEW FAILED" else "ho_control",
                         distress_date=ev, rev=keep(REVP, "flow"), cost=keep(COSTP, "flow"), gp="GrossProfit" if _n_ends(f, "GrossProfit", "flow", start, b) >= 4 else "",
                         inv=keep(INVP, "inst"), before=ev))
    new_tk = [r["ticker"] for r in rows]
    dup = set(new_tk) & set(design_tk)
    if dup or len(set(new_tk)) != len(new_tk): raise ValueError(f"ticker collision: {dup or [t for t in new_tk if new_tk.count(t) > 1]}")
    # --- the design stitching rule for the ADDED companies: an alternate tag must agree with the first tag within 1% where both report the same period, or not overlap at all ---
    rej = []
    if APPLY_OVERLAP_RULE:
        for r in rows:
            f, _p = _facts(r["cik"], rawdirs)
            for key, mt, inst in (("rev", "Revenue", False), ("cost", "CostOfGoods", False), ("inv", "Inventory", True)):
                L_ = r[key]
                if len(L_) < 2: continue
                keep_ = [L_[0]]
                for t in L_[1:]:
                    n, mx = _overlap(f, L_[0], t, start, inst); ok = (n == 0) or (mx <= 1.0)
                    if not ok: rej.append(dict(ticker=r["ticker"], group=r["group"], metric=mt, first_tag=L_[0][:34], rejected_tag=t[:34], overlap_periods=n, max_diff_pct=round(mx, 2)))
                    else: keep_.append(t)
                r[key] = keep_
    rep["rejected"] = rej
    comp_n = pd.DataFrame([{k: r[k] for k in ["ticker", "company_name", "cik", "group", "distress_date"]} for r in rows])
    comp2 = pd.concat([comp_d, comp_n], ignore_index=True)
    # --- design reference companies: older tags that hold 2014-2018 data, stitched behind the primary tag only if they agree with it (the design rule: within 1% or no overlap) ---
    ext, ext_rows = {}, []
    if EXTEND_REFERENCE:
        SKIP = {("PLCE", "Revenue"), ("DBI", "CostOfGoods"), ("COST", "GrossProfit")}      # already handled by your design cells
        pm = {(r.ticker, r.metric): r.primary_tag for r in tm.itertuples() if r.metric in ("Revenue", "CostOfGoods")}
        for _, c in comp_d[comp_d.group.isin(["healthy", "under_pressure"])].iterrows():
            tk = c["ticker"]; f, _p = _facts(c["cik"], rawdirs)
            for m in ("Revenue", "CostOfGoods"):
                prim = pm.get((tk, m), "")
                if not prim or (tk, m) in SKIP or f is None: continue
                cc = cov[(cov.ticker == tk) & (cov.metric == m) & (cov.tag != prim)].copy()
                cc = cc[(pd.to_datetime(cc.first_end, errors="coerce") < "2019-01-01") & (pd.to_datetime(cc.last_end, errors="coerce") >= pd.Timestamp(start))].sort_values("last_end", ascending=False)
                prio = [prim]
                for t in cc["tag"]:
                    n, mx = _overlap(f, prim, t, start); ok = (n == 0) or (mx <= 1.0)
                    ext_rows.append(dict(ticker=tk, metric=m, primary=prim[:40], added_tag=t[:40], overlap_periods=n, max_diff_pct=round(mx, 2) if n else "", decision=("ADDED" if ok and n else "ADDED (no overlap to test)") if ok else "REJECTED (differs > 1%)"))
                    if ok: prio.append(t)
                if len(prio) > 1: ext[(tk, m)] = prio
    rep["extension"] = ext_rows
    # --- tag map, coverage, stitch lists for the added companies ---
    tm_rows, cov_rows, stitch, issues = [], [], {}, []
    for r in rows:
        f, p = _facts(r["cik"], rawdirs)
        lists = {"Revenue": r["rev"], "CostOfGoods": r["cost"], "GrossProfit": [r["gp"]] if r["gp"] else [], "Inventory": r["inv"], "CurrAssets": ["AssetsCurrent"] if _n_ends(f, "AssetsCurrent", "inst", start, None) >= 8 else []}
        for m, tags in lists.items():
            if not tags: continue
            stitch[(r["ticker"], m)] = list(tags)
            tm_rows.append(dict(ticker=r["ticker"], group=r["group"], metric=m, status="ready", primary_tag=tags[0], primary_covers="", fallback_tags=" > ".join(tags[1:]), component_tag="",
                                remaining_gaps="", derived_rule="", reported_coverage_pct=np.nan, notes="held-out Step 43 map", debt_formula="", debt_basis="", debt_includes_leases="", debt_confidence=""))
            for t in tags:
                d = _usd(f, t, start)
                cov_rows.append(dict(ticker=r["ticker"], group=r["group"], metric=m, tag=t, records=len(d), first_end=str(d["end"].min().date()) if len(d) else "", last_end=str(d["end"].max().date()) if len(d) else ""))
        miss = [m for m in ["Revenue", "Inventory", "CurrAssets"] if not lists[m]] + (["GrossProfit or CostOfGoods"] if not lists["GrossProfit"] and not lists["CostOfGoods"] else [])
        if miss: issues.append((r["ticker"], r["company_name"][:28], r["group"], "no tag for: " + ", ".join(miss)))
    tm2 = pd.concat([tm, pd.DataFrame(tm_rows)], ignore_index=True); cov2 = pd.concat([cov, pd.DataFrame(cov_rows)], ignore_index=True)
    rep["added"] = {g: sum(1 for r in rows if r["group"] == g) for g in ["ho_failed", "ho_control"]}; rep["issues"] = issues
    # --- debt table in the format of debt_quarterly_final.csv ---
    dd = pd.read_csv(BASE_D / "debt_quarterly_final.csv", parse_dates=["end"]); cols = ["ticker", "end", "total_m", "qoq_pct", "flag", "detail", "gross_m"]
    pre = []
    pkp = HO / "design_debt_2014.pkl"
    if pkp.exists():
        pk = pd.read_pickle(pkp)
        for tk, S in pk.items():
            if tk not in design_tk or not len(S): continue
            first = dd[dd.ticker == tk]["end"].min(); first = first if pd.notna(first) else pd.Timestamp("2100-01-01")
            for e, v in S[(S.index < first) & (S.index >= pd.Timestamp(start))].items():
                pre.append(dict(ticker=tk, end=e, total_m=v, qoq_pct=np.nan, flag="FORMULA 2014-18", detail="debt_definition.csv formula; not tied to filings", gross_m=v))
    else: rep["no_design_pkl"] = True
    parts = [dd.reindex(columns=cols), pd.DataFrame(pre, columns=cols), DT.reindex(columns=cols), DC.reindex(columns=cols)]
    debt = pd.concat(parts, ignore_index=True).sort_values(["ticker", "end"]).reset_index(drop=True)
    rep["design_pre2019_debt_rows"] = len(pre)
    # manual overrides must already be inside the held-out table (Step 30); verify, add if absent
    mo = HO / "manual_debt_overrides.csv"; added_manual = 0
    if mo.exists():
        M = pd.read_csv(mo)
        for _, m in M.iterrows():
            tk = [v for k, v in TICK.items() if k in str(m["name"])]
            if not tk: continue
            tk = tk[0]; e = pd.Timestamp(m["end"]); s = debt[(debt.ticker == tk) & ((debt.end - e).abs() <= pd.Timedelta(days=5))]
            if not len(s) or s["total_m"].isna().all():
                debt = pd.concat([debt[~((debt.ticker == tk) & ((debt.end - e).abs() <= pd.Timedelta(days=5)))],
                                  pd.DataFrame([dict(ticker=tk, end=e, total_m=m["debt_total_usd"] / 1e6, qoq_pct=np.nan, flag="MANUAL", detail=str(m["basis"]), gross_m=m["debt_total_usd"] / 1e6)])], ignore_index=True); added_manual += 1
    rep["manual_rows_added_here"] = added_manual
    # quarter-level blanks (protocol 11)
    blanked = []
    for frag, d in BLANKS:
        t = FR[FR["name"].str.lower().str.contains(frag.lower(), regex=False)]   # SEC names are upper case
        if not len(t): blanked.append((frag, d, "company not in the final control file")); continue
        tk = t.iloc[0]["ticker"]; e = pd.Timestamp(d); m = (debt.ticker == tk) & ((debt.end - e).abs() <= pd.Timedelta(days=5))
        if not m.any(): blanked.append((tk, d, "no debt row on that date")); continue
        was = debt.loc[m, "total_m"].iloc[0]; debt.loc[m, ["total_m", "gross_m"]] = np.nan; debt.loc[m, "flag"] = "BLANKED (quarter-level rule, protocol 11)"
        blanked.append((tk, d, f"blanked (was {was})"))
    rep["blanked"] = blanked
    debt["end"] = pd.to_datetime(debt["end"]); debt["qoq_pct"] = debt.groupby("ticker")["total_m"].pct_change(fill_method=None) * 100
    stitch.update(ext)
    return dict(comp=comp2, cov=cov2, tm=tm2, stitch=stitch, new_tickers=new_tk, debt=debt, rep=rep, rows=rows)

# ------------------------------------------------------------------ PART B: regression test ------------------------------------------------------------------
def regression(new_base, old_base, design_tk, from_date="2020-01-01"):
    """Do the design companies come out unchanged from the given date? 'changed' = both runs have a value and they differ; 'lost' = the old run had a value and the new one does not;
    'gained' = the old run had no value (the 2019 start left the first year without a prior-year quarter) and the new run has one. Only gained is expected."""
    Qn = pd.read_csv(Path(new_base) / "clean_quarterly.csv", parse_dates=["end", "as_of_date"]); Qo = pd.read_csv(Path(old_base) / "clean_quarterly.csv", parse_dates=["end", "as_of_date"])
    Qn, Qo = [q[q.ticker.isin(design_tk) & (q.end >= from_date)] for q in (Qn, Qo)]
    J = Qo.merge(Qn, on=["ticker", "end"], how="outer", suffixes=("_old", "_new"), indicator=True)
    Fn, Fo = features_lite(new_base), features_lite(old_base)
    Fn, Fo = [f[f.ticker.isin(design_tk) & (f.end >= from_date)] for f in (Fn, Fo)]
    K = Fo.merge(Fn, on=["ticker", "end"], how="outer", suffixes=("_old", "_new"), indicator=True)
    out = [dict(item="quarter rows only in old run / only in new run / in both", changed="", lost="", gained=f"{int((J._merge == 'left_only').sum())} / {int((J._merge == 'right_only').sum())} / {int((J._merge == 'both').sum())}"),
           dict(item="feature rows only in old run / only in new run / in both", changed="", lost="", gained=f"{int((K._merge == 'left_only').sum())} / {int((K._merge == 'right_only').sum())} / {int((K._merge == 'both').sum())}")]
    diffs = []
    def cmp(B, c, text=False):
        a, b = B[c + "_old"], B[c + "_new"]
        same = (a == b) if text else ((a - b).abs() <= 1e-6 * np.maximum(1.0, a.abs()))
        ch = a.notna() & b.notna() & ~same; lo = a.notna() & b.isna(); ga = a.isna() & b.notna()
        out.append(dict(item=c, changed=int(ch.sum()), lost=int(lo.sum()), gained=f"{int(ga.sum())}" + (f" (latest {str(B[ga]['end'].max().date())})" if ga.any() else "")))
        for kind, m in [("changed", ch), ("lost", lo), ("gained", ga)]:
            if m.any(): diffs.append(B[m][["ticker", "end", c + "_old", c + "_new"]].assign(column=c, kind=kind).rename(columns={c + "_old": "old", c + "_new": "new"}))
    B = J[J._merge == "both"]
    for c in ["Revenue", "GrossProfit", "Inventory", "Debt", "CurrAssets", "as_of_date"]: cmp(B, c, text=(c == "as_of_date"))
    Bk = K[K._merge == "both"]
    for c in ["gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"]: cmp(Bk, c)
    cmp(Bk, "cal_q", text=True)
    D = pd.concat(diffs, ignore_index=True) if diffs else pd.DataFrame(columns=["ticker", "end", "old", "new", "column", "kind"])
    return pd.DataFrame(out), D
# ------------------------------------------------------------------ MAIN ------------------------------------------------------------------
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
print("PART A: building the held-out inputs (companies, tag map, coverage, debt table)\n")
I = build_inputs(); rep = I["rep"]; HP.mkdir(exist_ok=True)
I["debt"].to_csv(HP / "debt_quarterly_final.csv", index=False)
print(f"design companies {rep['design_tickers']} | added: {rep['added']} | design 2014-18 debt rows from design_debt_2014.pkl: {rep['design_pre2019_debt_rows']}" + (" (pkl NOT found)" if rep.get("no_design_pkl") else ""))
print("manual debt rows that were missing from the held-out table and were added here:", rep["manual_rows_added_here"])
print("quarter-level blanks:", rep["blanked"])
print("companies missing a required input tag (they cannot be scored):", rep["issues"] or "none")
print("\nREFERENCE EXTENSION (design reference companies: older tags stitched behind the primary tag if they agree within 1% or do not overlap):")
ex = pd.DataFrame(rep["extension"]); print(ex.to_string(index=False) if len(ex) else "none (EXTEND_REFERENCE is off or nothing to add)")
rj = pd.DataFrame(rep["rejected"])
print(f"\nOVERLAP RULE APPLIED TO THE ADDED COMPANIES (design rule: alternate tag within 1% of the first tag where both report a period, or no overlap): {len(rj)} tags rejected")
if len(rj): print(rj.sort_values(["metric", "max_diff_pct"], ascending=[True, False]).to_string(index=False))
ref_g = ["healthy", "under_pressure"]; dtk = list(companies["ticker"])
print("design groups:", companies["group"].value_counts().to_dict(), "| design reference companies (healthy + under_pressure):", sorted(companies[companies.group.isin(ref_g)]["ticker"]))
need = ["ticker", "cik", "group", "distress_date"]
ns = run_pipeline(HP, I["comp"], I["cov"], I["tm"], START_NEW, I["stitch"], I["new_tickers"], [RAW_D, HO / "raw", CT / "raw"])
print("\nPART B: your cleaning cells ran from", START_NEW, "(logs in", HP / "logs", ")")
Qn = pd.read_csv(HP / "clean_quarterly.csv", parse_dates=["end"]); print("clean_quarterly rows:", len(Qn), "| companies:", Qn.ticker.nunique(), "of", len(I["comp"]))
F = features_lite(HP); F.to_csv(HP / "features_heldout.csv", index=False)
print("features_heldout.csv:", len(F), "rows")
# tag switches inside the added companies (several tags stitched by priority)
st = pd.read_csv(HP / "clean_04b_stitched.csv"); new = st[st.ticker.isin(I["new_tickers"])]
sw = new.groupby(["ticker", "metric"])["tag_used"].agg(lambda s: dict(s.value_counts())).reset_index(); sw = sw[sw.tag_used.map(len) > 1]
print("\nadded companies where a metric was stitched from more than one tag (rows per tag):"); print(sw.to_string(index=False) if len(sw) else "none")
# coverage of inputs per added company
cq = Qn[Qn.ticker.isin(I["new_tickers"])].groupby("ticker")[["Revenue", "GrossProfit", "Inventory", "Debt"]].count()
low = cq[(cq < 8).any(axis=1)]
print("\nadded companies with fewer than 8 quarters of any input in clean_quarterly:", low.to_dict("index") if len(low) else "none")
# scorable-observation counts for held-out failed companies (inputs only, no scores)
fo = F[F.group == "ho_failed"].copy(); fo = fo[(fo.months_avail >= 3) & (fo.months_avail < 12) & ~fo.cal_q.isin(WIN_B)]
for lv in ["lev2_chg_yoy", "lev3_chg_yoy"]:
    fo["ok_" + lv[:4]] = fo[["gm_chg_yoy", "inv_gap", lv]].notna().all(axis=1)
tab = fo.groupby("ticker")[["ok_lev2", "ok_lev3"]].sum().astype(int)
tab = tab.reindex(sorted(set(I["comp"][I["comp"].group == "ho_failed"].ticker))).fillna(0).astype(int)
print("\nHeld-out failed companies: observations 3-12 months before the event with all three inputs present (COVID window blanked; this is an input count, not a score):")
print(tab.T.to_string())
print(f"companies with at least one such observation: lev2 {(tab.ok_lev2 > 0).sum()} of {len(tab)} | lev3 {(tab.ok_lev3 > 0).sum()} of {len(tab)} (protocol floor: 12 scored failed companies)")
# reference thinness: design reference companies with all three inputs in each calendar quarter
R = F[F.group.isin(ref_g)].copy(); R["full"] = R[["gm_chg_yoy", "inv_gap", "lev2_chg_yoy"]].notna().all(axis=1)
rc = R[R.full].groupby("cal_q")["ticker"].nunique()
print("\ndesign reference companies with all three inputs (lev2), by calendar quarter, 2014-2019 (the reference must have at least 5):")
print(rc[(rc.index >= "2014Q1") & (rc.index <= "2019Q4")].to_string() if len(rc) else "none")
# overlap audit for the ADDED companies (alternate tag must agree within 1% or not overlap)
c3 = pd.read_csv(HP / "clean_03_asof.csv", parse_dates=["end"]); aud = []
for (tk, mt), prio in I["stitch"].items():
    if tk not in I["new_tickers"] or len(prio) < 2: continue
    sub = c3[(c3.ticker == tk) & (c3.metric == mt)]
    base_ = sub[sub.tag == prio[0]].set_index(["end", "ptype"])["val"]
    for t in prio[1:]:
        o = sub[sub.tag == t].set_index(["end", "ptype"])["val"]; j = pd.concat([base_, o], axis=1, keys=["a", "b"]).dropna()
        if len(j): aud.append(dict(ticker=tk, metric=mt, first_tag=prio[0][:34], other_tag=t[:34], overlap=len(j), max_diff_pct=round(float(((j.a - j.b).abs() / j.a.abs().replace(0, np.nan)).max() * 100), 2)))
aud = pd.DataFrame(aud)
print(f"\nOVERLAP AUDIT after the rule (must be zero pairs above 1%), added companies: {len(aud)} tag pairs overlap; pairs differing by more than 1%: {int((aud.max_diff_pct > 1).sum()) if len(aud) else 0}")
if len(aud) and (aud.max_diff_pct > 1).any(): print(aud[aud.max_diff_pct > 1].sort_values("max_diff_pct", ascending=False).to_string(index=False))
# why a few tags are missing: list the candidate tags of the three odd companies
def tag_scan(cik, pats=("Inventor", "CostOf", "GrossProfit", "CostOfGoods")):
    f, p = _facts(cik, [RAW_D, HO / "raw", CT / "raw"]); out = []
    for t in f:
        if any(x in t for x in pats):
            d = _usd(f, t, START_NEW); kinds = "inst" if len(d) and d["days"].isna().all() else "flow"
            if len(d): out.append((t[:70], kinds, d["end"].nunique(), str(d["end"].min().date()), str(d["end"].max().date())))
    return out
print("\nTAG SCAN for companies with missing or thin inputs (us-gaap tags with inventory or cost wording: tag, kind, period ends, first, last):")
for lab, key in [("SPWH (no inventory tag)", "SPWH"), ("BLUE APRON (no cost or gross profit tag)", "CIK1701114"), ("CTRN (gross profit in only 4 quarters)", "CTRN")]:
    r_ = I["comp"][I["comp"].ticker == key]
    if not len(r_): print(lab, "not in companies"); continue
    print(" ", lab, "->", tag_scan(int(r_.iloc[0]["cik"])))
# the two late 'gained' cells of the regression: which quarters are new in the 2014 run?
print("\nDESIGN quarters that have a revenue value now but had none in your design run (2019 on): shows what the earlier start filled")
Qo = pd.read_csv(BASE_D / "clean_quarterly.csv", parse_dates=["end"]); Qn2 = pd.read_csv(HP / "clean_quarterly.csv", parse_dates=["end"])
jj = Qn2[Qn2.ticker.isin(dtk) & (Qn2.end >= "2019-01-01") & Qn2.Revenue.notna()].merge(Qo[["ticker", "end", "Revenue"]], on=["ticker", "end"], how="left", suffixes=("", "_old"))
print(jj[jj.Revenue_old.isna()][["ticker", "end", "Revenue"]].assign(Revenue=lambda d: (d.Revenue / 1e6).round(1)).to_string(index=False) or "none")
# FLOOR FORECAST: replicate the as-of engine's gating (reference needs at least 5 design companies with a value for each signal), no scores
def gate_forecast(F, comp, ref_tickers):
    F2 = F.copy(); sig = ["gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"]; F2.loc[F2.cal_q.isin(WIN_B), sig] = np.nan
    REF = F2[F2.ticker.isin(ref_tickers)].sort_values(["ticker", "end"]); out = []
    foc = F2[(F2.group == "ho_failed") & (F2.months_avail >= 3) & (F2.months_avail < 12) & F2.as_of_date.notna()]
    for _, r in foc.iterrows():
        t = r.as_of_date; x = REF[REF.as_of_date <= t].groupby("ticker").tail(1); x = x[(t - x.end).dt.days <= 135]
        n = {c: int(x[c].notna().sum()) for c in sig}
        for lv in ("lev2_chg_yoy", "lev3_chg_yoy"):
            ok = all(pd.notna(r[c]) for c in ["gm_chg_yoy", "inv_gap", lv]) and min(n["gm_chg_yoy"], n["inv_gap"], n[lv]) >= 5
            out.append(dict(ticker=r.ticker, event=r.distress_date, lev=lv[:4], scored=ok, n_ref=min(n["gm_chg_yoy"], n["inv_gap"], n[lv])))
    return pd.DataFrame(out)
G = gate_forecast(F, I["comp"], list(companies[companies.group.isin(ref_g)]["ticker"]))
allf = I["comp"][I["comp"].group == "ho_failed"][["ticker", "distress_date"]]
cut = lambda d: "pre-2019" if d < pd.Timestamp("2019-01-01") else "2019" if d < pd.Timestamp("2020-01-01") else "2020 to Jan 2021" if d < pd.Timestamp("2021-02-01") else "later"
allf["cut"] = allf.distress_date.map(cut)
print("\nFLOOR FORECAST (as-of engine gating, no scores): failed companies with at least one observation 3-12 months before the event that has all three inputs AND at least 5 design reference companies available")
for lv in ("lev2", "lev3"):
    g = G[(G.lev == lv) & G.scored].groupby("ticker").size()
    allf[lv + "_obs"] = allf.ticker.map(g).fillna(0).astype(int)
print(allf.sort_values("distress_date").to_string(index=False))
for lv in ("lev2", "lev3"):
    sc = allf[allf[lv + "_obs"] > 0]
    print(f"  {lv}: {len(sc)} of {len(allf)} failed companies would be scored (floor 12); by cut:", sc.cut.value_counts().to_dict(), "| not scored by cut:", allf[allf[lv + "_obs"] == 0].cut.value_counts().to_dict())
# THREE-INPUT RULE (protocol section 6): a company is dropped if it never has 4 consecutive quarters with gross margin inputs (revenue and gross profit), inventory and debt all present
def longest_run(g):
    g = g.sort_values("end"); ok = (g[["Revenue", "GrossProfit", "Inventory", "Debt"]].notna().all(axis=1)).values; ends = g["end"].values
    best = cur = 0
    for i in range(len(g)):
        if not ok[i]: cur = 0
        else: cur = cur + 1 if (cur > 0 and (ends[i] - ends[i - 1]) / np.timedelta64(1, "D") <= 130) else 1
        best = max(best, cur)
    return best
Qa = Qn.copy(); ctl_t = list(I["comp"][I["comp"].group == "ho_control"]["ticker"])
cvg = Qa[Qa.ticker.isin(I["new_tickers"])].groupby("ticker").agg(quarters=("end", "size"), Revenue=("Revenue", lambda s: round(s.notna().mean(), 2)), GrossProfit=("GrossProfit", lambda s: round(s.notna().mean(), 2)),
                                                                  Inventory=("Inventory", lambda s: round(s.notna().mean(), 2)), Debt=("Debt", lambda s: round(s.notna().mean(), 2)))
cvg["longest_run"] = [longest_run(Qa[Qa.ticker == tk]) for tk in cvg.index]
cvg["group"] = I["comp"].set_index("ticker").loc[cvg.index, "group"]; cvg["min_share"] = cvg[["Revenue", "GrossProfit", "Inventory", "Debt"]].min(axis=1)
cvg.sort_values("longest_run").to_csv(HP / "coverage_added_companies.csv")
drop_all = sorted(cvg[cvg.longest_run < 4].index)
drop_ctl = [x for x in drop_all if x in ctl_t]; drop_fail = [x for x in drop_all if x not in ctl_t]
print(f"\nTHREE-INPUT RULE (4 consecutive quarters with revenue, gross profit, inventory and debt): controls dropped: {drop_ctl} | failed companies dropped: {drop_fail or 'none'}")
print("lowest 12 by longest run (controls and failed); shares = share of usable quarters with the input:"); print(cvg.sort_values(["longest_run", "min_share"]).head(12).to_string())
F["excluded_control"] = F.ticker.isin(drop_ctl); F.to_csv(HP / "features_heldout.csv", index=False)
print(f"controls left: {len(ctl_t) - len(drop_ctl)} of {len(ctl_t)}")
low_rev = list(cvg[(cvg.group == "ho_failed") & (cvg.Revenue < 0.9)].index)
print(f"\nREVENUE GAP SCAN: failed companies with revenue in under 90% of quarters ({len(low_rev)}); every us-gaap tag with Revenue or Sales in its name that has at least 4 flow periods (tag, period ends, first, last):")
for tk in low_rev:
    f_, _p = _facts(int(I["comp"].set_index("ticker").loc[tk, "cik"]), [RAW_D, HO / "raw", CT / "raw"]); out = []
    for tg in f_:
        if re.search(r"Revenue|Sales", tg) and not re.search(r"Cost|Deferred|Percent|Increase|Decrease|Tax|Receivable|Proceeds|Gain|Loss|Allowance|Reserve|Discount|Return", tg):
            d = _usd(f_, tg, START_NEW); d = d[d["days"].notna() & (d["days"] >= 80)]
            if d["end"].nunique() >= 4: out.append((tg[:46], d["end"].nunique(), str(d["end"].min().date()), str(d["end"].max().date())))
    print(" ", tk, "revenue share", float(cvg.loc[tk, "Revenue"]), "->", out)
# WHY SOME FAILED COMPANIES HAVE NO SCORED OBSERVATION (inputs of the observations 3-12 months before the event, and reference counts at that date)
def why_zero(F, tickers, ref_tickers):
    F2 = F.copy(); sig = ["gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"]; F2.loc[F2.cal_q.isin(WIN_B), sig] = np.nan
    REF = F2[F2.ticker.isin(ref_tickers)].sort_values(["ticker", "end"]); rows_ = []
    for _, r in F[(F.ticker.isin(tickers)) & (F.months_avail >= 3) & (F.months_avail < 12) & F.as_of_date.notna()].sort_values(["ticker", "end"]).iterrows():
        t = r.as_of_date; x = REF[REF.as_of_date <= t].groupby("ticker").tail(1); x = x[(t - x.end).dt.days <= 135]
        blank = "COVID window" if r.cal_q in WIN_B else ""
        rows_.append(dict(ticker=r.ticker, quarter=str(r.end.date()), public=str(t.date()), months=round(r.months_avail, 1), missing=",".join([c[:5] for c in sig if pd.isna(r[c])]) or "none", covid=blank,
                          ref_gm=int(x.gm_chg_yoy.notna().sum()), ref_inv=int(x.inv_gap.notna().sum()), ref_lev2=int(x.lev2_chg_yoy.notna().sum()), ref_lev3=int(x.lev3_chg_yoy.notna().sum())))
    return pd.DataFrame(rows_)
zero = sorted(set(allf[(allf.lev2_obs == 0) | (allf.lev3_obs == 0)].ticker))
print("\nWHY ZERO: observations of the failed companies with no scored lev2 or lev3 (what is missing, and how many design reference companies were available on the public date):")
W0 = why_zero(F, zero, list(companies[companies.group.isin(ref_g)]["ticker"])); print(W0.to_string(index=False) if len(W0) else "no observations 3-12 months before the event")
nowin = [x for x in zero if x not in set(W0.ticker)]
for tk in nowin:
    z = F[F.ticker == tk].sort_values("end").tail(8)[["ticker", "end", "as_of_date", "distress_date", "months_avail", "gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"]]
    print(f"\nNO OBSERVATION 3-12 months before the event for {tk}: its last 8 quarters (NaN = missing input; months_avail outside 3-12 means not in the window):"); print(z.to_string(index=False))
# WHY THE AS-OF REFERENCE IS THIN BEFORE 2019 WHEN THE SAME-QUARTER COUNT IS 6-7: how late are the design reference rows public?
fcols = [c for c in pd.read_csv(HP / "clean_quarterly.csv", nrows=1).columns if c.startswith("f_")]
Qf = pd.read_csv(HP / "clean_quarterly.csv", parse_dates=["end", "as_of_date"] + fcols)
Rr = Qf[Qf.ticker.isin(list(companies[companies.group.isin(ref_g)]["ticker"])) & (Qf.end >= "2016-01-01") & (Qf.end <= "2018-12-31")].copy()
Rr["lag"] = (Rr.as_of_date - Rr.end).dt.days; Rr["driver"] = Rr[fcols].apply(lambda r: r.idxmax() if r.notna().any() else "", axis=1)
dg = Rr.groupby("ticker").agg(rows=("end", "size"), median_lag=("lag", "median"), share_over_135=("lag", lambda s: round(float((s > 135).mean()), 2)), no_asof=("as_of_date", lambda s: int(s.isna().sum())))
dg["usual_driver_when_late"] = [Rr[(Rr.ticker == tk) & (Rr.lag > 135)]["driver"].mode().iloc[0] if ((Rr.ticker == tk) & (Rr.lag > 135)).any() else "" for tk in dg.index]
print("\nDESIGN REFERENCE rows 2016-2018: days from quarter end to the date all inputs were public (a row older than 135 days at the score date is not used), and which input is filed last when it is late:")
print(dg.to_string())
def control_availability(F, comp, drop_ctl):
    F2 = F.copy(); sig = ["gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"]; F2.loc[F2.cal_q.isin(WIN_B), sig] = np.nan
    C = F2[(F2.group == "ho_control") & ~F2.ticker.isin(drop_ctl)].sort_values(["ticker", "end"]); out = []
    foc = F2[(F2.group == "ho_failed") & (F2.months_avail >= 3) & (F2.months_avail < 12) & F2.as_of_date.notna()]
    for _, r in foc.iterrows():
        t = r.as_of_date; x = C[C.as_of_date <= t].groupby("ticker").tail(1); x = x[(t - x.end).dt.days <= 135]
        for lv in ("lev2_chg_yoy", "lev3_chg_yoy"):
            if not all(pd.notna(r[c]) for c in ["gm_chg_yoy", "inv_gap", lv]): continue
            y = x[x[["gm_chg_yoy", "inv_gap", lv]].notna().all(axis=1)]; ratio = (y.ttm_rev / r.ttm_rev) if pd.notna(r.ttm_rev) else (y.ttm_rev * np.nan)
            out.append(dict(ticker=r.ticker, lev=lv[:4], controls=len(y), within3x=int(((ratio >= 1 / 3) & (ratio <= 3)).sum()), within10x=int(((ratio >= 0.1) & (ratio <= 10)).sum())))
    return pd.DataFrame(out)
CA = control_availability(F, I["comp"], drop_ctl)
if len(CA):
    ca = CA.groupby(["ticker", "lev"]).agg(obs=("controls", "size"), controls_min=("controls", "min"), within3x_min=("within3x", "min"), within3x_median=("within3x", "median"), within10x_min=("within10x", "min")).reset_index()
    print("\nCONTROL AVAILABILITY per failed company (scored observations; size = trailing four-quarter sales; approximate version of the protocol's annual-revenue rule):")
    print(ca.to_string(index=False))
    print("failed companies whose worst observation has fewer than 3 controls within 3x:", sorted(set(ca[ca.within3x_min < 3].ticker)))
# v6: gross profit made public earlier (added companies only)
_g = pd.read_csv(HP / "gp_earlier_public.csv")
print("\nGROSS PROFIT PUBLIC DATE (v6): quarters where the reported gross profit was first public later than revenue minus cost of goods (they agree within 1%), now dated by the earlier of the two:")
print(_g.groupby("ticker").days_earlier.agg(quarters="size", median_days_earlier="median").to_string() if len(_g) else "none")
# v6: the as-of lag audit for the failed companies, built in so it needs no extra run
_fc = [c for c in pd.read_csv(HP / "clean_quarterly.csv", nrows=1).columns if c.startswith("f_")]
_Q = pd.read_csv(HP / "clean_quarterly.csv", parse_dates=["end"] + _fc); _Q = _Q[_Q[_fc].notna().any(axis=1)].copy()
_d0 = pd.Timestamp("1970-01-01"); _days = _Q[_fc].apply(lambda s_: (s_ - _d0).dt.days)
_Q["lag"] = _days.max(axis=1) - (_Q["end"] - _d0).dt.days; _Q["driver"] = _days.idxmax(axis=1)
_F = _Q[_Q.ticker.isin(list(allf.ticker))]
_T = _F.groupby("ticker").apply(lambda g: pd.Series({"quarters": len(g), "median_lag": g.lag.median(), "share_over_135": round((g.lag > 135).mean(), 2),
      "usual_driver_when_late": (g[g.lag > 135]["driver"].value_counts().index[0] if (g.lag > 135).any() else "")}), include_groups=False)
print("\nAS-OF LAG for the failed companies (days from quarter end to the public date of all inputs):"); print(_T.to_string())
# regression: design companies unchanged from 2020?
print("\nPART C: REGRESSION TEST. design companies, quarters ending on or after 2020-01-01: your existing design run vs this run (start 2014)")
RG, DF_ = regression(HP, BASE_D, dtk); print(RG.to_string(index=False))
DF_.to_csv(HP / "regression_differences.csv", index=False)
rowsame = all(x.split(" / ")[0] == "0" and x.split(" / ")[1] == "0" for x in RG.gained.iloc[:2])
bad = DF_[DF_.kind.isin(["changed", "lost"])]
late = DF_[(DF_.kind == "gained") & (pd.to_datetime(DF_.end) > "2021-06-30")]
ok = rowsame and not len(bad)
print("\nVERDICT:", "PASS: from 2020 on, no design value was changed or lost; values that only appear now were blank in the 2019-start run (see the list of newly filled design quarters above)." if ok else
      f"DIFFERENCES FOUND ({len(bad)} changed, lost or unexpectedly gained cells, row sets equal: {rowsame}); see regression_differences.csv; first rows below. Do not trust the held-out run until these are explained.")
if not ok: print(bad.head(25).to_string(index=False))
if len(late): print("gained after mid-2021 (blank before, filled now; not a failure, cause shown in the newly-filled-quarters list):", late[["ticker", "end", "column"]].values.tolist())
print("\nStep 43 done. Paste everything above.")

