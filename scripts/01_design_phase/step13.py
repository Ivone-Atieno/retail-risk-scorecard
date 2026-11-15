# ===== STEP 13: fix the leverage measure (inventory was inflating the denominator) and the tie handling in the sign test =====
from scipy.stats import binomtest
F = pd.read_csv(BASE / "features_final.csv", parse_dates=["end", "distress_date"])
Qc = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end"]).sort_values(["ticker", "end"]).reset_index(drop=True)

# 1) new leverage measure: debt divided by the last four quarters of sales (not by current assets)
g = Qc.groupby("ticker")
Qc["ttm_rev"] = g["Revenue"].transform(lambda s: s.rolling(4, min_periods=4).sum())
span = Qc["end"] - g["end"].shift(3)
Qc.loc[~span.dt.days.between(240, 300), "ttm_rev"] = np.nan                    # the four quarters must really be consecutive
Qc["debt_to_sales"] = Qc["Debt"] / Qc["ttm_rev"]
Qc["debt_to_ca"] = Qc["Debt"] / Qc["CurrAssets"]

print("PART 0: PRTY, what moved the old leverage measure (millions)")
p = Qc[(Qc.ticker == "PRTY") & (Qc.end >= "2021-03-01") & (Qc.end <= "2022-12-31")].copy()
for c in ["Debt", "CurrAssets", "Inventory", "ttm_rev"]: p[c + "_m"] = (p[c] / 1e6).round(0)
print(p[["end", "Debt_m", "CurrAssets_m", "Inventory_m", "ttm_rev_m", "debt_to_ca", "debt_to_sales"]].round({"debt_to_ca": 2, "debt_to_sales": 2}).to_string(index=False), "\n")

# 2) year-on-year change, matched by date, then minus the median of the healthy peers in the same calendar quarter
Qc["end_prev"] = Qc["end"] - pd.Timedelta(days=364)
P = Qc[["ticker", "end", "debt_to_sales"]].rename(columns={"end": "end_py", "debt_to_sales": "ds_py"}).sort_values("end_py")
Qc = pd.merge_asof(Qc.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker",
                   tolerance=pd.Timedelta(days=15), direction="nearest")
Qc["lev2_chg_yoy"] = Qc["debt_to_sales"] - Qc["ds_py"]
F = F.merge(Qc[["ticker", "end", "lev2_chg_yoy", "debt_to_sales"]], on=["ticker", "end"], how="left")
H = F[F.group == "healthy"]
peer = []
for tk, cq in zip(F["ticker"], F["cal_q"]):
    v = H[(H.cal_q == cq) & (H.ticker != tk)]["lev2_chg_yoy"].dropna()
    peer.append(v.median() if len(v) >= 4 else np.nan)
F["lev2_chg_yoy_rel"] = F["lev2_chg_yoy"] - np.array(peer)
F.to_csv(BASE / "features_final2.csv", index=False)
print("saved features_final2.csv (adds debt_to_sales, lev2_chg_yoy, lev2_chg_yoy_rel)\n")

# 3) the same test as Step 12, but exact ties (no change at all) are left out of the sign test instead of counted as misses
WIN_A = set(F.loc[F["covid_window"], "cal_q"])
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
VARIANTS = {"A data-flagged": WIN_A, "B contiguous 2020Q2-2021Q4": WIN_B, "C peer-adjusted only": set()}
UP = F[F.group == "under_pressure"]

def company_table(win, col):
    rows = []
    for tk, gg in F[(F.group == "failed") & (F.qtd <= 8)].groupby("ticker"):
        gg = gg[~gg["cal_q"].isin(win)].dropna(subset=[col])
        if len(gg) == 0:
            rows.append(dict(ticker=tk, n=0, med=np.nan, up=np.nan, near=np.nan, far=np.nan)); continue
        upv = UP[UP["cal_q"].isin(set(gg["cal_q"]))][col].dropna()
        near, far = gg[gg.qtd <= 4][col], gg[gg.qtd > 4][col]
        rows.append(dict(ticker=tk, n=len(gg), med=gg[col].median(), up=upv.median() if len(upv) else np.nan,
                         near=near.median() if len(near) else np.nan, far=far.median() if len(far) else np.nan))
    return pd.DataFrame(rows).set_index("ticker")

def signtest(x, sign):
    x = x.dropna(); x = x[x != 0]
    return (int((np.sign(x) == sign).sum()), len(x), binomtest(int((np.sign(x) == sign).sum()), len(x), 0.5).pvalue if len(x) else np.nan)

TESTS = {"leverage, old (debt / current assets)": ("lev_chg_yoy_rel", +1), "leverage, new (debt / 4-qtr sales)": ("lev2_chg_yoy_rel", +1),
         "H4 filing delay": ("delay_chg_rel_clean", +1)}
out, det = [], {}
for vn, win in VARIANTS.items():
    for sn, (col, sg) in TESTS.items():
        T = company_table(win, col); det[(vn, sn)] = T; U = T[T.n >= 3]
        k, m, pv = signtest(U["med"], sg); ku, mu, pu = signtest(U["med"] - U["up"], sg)
        tt = (U["near"] - U["far"]).dropna(); kt, mt, pt = signtest(tt, sg)
        out.append(dict(variant=vn, signal=sn, companies=len(U), moved_as_predicted=f"{k}/{m}", p=round(pv, 3), median_of_medians=round(U["med"].median(), 3),
                        worse_than_under_pressure=f"{ku}/{mu}", worsening_into_failure=f"{kt}/{mt}"))
print("PART 1: sign tests with ties left out (k/m = companies moving as predicted / companies with a non-zero result)")
print(pd.DataFrame(out).to_string(index=False), "\n")

for vn, win in VARIANTS.items():
    a, b = det[(vn, "leverage, new (debt / 4-qtr sales)")], company_table(win, "gm_chg_yoy_rel")
    J = a[["n", "med"]].join(b[["n", "med"]], lsuffix="_lev", rsuffix="_gm"); J = J[(J.n_lev >= 3) & (J.n_gm >= 3)]
    k = int(((J.med_gm < 0) & (J.med_lev > 0)).sum())
    print(f"H1 joint with the new leverage measure, variant {vn}: {k} of {len(J)}; p (25% null) = {binomtest(k, len(J), 0.25).pvalue:.3f}" if len(J) else f"{vn}: no data")

print("\nPART 2: per-company detail with the new leverage measure, variant B (primary)")
print(det[("B contiguous 2020Q2-2021Q4", "leverage, new (debt / 4-qtr sales)")].round(3).to_string())
print("\nsame, variant C (no blanking), so thin companies keep their history")
print(det[("C peer-adjusted only", "leverage, new (debt / 4-qtr sales)")].round(3).to_string())
