# ===== STEP 8: debt fixes, flags, as-of filter and the final tables =====
V11 = FLOW + BAL + ["Debt"]
FC = ["f_" + m for m in V11]
W = pd.read_csv(BASE / "clean_07_wide.csv", parse_dates=["end"] + FC)

# 1) debt values read directly from the filings (balance sheet, us-gaap, no dimensions)
FIX = [("BIG", "2022-04-30", 270.8, "2022-06-08", "10-Q balance sheet: LongTermDebtNoncurrent (our formula missed this tag)"),
       ("BIG", "2022-07-30", 252.6, "2022-09-07", "10-Q balance sheet: LongTermDebtNoncurrent"),
       ("BIG", "2022-10-29", 459.9, "2022-12-07", "10-Q balance sheet: LongTermDebtNoncurrent"),
       ("BIG", "2023-04-29", 501.6, "2023-06-07", "10-Q balance sheet: LongTermDebtNoncurrent"),
       ("EXPR", "2019-11-02", 0.0, "2019-12-11", "10-Q: current and total liabilities tie out exactly with no borrowings line")]
for tk, d, v, filed, why in FIX:
    m = (W.ticker == tk) & (W.end == pd.Timestamp(d))
    assert m.sum() == 1, (tk, d, "row not found")
    assert W.loc[m, "Debt"].isna().all(), (tk, d, "already has a debt value, not overwriting")
    W.loc[m, "Debt"] = v * 1e6; W.loc[m, "debt_flag"] = "MANUAL (filing)"; W.loc[m, "f_Debt"] = pd.Timestamp(filed)
pd.DataFrame(FIX, columns=["ticker", "end", "debt_m", "filed", "source"]).to_csv(BASE / "debt_gap_overrides.csv", index=False)

# 2) flags
W["tariff_refund_quarter"] = W["end"] >= pd.Timestamp("2026-07-31")      # TGT and ROST verified; others not checked
W["gp_basis"] = np.where(W["ticker"] == "DBI", np.where(W["end"] < pd.Timestamp("2023-04-29"), "old", "new"), "")

# 3) distress dates, quarters relative to failure, as-of filter
co = pd.read_csv(BASE / "companies.csv", parse_dates=["distress_date"])[["ticker", "group", "distress_date"]]
W = W.merge(co, on="ticker", how="left").sort_values(["ticker", "end"]).reset_index(drop=True)
W["pos"] = W.groupby("ticker").cumcount()
last_ok = {}
for tk, g in W.groupby("ticker"):
    dd = g["distress_date"].iloc[0]
    if pd.isna(dd): continue
    ok = g[g["f_CurrAssets"] <= dd]
    last_ok[tk] = int(ok["pos"].max()) if len(ok) else -1
W["q_rel"] = [(p - last_ok[t] - 1) if t in last_ok else np.nan for t, p in zip(W["ticker"], W["pos"])]
W["usable"] = W["q_rel"].isna() | (W["q_rel"] <= -1)

masked = []
for tk, L in last_ok.items():
    dd = W.loc[W.ticker == tk, "distress_date"].iloc[0]
    for m in V11:
        bad = (W.ticker == tk) & W["usable"] & W["f_" + m].notna() & (W["f_" + m] > dd)
        if bad.any():
            masked.append((tk, m, int(bad.sum())))
            W.loc[bad, m] = np.nan; W.loc[bad, "f_" + m] = pd.NaT
W["as_of_date"] = W[FC].max(axis=1)

W.drop(columns=["pos"]).to_csv(BASE / "clean_quarterly_full.csv", index=False)
final = W[W["usable"]].drop(columns=["pos", "usable"]).reset_index(drop=True)
final.to_csv(BASE / "clean_quarterly.csv", index=False)
print("saved clean_quarterly.csv:", len(final), "rows | clean_quarterly_full.csv:", len(W), "rows (all quarters, with flags)\n")

print("CHECK 1: debt values added from the filings")
print(W[(W.ticker == "BIG") & (W.end >= "2022-01-01") & (W.end <= "2023-10-31")][["ticker", "end", "Debt", "debt_flag"]]
      .assign(Debt_m=lambda d: (d["Debt"] / 1e6).round(1)).drop(columns="Debt").to_string(index=False))
print(W[(W.ticker == "EXPR") & (W.end <= "2020-03-01")][["ticker", "end", "Debt", "debt_flag"]]
      .assign(Debt_m=lambda d: (d["Debt"] / 1e6).round(1)).drop(columns="Debt").to_string(index=False), "\n")

EXPECT = {"BBBY (old)": "2022-11-26", "RAD": "2023-06-03", "BIG": "2024-05-04", "PRTY": "2022-09-30",
          "JOAN": "2023-10-28", "EXPR": "2023-10-28", "TUEM": "2022-10-01", "CONN": "2024-01-31"}
rows = []
for tk, exp in EXPECT.items():
    if tk not in set(W.ticker): print("not in data, skipped:", tk); continue
    g = W[(W.ticker == tk) & W["usable"]]
    got = g["end"].max()
    rows.append(dict(ticker=tk, distress=W.loc[W.ticker == tk, "distress_date"].iloc[0].date(), usable_quarters=len(g),
                     dropped_after=int(((W.ticker == tk) & ~W["usable"]).sum()), last_usable=got.date(),
                     matches_earlier_table="PASS" if str(got.date()) == exp else "FAIL (expected " + exp + ")"))
print("CHECK 2: the as-of filter against the usable-history table from Step 1b")
print(pd.DataFrame(rows).to_string(index=False), "\n")
print("CHECK 3: single values removed because they were first filed after the distress date:", masked if masked else "none", "\n")

KEY = ["Revenue", "GrossProfit", "Inventory", "Debt"]
cnt = final.groupby("ticker")[KEY].count()
cnt.insert(0, "quarters", final.groupby("ticker").size())
print("CHECK 4: usable quarters with a value, per company (the 8-quarter minimum applies to each signal)")
print(cnt.reindex(W["ticker"].unique()).to_string())
low = [(t, k, int(cnt.loc[t, k])) for t in cnt.index for k in KEY if cnt.loc[t, k] < 8]
print("below 8:", low if low else "none", "\n")
print("CHECK 5: quarters flagged as tariff-refund quarters:", int(final["tariff_refund_quarter"].sum()),
      "| DBI quarters by gross-profit basis:", final[final.ticker == "DBI"]["gp_basis"].value_counts().to_dict())
