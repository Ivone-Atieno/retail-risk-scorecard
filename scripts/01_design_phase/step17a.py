# ===== STEP 17A: size-matched controls, and a closer look at the under-pressure companies (same fixed score as Step 16) =====
from collections import Counter
foc = D[((D.group == "failed") & (D.months_q >= 3) & (D.months_q < 18)) | ((D.group != "failed") & D.cal_q.isin(qs))]

print("PART 1: how different in size are the groups? Four-quarter sales in millions, in the same calendar quarters as the failed observations (3-18 months before distress)")
t = foc.groupby(["group", "ticker"]).ttm_rev.agg(["count", "min", "median", "max"])
t[["min", "median", "max"]] = (t[["min", "median", "max"]] / 1e6).round(0)
print(t.sort_values(["group", "median"]).to_string())

print("\nPART 2: size overlap. For each failed observation, how many controls in the same calendar quarter have four-quarter sales within a factor of 3 (or 10) of its own?")
rows = []
for K in (3, 10):
    for g in ["healthy", "under_pressure"]:
        cnt = []
        for i, r in fo_s.dropna(subset=["ttm_rev"]).iterrows():
            pool = D[(D.cal_q == r.cal_q) & (D.group == g) & D.ttm_rev.notna()]
            ratio = pool.ttm_rev / r.ttm_rev
            cnt.append(int(((ratio <= K) & (ratio >= 1 / K)).sum()))
        cnt = np.array(cnt)
        rows.append(dict(within=f"{K}x", control_group=g, failed_obs=len(cnt), with_at_least_1=int((cnt >= 1).sum()), with_at_least_3=int((cnt >= 3).sum()), median_matches=float(np.median(cnt))))
print(pd.DataFrame(rows).to_string(index=False))

def matched(fo, scol, K, min_m=3):
    """compare each failed observation only with controls of the same calendar quarter whose size is within a factor K of its own"""
    out = []
    for i, r in fo.dropna(subset=[scol, "ttm_rev"]).iterrows():
        pool = ctr_all[(ctr_all.cal_q == r.cal_q) & ctr_all[scol].notna() & ctr_all.ttm_rev.notna()]
        ratio = pool.ttm_rev / r.ttm_rev
        m = pool[(ratio <= K) & (ratio >= 1 / K)]
        if len(m) >= min_m:
            a = ((m[scol] < r[scol]).sum() + 0.5 * (m[scol] == r[scol]).sum()) / len(m)
            sz = ((m["size_risk"] < r["size_risk"]).sum() + 0.5 * (m["size_risk"] == r["size_risk"]).sum()) / len(m)
            out.append(dict(comp=r.ticker, auc=a, size_auc=sz, n=len(m), nh=int((m.group == "healthy").sum()), who=list(m.ticker)))
    return out

def failed_only_ci(vals):
    b = [rng.choice(vals, len(vals)).mean() for _ in range(NBOOT)]
    return f"{np.percentile(b, 2.5):.2f} to {np.percentile(b, 97.5):.2f}"

print("\nPART 3: the SAME fixed score, but each failed observation is compared only with size-matched controls (at least 3 matches, healthy and under-pressure together)")
print("size_only_auc = how well company size alone separates failed from the matched controls. If matching worked it should be near 0.5. ci95 resamples the failed companies only, so it is too narrow.\n")
rows = []; who = {}
for lv in LEVS:
    for K in (3, 10):
        for bn, lo, hi in [("3-12", 3, 12), ("12-18", 12, 18)]:
            fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
            res = matched(fo, "s_" + lv, K)
            tot = len(fo.dropna(subset=["s_" + lv, "ttm_rev"]))
            if not res:
                rows.append(dict(leverage=lv, size_within=f"{K}x", months=bn, obs_used=f"0/{tot}")); continue
            df = pd.DataFrame(res); cm = df.groupby("comp").auc.mean(); sm = df.groupby("comp").size_auc.mean()
            who[(lv, K, bn)] = Counter(t for w in df.who for t in w)
            rows.append(dict(leverage=lv, size_within=f"{K}x", months=bn, obs_used=f"{len(df)}/{tot}", companies=len(cm), avg_matches=round(df.n.mean(), 1),
                             healthy_share=f"{df.nh.sum() / df.n.sum():.0%}", auc=round(cm.mean(), 3), ci95=failed_only_ci(cm.values) if len(cm) > 1 else "n/a",
                             above_half=f"{int((cm > .5).sum())}/{len(cm)}", size_only_auc=round(sm.mean(), 3)))
print(pd.DataFrame(rows).to_string(index=False))
print("\nwhich controls supplied the matches (lev2, 3-12 months):", {K: dict(who.get(("lev2", K, "3-12"), {})) for K in (3, 10)})

print("\nPART 4: where does each company sit? Median across its quarters in the comparison window (failed: 3-18 months before distress; controls: the same calendar quarters).")
print("Percentiles are direction-adjusted: higher = riskier. s_lev2 / s_lev3 are the fixed core scores. n = quarters with a score.\n")
pc = {"gm": "p_gm_chg_yoy", "inv": "p_inv_gap", "lev2": "p_lev2_chg_yoy", "lev3": "p_lev3_chg_yoy", "s_lev2": "s_lev2", "s_lev3": "s_lev3"}
rawc = {"raw_gm": "gm_chg_yoy", "raw_inv": "inv_gap", "raw_lev2": "lev2_chg_yoy", "raw_lev3": "lev3_chg_yoy"}
agg = {**{k: (v, "median") for k, v in pc.items()}, **{k: (v, "median") for k, v in rawc.items()}, "n_lev2": ("s_lev2", "count"), "n_lev3": ("s_lev3", "count")}
tab = foc.groupby(["group", "ticker"]).agg(**agg).round(2)
print(tab.sort_values(["group", "s_lev2"], ascending=[True, False]).to_string())

print("\nBGFV and PLCE, quarter by quarter (raw signals, percentiles, core scores). blank = signal missing or blanked (COVID window, or last year's debt was zero for lev3)")
for tk in ["BGFV", "PLCE"]:
    x = D[(D.ticker == tk) & D.cal_q.isin(qs)][["cal_q", "gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy", "p_gm_chg_yoy", "p_inv_gap", "p_lev2_chg_yoy", "p_lev3_chg_yoy", "s_lev2", "s_lev3"]]
    x.columns = ["cal_q", "raw_gm", "raw_inv", "raw_lev2", "raw_lev3", "p_gm", "p_inv", "p_lev2", "p_lev3", "s_lev2", "s_lev3"]
    print(tk); print(x.round(2).to_string(index=False))

print("\nPART 5: failed vs under-pressure, signal by signal (failed observations 3-18 months before distress, same calendar quarters)")
print("company_mean_auc, 95% interval from the two-way bootstrap; 0.5 = no separation; below 0.5 = the under-pressure companies look riskier than the failed ones")
print("without BGFV and PLCE only 4 companies remain (KSS, M, WOOF, DBI), so that column needs at least 3 comparison companies per quarter and each observation's AUC moves in coarse steps\n")
scores = {"gm percentile": "p_gm_chg_yoy", "inventory percentile": "p_inv_gap", "lev2 percentile": "p_lev2_chg_yoy", "lev3 percentile": "p_lev3_chg_yoy", "core score lev2": "s_lev2", "core score lev3": "s_lev3"}
Ux = U[~U.ticker.isin(["BGFV", "PLCE"])]
rows = []
for nm, col in scores.items():
    a = summarize(prep(fo_s, U, col, tick_all), n_all); b = summarize(prep(fo_s, Ux, col, tick_all), n_all, min_w=3)
    rows.append(dict(score=nm, vs_all_UP=a.get("company_mean_auc"), ci_all=a.get("ci95"), vs_UP_without_BGFV_PLCE=b.get("company_mean_auc"), ci_without=b.get("ci95")))
print(pd.DataFrame(rows).to_string(index=False))
print("\nthe same, against each under-pressure company on its own (pooled over comparisons; n = number of comparisons)")
rows = []
for nm, col in scores.items():
    r_ = {"score": nm}
    for tk in sorted(U.ticker.unique()):
        cm, rr = comp_auc(prep(fo_s, D[D.ticker == tk], col, tick_all), np.ones(n_all), min_w=1)
        allv = np.concatenate([np.array(v) for v in rr.values()]) if rr else np.array([])
        r_[tk] = f"{allv.mean():.2f} (n={len(allv)})" if len(allv) else "-"
    rows.append(r_)
print(pd.DataFrame(rows).to_string(index=False))
