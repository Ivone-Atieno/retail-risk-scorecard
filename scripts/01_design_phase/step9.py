# ===== STEP 9: build the quarterly signals (no hypothesis testing yet) =====
Q = pd.read_csv(BASE / "clean_quarterly.csv", parse_dates=["end", "distress_date", "as_of_date", "f_CurrAssets"])
Q = Q.sort_values(["ticker", "end"]).reset_index(drop=True)

# 1) same quarter one year earlier, matched by DATE (not by row position), tolerance 15 days
Q["end_prev"] = Q["end"] - pd.Timedelta(days=364)
cols = ["ticker", "end", "Revenue", "Inventory", "GrossProfit", "Debt", "CurrAssets", "delay_days"]
Q["delay_days"] = (Q["f_CurrAssets"] - Q["end"]).dt.days
P = Q[cols].rename(columns=lambda c: c if c == "ticker" else c + "_py").sort_values("end_py")
Q = pd.merge_asof(Q.sort_values("end_prev"), P, left_on="end_prev", right_on="end_py", by="ticker",
                  tolerance=pd.Timedelta(days=15), direction="nearest").sort_values(["ticker", "end"]).reset_index(drop=True)

# 2) signals
Q["gross_margin"] = Q["GrossProfit"] / Q["Revenue"]
Q["gm_py"] = Q["GrossProfit_py"] / Q["Revenue_py"]
Q["gm_chg_yoy"] = (Q["gross_margin"] - Q["gm_py"]) * 100                      # percentage points
brk = (Q["ticker"] == "DBI") & (Q["end"] >= "2023-04-29") & (Q["end_py"] < "2023-04-29")
Q["basis_break_yoy"] = brk | ((Q["ticker"] == "DBI") & Q["end_py"].isna() & (Q["end"] >= "2023-04-29") & (Q["end"] < "2024-05-01"))
Q.loc[Q["basis_break_yoy"], "gm_chg_yoy"] = np.nan                           # old vs new basis cannot be compared

Q["rev_yoy"] = (Q["Revenue"] / Q["Revenue_py"] - 1) * 100
Q["inv_yoy"] = (Q["Inventory"] / Q["Inventory_py"] - 1) * 100
Q["inv_gap"] = Q["inv_yoy"] - Q["rev_yoy"]                                    # H2: inventory growth minus sales growth
Q["inv_to_rev"] = Q["Inventory"] / Q["Revenue"]

Q["debt_to_ca"] = Q["Debt"] / Q["CurrAssets"]
Q["lev_chg_yoy"] = Q["debt_to_ca"] - Q["Debt_py"] / Q["CurrAssets_py"]
Q["equity_negative"] = Q["Equity"] < 0
Q["debt_to_equity"] = np.where(Q["Equity"] > 0, Q["Debt"] / Q["Equity"], np.nan)
Q["current_ratio"] = Q["CurrAssets"] / Q["CurrLiab"]
Q["ocf_margin"] = Q["OpCashFlow"] / Q["Revenue"] * 100
Q["net_margin"] = Q["NetIncome"] / Q["Revenue"] * 100
Q["delay_chg_yoy"] = Q["delay_days"] - Q["delay_days_py"]                     # H4: filing delay vs same quarter last year
Q["qtd"] = -Q["q_rel"]                                                        # failed companies: 1 = last filed quarter before distress

SIG = ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "current_ratio", "ocf_margin", "delay_chg_yoy"]
keep = ["ticker", "group", "end", "qtd", "distress_date", "tariff_refund_quarter", "gp_basis", "basis_break_yoy", "equity_negative",
        "gross_margin", "gm_chg_yoy", "rev_yoy", "inv_yoy", "inv_gap", "inv_to_rev", "debt_to_ca", "lev_chg_yoy", "debt_to_equity",
        "current_ratio", "ocf_margin", "net_margin", "delay_days", "delay_chg_yoy", "as_of_date"]
F = Q[keep]
F.to_csv(BASE / "features_quarterly.csv", index=False)
print("saved features_quarterly.csv:", len(F), "rows,", F["ticker"].nunique(), "companies\n")

print("CHECK 1: share of rows with a value, by group (a signal needs a prior-year quarter, so each company loses its first year)")
print((F.groupby("group")[SIG].count().div(F.groupby("group").size(), axis=0) * 100).round(0).to_string(), "\n")

print("CHECK 2: ranges, to catch unit errors or extreme values (min / 1st pct / median / 99th pct / max)")
r = F[SIG + ["gross_margin", "debt_to_ca", "inv_to_rev"]].describe(percentiles=[.01, .5, .99]).T[["min", "1%", "50%", "99%", "max"]].round(2)
print(r.to_string(), "\n")

print("CHECK 3: the most extreme single values per signal (verify these before trusting any average)")
for s in ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "current_ratio", "ocf_margin"]:
    x = F.dropna(subset=[s]).reindex(F[s].abs().dropna().sort_values(ascending=False).index).head(3)
    print(s, "->", [(a, str(b.date()), round(c, 2)) for a, b, c in zip(x.ticker, x.end, x[s])])
print()

print("CHECK 4: failed companies, rows with a full set of the five core signals, by quarters before distress")
core = ["gm_chg_yoy", "inv_gap", "lev_chg_yoy", "current_ratio", "delay_chg_yoy"]
fl = F[F.group == "failed"].copy(); fl["full"] = fl[core].notna().all(axis=1)
print(fl.groupby("ticker").agg(rows=("end", "size"), full_rows=("full", "sum"), first_full=("end", lambda s: str(s[fl.loc[s.index, "full"]].min().date()) if fl.loc[s.index, "full"].any() else "none")).to_string())
print("\nrows affected by the DBI basis break:", int(F["basis_break_yoy"].sum()), "| negative-equity rows:", int(F["equity_negative"].sum()),
      "| tariff-refund rows:", int(F["tariff_refund_quarter"].sum()))
