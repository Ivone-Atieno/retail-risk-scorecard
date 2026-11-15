# ===== STEP 39: (A) Abercrombie 350m SeniorNotes re-check, (B) Genesco and Duluth spike quarters read in the filings, (C) checks of the protocol items against the data. NO SCORES, no outcomes. =====
# Run in the SAME Colab session after Steps 31-38 (about 5-10 minutes: roughly 15 filings are read).
for nm in ["CT", "facts_from", "all_debt", "val_at_s", "read_items", "REVT", "START"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Steps 31-38 in this session first")
import glob, json, re
from datetime import timedelta
HO = CT.parent
D37 = pd.read_csv(CT / "debt_quarterly_controls37.csv"); R37 = pd.read_csv(CT / "controls_final37.csv"); R37["spikes"] = R37["spikes"].fillna("")
def raw_facts(path): return json.load(open(path))["facts"]
def tag_vals_at(path, e, pat, skip=r"Interest|Fair|Expense|Rate|Percent|Fee|Maturit|Repay|Proceeds|Capacity|Maximum"):
    out = []; e = pd.Timestamp(e)
    for ns, d in raw_facts(path).items():
        for tag, v in d.items():
            if not re.search(pat, tag) or re.search(skip, tag): continue
            for u in v.get("units", {}).get("USD", []):
                if "start" in u or u["val"] <= 0 or abs((pd.Timestamp(u["end"]) - e).days) > 5: continue
                out.append((u["val"], f"{ns}:{tag}", u.get("form", ""), u.get("filed", ""), u.get("accn", "")))
    return sorted(set(out), reverse=True)[:9]
def show_tags(path, e):
    for val, tg, fm, fl, ac in tag_vals_at(path, e, r"(SeniorNotes|NotesPayable|Debt|Borrowing|LineOfCredit|LinesOfCredit|Debenture|Convertible|Notes)"):
        print(f"        fact {tg[:62]:62s} {val/1e6:10,.1f}m  {fm:5s} filed {fl}")
def filing_lines(cik, e):
    it, why = read_items(cik, e)
    if it is None: return None, f"filing not read: {why}"
    pos = [(l, v) for l, v in it if v > 0]
    return pos, "; ".join(f"{l[:34]}={v:,.0f}" for l, v in pos[:6]) or "no positive debt line"
def matches(total_usd, pos):
    fs = sum(v for _, v in pos)
    for sc in (1e3, 1e6, 1.0):
        if fs > 0 and abs(total_usd / sc - fs) <= 0.02 * fs: return True
    return fs == 0 and total_usd < 1e6

# ---------------- PART A: Abercrombie & Fitch ----------------
print("PART A: ABERCROMBIE & FITCH. The Step 38 screen flagged the series (303m) against a SeniorNotes tag (350m). Which is the balance-sheet figure?\n")
a = R37[R37.ticker == "ANF"]
if not len(a): print("ANF not found in controls_final37.csv")
else:
    cik = int(a.iloc[0]["cik"]); path = CT / "raw" / f"{cik:010d}.json"; ALLD = all_debt(facts_from(path)); bad = []
    for _, x in D37[(D37.ticker == "ANF") & D37.total_m.notna()].iterrows():
        e = pd.Timestamp(x["end"]); M = max([(val_at_s(ALLD[t], e) or 0, t) for t in ALLD] or [(0, "")])
        if M[0] >= 5e6 and x["total_m"] * 1e6 < 0.9 * M[0]: bad.append((e, x["total_m"], M))
    print(f"quarters where the series is more than 10% below a reported debt tag: {len(bad)}")
    for e, tot, M in bad[:3]:
        pos, txt = filing_lines(cik, e)
        verdict = "no filing" if pos is None else ("SERIES MATCHES the filing balance sheet" if matches(tot * 1e6, pos) else "series does NOT match the filing lines")
        print(f"   {e.date()}: series {tot:,.1f}m | tag {M[1]} {M[0]/1e6:,.1f}m | filing lines: {txt} | {verdict}"); show_tags(path, e)
    print("   Reading: if the series matches the balance sheet and the 350m is face value, the exclusion was a false positive and ANF can be restored (decide before the freeze, from this evidence).")

# ---------------- PART B: Genesco and Duluth spike quarters ----------------
print("\nPART B: spike quarters. A real seasonal revolver draw should match the filing balance sheet; a double count should not.\n")
for tk in ["GCO", "DLTH"]:
    r = R37[R37.ticker == tk]
    if not len(r): print(tk, "not found"); continue
    cik = int(r.iloc[0]["cik"]); path = CT / "raw" / f"{cik:010d}.json"; ds = D37[D37.ticker == tk].reset_index(drop=True)
    sp = [s for s in str(r.iloc[0]["spikes"]).split(";") if s]; print(f"{tk} ({r.iloc[0]['name'][:30]}): spikes {', '.join(sp) or 'none'}")
    for s in sp[:4]:
        i = ds.index[ds.end == s]
        if not len(i) or int(i[0]) == 0 or int(i[0]) >= len(ds) - 1: continue
        i = int(i[0]); a_, b_, c_ = ds.total_m[i - 1], ds.total_m[i], ds.total_m[i + 1]
        pos, txt = filing_lines(cik, pd.Timestamp(s))
        verdict = "no filing" if pos is None else ("MATCHES the filing: a real balance" if matches(b_ * 1e6, pos) else "does NOT match the filing: possible double count or missing line")
        print(f"   {s}: previous {a_:,.1f}m | spike {b_:,.1f}m | next {c_:,.1f}m | filing lines: {txt} | {verdict}")

# ---------------- PART C: the protocol items against the data ----------------
print("\nPART C: protocol v1.1 items checked against the data\n")
EV = pd.read_csv(HO / "failed_events_checked.csv"); CAND = pd.read_csv(HO / "failed_candidates.csv")
print("failed_events_checked.csv columns:", list(EV.columns))
def d10(x):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(x)); return pd.Timestamp(m.group(0)) if m else pd.NaT
CAND["pet"] = CAND["petition_date"].map(d10); CAND["cik_i"] = pd.to_numeric(CAND["cik"], errors="coerce")
ecol = next((c for c in EV.columns if "event_8k" in c), None)
if ecol is None: print("no event_8k column found: check the columns above"); EV["ev"] = pd.NaT
else: EV["ev"] = pd.to_datetime(EV[ecol], errors="coerce")
EV["cik_i"] = pd.to_numeric(EV["cik"], errors="coerce") if "cik" in EV else np.nan
M_ = CAND.merge(EV[["cik_i", "ev"]], on="cik_i", how="left")
M_["lag"] = (M_["ev"] - M_["pet"]).dt.days
DT = pd.read_csv(HO / "debt_quarterly_heldout.csv"); DC = pd.read_csv(CT / "debt_quarterly_controls_final.csv"); FR = pd.read_csv(CT / "controls_final.csv")
inc = M_[M_.ticker.isin(DT.ticker.unique())].copy()
print(f"C1 event rule: {len(inc)} included held-out companies; event 8-K found for {int(inc.ev.notna().sum())}; lag from petition (days) min/median/max = {inc.lag.min()}/{inc.lag.median()}/{inc.lag.max()}; outside -10..+30: {int(((inc.lag < -10) | (inc.lag > 30)).sum())}")
inc["cut"] = np.where(inc.ev < "2019-01-01", "pre-2019", np.where(inc.ev < "2020-01-01", "2019", np.where(inc.ev < "2021-02-01", "2020 to Jan 2021", "later")))
print("   events by cut (held-out included):", inc.cut.value_counts().to_dict())
for k, g in inc.groupby("cut"): print(f"   {k}: {', '.join(g.ticker)}")
print(f"C2 Container Store (CIK 1411688): in the held-out debt table: {'TCS' in set(DT.ticker)}; among final controls: {1411688 in set(FR.cik.astype(int))}")
ov = set(FR[FR.status == "CONTROL"].cik.astype(int)) & (set(EV.cik_i.dropna().astype(int)) | set(CAND.cik_i.dropna().astype(int)))
print(f"C3 control universe: {int((FR.status == 'CONTROL').sum())} controls, {int((FR.status == 'NEW FAILED').sum())} new failed; controls that are also in the failed candidate or event files: {sorted(ov) or 'none'}")
G = pd.read_csv(CT / "universe_size_gate.csv"); g = G[G.cik.isin(FR[FR.status == "CONTROL"].cik)]
print(f"   control revenue in the size gate: min {g.rev.min()/1e9:.2f}bn, median {g.rev.median()/1e9:.2f}bn, max {g.rev.max()/1e9:.2f}bn (gate 0.25-20bn)")

def ann_rev(path, asof):
    best = None
    for tag in REVT:
        for u in raw_facts(path).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", []):
            if "start" not in u: continue
            dur = (pd.Timestamp(u["end"]) - pd.Timestamp(u["start"])).days
            if not (340 <= dur <= 380) or pd.Timestamp(u["filed"]) > asof: continue
            key = (pd.Timestamp(u["end"]), -pd.Timestamp(u["filed"]).value)
            if best is None or key > best[0]: best = (key, u["val"])
    return None if best is None else best[1]
def raw_path(cik):
    p = CT / "raw" / f"{int(cik):010d}.json"
    if p.exists(): return p
    q = glob.glob(str(HO / "raw" / f"*{int(cik)}*.json")); return q[0] if q else None
ctl = FR[FR.status == "CONTROL"]
NEWF = {"QVCG": ("QVC Inc", pd.Timestamp("2026-04-16")), "CIK1575360": ("FTD", pd.Timestamp("2019-06-03")), "CIK1051251": ("J.Crew", pd.Timestamp("2020-05-04"))}
rows = [(r.ticker, r.ev if pd.notna(r.ev) else r.pet, r.cik_i) for r in inc.itertuples()] + [(tk, d, FR[FR.ticker == tk].cik.iloc[0]) for tk, (_, d) in NEWF.items() if (FR.ticker == tk).any()]
print("\nC4 size matching: annual revenue of each failed company, then controls within 3x and 10x of it (annual revenue known at 3 months before the event)")
print("   ticker   event       rev(bn)   controls within 3x | within 10x")
res4 = []
for tk, ev, cik in rows:
    p = raw_path(cik); asof = pd.Timestamp(ev) - timedelta(days=90); rv = ann_rev(p, asof) if p else None
    if rv is None: print(f"   {tk:8s} {str(pd.Timestamp(ev).date())}  revenue not found"); continue
    n3 = n10 = 0
    for c in ctl.itertuples():
        cv = ann_rev(CT / "raw" / f"{int(c.cik):010d}.json", asof)
        if cv and rv / 3 <= cv <= rv * 3: n3 += 1
        if cv and rv / 10 <= cv <= rv * 10: n10 += 1
    res4.append((tk, n3, n10)); print(f"   {tk:8s} {str(pd.Timestamp(ev).date())}  {rv/1e9:6.2f}   {n3:3d} | {n10:3d}")
if res4: print(f"   failed companies with at least 3 controls within 3x: {sum(n3 >= 3 for _, n3, _ in res4)} of {len(res4)}; within 10x: {sum(n10 >= 3 for _, _, n10 in res4)} of {len(res4)}")

print("\nC5 extraction-QA floor (debt part only): quarter ends before the event with a debt value; the protocol drops a company with fewer than 8")
ok = 0; tot = 0
for tk, ev, cik in rows:
    tab = DT if tk in set(DT.ticker) else DC; s = tab[(tab.ticker == tk) & tab.total_m.notna() & (pd.to_datetime(tab.end) < pd.Timestamp(ev))]
    tot += 1; ok += len(s) >= 8; print(f"   {tk:8s} {len(s):3d} quarter ends with debt {'ok' if len(s) >= 8 else 'BELOW 8: would be dropped'}")
print(f"   {ok} of {tot} pass the debt part. This is a ceiling for the 12-company floor: the three-input rule and the scored 3-12 month window can only lower it.")
print("\nStep 39 done. Paste everything above.")
