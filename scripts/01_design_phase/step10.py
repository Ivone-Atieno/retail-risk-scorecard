# ===== STEP 10: trace the odd values, then remove the shared shocks (COVID, tariffs) from each signal =====
F = pd.read_csv(BASE / "features_quarterly.csv", parse_dates=["end", "distress_date", "as_of_date"])
Qc = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end", "f_CurrAssets"])

print("PART A: filing-delay outliers (|change vs same quarter last year| > 45 days). delay_days = first-filed date of the balance sheet minus quarter end")
a = F[F["delay_chg_yoy"].abs() > 45][["ticker", "group", "end", "delay_days", "delay_chg_yoy"]].sort_values("delay_chg_yoy")
print(a.to_string(index=False) if len(a) else "none", "\n")
print("typical delay_days by company (median, max):")
print(F.groupby("ticker")["delay_days"].agg(["median", "max"]).T.round(0).to_string(), "\n")

print("PART B: negative-equity quarters by company")
ne = F.groupby(["group", "ticker"])["equity_negative"].agg(["sum", "size"]).rename(columns={"sum": "neg_equity_rows", "size": "rows"})
print(ne[ne.neg_equity_rows > 0].to_string(), "\n")

print("PART C: BIG leverage around the filing fixes")
print(F[(F.ticker == "BIG") & (F.end >= "2021-10-01") & (F.end <= "2023-08-01")][["end", "debt_to_ca", "lev_chg_yoy"]].round({"debt_to_ca": 3, "lev_chg_yoy": 3}).to_string(index=False), "\n")

# PART D: signal minus the median of the healthy peers in the same calendar quarter (leave-one-out)
# prior-year change in current ratio, matched by date
Cc = F[["ticker", "end", "current_ratio"]].copy()
P = Cc.rename(columns={"end": "end_py", "current_ratio": "cr_py"}).sort_values("end_py")
F["end_prev"] = F["end"] - pd.Timedelta(days=364)
F = pd.merge_asof(F.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker",
                  tolerance=pd.Timedelta(days=15), direction="nearest").sort_values(["ticker", "end"]).reset_index(drop=True)
F["cr_chg_yoy"] = F["current_ratio"] - F["cr_py"]
F["cal_q"] = (F["end"] + pd.Timedelta(days=30)).dt.to_period("Q").astype(str)    # fiscal quarter ends within ~1 month of each other
SIGS = ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "ocf_margin", "delay_chg_yoy", "cr_chg_yoy"]
H = F[F.group == "healthy"]
MINPEERS = 4
for s in SIGS:
    out = []
    for tk, cq in zip(F["ticker"], F["cal_q"]):
        peers = H[(H.cal_q == cq) & (H.ticker != tk)][s].dropna()
        out.append(peers.median() if len(peers) >= MINPEERS else np.nan)
    F[s + "_peer"] = out
    F[s + "_rel"] = F[s] - F[s + "_peer"]
REL = [s + "_rel" for s in SIGS]
F.drop(columns=["end_prev", "end_py", "cr_py"]).to_csv(BASE / "features_relative.csv", index=False)
print("saved features_relative.csv:", len(F), "rows\n")

print("PART D1: what the healthy peer median looked like in the shock quarters (this is what gets removed)")
pm = H.groupby("cal_q")[["gm_chg_yoy", "inv_gap", "ocf_margin", "lev_chg_yoy"]].median().round(2)
print(pm.loc["2020Q1":"2022Q3"].to_string(), "\n")

print("PART D2: share of rows with a relative value, by group")
print((F.groupby("group")[REL].count().div(F.groupby("group").size(), axis=0) * 100).round(0).to_string(), "\n")

print("PART D3: ranges after adjustment (min / 1% / median / 99% / max)")
print(F[REL].describe(percentiles=[.01, .5, .99]).T[["min", "1%", "50%", "99%", "max"]].round(2).to_string(), "\n")

print("PART D4: most extreme relative values")
for s in REL:
    x = F.dropna(subset=[s]).reindex(F[s].abs().dropna().sort_values(ascending=False).index).head(3)
    print(s, "->", [(a, str(b.date()), round(c, 2)) for a, b, c in zip(x.ticker, x.end, x[s])])
print()
print("PART D5: failed companies, rows with all of gm, inventory, leverage, delay (relative), and the same for the last 8 quarters before distress")
core = ["gm_chg_yoy_rel", "inv_gap_rel", "lev_chg_yoy_rel", "delay_chg_yoy_rel"]
fl = F[F.group == "failed"].copy(); fl["full"] = fl[core].notna().all(axis=1)
print(fl.groupby("ticker").agg(rows=("end", "size"), full_rows=("full", "sum"),
      full_last8=("full", lambda s: int((s & (fl.loc[s.index, "qtd"] <= 8)).sum()))).to_string())
