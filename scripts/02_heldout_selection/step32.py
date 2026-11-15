# ===== STEP 32: look inside the controls that did not pass (NEEDS HAND WORK), run the zero check on the debt-gap controls, and verify the bankruptcy events. NO SCORES. =====
# Run in the SAME Colab session right after Step 31 (it reuses Step 31's functions). Resumable: results are cached in heldout/controls/cache/diag_*.json
for nm in ["CT", "eval_formula", "debt_items", "verdict", "find_filing", "get_text", "sample_ends", "tie"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Step 31 in this session first")
Q = pd.read_csv(CT / "controls_summary.csv"); G = pd.read_csv(CT / "universe_size_gate.csv")
def fm(x): return "NA" if x is None else f"{x/1e6:,.1f}m"
def lines_of(items, k=4):
    pos = [(l, v) for l, v in (items or []) if v > 0]
    return "; ".join(f"{l[:30]}={v:,.0f}" for l, v in pos[:k]) or "no positive debt line"
def val_at_s(S_, e):
    if S_ is None or not len(S_): return None
    x = S_.index[np.argmin(np.abs((S_.index - e).days))]; return S_[x] if abs((x - e).days) <= 5 else None
def quarter_ends(f): ca = inst(f, "AssetsCurrent"); return [e for e in ca.index if e >= pd.Timestamp(START)]

# ---------------- PART A: NEEDS HAND WORK: where exactly does the best formula fail the tie-out? ----------------
print("PART A: NEEDS HAND WORK. For each sampled quarter: formula value | tie-out verdict | what the filing balance sheet shows (numbers as printed, usually thousands)\n")
for _, c in Q[Q.status == "NEEDS HAND WORK"].iterrows():
    cp = CT / "cache" / f"diag_{int(c['cik'])}.json"
    if cp.exists():
        for ln in json.load(open(cp)): print(ln)
        continue
    out = [f"{(c['ticker'] if isinstance(c['ticker'], str) and c['ticker'] else int(c['cik']))} | {c['name']} | formula {c['debt_formula']} | ties {c['ties']} | debt coverage {c['debt_cov']}"]
    try:
        f = facts_from(CT / "raw" / f"{int(c['cik']):010d}.json"); S_ = eval_formula(f, c["debt_formula"]); ends = quarter_ends(f); n = 0
        for e in sample_ends(ends, 9):
            if n >= 6: break
            try:
                hit = find_filing(int(c["cik"]), e)
                if hit is None: continue
                it = debt_items(get_text(int(c["cik"]), *hit)); _txt.clear()
                if it is None: continue
                n += 1; v = val_at_s(S_, e); t = tie(v, it)
                if t in ("TIE", "ZERO_OK"): out.append(f"   {e.date()} {fm(v):>10} | ok"); continue
                vd, miss = verdict(v or 0.0, it)
                out.append(f"   {e.date()} {fm(v):>10} | {vd[:34]}{(' | missing: ' + miss[:90]) if miss else ''} | filing: {lines_of(it)}")
            except Exception as ex: out.append(f"   {e.date()} could not read: {repr(ex)[:60]}")
    except Exception as ex: out.append(f"   ERROR {repr(ex)[:80]}")
    json.dump(out, open(cp, "w")); print("\n".join(out))

# ---------------- PART B: debt-gap controls: are the gap quarters true zeros? ----------------
print("\nPART B: debt-gap controls. Formula quarters vs gap quarters; up to 4 gap quarters read in the filing (zero check)\n")
for _, c in Q[Q.status.str.contains("debt gaps", na=False)].iterrows():
    cp = CT / "cache" / f"gap_{int(c['cik'])}.json"
    if cp.exists(): print(json.load(open(cp))[0]); continue
    nm = c["ticker"] if isinstance(c["ticker"], str) and c["ticker"] else int(c["cik"])
    try:
        f = facts_from(CT / "raw" / f"{int(c['cik']):010d}.json"); S_ = eval_formula(f, c["debt_formula"]); ends = quarter_ends(f)
        cov = [e for e in ends if val_at_s(S_, e) is not None]; gap = [e for e in ends if val_at_s(S_, e) is None]
        where = "never covered" if not cov else ("gaps before first value" if max(gap or [pd.Timestamp(START)]) < min(cov) else ("gaps after last value" if min(gap or [pd.Timestamp("2100-01-01")]) > max(cov) else "gaps in the middle / both ends"))
        zeros, exc, read = 0, [], 0
        for e in sample_ends(gap, 4):
            try:
                hit = find_filing(int(c["cik"]), e)
                if hit is None: continue
                it = debt_items(get_text(int(c["cik"]), *hit)); _txt.clear()
                if it is None: continue
                read += 1
                if not [v for _, v in it if v > 0]: zeros += 1
                else: exc.append(f"{e.date()}: {lines_of(it, 3)}")
            except Exception: continue
        line = f"{nm} | {c['name'][:24]} | {len(cov)} covered / {len(gap)} gap quarters ({where}) | covered {cov[0].date() if cov else '-'}..{cov[-1].date() if cov else '-'} | gap quarters read {read}: {zeros} show no debt line" + (f" | EXCEPTIONS {' || '.join(exc)[:300]}" if exc else "")
    except Exception as ex: line = f"{nm} | ERROR {repr(ex)[:80]}"
    json.dump([line], open(cp, "w")); print(line)

# ---------------- PART C: events found by the Item 1.03 rule: the filing itself ----------------
print("\nPART C: Item 1.03 8-Ks in the control universe (open the link to confirm it is a bankruptcy filing)\n")
for _, c in Q[Q.event.notna() & Q.event.astype(str).ne("")].iterrows():
    rec = _sub.get(int(c["cik"]))
    if rec is None: continue
    e = rec[(rec["form"] == "8-K") & rec["items"].fillna("").str.contains("1.03") & (pd.to_datetime(rec["filingDate"]) >= "2014-01-01")].sort_values("filingDate")
    for _, r in e.head(3).iterrows():
        print(f"{int(c['cik'])} | {c['name']} | status {c['status']} | filed {r['filingDate']} | items {r['items']} | https://www.sec.gov/Archives/edgar/data/{int(c['cik'])}/{r['accessionNumber'].replace('-', '')}/{r['primaryDocument']}")

# ---------------- PART D: who was dropped before the debt step, and why ----------------
print("\nPART D: excluded for data reasons (names, so tag misses can be told from real data gaps)\n")
for _, c in Q[Q.status == "EXCLUDED"].iterrows(): print(f"{int(c['cik'])} | {c['name']} | sic {c['sic']} | {c['reason']}")
print("\nin size range but no revenue found:")
for _, c in G[G.status == "no revenue found"].iterrows(): print(f"{int(c['cik'])} | {c['name']} | sic {c['sic']} | {c['why']}")
print("\nStep 32 done.")
