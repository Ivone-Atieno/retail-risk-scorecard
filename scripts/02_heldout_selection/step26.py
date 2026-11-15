# ===== STEP 26: corrected debt formulas (v2) tied out against the filings at four quarters per company. Extraction QA only: NO SCORES. =====
import json, re, time, itertools
import numpy as np, pandas as pd, requests
from bs4 import BeautifulSoup
for nm in ["BASE", "HEADERS"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run the start-of-session cell first")
HO = BASE / "heldout"; START = "2014-01-01"
TM = pd.read_csv(HO / "tag_map_heldout_proposed.csv").fillna("")
# corrections found in Steps 24-25 (evidence: filing lines matched to XBRL facts)
FIX = {
 "Bon-Ton":         "LongTermDebtNoncurrent+LongTermDebtCurrent?+LineOfCredit?",
 "Pier 1":          "LongTermDebtNoncurrent+LongTermDebtCurrent?",                                   # revolver is not in XBRL companyfacts: tie-out will show it as MISSING, to be added by hand
 "Destination":     "LongTermDebtNoncurrent+LongTermDebtCurrent?+LinesOfCreditCurrent?",
 "Gordmans":        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
 "Aeropostale":     "DueToRelatedPartiesNoncurrent?+DueToRelatedPartiesCurrent?+ShortTermBorrowings?",
 "Pacific Sunwear": "LongTermDebtNoncurrent+LongTermDebtCurrent?+LinesOfCreditCurrent?",
}
for frag, fm in FIX.items():
    TM.loc[TM["name"].str.contains(frag, regex=False), "debt_formula"] = fm
TM.to_csv(HO / "tag_map_heldout_v2.csv", index=False)

def facts_of(cik): return json.load(open(HO / "raw" / f"{int(cik):010d}.json"))["facts"]["us-gaap"]
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

WORDS = re.compile(r"(debt|borrowings?|credit facility|line of credit|revolv\w*|notes? payable|term loan|senior notes|convertible|indebtedness|related part\w*)", re.I)
BAD = re.compile(r"deferred|operating lease|unused|availability|issuance|discount|rent\b", re.I)
def debt_items(text):
    """Balance-sheet debt-like line items: (label, number as printed). Duplicates (same number position) are merged."""
    i = text.lower().find("total current liabilities")
    if i < 0: return None
    reg = text[max(0, i - 900): i + 1300]; items, seen = [], set()
    for m in WORDS.finditer(reg):
        label = reg[max(0, m.start() - 28): m.end() + 6]
        if BAD.search(reg[max(0, m.start() - 22): m.end()]): continue
        after = re.sub(r"\(\d\)", " ", reg[m.end(): m.end() + 70]); n = re.search(r"([—–-]\s|\d[\d,]*\.?\d*)", after)
        if not n: continue
        pos = m.end() + n.start()
        if any(abs(pos - p) < 6 for p in seen): continue
        seen.add(pos); tok = n.group(1).strip()
        val = 0.0 if tok in "—–-" else float(tok.replace(",", ""))
        items.append((label.strip(), val))
    return items
def verdict(formula_val, items):
    if items is None: return "NO BALANCE SHEET FOUND", ""
    vals = [v for _, v in items]
    for scale in (1e3, 1e6, 1.0):
        tgt = formula_val / scale
        subsets = [c for r in range(0, min(len(vals), 10) + 1) for c in itertools.combinations(range(len(vals)), r)]
        hits = [c for c in subsets if abs(sum(vals[k] for k in c) - tgt) <= max(0.004 * abs(tgt), 0.0006)]
        if hits:
            pos = {k for k, v in enumerate(vals) if v > 0}
            if any({k for k in c if vals[k] > 0} == pos for c in hits): return "TIES to all debt lines", ""
            best = max(hits, key=lambda c: sum(vals[k] > 0 for k in c))
            miss = [items[k][0] + f" = {items[k][1]:,.1f}" for k in sorted(pos - set(best))]
            return "TIES to a SUBSET: check what is missing", "; ".join(miss)
    return "NO TIE: read the filing", ""

rows = []
print("PART A: formulas v2 against the filing at four quarters per company (the 'lines' are what the balance sheet shows; numbers are in the filing's own unit)\n")
for _, r in TM.iterrows():
    f = facts_of(r["cik"]); b = pd.Timestamp(r["event"])
    D = eval_formula(f, r["debt_formula"]) if r["debt_formula"] else pd.Series(dtype=float)
    ca = inst(f, "AssetsCurrent"); ends = [e for e in ca.index if b - pd.Timedelta(days=int(40 * 30.4)) <= e < b]
    ends = [e for e in ends if len(D) and any(abs((x - e).days) <= 5 for x in D.index)]
    if not ends: print(f"{r['name']}: no quarter with a formula value"); continue
    pick = sorted({ends[0], ends[len(ends) // 3], ends[2 * len(ends) // 3], ends[-1]})
    print(f"{r['name']} | {r['debt_formula']}")
    for e in pick:
        x = D.index[np.argmin(np.abs((D.index - e).days))]; fv = D[x]
        try:
            hit = find_filing(r["cik"], e)
            if hit is None: res, miss, items = "FILING NOT FOUND", "", None
            else:
                items = debt_items(get_text(r["cik"], *hit)); res, miss = verdict(fv, items)
        except Exception as ex:
            res, miss, items = "ERROR " + repr(ex)[:70], "", None
        print(f"   {e.date()} formula {fv / 1e6:,.1f}m -> {res}" + (f" | missing: {miss}" if miss else ""))
        if res.startswith(("NO TIE", "TIES to a SUBSET")) and items:
            for lab, v in items[:6]: print(f"        line: {lab} | {v:,.1f}")
        rows.append(dict(name=r["name"], end=str(e.date()), formula_m=round(fv / 1e6, 2), result=res, missing=miss))
T = pd.DataFrame(rows); T.to_csv(HO / "debt_tieout_v2.csv", index=False)
print("\nSummary:", T["result"].value_counts().to_dict())
print("saved tag_map_heldout_v2.csv and debt_tieout_v2.csv in", HO)
