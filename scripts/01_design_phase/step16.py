# ===== STEP 16: does the H3 result survive the debt-definition problems, and can it tell failed from merely pressured companies? =====
F = pd.read_csv(BASE / "features_final2.csv", parse_dates=["end", "distress_date"]).reset_index(drop=True)
Qc = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end"]).sort_values(["ticker", "end"]).reset_index(drop=True)
Qc["end_prev"] = Qc["end"] - pd.Timedelta(days=364)
P = Qc[["ticker", "end", "Debt"]].rename(columns={"end": "end_py", "Debt": "Debt_py"}).sort_values("end_py")
Qc = pd.merge_asof(Qc.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker", tolerance=pd.Timedelta(days=15), direction="nearest")
Qc["lev3_chg_yoy"] = np.where(Qc["Debt_py"] > 0, (Qc["Debt"] / Qc["Debt_py"] - 1) * 100, np.nan)
F = F.merge(Qc[["ticker", "end", "lev3_chg_yoy"]], on=["ticker", "end"], how="left")

DIR = {"gm_chg_yoy": -1, "inv_gap": +1, "lev2_chg_yoy": +1, "lev3_chg_yoy": +1}
LEV = {"lev2": "lev2_chg_yoy", "lev3": "lev3_chg_yoy"}
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
# from debt_definition.csv: includes_leases = Y or partly ; confidence = low
LEASE = ["TGT", "HD", "M", "WOOF", "RAD", "PRTY", "CONN"]
LOWCONF = ["KSS", "WOOF", "PLCE", "BBBY (old)", "PRTY", "TUEM"]

def build(ctrl_groups, drop=()):
    D = F.copy()
    for c in DIR: D.loc[D["cal_q"].isin(WIN_B), c] = np.nan
    for c in DIR:
        pr = np.full(len(D), np.nan)
        for cq, g in D.groupby("cal_q"):
            ref = g[g.group.isin(ctrl_groups) & ~g.ticker.isin(drop)]
            for i, r in g[g[c].notna()].iterrows():
                v = ref[ref.ticker != r.ticker][c].dropna()
                if len(v) >= 5: pr[i] = ((v < r[c]).sum() + 0.5 * (v == r[c]).sum()) / len(v)
        D["p_" + c] = pr if DIR[c] > 0 else 1 - pr
    return D

def sc(D, lev, kind):
    cols = ["p_gm_chg_yoy", "p_inv_gap", "p_" + LEV[lev]] if kind == "core" else ["p_" + LEV[lev]]
    return pd.Series(np.where(D[cols].notna().all(axis=1), D[cols].mean(axis=1), np.nan), index=D.index)

def comp_auc(D, col, ref_groups, drop=(), lo=1, hi=4):
    R = D[(D.group == "failed") & D.qtd.between(lo, hi) & D[col].notna() & ~D.ticker.isin(drop)]
    out = []
    for i, r in R.iterrows():
        v = D[(D.cal_q == r.cal_q) & D.group.isin(ref_groups) & ~D.ticker.isin(drop) & (D.ticker != r.ticker)][col].dropna()
        out.append(((v < r[col]).sum() + 0.5 * (v == r[col]).sum()) / len(v) if len(v) >= 5 else np.nan)
    return R.assign(auc=out).dropna(subset=["auc"]).groupby("ticker")["auc"].mean()

CTRL = ["healthy", "under_pressure"]
print("PART 1: debt-definition sensitivity (variant B, last 4 quarters, healthy + under-pressure controls). 'leverage alone' = the one leverage signal, no margin or inventory")
rows = []
for label, drop in [("baseline (all companies)", ()), ("without companies whose debt includes finance leases", LEASE),
                    ("without low-confidence debt definitions", LOWCONF), ("without both", sorted(set(LEASE) | set(LOWCONF)))]:
    D = build(CTRL, drop)
    for lev in LEV:
        for kind in ["core", "leverage alone"]:
            D["s"] = sc(D, lev, "core" if kind == "core" else "lev"); T = comp_auc(D, "s", CTRL, drop)
            rows.append(dict(debt_set=label, leverage=lev, score=kind, failed_companies=len(T), mean_auc=round(T.mean(), 3) if len(T) else np.nan,
                             above_half=f"{int((T > .5).sum())}/{len(T)}", who=",".join(T.index.str.replace(" (old)", "", regex=False))))
print(pd.DataFrame(rows).to_string(index=False), "\n")

print("PART 2: failed companies against different control groups (variant B, last 4 quarters, all companies kept)")
rows = []
for label, cg in [("healthy only", ["healthy"]), ("under-pressure only", ["under_pressure"]), ("both (baseline)", CTRL)]:
    D = build(cg)
    for lev in LEV:
        for kind in ["core", "leverage alone"]:
            D["s"] = sc(D, lev, "core" if kind == "core" else "lev"); T = comp_auc(D, "s", cg)
            rows.append(dict(controls=label, leverage=lev, score=kind, failed_companies=len(T), mean_auc=round(T.mean(), 3), above_half=f"{int((T > .5).sum())}/{len(T)}"))
print(pd.DataFrame(rows).to_string(index=False), "\n")

print("PART 3: per failed company against the under-pressure companies only (core score, mean AUC over its last 4 quarters)")
D = build(["under_pressure"]); out = {}
for lev in LEV:
    D["s"] = sc(D, lev, "core"); out[lev] = comp_auc(D, "s", ["under_pressure"])
print(pd.DataFrame(out).round(2).to_string())
