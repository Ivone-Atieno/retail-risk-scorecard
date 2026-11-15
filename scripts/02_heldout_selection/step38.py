# ===== STEP 38: series-level consistency screen + FINAL control list and debt table. No filing reads, no scores, no outcomes. Run in the SAME Colab session after Step 37 (about 1 minute). =====
for nm in ["CT", "facts_from", "all_debt", "val_at_s", "quarter_ends", "nonconsumer", "START"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Steps 31-37 in this session first")
import re
R = pd.read_csv(CT / "controls_final37.csv"); D = pd.read_csv(CT / "debt_quarterly_controls37.csv"); Q = pd.read_csv(CT / "controls_summary.csv")
R["spikes"] = R["spikes"].fillna("") if "spikes" in R else ""
print(f"input: {int((R.status == 'CONTROL').sum())} controls and {int((R.status == 'NEW FAILED').sum())} new failed companies from Step 37\n")

# ---- rule 1: accepted tie-out deviations larger than 10% (and 5m) are not accepted. The offending lines were printed in Step 37; the five companies are named here with the evidence ----
DROP = {"DICKS SPORTING": "year-end quarters show exactly 2x the neighbouring quarters (2,984m vs 1,484m in Feb 2025; 3,845m vs 1,905m in Jan 2026): a double count in a multi-term formula",
        "BARNES & NOBLE EDUCATION": "formula 527.4m vs filing 277.7m in July 2023: LongTermLineOfCredit is added to LongTermDebt, which already contains it",
        "GAMESTOP": "formula 12.5m vs about 362m in the filing at Aug 2015: LongTermDebtNoncurrent (350m) is missing in quarters that use it",
        "SIGNET": "formula 0 vs 148m current portion in July 2023: no current-portion tag in the formula",
        "OFFICE DEPOT": "non-recourse debt (735m) is tagged inconsistently: formula 681m vs about 1,416m in Dec 2019"}
def dropped(name):
    for k, why in DROP.items():
        if k in str(name).upper(): return why
    return ""

# ---- rule 2: the series must not be below a debt tag the company reports (undercount, e.g. a note reclassified to current); 2+ quarters -> excluded, 1 quarter -> blanked ----
# ---- rule 3: a one-quarter spike of 1.8x-2.2x on both sides in a formula with several components is treated as a double count -> excluded ----
out, viol_rows = [], []
for _, r in R[R.status.isin(["CONTROL", "NEW FAILED"])].iterrows():
    tk = r["ticker"]; why = dropped(r["name"]); v_list = []; doubled = ""
    ds = D[D.ticker == tk].reset_index(drop=True)
    try:
        f = facts_from(CT / "raw" / f"{int(r['cik']):010d}.json"); ALLD = all_debt(f)
        for _, x in ds[ds.total_m.notna()].iterrows():
            e = pd.Timestamp(x["end"]); cand = [(val_at_s(ALLD[t], e) or 0, t) for t in ALLD]
            M, tg = max(cand) if cand else (0, "")
            if M >= 5e6 and x["total_m"] * 1e6 < 0.9 * M: v_list.append((x["end"], round(x["total_m"], 1), round(M / 1e6, 1), tg))
    except Exception as ex: v_list = []; print("could not check", tk, repr(ex)[:60])
    if "+" in str(r["formula"]) or "TOT[" in str(r["formula"]):
        for sd in [s for s in str(r["spikes"]).split(";") if s]:
            i = ds.index[ds.end == sd]
            if len(i) and 0 < int(i[0]) < len(ds) - 1:
                a, b, c = ds.total_m[int(i[0]) - 1], ds.total_m[int(i[0])], ds.total_m[int(i[0]) + 1]
                if min(a, c) > 0 and 1.8 <= b / a <= 2.2 and 1.8 <= b / c <= 2.2: doubled = f"double count at {sd} ({b:.0f}m vs {a:.0f}m and {c:.0f}m)"
    if r["status"] == "NEW FAILED": action = "NEW FAILED: kept" + (f" | WARNING {len(v_list)} undercount quarters" if v_list else "")
    elif why: action = "EXCLUDED: " + why
    elif doubled: action = "EXCLUDED: " + doubled
    elif len(v_list) >= 2: action = f"EXCLUDED: series below a reported debt tag in {len(v_list)} quarters (first {v_list[0][0]}: series {v_list[0][1]}m vs tag {v_list[0][3]} {v_list[0][2]}m)"
    elif len(v_list) == 1: action = f"KEPT, quarter {v_list[0][0]} blanked (series {v_list[0][1]}m vs tag {v_list[0][3]} {v_list[0][2]}m)"
    else: action = "KEPT"
    out.append(dict(cik=int(r["cik"]), ticker=tk, name=r["name"], status_in=r["status"], formula=r["formula"], action=action, violations=len(v_list)))
    viol_rows += [(tk, v[0]) for v in v_list]
A = pd.DataFrame(out)
print("ticker | action | violations  (only companies with something to report)\n")
for _, a in A[A.action != "KEPT"].iterrows(): print(f"{str(a['ticker'])[:10]:10s}| {a['name'][:26]:26s}| {a['action'][:170]}")

# ---- apply ----
final_ids = A[A.action.str.startswith(("KEPT", "NEW FAILED"))]["cik"].tolist()
DF = D[D.ticker.isin(A[A.cik.isin(final_ids)]["ticker"])].copy()
for tk, e in viol_rows:
    m = (DF.ticker == tk) & (DF.end == e) & (DF.ticker.isin(A[A.action.str.startswith("KEPT, quarter")]["ticker"]))
    DF.loc[m, ["total_m", "gross_m"]] = np.nan; DF.loc[m, "flag"] = "BLANKED-undercount"
FR = R[R.cik.isin(final_ids)].copy().merge(A[["cik", "action"]], on="cik")
FR.to_csv(CT / "controls_final.csv", index=False); DF.to_csv(CT / "debt_quarterly_controls_final.csv", index=False)
EX = []
for _, q in Q.iterrows():
    if int(q["cik"]) in final_ids: continue
    a = A[A.cik == int(q["cik"])]; rr = R[R.cik == int(q["cik"])]
    reason = a["action"].iloc[0] if len(a) else (("business-model exclusion: " + nonconsumer(q["name"])) if nonconsumer(q["name"]) else (rr["reason"].iloc[0] if len(rr) and isinstance(rr["reason"].iloc[0], str) and rr["reason"].iloc[0] else str(q["reason"])))
    EX.append(dict(cik=int(q["cik"]), name=q["name"], sic=q["sic"], reason=reason))
pd.DataFrame(EX).to_csv(CT / "controls_exclusions_final.csv", index=False)

n_c = int((FR.status == "CONTROL").sum()); n_f = int((FR.status == "NEW FAILED").sum())
print(f"\nFINAL: {n_c} controls and {n_f} new failed companies; {len(EX)} companies in the universe are out (reasons in controls_exclusions_final.csv)")
ex = pd.DataFrame(EX); ex["why"] = ex["reason"].str.replace(r"\d.*$", "", regex=True).str[:45]
print("\nexclusion reasons (grouped):"); print(ex["why"].value_counts().to_string())
M = []
for tk, g_ in DF[DF.ticker.isin(FR[FR.status == "CONTROL"]["ticker"])].groupby("ticker"):
    v_ = g_["total_m"].dropna(); M.append(float((v_ > 0).mean()) if len(v_) else np.nan)
M = pd.Series(M); print(f"\nleverage mix of the {n_c} final controls: levered (>=0.8 of quarters with debt) {int((M >= 0.8).sum())} | mixed {int(((M < 0.8) & (M > 0.2)).sum())} | mostly debt-free (<=0.2) {int((M <= 0.2).sum())}")
print("\nStep 38 done. Files: controls_final.csv, debt_quarterly_controls_final.csv, controls_exclusions_final.csv")
