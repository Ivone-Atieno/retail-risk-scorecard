# ===== STEP 16 (validation): fixed score, horizon bins, company-level results, consistent control comparisons, leakage and selection checks =====
from scipy.stats import wilcoxon, binomtest
NBOOT = 2000
rng = np.random.default_rng(42)
F = pd.read_csv(BASE / "features_final2.csv", parse_dates=["end", "distress_date", "as_of_date"]).reset_index(drop=True)
Qc = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end"]).sort_values(["ticker", "end"]).reset_index(drop=True)
g_ = Qc.groupby("ticker")
Qc["ttm_rev"] = g_["Revenue"].transform(lambda s: s.rolling(4, min_periods=4).sum())
Qc.loc[~(Qc["end"] - g_["end"].shift(3)).dt.days.between(240, 300), "ttm_rev"] = np.nan
Qc["end_prev"] = Qc["end"] - pd.Timedelta(days=364)
P = Qc[["ticker", "end", "Debt"]].rename(columns={"end": "end_py", "Debt": "Debt_py"}).sort_values("end_py")
Qc = pd.merge_asof(Qc.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker", tolerance=pd.Timedelta(days=15), direction="nearest")
Qc["lev3_chg_yoy"] = np.where(Qc["Debt_py"] > 0, (Qc["Debt"] / Qc["Debt_py"] - 1) * 100, np.nan)
F = F.merge(Qc[["ticker", "end", "lev3_chg_yoy", "ttm_rev"]], on=["ticker", "end"], how="left")
F["months_q"] = (F["distress_date"] - F["end"]).dt.days / 30.44            # horizon measured from quarter end
F["months_avail"] = (F["distress_date"] - F["as_of_date"]).dt.days / 30.44   # horizon measured from the date the inputs were public

# ---- the score is FIXED: equal-weight average of within-quarter percentiles of three signals, reference = healthy + under-pressure (leave self out) ----
DIR = {"gm_chg_yoy": -1, "inv_gap": +1, "lev2_chg_yoy": +1, "lev3_chg_yoy": +1}
LEVS = {"lev2": "lev2_chg_yoy", "lev3": "lev3_chg_yoy"}
CTRL = ["healthy", "under_pressure"]
WINS = {"B (2020Q2-2021Q4 blanked)": set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str)), "C (nothing blanked)": set()}
BINS = [("3-6", 3, 6), ("6-12", 6, 12), ("12-18", 12, 18), ("18-27", 18, 27.01)]

def pct(v, x):
    return ((v < x).sum() + 0.5 * (v == x).sum()) / len(v)

def build(win):
    D = F.copy()
    for c in DIR: D.loc[D["cal_q"].isin(win), c] = np.nan
    for c in DIR:
        pr = np.full(len(D), np.nan)
        for cq, g in D.groupby("cal_q"):
            ref = g[g.group.isin(CTRL)]
            for i, r in g[g[c].notna()].iterrows():
                v = ref[ref.ticker != r.ticker][c].dropna()
                if len(v) >= 5: pr[i] = pct(v.values, r[c])
        D["p_" + c] = pr if DIR[c] > 0 else 1 - pr
    for lv, lc in LEVS.items():
        cols = ["p_gm_chg_yoy", "p_inv_gap", "p_" + lc]
        D["s_" + lv] = np.where(D[cols].notna().all(axis=1), D[cols].mean(axis=1), np.nan)
    return D

# ---- AUC machinery: every observation is compared with the control observations of the SAME calendar quarter ----
def prep(focal, ref, scol, ref_tickers, min_ref=5):
    """one entry per focal observation: its score, the reference scores for that quarter, and which reference company each belongs to"""
    idx = {t: k for k, t in enumerate(ref_tickers)}
    byq = {cq: (g[scol].values, np.array([idx[t] for t in g.ticker])) for cq, g in ref.dropna(subset=[scol]).groupby("cal_q")}
    out = []
    for i, r in focal.dropna(subset=[scol]).iterrows():
        if r.cal_q in byq:
            out.append(dict(comp=r.ticker, s=r[scol], rs=byq[r.cal_q][0], ri=byq[r.cal_q][1], key=i))
    return out

def comp_auc(pr, W, min_w=5):
    rows = {}
    for o in pr:
        w = W[o["ri"]]
        if w.sum() >= min_w:
            a = (w * ((o["rs"] < o["s"]) + 0.5 * (o["rs"] == o["s"]))).sum() / w.sum()
            rows.setdefault(o["comp"], []).append(a)
    return {c: np.mean(v) for c, v in rows.items()}, rows

def summarize(pr, n_ref, label=""):
    W1 = np.ones(n_ref)
    cm, rows = comp_auc(pr, W1)
    if not cm: return dict(obs=0, companies=0)
    allrows = np.concatenate([np.array(v) for v in rows.values()])
    comps = sorted(cm); m = len(comps); vals = np.array([cm[c] for c in comps])
    boots = []
    for _ in range(NBOOT):
        W = np.bincount(rng.integers(0, n_ref, n_ref), minlength=n_ref).astype(float)
        cmb, _ = comp_auc(pr, W)
        if not cmb: continue
        pick = rng.choice(comps, m)
        v = [cmb[c] for c in pick if c in cmb]
        if v: boots.append(np.mean(v))
    k = int((vals > .5).sum())
    try: pw = wilcoxon(vals - 0.5).pvalue if m >= 4 else np.nan
    except Exception: pw = np.nan
    return dict(obs=len(allrows), companies=m, pooled_auc=round(allrows.mean(), 3), company_mean_auc=round(vals.mean(), 3),
                ci95=f"{np.percentile(boots, 2.5):.2f} to {np.percentile(boots, 97.5):.2f}" if boots else "n/a",
                above_half=f"{k}/{m}", wilcoxon_p=round(pw, 3) if pw == pw else np.nan, _cm=cm)

for vn, win in WINS.items():
    D = build(win)
    if vn.startswith("B"): DB = D
    ctr_all = D[D.group.isin(CTRL)]; tick_all = sorted(ctr_all.ticker.unique())
    print(f"\nPART 1 [{vn}]: AUC by distance to distress. pooled_auc = average over all failed observations; company_mean_auc = average of company averages (what Steps 14-15 reported).")
    print("ci95 = two-way bootstrap (resamples failed companies AND control companies, repeated quarters stay with their company); wilcoxon_p = signed-rank test of the company AUCs against 0.5\n")
    rows = []
    for lv in LEVS:
        for bn, lo, hi in BINS:
            fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
            s = summarize(prep(fo, ctr_all, "s_" + lv, tick_all), len(tick_all))
            s.pop("_cm", None); rows.append(dict(leverage=lv, months=bn, **s))
    print(pd.DataFrame(rows).to_string(index=False))

D = DB.copy(); D["size_risk"] = -np.log(D["ttm_rev"])        # used only in check 4d
ctr_all = D[D.group.isin(CTRL)]; tick_all = sorted(ctr_all.ticker.unique()); n_all = len(tick_all)
H = D[D.group == "healthy"]; U = D[D.group == "under_pressure"]

print("\nPART 2: each failed company on its own (variant B). AUC by distance to distress; n = number of scored quarters in that bin")
for lv in LEVS:
    tab = {}
    for bn, lo, hi in BINS:
        fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
        cm, rows = comp_auc(prep(fo, ctr_all, "s_" + lv, tick_all), np.ones(n_all))
        for c in cm: tab.setdefault(c, {})[bn] = f"{cm[c]:.2f} (n={len(rows[c])})"
    print(f"\n{lv}"); print(pd.DataFrame(tab).T.reindex(columns=[b[0] for b in BINS]).fillna("-").to_string())
print("\nper-company uncertainty, all scored quarters from 3 to 27 months, resampling the CONTROL companies only (the failed company's own quarters are fixed). min / max = range of its single-quarter AUCs")
rows = []
for lv in LEVS:
    fo = D[(D.group == "failed") & (D.months_q >= 3) & (D.months_q < 27.01)]
    pr = prep(fo, ctr_all, "s_" + lv, tick_all); cm, rr = comp_auc(pr, np.ones(n_all))
    bs = {c: [] for c in cm}
    for _ in range(NBOOT):
        W = np.bincount(rng.integers(0, n_all, n_all), minlength=n_all).astype(float)
        cb, _ = comp_auc(pr, W)
        for c, v in cb.items(): bs[c].append(v)
    for c in sorted(cm):
        rows.append(dict(leverage=lv, company=c, quarters=len(rr[c]), auc=round(cm[c], 2), ci95_controls=f"{np.percentile(bs[c], 2.5):.2f} to {np.percentile(bs[c], 97.5):.2f}",
                         min=round(min(rr[c]), 2), max=round(max(rr[c]), 2)))
print(pd.DataFrame(rows).to_string(index=False))

print("\nPART 3: SAME fixed score, SAME quarters, different comparison groups (variant B). healthy_gap = AUC vs healthy only minus AUC vs under-pressure only, per failed company")
rows = []
for lv in LEVS:
    for bn, lo, hi in BINS:
        fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
        qs = set(fo.cal_q)
        ph, pu = prep(fo, H, "s_" + lv, tick_all), prep(fo, U, "s_" + lv, tick_all)
        sh, su = summarize(ph, n_all), summarize(pu, n_all)
        # UP against healthy in the same calendar quarters
        up_rows = U[U.cal_q.isin(qs)]
        s_uh = summarize(prep(up_rows, H, "s_" + lv, tick_all), n_all)
        # paired difference by failed company
        cmh, cmu = sh.get("_cm", {}), su.get("_cm", {}); common = sorted(set(cmh) & set(cmu))
        d = np.array([cmh[c] - cmu[c] for c in common]) if common else np.array([])
        bd = []
        if len(d):
            for _ in range(NBOOT):
                W = np.bincount(rng.integers(0, n_all, n_all), minlength=n_all).astype(float)
                a, _ = comp_auc(ph, W); b, _ = comp_auc(pu, W)
                cc = [c for c in rng.choice(common, len(common)) if c in a and c in b]
                if cc: bd.append(np.mean([a[c] - b[c] for c in cc]))
        rows.append(dict(leverage=lv, months=bn, failed_vs_healthy=sh.get("company_mean_auc"), ci_h=sh.get("ci95"), failed_vs_UP=su.get("company_mean_auc"), ci_u=su.get("ci95"),
                         UP_vs_healthy=s_uh.get("company_mean_auc"), ci_uh=s_uh.get("ci95"),
                         healthy_gap=round(d.mean(), 3) if len(d) else np.nan, gap_ci=f"{np.percentile(bd, 2.5):.2f} to {np.percentile(bd, 97.5):.2f}" if bd else "n/a",
                         gap_positive=f"{int((d > 0).sum())}/{len(d)}"))
print(pd.DataFrame(rows).to_string(index=False))
print("ordering failed > under-pressure > healthy needs: failed_vs_healthy > failed_vs_UP > 0.5 and UP_vs_healthy > 0.5, with healthy_gap clearly above 0")

print("\nPART 4: leakage and selection checks (variant B)")
fo_all = D[(D.group == "failed") & (D.months_q >= 3) & (D.months_q < 27.01)]
print("4a. failed observations whose inputs were first public AFTER the distress date:", int((fo_all.as_of_date > fo_all.distress_date).sum()), "of", len(fo_all), "(must be 0)")
gap = (D.as_of_date - D.end).dt.days
print("4b. days from quarter end until all inputs were public, median by group:", gap.groupby(D.group).median().round(0).to_dict())
print("    so a score cannot be computed until about", int(gap[D.group == "failed"].median()), "days after quarter end; the real-time lead is shorter than the 'months from quarter end' bins")
print("    median months from the date inputs were public to distress, by bin:", {bn: round(fo_all[(fo_all.months_q >= lo) & (fo_all.months_q < hi)].months_avail.median(), 1) for bn, lo, hi in BINS})

# 4c: strict real-time version: for each failed observation use only controls whose inputs were public on or before that observation's own availability date
def realtime(lv, lo, hi):
    lc = LEVS[lv]; out = {}; excl = []
    fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
    for i, r in fo.iterrows():
        pool = D[(D.cal_q == r.cal_q) & D.group.isin(CTRL)]
        A = pool[pool.as_of_date <= r.as_of_date]
        excl.append(1 - len(A) / max(len(pool), 1))
        if len(A) < 6: continue
        sc_f, sc_c = [], np.zeros(len(A)); ok = True; cnt = np.zeros(len(A))
        sig = {"gm_chg_yoy": -1, "inv_gap": +1, lc: +1}
        pf, pcs = [], []
        for c, sg in sig.items():
            if pd.isna(r[c]): ok = False; break
            vals = A[c].values; valid = ~np.isnan(vals)
            if valid.sum() < 6: ok = False; break
            pfc = pct(vals[valid], r[c]); pfc = pfc if sg > 0 else 1 - pfc
            pc = np.full(len(A), np.nan)
            for j in np.where(valid)[0]:
                others = vals[valid & (np.arange(len(A)) != j)]
                if len(others) >= 5:
                    x = pct(others, vals[j]); pc[j] = x if sg > 0 else 1 - x
            pf.append(pfc); pcs.append(pc)
        if not ok: continue
        cs = np.nanmean(np.vstack(pcs), axis=0); cs[np.isnan(np.vstack(pcs)).any(axis=0)] = np.nan
        cs = cs[~np.isnan(cs)]
        if len(cs) < 5: continue
        s0 = np.mean(pf); out.setdefault(r.ticker, []).append(((cs < s0).sum() + 0.5 * (cs == s0).sum()) / len(cs))
    return out, float(np.mean(excl)) if excl else np.nan
print("4c. strict real-time comparison: controls restricted to those already public. company_mean_auc, restricted vs the fixed-score figure in Part 1 (leverage lev2)")
rows = []
for bn, lo, hi in BINS:
    o, ex = realtime("lev2", lo, hi)
    fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
    base, _ = comp_auc(prep(fo, ctr_all, "s_lev2", tick_all), np.ones(n_all))
    rows.append(dict(months=bn, controls_not_yet_public=f"{ex:.0%}", companies=len(o), realtime_auc=round(np.mean([np.mean(v) for v in o.values()]), 3) if o else np.nan,
                     fixed_score_auc=round(np.mean(list(base.values())), 3) if base else np.nan))
print(pd.DataFrame(rows).to_string(index=False))

print("4d. selection by size: median four-quarter sales (millions) in the same quarters, and a score that is only company size (smaller = riskier)")
fo_s = D[(D.group == "failed") & (D.months_q >= 3) & (D.months_q < 18)].copy()
qs = set(fo_s.cal_q)
print({g: round(D[(D.group == g) & D.cal_q.isin(qs)].ttm_rev.median() / 1e6) for g in ["failed", "under_pressure", "healthy"]})
for lab, ref in [("vs healthy only", H), ("vs under-pressure only", U), ("vs both", ctr_all)]:
    s = summarize(prep(fo_s, ref, "size_risk", tick_all), n_all)
    print(f"    size alone, {lab}: company_mean_auc = {s.get('company_mean_auc')}  ci95 {s.get('ci95')}")
print("4e. against each control company separately (failed observations from 3 to 18 months, same quarters)")
rows = []
for t in tick_all:
    ref = D[D.ticker == t]; pr = prep(fo_s, ref, "s_lev2", tick_all, min_ref=1)
    cm, rr = comp_auc(pr, np.ones(n_all), min_w=1)
    allv = np.concatenate([np.array(v) for v in rr.values()]) if rr else np.array([])
    rows.append(dict(control=t, group=ref.group.iloc[0], comparisons=len(allv), auc=round(allv.mean(), 2) if len(allv) else np.nan))
print(pd.DataFrame(rows).sort_values("auc", ascending=False).to_string(index=False))
