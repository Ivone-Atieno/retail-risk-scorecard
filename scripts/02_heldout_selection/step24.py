# ===== STEP 24: proposed held-out tag map + debt-gap review against the filings. Extraction QA only: NO SCORES. =====
import json, re, time
import numpy as np, pandas as pd, requests
from bs4 import BeautifulSoup
for nm in ["BASE", "HEADERS"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run the start-of-session cell first")
HO = BASE / "heldout"; START = "2014-01-01"
EXCLUDE = ("Container Store", "Christopher & Banks")        # excluded: insufficient history / one usable quarter after COVID blanking
ev = pd.read_csv(HO / "failed_events_checked.csv"); ev["event_8k_date"] = pd.to_datetime(ev["event_8k_date"])
ev = ev[ev["event_8k_date"].notna() & ~ev["name"].apply(lambda s: any(x in str(s) for x in EXCLUDE))].reset_index(drop=True)

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
def n_ends(f, tag, kind, before):
    d = usd(f, tag); d = d[d["end"] < before]
    d = d[d["days"].isna()] if kind == "inst" else d[d["days"].notna() & (d["days"] >= 80)]
    return d["end"].nunique()

def eval_formula(f, formula):      # same formula language as debt_definition.csv: '+' add, '|' first available, '?' optional
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

# ---------------- PART 1: proposed tag map ----------------
REVP  = ["RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet"]
COSTP = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]
INVP  = ["InventoryNet", "InventoryFinishedGoodsNetOfReserves", "InventoryFinishedGoods", "RetailRelatedInventoryMerchandise", "MerchandiseInventoryNet"]
VERIFIED = {"Sears Holdings": dict(rev=["SalesRevenueNet"], cost=["CostOfGoodsAndServicesSold"], inv=["InventoryFinishedGoods"],
                                   debt="DebtAndCapitalLeaseObligations", note="verified against 10-Q/10-K text; cost includes buying and occupancy; debt includes short-term borrowings and capital leases")}
def propose_debt(f, before):
    c = lambda t, k="inst": n_ends(f, t, k, before)
    if c("DebtAndCapitalLeaseObligations") >= 8: return "DebtAndCapitalLeaseObligations", "lease-inclusive total"
    if c("LongTermDebtNoncurrent") >= 4:
        extra = "".join(f"+{t}?" for t in ["ShortTermBorrowings", "LineOfCredit", "LongTermLineOfCredit"] if c(t) >= 4)
        return "LongTermDebtNoncurrent+LongTermDebtCurrent?" + extra, "noncurrent + current (+ revolver/short-term where tagged)"
    if c("LongTermDebt") >= 4:
        extra = "".join(f"+{t}?" for t in ["ShortTermBorrowings", "LineOfCredit", "LongTermLineOfCredit"] if c(t) >= 4)
        return "LongTermDebt" + extra, "LongTermDebt (check it includes the current portion)"
    for t in ["LongTermLineOfCredit", "LineOfCredit", "LongTermDebtAndCapitalLeaseObligations", "SecuredDebt", "ConvertibleNotesPayable"]:
        if c(t) >= 4: return t, "only tag available: " + t
    return "", "NO DEBT TAG"
rows = []
for _, r in ev.iterrows():
    f = facts_of(r["cik"]); b = r["event_8k_date"]; v = VERIFIED.get(r["name"])
    keep = lambda L, k="flow": [t for t in L if n_ends(f, t, k, b) >= 4]
    rev, cost, inv = (v["rev"], v["cost"], v["inv"]) if v else (keep(REVP), keep(COSTP), keep(INVP, "inst"))
    gp = n_ends(f, "GrossProfit", "flow", b)
    debt, dnote = (v["debt"], "verified") if v else propose_debt(f, b)
    flags = []
    if len(rev) > 1 and not v: flags.append("several revenue tags: confirm they do not overlap or double count")
    if not cost and gp < 4: flags.append("NO COST OR GROSS PROFIT TAG")
    if not cost and gp >= 4: flags.append("cost missing, use GrossProfit")
    if len(inv) > 1 and not v: flags.append("several inventory tags: confirm the first is the total")
    if not debt: flags.append("NO DEBT TAG")
    rows.append(dict(name=r["name"], cik=int(r["cik"]), event=str(b.date()), revenue=" > ".join(rev), cost=" > ".join(cost), gross_profit_tag="GrossProfit" if gp >= 4 else "",
                     inventory=" > ".join(inv), debt_formula=debt, debt_basis=dnote, flags="; ".join(flags)))
TM = pd.DataFrame(rows); TM.to_csv(HO / "tag_map_heldout_proposed.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
print("PART 1: proposed held-out tag map (saved as tag_map_heldout_proposed.csv). Priority lists use '>' (first available per period).\n")
print(TM[["name", "revenue", "cost", "inventory", "debt_formula", "flags"]].to_string(index=False), "\n")

# ---------------- filing helpers ----------------
_sub, _txt = {}, {}
def find_filing(cik, end):
    if cik not in _sub:
        time.sleep(0.25)
        _sub[cik] = pd.DataFrame(requests.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", headers=HEADERS, timeout=40).json()["filings"]["recent"])
        _sub[cik]["reportDate"] = pd.to_datetime(_sub[cik]["reportDate"], errors="coerce")
    s = _sub[cik]; m = s[s["form"].isin(["10-Q", "10-K"]) & ((s["reportDate"] - pd.Timestamp(end)).abs() <= pd.Timedelta(days=4))]
    if m.empty: return None
    x = m.sort_values("filingDate").iloc[0]; return x["accessionNumber"], x["primaryDocument"], x["form"]
def get_text(cik, accn, doc):
    if (cik, accn) in _txt: return _txt[(cik, accn)]
    time.sleep(0.25)
    html = requests.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{doc}", headers=HEADERS, timeout=60).text
    t = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ")); _txt[(cik, accn)] = t; return t
DEBTWORDS = r"(debt|borrowings?|credit facility|line of credit|revolv\w*|notes? payable|term loan|senior notes|convertible)"
def liabilities_region(text):
    i = text.lower().find("total current liabilities")
    return None if i < 0 else text[max(0, i - 900): i + 1300]
def debt_lines(region, width=95):
    """(snippet, first_value_token) for each debt-like line item; token is '-' for a dash/nil, else the first number after the label."""
    out = []
    for m in re.finditer(DEBTWORDS, region, re.I):
        before = region[max(0, m.start() - 22): m.end()]
        if re.search(r"deferred|operating lease", before, re.I): continue
        after = re.sub(r"\(\d\)", " ", region[m.end(): m.end() + 80])
        t = re.search(r"([—–]|\d[\d,\.]*)", after)
        tok = "-" if (t and t.group(1) in "—–") else (t.group(1) if t else "?")
        out.append((region[max(0, m.start() - 25): m.start() + width], tok))
    return out[:4]
def classify(region):
    if region is None: return "NO BALANCE SHEET FOUND", []
    L = debt_lines(region)
    if not L: return "ZERO-LIKELY (no debt line)", []
    if all(tok == "-" for _, tok in L): return "ZERO-LIKELY (dash)", [x for x, _ in L]
    return "HAS DEBT LINE: add the tag or an override", [x for x, _ in L]

# ---------------- PART 2: debt-gap quarters, checked against the filings ----------------
print("PART 2: quarter ends with no value from the proposed debt formula (quarters from 40 months before the event on), checked against the filing's balance sheet\n")
gaprows = []
for _, r in TM.iterrows():
    f = facts_of(r["cik"]); b = pd.Timestamp(r["event"])
    ca = inst(f, "AssetsCurrent"); ca = ca[(ca.index < b) & (ca.index >= b - pd.Timedelta(days=int(40 * 30.4)))]
    D = eval_formula(f, r["debt_formula"]) if r["debt_formula"] else pd.Series(dtype=float)
    gaps = [e for e in ca.index if not len(D) or not any(abs((x - e).days) <= 5 for x in D.index)]
    print(f"{r['name']}: {len(ca)} quarter ends in range, {len(gaps)} without a debt value")
    for e in gaps:
        try:
            hit = find_filing(r["cik"], e)
            if hit is None: res, L = "FILING NOT FOUND IN SEC LIST: check by hand", []
            else: res, L = classify(liabilities_region(get_text(r["cik"], hit[0], hit[1])))
        except Exception as ex:
            res, L = "ERROR " + repr(ex)[:80], []
        print(f"   {e.date()}  {res}" + (f" | {L[0][:70]}" if L else ""))
        gaprows.append(dict(name=r["name"], end=str(e.date()), result=res, snippet=(L[0][:120] if L else "")))
G = pd.DataFrame(gaprows); G.to_csv(HO / "debt_gap_review.csv", index=False)
print("\nSummary of gap quarters:", G["result"].str.split(" \\(").str[0].str.split(":").str[0].value_counts().to_dict() if len(G) else "none")

# ---------------- PART 3: formula spot check, one filing per company ----------------
print("\nPART 3: the proposed debt formula against the latest filing before the event (compare the formula value with the debt lines; values in millions)\n")
for _, r in TM.iterrows():
    f = facts_of(r["cik"]); b = pd.Timestamp(r["event"])
    D = eval_formula(f, r["debt_formula"]) if r["debt_formula"] else pd.Series(dtype=float)
    D = D[D.index < b]
    if D.empty: print(f"{r['name']}: no formula value before the event"); continue
    e = D.index.max()
    try:
        hit = find_filing(r["cik"], e); reg = liabilities_region(get_text(r["cik"], hit[0], hit[1])) if hit else None
        L = [x for x, _ in debt_lines(reg)] if reg else []
    except Exception as ex:
        L = ["ERROR " + repr(ex)[:80]]
    print(f"{r['name']} | {e.date()} | formula {r['debt_formula']} = {D[e] / 1e6:,.1f}m (in the filing's own unit: check thousands vs millions)")
    for s in L: print("      ", s)
print("\nsaved tag_map_heldout_proposed.csv and debt_gap_review.csv in", HO)
