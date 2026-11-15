# ===== STEP 19: held-out candidates. Part A checks each candidate's CIK and bankruptcy event on EDGAR. Part B downloads their filing data and audits how far back each metric reaches. =====
# Needs from your start-of-session cells: BASE, RAW, companies, HEADERS (your SEC User-Agent with your name and email). Other imports are done here.
# Before running: make the folder BASE/"heldout" and upload failed_candidates.csv into it. Nothing here computes a score.
import re, time, json, requests
import numpy as np, pandas as pd
for _n in ["BASE", "RAW", "companies", "HEADERS"]:
    if _n not in globals(): raise NameError(f"{_n} is not defined in this session. Rerun your start-of-session cell first (HEADERS = {{'User-Agent': 'Your Name your.email@example.com'}} with your own details).")
HO = BASE / "heldout"; HO.mkdir(exist_ok=True); RAW_HO = HO / "raw"; RAW_HO.mkdir(exist_ok=True)
if not (HO / "failed_candidates.csv").exists(): raise FileNotFoundError(f"Upload failed_candidates.csv into {HO} first.")
START_YEAR = 2014

def get_json(url):
    time.sleep(0.15)
    r = requests.get(url, headers=HEADERS, timeout=90); r.raise_for_status()
    return r.json()

def all_filings(sub):
    pages = [sub["filings"]["recent"]] + [get_json(f"https://data.sec.gov/submissions/{f['name']}") for f in sub["filings"].get("files", [])]
    df = pd.concat([pd.DataFrame({k: p[k] for k in ["accessionNumber", "form", "filingDate", "reportDate", "items"]}) for p in pages], ignore_index=True)
    df["filingDate"] = pd.to_datetime(df["filingDate"]); df["reportDate"] = pd.to_datetime(df["reportDate"].replace("", np.nan))
    return df.sort_values("filingDate").reset_index(drop=True)

def petition_date(s):
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(s))
    if m: return pd.Timestamp(m.group(0).strip()), "day"
    m = re.match(r"\s*(\d{4})-(\d{2})\b", str(s))
    if m: return pd.Timestamp(f"{m.group(1)}-{m.group(2)}-15"), "month"
    return pd.NaT, "none"

def has_item(series, item):
    return series.fillna("").str.contains(rf"(?:^|,)\s*{re.escape(item)}\s*(?:,|$)")

def check_event(name, sub, petition_text):
    f = all_filings(sub); k8 = f[f.form.isin(["8-K", "8-K/A"])]
    pet, prec = petition_date(petition_text)
    out = dict(edgar_name=sub.get("name"), former=";".join(x["name"] for x in sub.get("formerNames", []))[:60])
    tok = [w for w in re.findall(r"[a-z]{4,}", name.lower()) if w not in ("holdings", "stores", "group", "company", "brands", "retail", "inc")]
    names = (str(out["edgar_name"]) + " " + out["former"]).lower()
    out["name_matches"] = "yes" if any(w in names for w in tok[:2]) else "CHECK"
    first103 = k8[has_item(k8["items"], "1.03")]
    out["first_item_1_03_anywhere"] = first103.filingDate.min().date() if len(first103) else None
    if pd.notna(pet):
        half = 20 if prec == "month" else 0
        win = k8[(k8.filingDate >= pet - pd.Timedelta(days=10 + half)) & (k8.filingDate <= pet + pd.Timedelta(days=30 + half))]
        out["8ks_around_petition"] = "; ".join(f"{d.date()}[{i}]" for d, i in zip(win.filingDate, win["items"].fillna("")))[:150]
        w103 = win[has_item(win["items"], "1.03")]
        if len(w103): ev, rule = w103.iloc[0], "ITEM_1.03"
        else:
            fb = win[has_item(win["items"], "1.01") | has_item(win["items"], "2.03") | has_item(win["items"], "3.01")]
            ev, rule = (fb.iloc[0], "NO_1.03_FALLBACK: read the document") if len(fb) else (None, "NO_8K_FOUND_IN_WINDOW")
    else:
        ev, rule = (first103.iloc[0], "ITEM_1.03 (no petition date supplied)") if len(first103) else (None, "NO_EVENT_FOUND")
    out["rule"] = rule
    if ev is not None:
        out["event_8k_date"] = ev.filingDate.date(); out["event_accession"] = ev.accessionNumber
        out["days_after_petition"] = (ev.filingDate - pet).days if pd.notna(pet) else None
        per = f[f.form.isin(["10-Q", "10-K", "10-K405", "10-KT"]) & (f.filingDate < ev.filingDate)]
        out["last_periodic_period_end"] = per.reportDate.max().date() if len(per) else None
        out["last_periodic_filed"] = per.filingDate.max().date() if len(per) else None
        out["periodic_reports_since_2014"] = int((per.reportDate >= f"{START_YEAR}-01-01").sum())
    return out

fc = pd.read_csv(HO / "failed_candidates.csv", dtype=str)
fc["poor_candidate"] = fc["poor_candidate"].fillna("N")
ok_cik = fc["cik"].fillna("").str.fullmatch(r"\d+")
use = fc[(fc["poor_candidate"].str.strip().str.upper() != "Y") & ok_cik].copy()
print(f"PART A: checking {len(use)} candidates on EDGAR. skipped {len(fc) - len(use)} (flagged poor candidates, or no CIK):",
      list(fc[~fc.index.isin(use.index)].name)[:40], "\n")
res = []
for i, r in use.iterrows():
    try:
        sub = get_json(f"https://data.sec.gov/submissions/CIK{int(r['cik']):010d}.json")
        d = dict(name=r["name"], ticker=r["ticker"], cik=int(r["cik"]), claimed_petition=str(r["petition_date"])[:25], **check_event(r["name"], sub, r["petition_date"]))
    except Exception as e:
        d = dict(name=r["name"], ticker=r["ticker"], cik=r["cik"], error=f"{type(e).__name__}: {str(e)[:80]}")
    res.append(d)
EV = pd.DataFrame(res)
for c in ["event_8k_date", "rule"]:
    if c not in EV: EV[c] = None      # if every EDGAR call failed, keep the table shape so later parts still run
EV.to_csv(HO / "failed_events_checked.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print(EV[[c for c in ["name", "cik", "name_matches", "claimed_petition", "first_item_1_03_anywhere", "rule", "event_8k_date", "days_after_petition", "last_periodic_period_end", "periodic_reports_since_2014", "error"] if c in EV]].to_string(index=False))
print("\n8-Ks around the petition (items in brackets) for rows that did not give a clean Item 1.03:")
if "rule" in EV:
    for _, r in EV[EV.rule != "ITEM_1.03"].iterrows(): print("  ", r["name"], "|", r.get("rule"), "|", r.get("8ks_around_petition"))

print("\nPART B: downloading companyfacts for the candidates that passed Part A (held-out raw files go in heldout/raw, never into your design raw/ folder)")
for _, r in EV.dropna(subset=["event_8k_date"]).iterrows():
    p = RAW_HO / f"{int(r['cik']):010d}.json"
    if p.exists(): continue
    try: json.dump(get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(r['cik']):010d}.json"), open(p, "w"))
    except Exception as e: print("  download failed:", r["name"], type(e).__name__)

CANDS = {"Revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet"],
         "CostOfGoods": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"], "GrossProfit": ["GrossProfit"],
         "Inventory": ["InventoryNet", "RetailRelatedInventoryMerchandise", "InventoryFinishedGoodsNetOfReserves"], "CurrAssets": ["AssetsCurrent"], "CurrLiab": ["LiabilitiesCurrent"],
         "Equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
         "Debt": ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "LineOfCredit", "LongTermLineOfCredit", "SecuredDebt", "NotesPayable", "SeniorNotes", "ConvertibleNotesPayable"],
         "NetIncome": ["NetIncomeLoss"], "OpCashFlow": ["NetCashProvidedByUsedInOperatingActivities"]}
FLOWM = {"Revenue", "CostOfGoods", "GrossProfit", "NetIncome", "OpCashFlow"}
def kind(days):
    if days != days: return "I"
    return "Q" if 80 <= days <= 105 else "YTD" if 150 <= days <= 300 else "A" if 340 <= days <= 380 else "other"
def first_full_year(facts, metric):
    ends = set()
    for tag in CANDS[metric]:
        recs = facts.get(tag, {}).get("units", {}).get("USD", [])
        if not recs: continue
        d = pd.DataFrame(recs); d["end"] = pd.to_datetime(d["end"])
        d["days"] = (d["end"] - pd.to_datetime(d["start"])).dt.days if "start" in d else np.nan
        d["k"] = d["days"].map(kind)
        d = d[d.k.isin(["Q", "YTD", "A"])] if metric in FLOWM else d[d.k == "I"]
        ends |= set(d["end"])
    if not ends: return "no tag", None
    e = pd.Series(sorted(ends)); last_full = e.max().year - 1
    per_year = e.groupby(e.dt.year).size()
    ok = [y for y in range(START_YEAR, last_full + 1) if per_year.get(y, 0) >= 4]
    if not ok: return "none", e.min().date()
    # earliest year from which every year up to last_full has >= 4 period ends
    y0 = last_full
    while y0 - 1 >= START_YEAR and per_year.get(y0 - 1, 0) >= 4: y0 -= 1
    return (str(y0) if per_year.get(last_full, 0) >= 4 else "none"), e.min().date()

rows = []
srcs = [(r["ticker"], r["group"], RAW / f"{int(r['cik']):010d}.json") for _, r in companies.iterrows()]
srcs += [(r["ticker"], "heldout_failed", RAW_HO / f"{int(r['cik']):010d}.json") for _, r in EV.dropna(subset=["event_8k_date"]).iterrows()]
for tk, grp, path in srcs:
    if not path.exists(): rows.append(dict(ticker=tk, group=grp, note="no file")); continue
    facts = json.load(open(path))["facts"]["us-gaap"]; row = dict(ticker=tk, group=grp)
    for m in CANDS:
        y, fe = first_full_year(facts, m); row[m] = y
        if m == "Revenue": row["rev_first_end"] = fe
    rows.append(row)
AUD = pd.DataFrame(rows)
for m in CANDS:
    if m not in AUD: AUD[m] = np.nan
AUD.to_csv(HO / "history_audit.csv", index=False)
print("\nPART B: for each company and metric, the earliest year from which EVERY year up to its last full year has at least 4 period ends (any of the candidate tags).")
print("'none' = gaps in the most recent years too; 'no tag' = none of the candidate tags exists. Compare with 2014-2016: a metric whose first full year is 2019 cannot be used for pre-2019 scoring.\n")
print(AUD.to_string(index=False))
print("\nmetrics by number of companies whose first full year is 2016 or earlier:")
print({m: int(pd.to_numeric(AUD[m], errors="coerce").le(2016).sum()) for m in CANDS}, "of", len(AUD), "companies")
