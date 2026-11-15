# ===== STEP 7b: three diagnostics on the wide table =====
W = pd.read_csv(BASE / "clean_07_wide.csv", parse_dates=["end"])
q = pd.read_csv(BASE / "clean_06_quarters.csv", parse_dates=["end", "filed", "alt_filed"])
order = list(companies["ticker"])

# A. quarters with no debt value, with the neighbouring debt values for context
rows = []
for _, r in W[W["Debt"].isna()].iterrows():
    w = W[W.ticker == r.ticker].sort_values("end").reset_index(drop=True)
    i = int(w.index[w.end == r.end][0])
    prev = w.loc[i - 1, "Debt"] if i > 0 else np.nan
    nxt = w.loc[i + 1, "Debt"] if i + 1 < len(w) else np.nan
    rows.append(dict(ticker=r.ticker, end=r.end.date(),
                     flag=r.debt_flag if pd.notna(r.debt_flag) else "(no debt row)",
                     debt_before_m=round(prev / 1e6, 1) if pd.notna(prev) else None,
                     debt_after_m=round(nxt / 1e6, 1) if pd.notna(nxt) else None))
print("A. QUARTERS WITH NO DEBT VALUE (", len(rows), "): zero-like neighbours suggest an undrawn revolver, large ones a missing tag")
print(pd.DataFrame(rows).to_string(index=False), "\n")

# B. does the latest quarter of each company jump versus the same quarter a year earlier?
W["margin"] = W["GrossProfit"] / W["Revenue"] * 100
rows = []
for tk in order:
    w = W[(W.ticker == tk) & W["margin"].notna()].sort_values("end")
    if len(w) < 6:
        continue
    last = w.iloc[-1]
    yago = w[(w["end"] - (last["end"] - pd.Timedelta(days=364))).abs() <= pd.Timedelta(days=10)]
    s = q[(q.ticker == tk) & (q.end == last["end"])].set_index("metric")["src"]
    rows.append(dict(ticker=tk, last_end=last["end"].date(), last_margin=round(last["margin"], 1),
                     year_earlier=round(yago["margin"].iloc[0], 1) if len(yago) else None,
                     prev4_avg=round(w.iloc[-5:-1]["margin"].mean(), 1),
                     rev_src=s.get("Revenue"), cogs_src=s.get("CostOfGoods"), gp_src=s.get("GrossProfit")))
b = pd.DataFrame(rows)
b["vs_year_earlier_pts"] = (b["last_margin"] - b["year_earlier"]).round(1)
print("B. LATEST-QUARTER GROSS MARGIN VS A YEAR EARLIER (one company jumping alone is real; many together would suggest a method problem)")
print(b.reindex(b["vs_year_earlier_pts"].abs().sort_values(ascending=False).index).to_string(index=False), "\n")

# C. the two TGT quarters above 31%, with their sources
rows = []
for e in ["2019-08-03", "2026-08-01"]:
    for m in ["Revenue", "CostOfGoods", "GrossProfit"]:
        z = q[(q.ticker == "TGT") & (q.metric == m) & (q.end == pd.Timestamp(e))]
        for _, r in z.iterrows():
            rows.append(dict(end=e, metric=m, val_m=round(r["val"] / 1e6), src=r["src"], filed=r["filed"].date(),
                             other_version_m=round(r["alt_val"] / 1e6) if pd.notna(r["alt_val"]) else None))
print("C. TGT QUARTERS ABOVE 31%"); print(pd.DataFrame(rows).to_string(index=False))
