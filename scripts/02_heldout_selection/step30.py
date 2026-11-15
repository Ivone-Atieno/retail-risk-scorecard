# ===== STEP 30: LL Flooring re-read ('Credit Agreement'), and the held-out debt table in the format of debt_quarterly_final.csv. Extraction QA only: NO SCORES. =====
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

WORDS = re.compile(r"(debt|borrowings?|credit facility|line of credit|revolv\w*|notes? payable|term loan|senior notes|convertible|indebtedness|credit agreement|due to related part\w*)", re.I)
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
TICK = {"Sears": "SHLD", "Bon-Ton": "BONT", "Pier 1": "PIR", "Stein Mart": "SMRT", "Stage": "SSI", "Penney": "JCP", "Tailored": "TLRD", "Ascena": "ASNA",
        "francesca": "FRAN", "RTW": "RTW", "GNC": "GNC", "Fred": "FRED", "Destination": "DEST", "hhgregg": "HGG", "Gordmans": "GMAN",
        "Aeropostale": "ARO", "Pacific Sunwear": "PSUN", "LL Flooring": "LL", "iMedia": "IMBI"}
def tick(name): return [v for k, v in TICK.items() if k in name][0]
# ---------------- PART A: LL Flooring ----------------
print("PART A: LL Flooring, 'Credit Agreement' line against the formula (LongTermLineOfCredit)\n")
LL = nm("LL Flooring"); f = facts_of(cikm[LL]); D = eval_formula(f, fm[LL]); b = pd.Timestamp(TM.loc[TM.name == LL, "event"].iloc[0])
ca = inst(f, "AssetsCurrent"); ends = [e for e in ca.index if b - pd.Timedelta(days=int(40 * 30.4)) <= e < b]
manual = pd.read_csv(HO / "manual_debt_overrides.csv") if (HO / "manual_debt_overrides.csv").exists() else pd.DataFrame()
new = []
for e in ends:
    hit = find_filing(cikm[LL], e); items = debt_items(get_text(cikm[LL], *hit)) if hit else None
    has = any(abs((x - e).days) <= 5 for x in D.index)
    if items is None: print(f"   {e.date()}: balance sheet not found"); continue
    pos = [(l, v) for l, v in items if v > 0]
    if has:
        fv = D[D.index[np.argmin(np.abs((D.index - e).days))]]
        ok = any(abs(v * 1e3 - fv) <= 0.013 * fv for _, v in pos)
        print(f"   {e.date()}: formula {fv / 1e6:,.1f}m -> " + ("TIES to the credit agreement line" if ok else f"NO TIE, lines {pos[:3]}"))
    elif pos: print(f"   {e.date()}: no formula value but DEBT LINE FOUND {pos[:3]}")
    else:
        print(f"   {e.date()}: confirmed zero (no positive debt line)  filing {hit[0]}")
        new.append(dict(name=LL, cik=int(cikm[LL]), end=str(e.date()), debt_total_usd=0, basis="zero: credit agreement line nil or absent", source_accession=hit[0], note="gap quarter, no XBRL value"))
if new:
    manual = pd.concat([manual[~((manual["name"] == LL) & manual["end"].isin([n["end"] for n in new]))], pd.DataFrame(new)], ignore_index=True)
    manual.to_csv(HO / "manual_debt_overrides.csv", index=False)
print(f"\nmanual_debt_overrides.csv now has {len(manual)} rows")

# ---------------- PART B: the held-out debt table, same columns as debt_quarterly_final.csv ----------------
print("\nPART B: held-out debt table (formula values for every quarter end from 2014, manual rows override or fill)\n")
rows, exposure = [], []
for name in fm:
    f = facts_of(cikm[name]); D = eval_formula(f, fm[name]) / 1e6
    ca = inst(f, "AssetsCurrent"); evd = pd.Timestamp(TM.loc[TM.name == name, "event"].iloc[0])
    man = manual[manual["name"] == name]
    for e in ca.index:
        if e >= evd: continue
        mm = man[(pd.to_datetime(man["end"]) - e).abs() <= pd.Timedelta(days=5)]
        if len(mm): val, flag, det = mm.iloc[0]["debt_total_usd"] / 1e6, "MANUAL", mm.iloc[0]["basis"] + " | " + mm.iloc[0]["source_accession"]
        else:
            near = D.index[np.argmin(np.abs((D.index - e).days))] if len(D) else None
            if near is not None and abs((near - e).days) <= 5: val, flag, det = D[near], "ok", fm[name]
            else: val, flag, det = np.nan, "MISSING", "no formula value and no verified manual row"
        rows.append(dict(ticker=tick(name), end=e, total_m=val, flag=flag, detail=det, gross_m=val))
T = pd.DataFrame(rows).sort_values(["ticker", "end"]).reset_index(drop=True)
T["qoq_pct"] = T.groupby("ticker")["total_m"].pct_change() * 100
T = T[["ticker", "end", "total_m", "qoq_pct", "flag", "detail", "gross_m"]]
T.to_csv(HO / "debt_quarterly_heldout.csv", index=False)
cnt = T.pivot_table(index="ticker", columns="flag", values="end", aggfunc="count", fill_value=0)
print(cnt.to_string())
miss = T[T.flag == "MISSING"]
print("\nquarters with no debt value (outside the 40-month window these were not checked against filings):")
print(miss.groupby("ticker")["end"].agg(["count", "min", "max"]).to_string() if len(miss) else "none")
print("\nsaved debt_quarterly_heldout.csv and the updated manual_debt_overrides.csv in", HO)
