# ===== STEP 15: how fragile is the H3 result? (months before failure, leave-one-out, other control groups, dropping one signal) =====
F = pd.read_csv(BASE / "features_final2.csv", parse_dates=["end", "distress_date"]).reset_index(drop=True)
Qc = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end"]).sort_values(["ticker", "end"]).reset_index(drop=True)
Qc["end_prev"] = Qc["end"] - pd.Timedelta(days=364)
P = Qc[["ticker", "end", "Debt"]].rename(columns={"end": "end_py", "Debt": "Debt_py"}).sort_values("end_py")
Qc = pd.merge_asof(Qc.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker", tolerance=pd.Timedelta(days=15), direction="nearest")
Qc["lev3_chg_yoy"] = np.where(Qc["Debt_py"] > 0, (Qc["Debt"] / Qc["Debt_py"] - 1) * 100, np.nan)
F = F.merge(Qc[["ticker", "end", "lev3_chg_yoy"]], on=["ticker", "end"], how="left")

DIR = {"gm_chg_yoy": -1, "inv_gap": +1, "lev2_chg_yoy": +1, "lev3_chg_yoy": +1}
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
LEV = {"lev2": "lev2_chg_yoy", "lev3": "lev3_chg_yoy"}

# PART 1: what "last 4 quarters" means in months
F["months_before"] = (F["distress_date"] - F["end"]).dt.days / 30.44
mb = F[(F.group == "failed") & F.qtd.between(1, 8)].groupby("qtd")["months_before"].agg(["min", "median", "max"]).round(1)
print("PART 1: months between quarter end and the distress date (failed companies)")
print(mb.to_string(), "\n")

def build(ctrl_groups, drop_ctrl=()):
    D = F.copy()
    for c in DIR: D.loc[D["cal_q"].isin(WIN_B), c] = np.nan
    for c in DIR:
        pr = np.full(len(D), np.nan)
        for cq, g in D.groupby("cal_q"):
            ref = g[g.group.isin(ctrl_groups) & ~g.ticker.isin(drop_ctrl)]
            for i, r in g[g[c].notna()].iterrows():
                v = ref[ref.ticker != r.ticker][c].dropna()
                if len(v) >= 5: pr[i] = ((v < r[c]).sum() + 0.5 * (v == r[c]).sum()) / len(v)
        D["p_" + c] = pr if DIR[c] > 0 else 1 - pr
    return D

def score(D, lev, drop=None):
    cols = [c for c in ["p_gm_chg_yoy", "p_inv_gap", "p_" + LEV[lev]] if c != drop]
    return pd.Series(np.where(D[cols].notna().all(axis=1), D[cols].mean(axis=1), np.nan), index=D.index)

def comp_auc(D, col, ref_groups, drop_ctrl=(), lo=1, hi=4):
    R = D[(D.group == "failed") & D.qtd.between(lo, hi) & D[col].notna()]
    out = []
    for i, r in R.iterrows():
        v = D[(D.cal_q == r.cal_q) & D.group.isin(ref_groups) & ~D.ticker.isin(drop_ctrl) & (D.ticker != r.ticker)][col].dropna()
        out.append(((v < r[col]).sum() + 0.5 * (v == r[col]).sum()) / len(v) if len(v) >= 5 else np.nan)
    R = R.assign(auc=out).dropna(subset=["auc"])
    return R.groupby("ticker")["auc"].mean()

CTRL = ["healthy", "under_pressure"]
D0 = build(CTRL)
print("PART 2: leave one failed company out (variant B, last 4 quarters, core score). mean AUC of the remaining companies")
rows = []
for lev in LEV:
    D0["s"] = score(D0, lev); T = comp_auc(D0, "s", CTRL)
    for tk in T.index:
        rows.append(dict(leverage=lev, left_out=tk, mean_auc_of_rest=round(T.drop(tk).mean(), 3)))
    rows.append(dict(leverage=lev, left_out="(none)", mean_auc_of_rest=round(T.mean(), 3)))
R2 = pd.DataFrame(rows)
print(R2.pivot(index="left_out", columns="leverage", values="mean_auc_of_rest").to_string(), "\n")

print("PART 3: different control groups (variant B, last 4 quarters, core score)")
rows = []
for label, cg, dc in [("healthy + under-pressure (baseline)", CTRL, ()), ("healthy only", ["healthy"], ()),
                      ("without DBI", CTRL, ("DBI",)), ("without BGFV", CTRL, ("BGFV",)), ("without DBI and BGFV", CTRL, ("DBI", "BGFV"))]:
    D = build(cg, dc)
    for lev in LEV:
        D["s"] = score(D, lev); T = comp_auc(D, "s", cg, dc)
        rows.append(dict(controls=label, leverage=lev, companies=len(T), mean_auc=round(T.mean(), 3), above_half=f"{int((T > .5).sum())}/{len(T)}"))
print(pd.DataFrame(rows).to_string(index=False), "\n")

print("PART 4: drop one signal at a time from the score (variant B, last 4 quarters, baseline controls). Diagnostic only, not a new score")
rows = []
for lev in LEV:
    for label, dr in [("all three", None), ("without gross margin", "p_gm_chg_yoy"), ("without inventory gap", "p_inv_gap"), ("without leverage", "p_" + LEV[lev])]:
        D0["s"] = score(D0, lev, dr); T = comp_auc(D0, "s", CTRL)
        rows.append(dict(leverage=lev, score=label, companies=len(T), mean_auc=round(T.mean(), 3), above_half=f"{int((T > .5).sum())}/{len(T)}"))
print(pd.DataFrame(rows).to_string(index=False))
