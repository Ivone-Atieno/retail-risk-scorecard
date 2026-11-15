# ===== STEP 34: Step 33 with its bugs fixed (reader regression, short-lived debt tags, tie-break, unreadable older filings) + older-filing event rescan + diagnostics. NO SCORES. =====
# Run in the SAME Colab session after Steps 31-33. Resumable (heldout/controls/cache/c34_*.json): after a timeout just run it again.
for nm in ["CT", "facts_from", "inst", "find_filing", "get_text", "balance_region", "sample_ends", "WORDS", "NUM", "_sub", "_txt", "START", "usd", "HEADERS"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Step 31 in this session first")
import itertools, json, re, time
for nm in ["load_sub", "ends_union", "near", "REVT", "COSTT", "INVT"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Step 31 in this session first")
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
BAD2 = re.compile(r"deferred|operating lease|unused|availability|issuance|discount|payable due to related|held by related|loss on|gain on|refinanc|preferred|mezzanine", re.I)
EQ_CTX = re.compile(r"shares|authorized|class [a-z]|par value|preferred|series [a-z]|common stock|treasury", re.I)
def debt_items2(text):
    reg = balance_region(text)
    if reg is None: return None
    items, seen = [], set()
    for m in WORDS.finditer(reg):
        seg = reg[max(0, m.start() - 70): m.start()]
        cut = list(re.finditer(r"[\d][\d,\.]*\s|[—–]\s", seg)); lab = ((seg[cut[-1].end():] if cut else seg) + m.group(0)).split(":")[-1]          # text after a heading colon only
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
        if len(s) < 1 or s.min() < 0 or s.max() <= 0: continue          # short-lived tags are kept: a revolver drawn in 3 quarters is still debt
        P[tag] = s
    if not P: return {}
    mx = max(s.max() for s in P.values())
    order = sorted(P, key=lambda t: (0 if P[t].max() >= 0.15 * mx else 1, -len(P[t])))
    return {t: P[t] for t in order[:14]}
def all_debt(f):
    A = {}
    for tag in f:
        if not POOL_IN.search(tag) or POOL_OUT.search(tag): continue
        if "Lease" in tag and not LEASE_OK.match(tag): continue
        s = inst(f, tag)
        if len(s) and s.max() > 0: A[tag] = s
    return A
def overlap(combo): return any(a != b and b.startswith(a) for a in combo for b in combo)      # a total tag together with its own components double counts
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
            if overlap(combo): continue
            outc = []
            for e in samp:
                pr = [V[t][e] for t in combo if V[t][e] is not None]; outc.append(tie2(sum(pr) if pr else None, items_by[e]))
            sc = sum(o in ("TIE", "ZERO_OK") for o in outc)
            if best is not None and sc < best[0][0]: continue
            cov = sum(any(V[t][e] is not None for t in combo) for e in ends) / max(len(ends), 1)
            key = (sc, round(cov, 3), -r)          # among equal tie-outs: widest coverage first, then fewest components
            if best is None or key > best[0]: best = (key, combo, outc)
    return best

def process(c):
    cik = int(c["cik"]); tk = c["ticker"] if isinstance(c["ticker"], str) and c["ticker"] else f"CIK{cik}"
    ev = pd.Timestamp(c["event"]) if isinstance(c["event"], str) and c["event"] else None
    f = facts_from(CT / "raw" / f"{cik:010d}.json"); ends = [e for e in quarter_ends(f) if ev is None or e < ev]
    pool = build_pool(f, ends); ALLD = all_debt(f); V = {t: {e: val_at_s(pool[t], e) for e in ends} for t in pool}
    res = dict(cik=cik, ticker=tk, name=c["name"], event=c["event"] if isinstance(c["event"], str) else "", old_status=c["status"], status="", formula="", ties="", debt_cov=np.nan, gap_check="", reason="")
    # read filings for the tie-out
    samp, items_by, why = [], {}, {}
    res["read"] = ""; res["diag_ends"] = []
    for e in sample_ends(ends, 9):
        if len(samp) >= 6: break
        it, rs = read_items(cik, e)
        if it is None: why[str(e.date())] = rs; continue
        items_by[e] = it; samp.append(e)
    if len(samp) < 4:
        res.update(status="NEEDS HAND WORK", reason=f"only {len(samp)} filings readable: " + "; ".join(sorted(set(why.values())))[:150]); return res, [], []
    totals = {}; fails = []; zerofilled = set(ends) if not ALLD else set()
    res["read"] = f"{min(samp).year}-{max(samp).year}"; res["diag_ends"] = []
    if not ALLD:
        if all(not [v for _, v in items_by[e] if v > 0] for e in samp):
            res.update(status="CONTROL", formula="(none)", ties=f"{len(samp)}/{len(samp)} zero", debt_cov=1.0, gap_check="no debt tag with any value, no debt lines (rule R2)")
            totals = {e: 0.0 for e in ends}
        else: res.update(status="NEEDS HAND WORK", reason="no debt tags but the filing shows debt lines")
    elif not pool: res.update(status="NEEDS HAND WORK", reason="debt tags exist but none usable (negative values?)")
    else:
        (sc, cov, nr), combo, outc = search(pool, V, samp, items_by, ends)
        res.update(formula="+".join(t + "?" for t in combo), ties=f"{sc}/{len(samp)}", debt_cov=round(cov, 2))
        for e, o in zip(samp, outc):
            if o == "NOTIE":
                res["diag_ends"].append(str(e.date()))
                pr = [V[t][e] for t in combo if V[t][e] is not None]; fails.append(f"      {e.date()} formula {sum(pr)/1e6 if pr else float('nan'):,.1f}m | filing: " + ("; ".join(f"{l[:26]}={v:,.0f}" for l, v in items_by[e] if v > 0)[:200] or "no positive debt line"))
        if sc < len(samp) - 1 or len(samp) < 5: res.update(status="NEEDS HAND WORK", reason=f"best component set ties {sc}/{len(samp)}")
        else:
            for e in ends:
                pr = [V[t][e] for t in combo if V[t][e] is not None]; totals[e] = sum(pr) if pr else None
            gap = [e for e in ends if totals[e] is None]
            if not gap: res.update(status="CONTROL", gap_check="no gaps")
            else:
                anytag = [e for e in gap if any((val_at_s(ALLD[t], e) or 0) > 0 for t in ALLD)]            # a debt tag has a value in a 'gap' quarter
                zr = 0; ex = []
                for e in sample_ends(gap, 4):
                    it, rs = read_items(cik, e)
                    if it is None: continue
                    if [v for _, v in it if v > 0]: ex.append(f"{e.date()} " + "; ".join(f"{l[:22]}={v:,.0f}" for l, v in it if v > 0)[:90])
                    else: zr += 1
                n_read = zr + len(ex)
                if anytag: res["diag_ends"] += [str(x.date()) for x in anytag[:2]]
                if anytag: res.update(status="NEEDS HAND WORK", gap_check=f"{len(gap)} gap quarters; {len(anytag)} have a debt tag value outside the formula", reason="gap quarters hold debt tags not in the formula")
                elif ex: res.update(status="NEEDS HAND WORK", gap_check=f"{len(gap)} gap quarters; read {n_read}: {zr} zero", reason="debt lines in gap quarters: " + " || ".join(ex)[:200])
                elif n_read < 3: res.update(status="NEEDS HAND WORK", gap_check=f"{len(gap)} gap quarters; only {n_read} readable", reason="gap quarters not verifiable")
                else:
                    res.update(status="CONTROL", gap_check=f"{len(gap)} gap quarters zero-filled (read {n_read}/{n_read} = no debt line; no debt tag of any kind has a value)")
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

# ---------- 3. full filing history (older submission files) and the Item 1.03 rescan ----------
def full_sub(cik):
    j = load_sub(cik); parts = [pd.DataFrame(j["filings"]["recent"])]
    for fl in j["filings"].get("files", []):
        if str(fl.get("filingTo", "9999")) < "2014-01-01": continue
        p = CT / "cache" / f"subfile_{fl['name']}"
        if not p.exists(): time.sleep(0.2); p.write_bytes(requests.get(f"https://data.sec.gov/submissions/{fl['name']}", headers=HEADERS, timeout=40).content)
        parts.append(pd.DataFrame(json.load(open(p))))
    d = pd.concat(parts, ignore_index=True).drop_duplicates("accessionNumber"); d["reportDate"] = pd.to_datetime(d["reportDate"], errors="coerce"); return d
EVN = {}
for k, cik in enumerate(Q["cik"].astype(int)):
    try:
        d = full_sub(cik); _sub[cik] = d
        e = d[(d["form"] == "8-K") & d["items"].fillna("").str.contains("1.03") & (pd.to_datetime(d["filingDate"]) >= "2014-01-01")]
        EVN[cik] = str(e["filingDate"].min()) if len(e) else ""
    except Exception as ex: EVN[cik] = ""; print("could not load full history for", cik, repr(ex)[:60])
Q["event_old"] = Q["event"].fillna("").astype(str); Q["event"] = Q["cik"].astype(int).map(EVN).fillna("")
new_ev = Q[(Q.event != "") & (Q.event_old == "")]
print(f"PART 1: Item 1.03 rescan with the FULL filing history: {int((Q.event != '').sum())} companies with an event; NEW compared with Step 31: " + (", ".join(f"{n} {e}" for n, e in zip(new_ev['name'], new_ev['event'])) or "none") + "\n")

# ---------- 4. candidates ----------
extra = []
for i, c in Q[(Q.status == "EXCLUDED") & Q.reason.fillna("").str.contains("core data incomplete") & (Q["name"].map(nonconsumer) == "")].iterrows():
    f = facts_from(CT / "raw" / f"{int(c['cik']):010d}.json"); en = quarter_ends(f)
    cv = [sum(near(S_, e) for e in en) / max(len(en), 1) for S_ in (ends_union(f, REVT, "flow"), ends_union(f, COSTT, "flow"), ends_union(f, INVT + ["RetailRelatedInventory"], "inst"))]
    print(f"core re-check {c['name']}: rev/cost/inv with RetailRelatedInventory added = {cv[0]:.2f}/{cv[1]:.2f}/{cv[2]:.2f} -> " + ("now eligible" if min(cv) >= 0.85 else "stays excluded"))
    if min(cv) >= 0.85: extra.append(i)
sel = Q.status.isin(["CONTROL", "CONTROL (debt gaps)", "NEEDS HAND WORK", "NEW FAILED"]) | Q.reason.fillna("").str.contains("could be read") | Q.index.isin(extra)
todo = Q[sel & (Q["name"].map(nonconsumer) == "")].copy()
print(f"\nPART 2: {len(todo)} companies. ticker | old -> new status | components | ties | debt coverage | gap check | filings read (years) | reason\n")
ALL, ROWS = [], []
def facts_near(cik, e):
    raw = json.load(open(CT / "raw" / f"{int(cik):010d}.json"))["facts"]; out = set(); e = pd.Timestamp(e)
    for ns, d in raw.items():
        for tag, v in d.items():
            if not re.search(r"(Debt|Borrow|Credit|NotesPayable|Loan|Convertible|Debenture|Notes)", tag) or re.search(r"Interest|Fair|Expense|Maturit|Repay|Proceeds|Issuance|Capacity|Maximum|Rate|Percent|Fee", tag): continue
            for u in v.get("units", {}).get("USD", []):
                if "start" in u or u["val"] <= 0: continue
                if abs((pd.Timestamp(u["end"]) - e).days) <= 5: out.add((u["val"], f"{ns}:{tag}"))
    top = sorted(out, reverse=True)[:7]
    return "; ".join(f"{t.split(':')[1][:40]}={v/1e6:,.1f}m" for v, t in top) or "no debt-like fact at that date"
for _, c in todo.iterrows():
    cp = CT / "cache" / f"c34_{int(c['cik'])}.json"
    if cp.exists(): d = json.load(open(cp)); res, fails, rows, dg = d["res"], d["fails"], d["rows"], d["dg"]
    else:
        try:
            res, fails, rows = process(c); dg = []
            if res["status"] == "NEEDS HAND WORK":
                for e in res.get("diag_ends", [])[:2]:
                    try: dg.append(f"      facts near {e} (all namespaces): " + facts_near(c["cik"], e))
                    except Exception: pass
        except Exception as ex:
            res, fails, rows, dg = dict(cik=int(c["cik"]), ticker=str(c["ticker"]), name=c["name"], event="", old_status=c["status"], status="NEEDS HAND WORK", formula="", ties="", debt_cov=np.nan, gap_check="", reason="ERROR " + repr(ex)[:100], read=""), [], [], []
        json.dump(dict(res=res, fails=fails, rows=rows, dg=dg), open(cp, "w"), default=str)
    ALL.append(res); ROWS += rows
    print(f"{res['ticker'][:9]:9s}| {res['old_status'][:12]:12s} -> {res['status']:15s}| {res['formula'][:70]:70s}| {res['ties']:9s}| {res['debt_cov']} | {res['gap_check'][:75]} | {res.get('read', '')}" + (f" | {res['reason'][:140]}" if res["reason"] else ""))
    if res["status"] == "NEEDS HAND WORK":
        for ln in fails[:2] + dg: print(ln)
R = pd.DataFrame(ALL); R.to_csv(CT / "controls_final34.csv", index=False)
pd.DataFrame(ROWS).to_csv(CT / "debt_quarterly_controls34.csv", index=False)
print("\nSUMMARY:", R["status"].value_counts().to_dict(), "| usable controls:", int((R.status == "CONTROL").sum()), "| new failed:", int((R.status == "NEW FAILED").sum()))
print("\nZERO-DEBT (rule R2) companies:", ", ".join(R[R.gap_check.str.contains("R2", na=False)]["ticker"]))

# ---------- 5. the new failed companies: last quarters of the debt series (watch for a drop caused by reclassification to current debt) ----------
print("\nPART 3: last 6 debt quarters before the petition for each NEW FAILED company\n")
D = pd.DataFrame(ROWS)
for tk in R[R.status == "NEW FAILED"]["ticker"]:
    print(tk, R[R.ticker == tk]["event"].iloc[0], R[R.ticker == tk]["formula"].iloc[0]); print(D[D.ticker == tk].tail(6)[["end", "total_m", "qoq_pct", "flag"]].to_string(index=False))
print("\nStep 34 done. Files: controls_final34.csv, debt_quarterly_controls34.csv")
