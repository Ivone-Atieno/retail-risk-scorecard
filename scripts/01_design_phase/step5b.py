# ===== STEP 5b: diagnostics before we finalise the quarterly table =====
st = pd.read_csv(BASE / "clean_04b_stitched.csv", parse_dates=["start", "end", "filed"])
flows = st[st.metric.isin(FLOW) & st.ptype.isin(["Q", "YTD", "A"])]

def near(g, d):
    diff = np.abs((g - d).days); p = int(diff.argmin())
    return p if diff[p] <= 5 else None

reasons = []
for tk in companies["ticker"]:
    g = pd.DatetimeIndex(sorted(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique()))
    if len(g) < 2:
        continue
    for _, r in flows[flows.ticker == tk].iterrows():
        i, j = near(g, r["start"] - pd.Timedelta(days=1)), near(g, r["end"])
        if i is not None and j is not None and j > i:
            continue
        if r["end"] <= g[0] + pd.Timedelta(days=5): why = "ends on/before the first balance-sheet date"
        elif i is None and r["start"] - pd.Timedelta(days=1) < g[0] - pd.Timedelta(days=5): why = "starts before the first balance-sheet date"
        elif j is None: why = "end date not on the grid"
        elif i is None: why = "start date not on the grid"
        else: why = "other"
        reasons.append(dict(ticker=tk, metric=r["metric"], ptype=r["ptype"], start=r["start"].date(), end=r["end"].date(), why=why))
rs = pd.DataFrame(reasons)
print("A. WHY ROWS COULD NOT BE PLACED (", len(rs), "rows )")
print(rs["why"].value_counts().to_string(), "\n")
odd = rs[~rs["why"].str.contains("before the first")]
print("rows with an unexpected reason:", len(odd))
if len(odd):
    print(odd.head(25).to_string(index=False))
print()

q = pd.read_csv(BASE / "clean_05_quarters.csv", parse_dates=["end"])
d = q[(q.ticker == "DBI") & q.metric.isin(["Revenue", "GrossProfit"])].pivot(index="end", columns="metric", values="val")
d["gm_pct"] = (d["GrossProfit"] / d["Revenue"] * 100).round(1)
src = q[(q.ticker == "DBI") & (q.metric == "GrossProfit")].set_index("end")["src"]
out = (d[["Revenue", "GrossProfit"]] / 1e6).round(1).join(d["gm_pct"]).join(src.rename("gp_source"))
print("B. DBI QUARTERLY GROSS MARGIN (look for a jump in the 2022-2023 range)")
print(out.to_string())
