# ===== STEP 14 (revised): H3, equal-weight risk score, with the leverage signal measured two ways =====
from scipy.stats import binomtest
F = pd.read_csv(BASE / "features_final2.csv", parse_dates=["end", "distress_date"]).reset_index(drop=True)
Qc = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end"]).sort_values(["ticker", "end"]).reset_index(drop=True)

# second leverage signal with NO sales or asset denominator: growth in debt over the same quarter last year
Qc["end_prev"] = Qc["end"] - pd.Timedelta(days=364)
P = Qc[["ticker", "end", "Debt"]].rename(columns={"end": "end_py", "Debt": "Debt_py"}).sort_values("end_py")
Qc = pd.merge_asof(Qc.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker", tolerance=pd.Timedelta(days=15), direction="nearest")
Qc["lev3_chg_yoy"] = np.where(Qc["Debt_py"] > 0, (Qc["Debt"] / Qc["Debt_py"] - 1) * 100, np.nan)    # percent; blank when last year's debt was zero
F = F.merge(Qc[["ticker", "end", "lev3_chg_yoy"]], on=["ticker", "end"], how="left")

BASE_SIG = {"gm_chg_yoy": -1, "inv_gap": +1}                      # +1: higher value = more risk, -1: lower value = more risk
LEVS = {"lev2 (debt / 4-qtr sales)": "lev2_chg_yoy", "lev3 (debt growth %)": "lev3_chg_yoy"}
ALL = ["gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy", "delay_chg_clean"]
DIR = dict(BASE_SIG, lev2_chg_yoy=+1, lev3_chg_yoy=+1, delay_chg_clean=+1)
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
        D["p_" + c] = pr if DIR[c] > 0 else 1 - pr
    for ln, lc in LEVS.items():
        core = ["p_gm_chg_yoy", "p_inv_gap", "p_" + lc]
        D["core|" + ln] = np.where(D[core].notna().all(axis=1), D[core].mean(axis=1), np.nan)
        full = core + ["p_delay_chg_clean"]
        D["full|" + ln] = np.where(D[full].notna().sum(axis=1) >= 3, D[full].mean(axis=1), np.nan)
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
    D = build(win); keep[(vn, "D")] = D
    for ln in LEVS:
        for kind in ["core", "full"]:
            col = f"{kind}|{ln}"
            for lab, (lo, hi) in {"last 4 quarters": (1, 4), "quarters 5-8": (5, 8)}.items():
                T = company_auc(D, col, lo, hi); T = T[T["count"] >= 2]; keep[(vn, col, lab)] = T
                m = len(T)
                if m == 0: continue
                boots = [rng.choice(T["mean"].values, m).mean() for _ in range(3000)]
                k = int((T["mean"] > 0.5).sum())
                res.append(dict(variant=vn[:1], leverage=ln.split(" ")[0], score=kind, window=lab, companies=m, quarters=int(T["count"].sum()),
                                mean_auc=round(T["mean"].mean(), 3), ci95=f"{np.percentile(boots, 2.5):.2f} to {np.percentile(boots, 97.5):.2f}",
                                above_half=f"{k}/{m}", p=round(binomtest(k, m, 0.5).pvalue, 3)))
print("PART 1: mean 'AUC' = chance that a failed company's score is riskier than a control company's in the same calendar quarter. 0.5 = no information, 1.0 = perfect.")
print("variant A/B/C as before; companies = failed companies with at least 2 scored quarters; quarters = scored company-quarters behind the mean; ci95 = bootstrap over companies\n")
print(pd.DataFrame(res).to_string(index=False), "\n")

VB = "B contiguous 2020Q2-2021Q4"; D = keep[(VB, "D")]
for ln in LEVS:
    col = "core|" + ln
    print(f"PART 2: per company, variant B, core score with {ln}")
    a = keep[(VB, col, "last 4 quarters")].rename(columns={"mean": "auc_last4", "count": "n_last4"})
    b = keep[(VB, col, "quarters 5-8")].rename(columns={"mean": "auc_5to8", "count": "n_5to8"})
    print(a.join(b, how="outer").round(2).to_string(), "\n")

print("PART 3: one signal at a time, variant B, failed companies' last 4 quarters (mean risk percentile of company means; 0.5 = no information)")
rows = []
for c in ALL:
    R = D[(D.group == "failed") & D.qtd.between(1, 4)].dropna(subset=["p_" + c]).groupby("ticker")["p_" + c].mean()
    rows.append(dict(signal=c, companies=len(R), mean_percentile=round(R.mean(), 3) if len(R) else np.nan, above_half=f"{int((R > .5).sum())}/{len(R)}"))
print(pd.DataFrame(rows).to_string(index=False), "\n")

print("PART 4: sanity check, do under-pressure companies score riskier than healthy ones in the same quarters? (variant B, core score)")
for ln in LEVS:
    col = "core|" + ln
    U = D[(D.group == "under_pressure") & D[col].notna()]
    U = U.assign(auc=auc_rows(D, U, col, ["healthy"])).dropna(subset=["auc"])
    print(f"{ln}: all under-pressure rows, mean AUC vs healthy =", round(U["auc"].mean(), 3), "| by company:", U.groupby("ticker")["auc"].mean().round(2).to_dict())
