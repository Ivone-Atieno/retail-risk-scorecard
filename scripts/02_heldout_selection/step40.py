# ===== STEP 40: apply the Step 39 evidence. (A) re-check Haverty's with the same filing test as Abercrombie, restore ANF/HVT only if EVERY flagged quarter matches the filing balance sheet, (B) read the one Duluth spike left unread. NO SCORES. =====
# Run in the SAME Colab session after Step 39 (about 3 minutes: roughly 10 filings are read). Backups of the three final files are saved first.
for nm in ["CT", "facts_from", "all_debt", "val_at_s", "read_items"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Steps 31-39 in this session first")
import re, shutil
D37 = pd.read_csv(CT / "debt_quarterly_controls37.csv"); R37 = pd.read_csv(CT / "controls_final37.csv")
FR = pd.read_csv(CT / "controls_final.csv"); DF = pd.read_csv(CT / "debt_quarterly_controls_final.csv"); EX = pd.read_csv(CT / "controls_exclusions_final.csv")
for f in ["controls_final.csv", "debt_quarterly_controls_final.csv", "controls_exclusions_final.csv"]:
    if not (CT / (f[:-4] + "_before40.csv")).exists(): shutil.copy(CT / f, CT / (f[:-4] + "_before40.csv"))
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

# ---------------- PART A: the screen compared the series with tags that can be face value or lease-inclusive; test it against the filing instead ----------------
print("PART A: re-check of the two companies the Step 38 'series below a reported debt tag' rule excluded. Restore rule (fixed now, before reading): every flagged quarter must be read and must match the filing balance sheet within 2%.\n")
for tk in ["ANF", "HVT"]:
    r = R37[R37.ticker == tk]
    if not len(r): print(tk, "not found in controls_final37.csv"); continue
    r = r.iloc[0]; cik = int(r["cik"]); ALLD = all_debt(facts_from(CT / "raw" / f"{cik:010d}.json")); bad = []
    for _, x in D37[(D37.ticker == tk) & D37.total_m.notna()].iterrows():
        e = pd.Timestamp(x["end"]); M = max([(val_at_s(ALLD[t], e) or 0, t) for t in ALLD] or [(0, "")])
        if M[0] >= 5e6 and x["total_m"] * 1e6 < 0.9 * M[0]: bad.append((e, x["total_m"], M))
    print(f"{tk} ({r['name'][:30]}): {len(bad)} flagged quarters")
    allok = len(bad) > 0
    for e, tot, M in bad[:6]:
        pos, txt = filing_lines(cik, e); ok = pos is not None and matches(tot * 1e6, pos); allok &= ok
        print(f"   {e.date()}: series {tot:,.1f}m | tag {M[1]} {M[0]/1e6:,.1f}m | filing lines: {txt} | {'MATCH' if ok else 'NO MATCH or not read'}")
    if allok and len(bad) <= 6:
        FR = FR[FR.cik.astype(int) != cik]; a = r.to_frame().T; a["action"] = f"KEPT (restored in Step 40: series matches the filing balance sheet in all {len(bad)} flagged quarters)"; FR = pd.concat([FR, a], ignore_index=True)
        DF = DF[DF.ticker != tk]; DF = pd.concat([DF, D37[D37.ticker == tk]], ignore_index=True); EX = EX[EX.cik.astype(int) != cik]
        print(f"   -> {tk} RESTORED to the control group")
    else: print(f"   -> {tk} stays excluded (rule not met)")

# ---------------- PART B: the Duluth spike Step 39 did not read ----------------
print("\nPART B: Duluth spike quarter not read in Step 39")
r = R37[R37.ticker == "DLTH"]
if len(r):
    cik = int(r.iloc[0]["cik"]); ds = D37[D37.ticker == "DLTH"].reset_index(drop=True); i = ds.index[ds.end == "2024-10-27"]
    if len(i) and 0 < int(i[0]) < len(ds) - 1:
        i = int(i[0]); pos, txt = filing_lines(cik, pd.Timestamp("2024-10-27"))
        print(f"   2024-10-27: previous {ds.total_m[i-1]:,.1f}m | spike {ds.total_m[i]:,.1f}m | next {ds.total_m[i+1]:,.1f}m | filing lines: {txt} | {'no filing' if pos is None else ('MATCHES the filing: a real balance' if matches(ds.total_m[i] * 1e6, pos) else 'does NOT match the filing')}")
    else: print("   quarter not found in the debt table")

FR.to_csv(CT / "controls_final.csv", index=False); DF.to_csv(CT / "debt_quarterly_controls_final.csv", index=False); EX.to_csv(CT / "controls_exclusions_final.csv", index=False)
print(f"\nFINAL after Step 40: {int((FR.status == 'CONTROL').sum())} controls and {int((FR.status == 'NEW FAILED').sum())} new failed companies. Files updated (originals kept as *_before40.csv).")
