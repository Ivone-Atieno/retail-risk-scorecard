# ===== STEP 7: one wide quarterly table (flows + balance sheet + debt) =====
q = pd.read_csv(BASE / "clean_06_quarters.csv", parse_dates=["end", "filed"])
st = pd.read_csv(BASE / "clean_04b_stitched.csv", parse_dates=["start", "end", "filed"])
bal = st[st.metric.isin(BAL) & (st.ptype == "I")]
dbt = pd.read_csv(BASE / "debt_quarterly_final.csv", parse_dates=["end"])

order = list(companies["ticker"])
grid = {tk: pd.DatetimeIndex(sorted(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique())) for tk in order}
W = pd.DataFrame([(tk, e) for tk in order for e in grid[tk]], columns=["ticker", "end"])

for m in FLOW:
    W = W.merge(q[q.metric == m][["ticker", "end", "val", "filed"]].rename(columns={"val": m, "filed": "f_" + m}),
                on=["ticker", "end"], how="left")
for m in BAL:
    W = W.merge(bal[bal.metric == m][["ticker", "end", "val", "filed"]].rename(columns={"val": m, "filed": "f_" + m}),
                on=["ticker", "end"], how="left")

# debt: snap its dates onto the quarter grid (within 5 days), then attach
def snap(tk, d):
    g = grid.get(tk)
    if g is None or len(g) == 0: return pd.NaT
    diff = np.abs((g - d).days); p = int(diff.argmin())
    return g[p] if diff[p] <= 5 else pd.NaT
dbt["end_grid"] = [snap(t, d) for t, d in zip(dbt["ticker"], dbt["end"])]
unmatched = dbt[dbt["end_grid"].isna()]
d2 = dbt.dropna(subset=["end_grid"]).copy()
d2["has"] = d2["total_m"].notna()
d2 = d2.sort_values(["ticker", "end_grid", "has"], ascending=[True, True, False])
n_dup = int(d2.duplicated(["ticker", "end_grid"]).sum())
d2 = d2.drop_duplicates(["ticker", "end_grid"], keep="first")
d2 = d2.rename(columns={"end_grid": "end", "end": "end_raw", "flag": "debt_flag"})
d2["Debt"] = d2["total_m"] * 1e6
W = W.merge(d2[["ticker", "end", "Debt", "debt_flag"]], on=["ticker", "end"], how="left")
W["f_Debt"] = W["f_CurrAssets"].where(W["Debt"].notna())      # debt comes from the same balance sheet filing

V11 = FLOW + BAL + ["Debt"]
W["n_metrics"] = W[V11].notna().sum(axis=1)
W.to_csv(BASE / "clean_07_wide.csv", index=False)
print("saved clean_07_wide.csv:", len(W), "rows x", W.shape[1], "columns\n")

print("CHECK 1: rows per company")
print(W.groupby("ticker").agg(rows=("end", "size"), first=("end", "min"), last=("end", "max")).reindex(order).to_string(), "\n")
print("CHECK 2: how many quarters have a value, per metric")
print(W.groupby("ticker")[V11].count().reindex(order).to_string(), "\n")

W["cur_ratio"] = W["CurrAssets"] / W["CurrLiab"]
W["inv_to_qsales"] = W["Inventory"] / W["Revenue"]
W["debt_to_curr_assets"] = W["Debt"] / W["CurrAssets"]
print("CHECK 3: unit sanity (a unit mistake would show as a 1,000,000x jump)")
s3 = W.groupby("ticker")[["cur_ratio", "inv_to_qsales", "debt_to_curr_assets"]].agg(["min", "median", "max"]).round(2)
print(s3.reindex(order).to_string(), "\n")

print("CHECK 4: debt rows not matched to the grid:", len(unmatched), "| duplicate debt dates merged:", n_dup)
if len(unmatched):
    print(unmatched[["ticker", "end", "total_m", "flag"]].head(15).to_string(index=False))
print(pd.crosstab(W["ticker"], W["debt_flag"].fillna("(no debt row)")).reindex(order).to_string(), "\n")

W["margin"] = W["GrossProfit"] / W["Revenue"] * 100
print("CHECK 5: margin outliers to look at")
t = W[(W.ticker == "TGT") & (W.margin > 31)][["ticker", "end", "Revenue", "CostOfGoods", "GrossProfit", "margin"]].copy()
for c in ["Revenue", "CostOfGoods", "GrossProfit"]: t[c] = (t[c] / 1e6).round(0)
t["margin"] = t["margin"].round(1)
print("TGT quarters above 31%:"); print(t.to_string(index=False) if len(t) else "  none")
dd = W[(W.ticker == "DBI")].tail(6)[["ticker", "end", "Revenue", "GrossProfit", "margin"]].copy()
dd["Revenue"] = (dd["Revenue"] / 1e6).round(0); dd["GrossProfit"] = (dd["GrossProfit"] / 1e6).round(0); dd["margin"] = dd["margin"].round(1)
print("\nDBI latest quarters:"); print(dd.to_string(index=False))
