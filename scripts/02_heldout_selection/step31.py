# ===== STEP 31: dated control universe + tag maps + debt-formula selection + filing tie-out, in one run. NO SCORES, outcomes are never used to choose anything. =====
# Resumable: per-company results are cached in heldout/controls/, so after a timeout just run the cell again.
import json, re, time, io, zipfile, itertools
import numpy as np, pandas as pd, requests
from bs4 import BeautifulSoup
for nm in ["BASE", "HEADERS"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run the start-of-session cell first")
HO = BASE / "heldout"; CT = HO / "controls"; CT.mkdir(exist_ok=True); (CT / "raw").mkdir(exist_ok=True); (CT / "cache").mkdir(exist_ok=True); (CT / "dl").mkdir(exist_ok=True)
START = "2014-01-01"
UNIVERSE_Q = ["2019q1", "2019q2"]            # 10-K filers in these quarters = Dec 2019 universe (Dec and Jan fiscal year ends)
REV_MIN, REV_MAX = 250e6, 20e9               # annual revenue range, set from the failed companies' sales (0.4bn to 17bn)
SAMPLE_N = 6                                 # quarters per company tied out against the filing
MAX_COMPANIES = None                         # set e.g. 5 to test the run on a few companies first
def sic_ok(s):
    s = int(s)
    return (5200 <= s <= 5499) or s == 5531 or (5600 <= s <= 5799) or (5900 <= s <= 5999)
def facts_from(path): return json.load(open(path))["facts"]["us-gaap"]
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
    return d.sort_values("filed").drop_duplicates("end", keep="first").set_index("end")["val"]
def eval_formula(f, formula):
    terms = [t.strip() for t in str(formula).split("+") if t.strip()]; parts, opt = [], []
    for t in terms:
        alts = [a.strip() for a in t.split("|")]; opt.append(any(a.endswith("?") for a in alts))
        ser = [inst(f, a.rstrip("?")) for a in alts]; ser = [s for s in ser if len(s)]
        parts.append(pd.concat(ser, axis=1).bfill(axis=1).iloc[:, 0] if ser else pd.Series(dtype=float))
    if not parts: return pd.Series(dtype=float)
    ends = sorted(set().union(*[set(p.index) for p in parts])); out = {}
    for e in ends:
        tot, ok = 0.0, True
        for p, o in zip(parts, opt):
            if e in p.index and pd.notna(p[e]): tot += p[e]
            elif not o: ok = False; break
        if ok: out[e] = tot
    return pd.Series(out, dtype=float).sort_index()

_sub, _txt = {}, {}
def find_filing(cik, end):
    if cik not in _sub:
        time.sleep(0.25)
        _sub[cik] = pd.DataFrame(requests.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", headers=HEADERS, timeout=40).json()["filings"]["recent"])
        _sub[cik]["reportDate"] = pd.to_datetime(_sub[cik]["reportDate"], errors="coerce")
    s = _sub[cik]; m = s[s["form"].isin(["10-Q", "10-K"]) & ((s["reportDate"] - pd.Timestamp(end)).abs() <= pd.Timedelta(days=4))]
    if m.empty: return None
    x = m.sort_values("filingDate").iloc[0]; return x["accessionNumber"], x["primaryDocument"]
def get_text(cik, accn, doc):
    if (cik, accn) in _txt: return _txt[(cik, accn)]
    time.sleep(0.25)
    html = requests.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{doc}", headers=HEADERS, timeout=60).text
    t = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ")); _txt[(cik, accn)] = t; return t

WORDS = re.compile(r"(debt|borrowings?|credit facility|line of credit|revolv\w*|notes? payable|term loan|senior (?:unsecured |secured )?notes|debentures|convertible|indebtedness|credit agreement|due to related part\w*)", re.I)
BAD = re.compile(r"deferred|operating lease|unused|availability|issuance|discount|payable due to related|held by related|loss on|gain on|refinanc|preferred|mezzanine", re.I)
def balance_region(text):
    low = text.lower(); i = -1; first = -1
    while True:
        i = low.find("total current liabilities", i + 1)
        if i < 0: break
        if first < 0: first = i
        if "total liabilities" in low[i: i + 2500] and "current liabilities" in low[max(0, i - 2500): i]: return text[max(0, i - 900): i + 1300]
    return None if first < 0 else text[max(0, first - 900): first + 1300]       # fallback: first occurrence
NUM = re.compile(r"([—–]|(?<=\s)-(?=\s+(?:[—–$\d]|-))|\d[\d,]*\.?\d*)")
def debt_items(text):
    """Balance-sheet debt-like line items: (label, number as printed). The label is only the words between the previous number and the keyword."""
    reg = balance_region(text)
    if reg is None: return None
    items, seen = [], set()
    for m in WORDS.finditer(reg):
        seg = reg[max(0, m.start() - 70): m.start()]
        cut = list(re.finditer(r"[\d][\d,\.]*\s|[—–]\s", seg)); lab = (seg[cut[-1].end():] if cut else seg) + m.group(0)
        if BAD.search(lab): continue
        after = re.sub(r"\((?:See\s+)?(?:Note\s*)?\d+\)", " ", reg[m.end(): m.end() + 70]); n = NUM.search(after)
        if not n: continue
        pos = m.end() + n.start()
        if any(abs(pos - p) < 6 for p in seen): continue
        seen.add(pos); tok = n.group(1).strip()
        val = 0.0 if tok in "—–-" else float(tok.replace(",", ""))
        items.append((reg[max(0, m.start() - 28): m.end() + 6].strip(), val))
    return items
def verdict(formula_val, items):
    if items is None: return "NO BALANCE SHEET FOUND", ""
    vals = [v for _, v in items]
    for scale in (1e3, 1e6, 1.0):
        tgt = formula_val / scale
        subsets = [c for r in range(0, min(len(vals), 10) + 1) for c in itertools.combinations(range(len(vals)), r)]
        hits = [c for c in subsets if abs(sum(vals[k] for k in c) - tgt) <= max(0.013 * abs(tgt), 0.0006)]
        if hits:
            pos = {k for k, v in enumerate(vals) if v > 0}
            if any({k for k in c if vals[k] > 0} == pos for c in hits): return "TIES to all debt lines", ""
            best = max(hits, key=lambda c: sum(vals[k] > 0 for k in c))
            miss = [items[k][0] + f" = {items[k][1]:,.1f}" for k in sorted(pos - set(best))]
            return "TIES to a SUBSET: check what is missing", "; ".join(miss)
    return "NO TIE: read the filing", ""




# ---------- who is excluded from the new batch ----------
cfile = BASE / "companiesv2.csv" if (BASE / "companiesv2.csv").exists() else BASE / "companies.csv"
DESIGN = set(pd.read_csv(cfile)["cik"].astype(int))
HELD = set(pd.read_csv(HO / "failed_events_checked.csv")["cik"].dropna().astype(int))

# ======================================================================
# PART 1: universe = US retail-SIC 10-K filers in 2019 (SEC Financial Statement Data Sets, sub.txt)
# ======================================================================
frames = []
for q in UNIVERSE_Q:
    zp = CT / "dl" / f"{q}.zip"
    if not zp.exists():
        r = requests.get(f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip", headers=HEADERS, stream=True, timeout=600)
        r.raise_for_status()
        with open(zp, "wb") as fh:
            for ch in r.iter_content(1 << 20): fh.write(ch)
    with zipfile.ZipFile(zp) as z:
        frames.append(pd.read_csv(z.open("sub.txt"), sep="\t", usecols=["cik", "name", "sic", "countryinc", "form", "filed"], dtype=str))
S = pd.concat(frames); S = S[S.form.eq("10-K") & S.sic.notna()]
S = S[S.sic.apply(lambda x: str(x).isdigit() and sic_ok(x))]
S = S[S.countryinc.fillna("US").isin(["US", ""])]
U = S.sort_values("filed").drop_duplicates("cik", keep="last")[["cik", "name", "sic"]].copy(); U["cik"] = U["cik"].astype(int)
print(f"PART 1: {len(U)} US retail-SIC 10-K filers in {UNIVERSE_Q}")

# ======================================================================
# PART 2: companyfacts download + size gate
# ======================================================================
REVT = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet"]
def annual_rev(f):
    best = None
    for t in REVT:
        d = usd(f, t); d = d[d["days"].between(340, 380) & (d["end"] >= "2018-12-01") & (d["end"] <= "2020-03-15")]
        if len(d):
            x = d.sort_values(["end", "filed"]).iloc[-1]
            if best is None or x["val"] > best: best = x["val"]
    return best
rows = []
for k, (_, u) in enumerate(U.iterrows()):
    p = CT / "raw" / f"{u['cik']:010d}.json"
    if not p.exists():
        time.sleep(0.15)
        r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{u['cik']:010d}.json", headers=HEADERS, timeout=60)
        if r.status_code != 200: rows.append(dict(cik=u["cik"], name=u["name"], sic=u["sic"], rev=None, why=f"no companyfacts ({r.status_code})")); continue
        p.write_bytes(r.content)
    try: rev = annual_rev(facts_from(p))
    except Exception: rev = None
    rows.append(dict(cik=u["cik"], name=u["name"], sic=u["sic"], rev=rev, why=""))
R = pd.DataFrame(rows)
R["status"] = np.where(R.cik.isin(DESIGN), "design sample (excluded)", np.where(R.cik.isin(HELD), "held-out failed (already extracted)",
              np.where(R.rev.isna(), "no revenue found", np.where(R.rev < REV_MIN, "too small", np.where(R.rev > REV_MAX, "too large", "IN SIZE RANGE")))))
print("PART 2: size gate:", R["status"].value_counts().to_dict(), "\n")
todo = R[R.status == "IN SIZE RANGE"].copy()

# ======================================================================
# PART 3: Item 1.03 events for everyone in range (objective rule, same as the failed list)
# ======================================================================
def load_sub(cik):
    p = CT / "cache" / f"sub_{cik}.json"
    if not p.exists():
        time.sleep(0.2); p.write_bytes(requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=HEADERS, timeout=40).content)
    return json.load(open(p))
events, tickers = {}, {}
for cik in todo["cik"]:
    j = load_sub(cik); rec = pd.DataFrame(j["filings"]["recent"]); rec["reportDate"] = pd.to_datetime(rec["reportDate"], errors="coerce")
    _sub[cik] = rec; tickers[cik] = (j.get("tickers") or [""])[0]
    e = rec[(rec["form"] == "8-K") & rec["items"].fillna("").str.contains("1.03") & (pd.to_datetime(rec["filingDate"]) >= "2014-01-01")]
    events[cik] = str(e["filingDate"].min()) if len(e) else ""
todo["ticker"] = todo["cik"].map(tickers); todo["event"] = todo["cik"].map(events)
print(f"PART 3: {int((todo.event != '').sum())} of {len(todo)} companies in range have an Item 1.03 8-K since 2014:")
print(todo[todo.event != ""][["ticker", "name", "event"]].to_string(index=False), "\n")

# ======================================================================
# PART 4: per company: core data coverage, debt formula chosen by agreement with the filings, tie-out
# ======================================================================
CANDS = ["LongTermDebtNoncurrent+LongTermDebtCurrent?",
         "LongTermDebtNoncurrent+LongTermDebtCurrent?+LineOfCredit?",
         "LongTermDebtNoncurrent+LongTermDebtCurrent?+LinesOfCreditCurrent?",
         "LongTermDebtNoncurrent+LongTermDebtCurrent?+ShortTermBorrowings?",
         "LongTermDebtNoncurrent+LongTermDebtCurrent?+ShortTermBorrowings?+LinesOfCreditCurrent?",
         "LongTermDebt", "LongTermDebt+ShortTermBorrowings?", "LongTermDebt+LongTermDebtCurrent?",
         "DebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligations+LongTermDebtAndCapitalLeaseObligationsCurrent?",
         "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "LongTermLineOfCredit", "LongTermLineOfCredit+LongTermDebtCurrent?",
         "LongTermDebtNoncurrent+LongTermDebtCurrent?+LongTermLineOfCredit?", "ShortTermBorrowings", "LineOfCredit", "ConvertibleNotesPayable+LongTermDebtNoncurrent?"]
INVT  = ["InventoryNet", "InventoryFinishedGoodsNetOfReserves", "InventoryFinishedGoods", "RetailRelatedInventoryMerchandise", "MerchandiseInventoryNet"]
COSTT = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "GrossProfit", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"]
def ends_union(f, tags, kind):
    S_ = set()
    for t in tags:
        d = usd(f, t); d = d[d["days"].isna()] if kind == "inst" else d[d["days"].notna() & (d["days"] >= 80)]
        S_ |= set(d["end"])
    return sorted(S_)
def near(sorted_ends, e, tol=6): return any(abs((x - e).days) <= tol for x in sorted_ends)
def tie(val, items):
    if items is None: return "NOBS"
    pos = [v for _, v in items if v > 0]
    if val is None or val == 0: return "ZERO_OK" if not pos else "NOTIE"
    return "TIE" if verdict(val, items)[0].startswith("TIES to all") else "NOTIE"
def sample_ends(ends, n):
    if len(ends) <= n: return list(ends)
    return [ends[int(round(i * (len(ends) - 1) / (n - 1)))] for i in range(n)]

results = []
work = todo if MAX_COMPANIES is None else todo.head(MAX_COMPANIES)
print(f"PART 4: {len(work)} companies (cached results are reused). Columns: ticker | status | core coverage rev/cost/inv | debt formula | ties | debt coverage\n")
for _, c in work.iterrows():
    cp = CT / "cache" / f"res_{c['cik']}.json"
    if cp.exists(): res = json.load(open(cp)); results.append(res); print(res["line"]); continue
    try:
        f = facts_from(CT / "raw" / f"{c['cik']:010d}.json"); ev = pd.Timestamp(c["event"]) if c["event"] else None
        ca = inst(f, "AssetsCurrent"); ends = [e for e in ca.index if e >= pd.Timestamp(START) and (ev is None or e < ev)]
        N = max(len(ends), 1)
        revE, costE, invE = ends_union(f, REVT, "flow"), ends_union(f, COSTT, "flow"), ends_union(f, INVT, "inst")
        cov = [sum(near(S_, e) for e in ends) / N for S_ in (revE, costE, invE)]
        res = dict(cik=int(c["cik"]), ticker=c["ticker"], name=c["name"], sic=c["sic"], rev=c["rev"], event=c["event"], n_quarters=len(ends),
                   cov_rev=round(cov[0], 2), cov_cost=round(cov[1], 2), cov_inv=round(cov[2], 2), debt_formula="", ties="", debt_cov=np.nan, status="", reason="")
        if len(ends) < 12: res.update(status="EXCLUDED", reason="fewer than 12 quarters of balance sheets")
        elif min(cov) < 0.85: res.update(status="EXCLUDED", reason=f"core data incomplete (rev/cost/inv {cov[0]:.2f}/{cov[1]:.2f}/{cov[2]:.2f})")
        else:
            series = {cf: eval_formula(f, cf) for cf in CANDS}
            def val_at(cf, e):
                S_ = series[cf]
                if not len(S_): return None
                x = S_.index[np.argmin(np.abs((S_.index - e).days))]; return S_[x] if abs((x - e).days) <= 5 else None
            samp, items_by = [], {}
            for e in sample_ends(ends, SAMPLE_N + 3):
                if len(samp) >= SAMPLE_N: break
                try:
                    hit = find_filing(int(c["cik"]), e)
                    if hit is None: continue
                    it = debt_items(get_text(int(c["cik"]), *hit)); _txt.clear()
                    if it is None: continue
                    items_by[e] = it; samp.append(e)
                except Exception: continue
            if len(samp) < 4: res.update(status="EXCLUDED", reason=f"only {len(samp)} filings could be read for the tie-out")
            else:
                best = None
                for cf in CANDS:
                    outc = [tie(val_at(cf, e), items_by[e]) for e in samp]
                    score = sum(o in ("TIE", "ZERO_OK") for o in outc)
                    covd = sum(val_at(cf, e) is not None for e in ends) / N
                    key = (score, covd)
                    if best is None or key > best[0]: best = (key, cf, outc)
                (score, covd), cf, outc = best
                nodebt = all(not [v for _, v in items_by[e] if v > 0] for e in samp) and not any(len(series[x]) for x in series)
                if nodebt: res.update(status="CONTROL", debt_formula="(none: no debt tags and no debt lines)", ties=f"{len(samp)}/{len(samp)} zero", debt_cov=1.0, reason="NO DEBT: zero for all quarters (rule R2)")
                else:
                    res.update(debt_formula=cf, ties=f"{score}/{len(samp)}", debt_cov=round(covd, 2))
                    if score >= len(samp) - 1 and covd >= 0.8: res.update(status="CONTROL")
                    elif score >= len(samp) - 1: res.update(status="CONTROL (debt gaps)", reason=f"formula ties but covers {covd:.0%} of quarters: gaps need the zero check")
                    else: res.update(status="NEEDS HAND WORK", reason=f"best formula ties only {score}/{len(samp)}")
        if res["event"] and res["status"].startswith("CONTROL"): res["status"] = res["status"].replace("CONTROL", "NEW FAILED")
        res["line"] = f"{(c['ticker'] or str(c['cik'])):6s}| {res['status']:22s}| {res['cov_rev']:.2f}/{res['cov_cost']:.2f}/{res['cov_inv']:.2f} | {res['debt_formula'][:58]:58s}| {res['ties']:9s}| {res['debt_cov']}" + (f" | {res['reason'][:70]}" if res["reason"] else "")
    except Exception as ex:
        res = dict(cik=int(c["cik"]), ticker=c["ticker"], name=c["name"], status="ERROR", reason=repr(ex)[:90], event=c["event"])
        res["line"] = f"{(c['ticker'] or str(c['cik'])):6s}| ERROR {res['reason']}"
    json.dump(res, open(cp, "w"), default=str); results.append(res); print(res["line"])
Q = pd.DataFrame(results).drop(columns=["line"], errors="ignore")
Q.to_csv(CT / "controls_summary.csv", index=False); R.to_csv(CT / "universe_size_gate.csv", index=False)
print("\nSUMMARY:", Q["status"].value_counts().to_dict())
print(f"usable controls: {int(Q['status'].str.startswith('CONTROL').sum())}; new failed companies found by the Item 1.03 rule: {int(Q['status'].str.startswith('NEW FAILED').sum())}")
print("saved controls_summary.csv and universe_size_gate.csv in", CT)
