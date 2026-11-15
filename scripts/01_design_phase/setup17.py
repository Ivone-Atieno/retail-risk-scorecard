# ===== STEP 17 SETUP: run this cell first (it prints one check line); the next two cells use what it defines =====
from scipy.stats import wilcoxon
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
F["months_q"] = (F["distress_date"] - F["end"]).dt.days / 30.44
F["months_avail"] = (F["distress_date"] - F["as_of_date"]).dt.days / 30.44

# the score is the same fixed score as Step 16: equal-weight mean of within-quarter percentiles, reference = healthy + under-pressure (leave self out), window B blanked
DIR = {"gm_chg_yoy": -1, "inv_gap": +1, "lev2_chg_yoy": +1, "lev3_chg_yoy": +1}
LEVS = {"lev2": "lev2_chg_yoy", "lev3": "lev3_chg_yoy"}
CTRL = ["healthy", "under_pressure"]
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))

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

def prep(focal, ref, scol, ref_tickers):
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

def summarize(pr, n_ref, min_w=5):
    """company-mean AUC with a two-way bootstrap. Control companies are resampled only among those actually in the reference group."""
    cm, rows = comp_auc(pr, np.ones(n_ref), min_w)
    if not cm: return dict(obs=0, companies=0)
    allrows = np.concatenate([np.array(v) for v in rows.values()])
    comps = sorted(cm); m = len(comps); vals = np.array([cm[c] for c in comps])
    present = np.unique(np.concatenate([o["ri"] for o in pr]))
    boots = []
    for _ in range(NBOOT):
        W = np.bincount(rng.choice(present, len(present)), minlength=n_ref).astype(float)
        cmb, _ = comp_auc(pr, W, min_w)
        if not cmb: continue
        v = [cmb[c] for c in rng.choice(comps, m) if c in cmb]
        if v: boots.append(np.mean(v))
    return dict(obs=len(allrows), companies=m, pooled_auc=round(allrows.mean(), 3), company_mean_auc=round(vals.mean(), 3),
                ci95=f"{np.percentile(boots, 2.5):.2f} to {np.percentile(boots, 97.5):.2f}" if boots else "n/a",
                above_half=f"{int((vals > .5).sum())}/{m}", _cm=cm)

D = build(WIN_B)
D["size_risk"] = -np.log(D["ttm_rev"])
ctr_all = D[D.group.isin(CTRL)]; tick_all = sorted(ctr_all.ticker.unique()); n_all = len(tick_all)
H = D[D.group == "healthy"]; U = D[D.group == "under_pressure"]
fo_all = D[(D.group == "failed") & (D.months_q >= 3) & (D.months_q < 27.01)]
fo_s = D[(D.group == "failed") & (D.months_q >= 3) & (D.months_q < 18)]
qs = set(fo_s.cal_q)
print(f"setup done: {len(D)} rows, {D.ticker.nunique()} companies, {len(fo_all)} failed observations 3-27 months before distress (Step 16 had 64), {len(fo_s)} of them 3-18 months")
