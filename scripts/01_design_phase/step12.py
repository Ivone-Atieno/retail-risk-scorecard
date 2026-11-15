# ===== STEP 12: first test of H1, H2 and H4, under three ways of treating the shock quarters =====
from scipy.stats import binomtest
F = pd.read_csv(BASE / "features_final.csv", parse_dates=["end", "distress_date"])

# PART 0: trace the odd PRTY leverage drop (debt detail from the debt table)
try:
    dq = pd.read_csv(BASE / "debt_quarterly_final.csv", parse_dates=["end"])
    print("PART 0: PRTY debt build-up, 2021-03 to 2022-12 (millions)")
    print(dq[(dq.ticker == "PRTY") & (dq.end >= "2021-03-01") & (dq.end <= "2022-12-31")][["end", "total_m", "gross_m", "flag", "detail"]].to_string(index=False), "\n")
except Exception as e:
    print("PART 0 skipped:", e, "\n")

WIN_A = set(F.loc[F["covid_window"], "cal_q"])                                  # what Step 11 flagged
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))           # contiguous window (primary)
VARIANTS = {"A data-flagged": WIN_A, "B contiguous 2020Q2-2021Q4": WIN_B, "C peer-adjusted only": set()}
SIG = {"H1 gross margin": ("gm_chg_yoy_rel", -1), "H1 leverage": ("lev_chg_yoy_rel", +1),
       "H2 inventory vs sales": ("inv_gap_rel", +1), "H4 filing delay": ("delay_chg_rel_clean", +1)}
UP = F[F.group == "under_pressure"]

def company_table(win, col, sign):
    rows = []
    for tk, g in F[(F.group == "failed") & (F.qtd <= 8)].groupby("ticker"):
        g = g[~g["cal_q"].isin(win)].dropna(subset=[col])
        if len(g) == 0:
            rows.append(dict(ticker=tk, n=0, med=np.nan, up=np.nan)); continue
        upv = UP[UP["cal_q"].isin(set(g["cal_q"]))][col].dropna()
        near, far = g[g.qtd <= 4][col], g[g.qtd > 4][col]
        rows.append(dict(ticker=tk, n=len(g), med=g[col].median(), up=upv.median() if len(upv) else np.nan,
                         near=near.median() if len(near) else np.nan, far=far.median() if len(far) else np.nan))
    return pd.DataFrame(rows).set_index("ticker")

summary, detail = [], {}
for vname, win in VARIANTS.items():
    for sname, (col, sign) in SIG.items():
        T = company_table(win, col, sign); detail[(vname, sname)] = T
        U = T[T.n >= 3]
        m = len(U); k = int((np.sign(U["med"]) == sign).sum())
        kup = int((np.sign(U["med"] - U["up"]) == sign).sum())
        p = binomtest(k, m, 0.5).pvalue if m else np.nan
        pu = binomtest(kup, m, 0.5).pvalue if m else np.nan
        kt = int((np.sign(U["near"] - U["far"]) == sign).sum()); mt = int(U[["near", "far"]].notna().all(axis=1).sum())
        summary.append(dict(variant=vname, signal=sname, companies=m, in_expected_direction=k, p_vs_healthy=round(p, 3),
                            median_of_medians=round(U["med"].median(), 3) if m else np.nan,
                            worse_than_under_pressure=kup, p_vs_UP=round(pu, 3), worsening_into_failure=f"{kt}/{mt}"))
S = pd.DataFrame(summary)
print("PART 1: how many failed companies moved in the direction the hypothesis predicts (companies with at least 3 usable quarters in their last 8)")
print("expected direction: gross margin falls, leverage rises, inventory outgrows sales, filing delay grows. p = exact sign test, 50/50 null.\n")
print(S.to_string(index=False), "\n")

# H1 needs both at once
for vname, win in VARIANTS.items():
    a, b = detail[(vname, "H1 gross margin")], detail[(vname, "H1 leverage")]
    J = a[["n", "med"]].join(b[["n", "med"]], lsuffix="_gm", rsuffix="_lev")
    J = J[(J.n_gm >= 3) & (J.n_lev >= 3)]
    k = int(((J.med_gm < 0) & (J.med_lev > 0)).sum())
    print(f"H1 joint (margin down AND leverage up), variant {vname}: {k} of {len(J)} failed companies; p (25% null) = {binomtest(k, len(J), 0.25).pvalue:.3f}" if len(J) else f"H1 joint {vname}: no data")
print()

print("PART 2: per-company detail, variant B (primary). med = median peer-adjusted value over the last 8 quarters; up = same quarters, under-pressure group")
for sname in SIG:
    print("\n", sname); print(detail[("B contiguous 2020Q2-2021Q4", sname)].round(2).to_string())
