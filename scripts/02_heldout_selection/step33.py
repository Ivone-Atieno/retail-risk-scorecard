# ===== STEP 33: multi-component debt search for ALL control candidates, fixed filing reader, strong zero check, debt table, event text, core-tag diagnostics. NO SCORES. =====
# Run in the SAME Colab session after Steps 31 and 32. Resumable (heldout/controls/cache/c33_*.json): after a timeout just run it again.
for nm in ["CT", "facts_from", "inst", "find_filing", "get_text", "balance_region", "sample_ends", "WORDS", "NUM", "_sub", "_txt", "START", "usd", "HEADERS"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Step 31 in this session first")
import itertools, json, re
Q = pd.read_csv(CT / "controls_summary.csv")

# ---------- 0. business-model exclusions: decided on what the company does, before any score is seen ----------
NONCONSUMER = {"CDW": "B2B IT reseller", "INSIGHT ENTERPRISES": "B2B IT reseller", "PC CONNECTION": "B2B IT reseller", "PCM": "B2B IT reseller",
               "TITAN MACHINERY": "machinery dealer", "BUILDERS FIRSTSOURCE": "B2B building products", "BMC STOCK": "B2B building products",
               "DIPLOMAT PHARMACY": "specialty pharmacy services", "FASTENAL": "industrial distributor", "HANESBRANDS": "apparel manufacturer",
               "FIRSTCASH": "pawn lender", "IAC": "not retail", "MATCH GROUP": "not retail", "LIBERTY EXPEDIA": "not retail", "CRESTWOOD": "not retail (energy)"}
def nonconsumer(name):
    n = str(name).upper()
    for k, why in NONCONSUMER.items():
        if k in n: return why
    return ""

# ---------- 1. a better filing reader (fixes found in Step 32): equity-section "convertible" lines, years read as amounts, note-number columns ----------
BAD2 = re.compile(r"deferred|operating lease|unused|availability|issuance|discount|payable due to related|held by related|loss on|gain on|refinanc|preferred|mezzanine|redeemable|stockholders|shareholders", re.I)
EQ_CTX = re.compile(r"shares|authorized|class [a-z]|par value|preferred|series [a-z]|common stock|treasury", re.I)
def debt_items2(text):
    reg = balance_region(text)
    if reg is None: return None
    items, seen = [], set()
    for m in WORDS.finditer(reg):
        seg = reg[max(0, m.start() - 70): m.start()]
        cut = list(re.finditer(r"[\d][\d,\.]*\s|[—–]\s", seg)); lab = (seg[cut[-1].end():] if cut else seg) + m.group(0)
        if BAD2.search(lab): continue
        after = re.sub(r"\((?:See\s+)?(?:Note\s*)?\d+\)", " ", reg[m.end(): m.end() + 70])
        if m.group(0).lower().startswith("convertible") and EQ_CTX.search(seg[-40:] + after[:45]): continue
        toks = list(NUM.finditer(after))
        keep, prev = [], None                                                                        # a plain 4-digit year (and a dash glued to it, "2019—net") is not an amount
        for t in toks:
            g = t.group(1).strip()
            if re.fullmatch(r"(19|20)\d\d", g): prev = t; continue
            if g in "—–-" and prev is not None and t.start() == prev.end(): prev = None; continue
            prev = None; keep.append(t)
        toks = keep
        if not toks: continue
        n = toks[0]
        if len(toks) > 1 and re.fullmatch(r"\d{1,2}", n.group(1).strip()) and "," in toks[1].group(1): n = toks[1]   # "Debt 5 4,925": 5 is a note number
        pos = m.end() + n.start()
        if any(abs(pos - p) < 6 for p in seen): continue
        seen.add(pos); tok = n.group(1).strip()
        val = 0.0 if tok in "—–-" else float(tok.replace(",", ""))
        items.append((reg[max(0, m.start() - 28): m.end() + 6].strip(), val))
    return items
def read_items(cik, e):
    """(items, reason): reason tells why a filing could not be read"""
    try:
        hit = find_filing(int(cik), e)
        if hit is None: return None, "no 10-Q/10-K with that period end in the submissions list"
        it = debt_items2(get_text(int(cik), *hit)); _txt.clear()
        if it is None: return None, "balance sheet not found in the filing text"
        return it, ""
    except Exception as ex: return None, "fetch/parse error " + repr(ex)[:60]

# ---------- 2. component pool and formula search ----------
POOL_IN = re.compile(r"(Debt|Borrowing|LineOfCredit|NotesPayable|SeniorNotes|ConvertibleNotes|Debentures|SecuredDebt|UnsecuredDebt|TermLoan|LoansPayable|NotesAndLoans)")
POOL_OUT = re.compile(r"(Fair|Maturit|Repay|Interest|Expense|Issuance|Proceeds|Percent|Rate|Gain|Loss|Fee|Cost|Unamort|Discount|Premium|Face|Increase|Decrease|Payment|Remaining|Available|Capacity|Maximum|Facility|Related|Instrument|Extinguish|Conversion|Equity|Noncash|Assumed|Acquired|Forgiv|Guarant|Covenant|Collateral|Debtor|Reduction|Sale|Hedg|Derivative|Receivable|Securities|HeldTo|Tax|Excluded|Amount$)")
LEASE_OK = re.compile(r"^(Debt|LongTermDebt)AndCapitalLease")
def quarter_ends(f): ca = inst(f, "AssetsCurrent"); return [e for e in ca.index if e >= pd.Timestamp(START)]
def val_at_s(S_, e):
    if S_ is None or not len(S_): return None
    x = S_.index[np.argmin(np.abs((S_.index - e).days))]; return float(S_[x]) if abs((x - e).days) <= 5 else None
def build_pool(f, ends):
    P = {}
    for tag in f:
        if not POOL_IN.search(tag) or POOL_OUT.search(tag): continue
        if "Lease" in tag and not LEASE_OK.match(tag): continue
        s = inst(f, tag)
        if len(s) < 8 or s.min() < 0 or s.max() <= 0: continue
        P[tag] = s
    if not P: return {}
    mx = max(s.max() for s in P.values())
    order = sorted(P, key=lambda t: (0 if P[t].max() >= 0.15 * mx else 1, -len(P[t])))
    return {t: P[t] for t in order[:14]}
def tie2(total, items):
    pos = [v for _, v in items if v > 0]
    if not pos: return "ZERO_OK" if (total is None or total == 0) else "NOTIE"
    if total is None or total == 0: return "NOTIE"
    for sc in (1e3, 1e6, 1.0):
        if abs(sum(pos) - total / sc) <= max(0.013 * abs(total / sc), 0.0006): return "TIE"
    return "NOTIE"
def search(pool, V, samp, items_by, ends):
    best = None; tags = list(pool)
    for r in range(1, 5):
        for combo in itertools.combinations(tags, r):
            outc = []
            for e in samp:
                pr = [V[t][e] for t in combo if V[t][e] is not None]; outc.append(tie2(sum(pr) if pr else None, items_by[e]))
            sc = sum(o in ("TIE", "ZERO_OK") for o in outc)
            if best is not None and sc < best[0][0]: continue
            cov = sum(any(V[t][e] is not None for t in combo) for e in ends) / max(len(ends), 1)
            key = (sc, -r, cov)
            if best is None or key > best[0]: best = (key, combo, outc)
    return best

def process(c):
    cik = int(c["cik"]); tk = c["ticker"] if isinstance(c["ticker"], str) and c["ticker"] else f"CIK{cik}"
    ev = pd.Timestamp(c["event"]) if isinstance(c["event"], str) and c["event"] else None
    f = facts_from(CT / "raw" / f"{cik:010d}.json"); ends = [e for e in quarter_ends(f) if ev is None or e < ev]
    pool = build_pool(f, ends); V = {t: {e: val_at_s(pool[t], e) for e in ends} for t in pool}
    res = dict(cik=cik, ticker=tk, name=c["name"], event=c["event"] if isinstance(c["event"], str) else "", old_status=c["status"], status="", formula="", ties="", debt_cov=np.nan, gap_check="", reason="")
    # read filings for the tie-out
    samp, items_by, why = [], {}, {}
    for e in sample_ends(ends, 9):
        if len(samp) >= 6: break
        it, rs = read_items(cik, e)
        if it is None: why[str(e.date())] = rs; continue
        items_by[e] = it; samp.append(e)
    if len(samp) < 4:
        res.update(status="NEEDS HAND WORK", reason=f"only {len(samp)} filings readable: " + "; ".join(sorted(set(why.values())))[:150]); return res, [], []
    totals = {}; fails = []; zerofilled = set(ends) if not pool else set()
    if not pool:
        if all(not [v for _, v in items_by[e] if v > 0] for e in samp):
            res.update(status="CONTROL", formula="(none)", ties=f"{len(samp)}/{len(samp)} zero", debt_cov=1.0, gap_check="no debt tags, no debt lines (rule R2)")
            totals = {e: 0.0 for e in ends}
        else: res.update(status="NEEDS HAND WORK", reason="no debt tags but the filing shows debt lines")
    else:
        (sc, nr, cov), combo, outc = search(pool, V, samp, items_by, ends)
        res.update(formula="+".join(t + "?" for t in combo), ties=f"{sc}/{len(samp)}", debt_cov=round(cov, 2))
        for e, o in zip(samp, outc):
            if o == "NOTIE":
                pr = [V[t][e] for t in combo if V[t][e] is not None]; fails.append(f"      {e.date()} formula {sum(pr)/1e6 if pr else float('nan'):,.1f}m | filing: " + ("; ".join(f"{l[:26]}={v:,.0f}" for l, v in items_by[e] if v > 0)[:200] or "no positive debt line"))
        if sc < len(samp) - 1 or len(samp) < 5: res.update(status="NEEDS HAND WORK", reason=f"best component set ties {sc}/{len(samp)}")
        else:
            for e in ends:
                pr = [V[t][e] for t in combo if V[t][e] is not None]; totals[e] = sum(pr) if pr else None
            gap = [e for e in ends if totals[e] is None]
            if not gap: res.update(status="CONTROL", gap_check="no gaps")
            else:
                anytag = [e for e in gap if any((V[t][e] or 0) > 0 for t in pool)]            # a debt tag has a value in a 'gap' quarter
                zr = 0; ex = []
                for e in sample_ends(gap, 4):
                    it, rs = read_items(cik, e)
                    if it is None: continue
                    if [v for _, v in it if v > 0]: ex.append(f"{e.date()} " + "; ".join(f"{l[:22]}={v:,.0f}" for l, v in it if v > 0)[:90])
                    else: zr += 1
                n_read = zr + len(ex)
                if anytag: res.update(status="NEEDS HAND WORK", gap_check=f"{len(gap)} gap quarters; {len(anytag)} have a debt tag value outside the formula", reason="gap quarters hold debt tags not in the formula")
                elif ex: res.update(status="NEEDS HAND WORK", gap_check=f"{len(gap)} gap quarters; read {n_read}: {zr} zero", reason="debt lines in gap quarters: " + " || ".join(ex)[:200])
                elif n_read < 3: res.update(status="NEEDS HAND WORK", gap_check=f"{len(gap)} gap quarters; only {n_read} readable", reason="gap quarters not verifiable")
                else:
                    res.update(status="CONTROL", gap_check=f"{len(gap)} gap quarters zero-filled (read {n_read}/{n_read} = no debt line; no debt tag has a value)")
                    for e in gap: totals[e] = 0.0
                    zerofilled = set(gap)
    if res["status"] == "CONTROL" and res["event"]: res["status"] = "NEW FAILED"
    rows = []; prev = None
    if res["status"] in ("CONTROL", "NEW FAILED"):
        for e in ends:
            v = totals.get(e)
            q = (100 * (v - prev) / prev) if (v is not None and prev not in (None, 0)) else np.nan
            fl = "MISSING" if v is None else ("JUMP>50%" if (pd.notna(q) and abs(q) > 50) else "")
            rows.append(dict(ticker=tk, end=str(e.date()), total_m=None if v is None else round(v / 1e6, 3), qoq_pct=None if pd.isna(q) else round(q, 1), flag=fl,
                             detail=("zero-verified" if e in zerofilled else res["formula"]), gross_m=None if v is None else round(v / 1e6, 3)))
            if v is not None: prev = v
    return res, fails, rows

# ---------- 3. run ----------
todo = Q[Q.status.isin(["CONTROL", "CONTROL (debt gaps)", "NEEDS HAND WORK", "NEW FAILED"]) | Q.reason.fillna("").str.contains("could be read")].copy()
skip = todo[todo["name"].map(nonconsumer) != ""]
todo = todo[todo["name"].map(nonconsumer) == ""]
print(f"PART 1: business-model exclusions ({len(skip)}): " + "; ".join(f"{n} ({nonconsumer(n)})" for n in skip["name"]))
print(f"\nPART 2: {len(todo)} companies: ticker | old status -> new status | components found | ties | debt coverage | gap check | reason\n")
ALL, ROWS = [], []
for _, c in todo.iterrows():
    cp = CT / "cache" / f"c33_{int(c['cik'])}.json"
    if cp.exists(): d = json.load(open(cp)); res, fails, rows = d["res"], d["fails"], d["rows"]
    else:
        try: res, fails, rows = process(c)
        except Exception as ex: res, fails, rows = dict(cik=int(c["cik"]), ticker=str(c["ticker"]), name=c["name"], event="", old_status=c["status"], status="NEEDS HAND WORK", formula="", ties="", debt_cov=np.nan, gap_check="", reason="ERROR " + repr(ex)[:100]), [], []
        json.dump(dict(res=res, fails=fails, rows=rows), open(cp, "w"), default=str)
    ALL.append(res); ROWS += rows
    print(f"{res['ticker'][:8]:8s}| {res['old_status'][:16]:16s} -> {res['status']:15s}| {res['formula'][:75]:75s}| {res['ties']:9s}| {res['debt_cov']} | {res['gap_check'][:80]}" + (f" | {res['reason'][:150]}" if res["reason"] else ""))
    if res["status"] == "NEEDS HAND WORK":
        for ln in fails[:3]: print(ln)
R = pd.DataFrame(ALL); R.to_csv(CT / "controls_final.csv", index=False)
pd.DataFrame(ROWS).to_csv(CT / "debt_quarterly_controls.csv", index=False)
print("\nSUMMARY:", R["status"].value_counts().to_dict(), "| usable controls:", int((R.status == "CONTROL").sum()), "| new failed:", int((R.status == "NEW FAILED").sum()))

# ---------- 4. the Item 1.03 filings: what do they actually say? ----------
print("\nPART 3: text around Item 1.03 in each event 8-K (first 450 characters)\n")
seen = set()
for _, c in Q[Q.event.notna() & Q.event.astype(str).ne("")].iterrows():
    rec = _sub.get(int(c["cik"]))
    if rec is None: continue
    e = rec[(rec["form"] == "8-K") & rec["items"].fillna("").str.contains("1.03") & (pd.to_datetime(rec["filingDate"]) >= "2014-01-01")].sort_values("filingDate")
    for _, r in e.head(2).iterrows():
        if r["accessionNumber"] in seen: continue
        seen.add(r["accessionNumber"])
        try:
            t = get_text(int(c["cik"]), r["accessionNumber"], r["primaryDocument"]); _txt.clear(); i = t.find("1.03")
            print(f"{int(c['cik'])} {c['name']} filed {r['filingDate']}: ...{t[max(0, i - 20): i + 450]}\n")
        except Exception as ex: print(f"{int(c['cik'])} {c['name']} filed {r['filingDate']}: could not fetch {repr(ex)[:80]}\n")

# ---------- 5. real retailers excluded for incomplete core data: which tags exist? (diagnostic only, nothing is adopted automatically) ----------
print("PART 4: core-data diagnostics for real retailers excluded on cost/inventory coverage (tag: share of quarter ends covered)\n")
def share(f, tag, kind, ends):
    d = usd(f, tag); d = d[d["days"].isna()] if kind == "inst" else d[d["days"].notna() & (d["days"] >= 80)]
    S_ = sorted(set(d["end"])); return sum(any(abs((x - e).days) <= 6 for x in S_) for e in ends) / max(len(ends), 1)
for _, c in Q[(Q.status == "EXCLUDED") & Q.reason.fillna("").str.contains("core data incomplete")].iterrows():
    if nonconsumer(c["name"]): continue
    f = facts_from(CT / "raw" / f"{int(c['cik']):010d}.json"); ends = quarter_ends(f)
    cost = sorted(((share(f, t, "flow", ends), t) for t in f if re.search(r"Cost", t) and not re.search(r"Interest|Tax|Deferred|Estimated|Unrecognized|Impair|Share|Stock|Lease|Pension|Expense|Capitalized|Restructuring", t)), reverse=True)[:4]
    invt = sorted(((share(f, t, "inst", ends), t) for t in f if re.search(r"Inventor", t)), reverse=True)[:4]
    print(f"{c['name']} ({c['reason']})\n   cost-like: " + "; ".join(f"{t}:{s:.2f}" for s, t in cost) + "\n   inventory-like: " + "; ".join(f"{t}:{s:.2f}" for s, t in invt))
print("\nStep 33 done. Files: controls_final.csv, debt_quarterly_controls.csv")
