# ===== STEP 14: H3, does an equal-weight risk score rank failed companies as riskier than the others in the same calendar quarter? =====
from scipy.stats import binomtest
F = pd.read_csv(BASE / "features_final2.csv", parse_dates=["end", "distress_date"]).reset_index(drop=True)
CORE = {"gm_chg_yoy": -1, "lev2_chg_yoy": +1, "inv_gap": +1}          # +1: a higher value means more risk, -1: a lower value means more risk
FULL = dict(CORE, delay_chg_clean=+1)
ALL = list(FULL)
CTRL = ["healthy", "under_pressure"]
WIN_A = set(F.loc[F["covid_window"], "cal_q"])
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
VARIANTS = {"A data-flagged": WIN_A, "B contiguous 2020Q2-2021Q4": WIN_B, "C no blanking": set()}
rng = np.random.default_rng(0)

def build(win):
    D = F.copy()
    for c in ALL: D.loc[D["cal_q"].isin(win), c] = np.nan
    for c in ALL:
        pr = np.full(len(D), np.nan)
        for cq, g in D.groupby("cal_q"):
            ref = g[g.group.isin(CTRL)]
            for i, r in g[g[c].notna()].iterrows():
                v = ref[ref.ticker != r.ticker][c].dropna()
                if len(v) >= 5: pr[i] = ((v < r[c]).sum() + 0.5 * (v == r[c]).sum()) / len(v)
        D["p_" + c] = pr if FULL[c] > 0 else 1 - pr
    D["score_core"] = np.where(D[["p_" + c for c in CORE]].notna().all(axis=1), D[["p_" + c for c in CORE]].mean(axis=1), np.nan)
    D["score_full"] = np.where(D[["p_" + c for c in ALL]].notna().sum(axis=1) >= 3, D[["p_" + c for c in ALL]].mean(axis=1), np.nan)
    return D

def auc_rows(D, rows, col, ref_groups):
    out = []
    for i, r in rows.iterrows():
        v = D[(D.cal_q == r.cal_q) & D.group.isin(ref_groups) & (D.ticker != r.ticker)][col].dropna()
        out.append(((v < r[col]).sum() + 0.5 * (v == r[col]).sum()) / len(v) if len(v) >= 5 else np.nan)
    return pd.Series(out, index=rows.index)

def company_auc(D, col, lo, hi):
    R = D[(D.group == "failed") & D.qtd.between(lo, hi) & D[col].notna()]
    R = R.assign(auc=auc_rows(D, R, col, CTRL)).dropna(subset=["auc"])
    return R.groupby("ticker")["auc"].agg(["mean", "count"])

res, keep = [], {}
for vn, win in VARIANTS.items():
    D = build(win)
    for sc in ["score_core", "score_full"]:
        for lab, (lo, hi) in {"last 4 quarters": (1, 4), "quarters 5-8": (5, 8)}.items():
            T = company_auc(D, sc, lo, hi); T = T[T["count"] >= 2]; keep[(vn, sc, lab)] = T
            m = len(T)
            if m == 0: continue
            boots = [rng.choice(T["mean"].values, m).mean() for _ in range(3000)]
            k = int((T["mean"] > 0.5).sum())
            res.append(dict(variant=vn, score=sc, window=lab, companies=m, mean_auc=round(T["mean"].mean(), 3),
                            ci95=f"{np.percentile(boots, 2.5):.2f} to {np.percentile(boots, 97.5):.2f}", above_half=f"{k}/{m}", p=round(binomtest(k, m, 0.5).pvalue, 3)))
    keep[(vn, "D")] = D
print("PART 1: mean 'AUC' = chance that a failed company's score is higher (riskier) than a control company's in the same calendar quarter. 0.5 = no information, 1.0 = perfect.")
print("companies = failed companies with at least 2 scored quarters in that window; ci95 = bootstrap over companies\n")
print(pd.DataFrame(res).to_string(index=False), "\n")

D = keep[("B contiguous 2020Q2-2021Q4", "D")]
print("PART 2: per company, variant B, core score (mean AUC, scored quarters)")
a = keep[("B contiguous 2020Q2-2021Q4", "score_core", "last 4 quarters")].rename(columns={"mean": "auc_last4", "count": "n_last4"})
b = keep[("B contiguous 2020Q2-2021Q4", "score_core", "quarters 5-8")].rename(columns={"mean": "auc_5to8", "count": "n_5to8"})
print(a.join(b, how="outer").round(2).to_string(), "\n")

print("PART 3: one signal at a time, variant B, failed companies' last 4 quarters (mean risk percentile of company means; 0.5 = no information)")
rows = []
for c in ALL:
    R = D[(D.group == "failed") & D.qtd.between(1, 4)].dropna(subset=["p_" + c]).groupby("ticker")["p_" + c].mean()
    rows.append(dict(signal=c, companies=len(R), mean_percentile=round(R.mean(), 3), above_half=f"{int((R > .5).sum())}/{len(R)}"))
print(pd.DataFrame(rows).to_string(index=False), "\n")

print("PART 4: sanity check, do under-pressure companies score riskier than healthy ones in the same quarters? (variant B, core score)")
U = D[(D.group == "under_pressure") & D.score_core.notna()]
U = U.assign(auc=auc_rows(D, U, "score_core", ["healthy"])).dropna(subset=["auc"])
print(U.groupby("ticker")["auc"].agg(["mean", "count"]).round(2).to_string())
print("all under-pressure rows: mean AUC vs healthy =", round(U["auc"].mean(), 3))
