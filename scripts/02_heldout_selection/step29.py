# ===== STEP 29: manual debt rows from the filings (Pier 1 revolver, confirmed zero quarters) and three balance sheets to read. Extraction QA only: NO SCORES. =====
import json, re, time, itertools
import numpy as np, pandas as pd, requests
from bs4 import BeautifulSoup
for nm in ["BASE", "HEADERS"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run the start-of-session cell first")
HO = BASE / "heldout"; START = "2014-01-01"
TM = pd.read_csv(HO / "tag_map_heldout_v4.csv").fillna("")
ONLY = ["Pier 1", "francesca", "iMedia", "Aeropostale", "Pacific Sunwear", "LL Flooring", "Stage Stores"]
SHOW_ALL_LINES = ["Pier 1"]            # print every debt line found, so the revolver amounts can be read off
SHOW_REGION = [("Aeropostale", "2014-08-02"), ("francesca", "2019-11-02")]   # print the balance-sheet text itself
# corrections found in Steps 24-25 (evidence: filing lines matched to XBRL facts)
FIX = {
 "Bon-Ton":         "LongTermDebtNoncurrent+LongTermDebtCurrent?+LineOfCredit?",
 "Pier 1":          "LongTermDebtNoncurrent+LongTermDebtCurrent?",                                   # revolver is not in XBRL companyfacts: tie-out will show it as MISSING, to be added by hand
 "Destination":     "LongTermDebtNoncurrent+LongTermDebtCurrent?+LinesOfCreditCurrent?",
 "Gordmans":        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
 "Aeropostale":     "DueToRelatedPartiesNoncurrent?+DueToRelatedPartiesCurrent?+ShortTermBorrowings?",
 "Pacific Sunwear": "LongTermDebtNoncurrent+LongTermDebtCurrent?+LinesOfCreditCurrent?",
 "Stein Mart":      "LongTermDebtNoncurrent+LongTermDebtCurrent?",
 "francesca":       "LongTermDebtNoncurrent+LongTermDebtCurrent?",                                   # Step 27: LineOfCredit duplicated long-term debt (20.0 vs 10.0)
 "iMedia":          "LongTermDebtNoncurrent+LongTermDebtCurrent?",                                   # Step 27: LongTermLineOfCredit duplicated long-term debt (2x)
                                   # Step 26: LineOfCredit duplicated the long-term debt line (double count)
}
for frag, fm in FIX.items():
    TM.loc[TM["name"].str.contains(frag, regex=False), "debt_formula"] = fm


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

WORDS = re.compile(r"(debt|borrowings?|credit facility|line of credit|revolv\w*|notes? payable|term loan|senior notes|convertible|indebtedness|due to related part\w*)", re.I)
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


fm = dict(zip(TM["name"], TM["debt_formula"])); cikm = dict(zip(TM["name"], TM["cik"]))
def nm(frag): return [n for n in fm if frag in n][0]
def fval(name, end):
    f = facts_of(cikm[name]); D = eval_formula(f, fm[name]); x = D.index[np.argmin(np.abs((D.index - pd.Timestamp(end)).days))]
    return D[x] if abs((x - pd.Timestamp(end)).days) <= 5 else None
def scale_of(items, fv):
    s = sum(v for lab, v in items if not re.search(r"borrowings under", lab, re.I) and v > 0) or 1.0
    return 10 ** round(np.log10(fv / s)) if fv else 1.0
out = []
# ---- PART A: Pier 1 revolver ----
print("PART A: Pier 1, revolver borrowings read from the balance sheet (added to the formula value as a manual row)\n")
P = nm("Pier 1")
for e in ["2016-11-26", "2019-06-01", "2019-08-31", "2019-11-30"]:
    hit = find_filing(cikm[P], e); items = debt_items(get_text(cikm[P], *hit)); fv = fval(P, e)
    rev = [v for lab, v in items if re.search(r"borrowings under", lab, re.I) and v > 0]; sc = scale_of(items, fv)
    if not rev: print(f"   {e}: no revolver amount found: read by hand"); continue
    tot = fv + rev[0] * sc
    print(f"   {e}: formula {fv / 1e6:,.3f}m + revolver {rev[0] * sc / 1e6:,.3f}m = {tot / 1e6:,.3f}m   (filing {hit[0]})")
    out.append(dict(name=P, cik=int(cikm[P]), end=e, debt_total_usd=round(tot), basis="formula + revolver read from balance sheet", source_accession=hit[0], note="revolver not in XBRL companyfacts"))
# ---- PART B: gap quarters, zero only if no positive debt line is found in a balance sheet that was actually found ----
print("\nPART B: gap quarters rescanned with the fixed parser (zero rows only where the balance sheet is found and has no positive debt line)\n")
G = pd.read_csv(HO / "debt_gap_review.csv")
for frag in ["RTW", "francesca", "hhgregg"]:
    name = nm(frag)
    for _, g in G[(G["name"].str.contains(frag, regex=False)) & G["result"].str.startswith("ZERO")].iterrows():
        hit = find_filing(cikm[name], g["end"])
        if hit is None: print(f"   {name} {g['end']}: filing not found"); continue
        items = debt_items(get_text(cikm[name], *hit))
        if items is None: print(f"   {name} {g['end']}: NO BALANCE SHEET FOUND, not set to zero"); continue
        pos = [(l, v) for l, v in items if v > 0]
        if pos: print(f"   {name} {g['end']}: DEBT LINE FOUND, not zero: {pos[:3]}"); continue
        print(f"   {name} {g['end']}: confirmed zero ({len(items)} debt-like lines, all nil)  filing {hit[0]}")
        out.append(dict(name=name, cik=int(cikm[name]), end=g["end"], debt_total_usd=0, basis="zero: no debt line or nil line in balance sheet", source_accession=hit[0], note="gap quarter, no XBRL value"))
O = pd.DataFrame(out); O.to_csv(HO / "manual_debt_overrides.csv", index=False)
print(f"\n{len(O)} manual rows saved to manual_debt_overrides.csv (review them before they are used)")
# ---- PART C: balance sheets to read by eye ----
print("\nPART C: balance-sheet text for the three cases the checker cannot read\n")
for frag, e in [("LL Flooring", "2024-03-31"), ("LL Flooring", "2021-12-31"), ("iMedia", "2021-10-30"), ("Stage Stores", "2017-04-29")]:
    n = nm(frag); hit = find_filing(cikm[n], e)
    txt = get_text(cikm[n], *hit) if hit else ""
    reg = balance_region(txt) if txt else None
    print(f"--- {n} {e} (formula {(fval(n, e) or 0) / 1e6:,.1f}m) ---\n{(reg or 'balance sheet not found')[:1700]}\n")
