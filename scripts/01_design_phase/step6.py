# ===== STEP 6: derive gross profit / cost of goods where the agreed rule says so =====
q = pd.read_csv(BASE / "clean_05c_quarters.csv", parse_dates=["end", "filed", "alt_filed"])
q["basis"] = q["basis"].fillna("")
V = q.pivot(index=["ticker", "end"], columns="metric", values="val")
F = q.pivot(index=["ticker", "end"], columns="metric", values="filed")
basis_gp = q[q.metric == "GrossProfit"].set_index(["ticker", "end"])["basis"].to_dict()

DERIVE_GP = ["WMT", "COST", "TGT", "TJX", "ROST", "KSS", "M", "JOAN", "CONN"]   # gross profit = revenue - cost of goods
DERIVE_COGS = ["PLCE", "DBI"]                                                  # cost of goods = revenue - gross profit
add = []
for (tk, end), row in V.iterrows():
    rev, cg, gp = row.get("Revenue"), row.get("CostOfGoods"), row.get("GrossProfit")
    if tk in DERIVE_GP and pd.isna(gp) and pd.notna(rev) and pd.notna(cg):
        add.append(dict(ticker=tk, metric="GrossProfit", end=end, val=rev - cg,
                        filed=max(F.loc[(tk, end), "Revenue"], F.loc[(tk, end), "CostOfGoods"]), src="derived (rule)", basis=""))
    if tk in DERIVE_COGS and pd.isna(cg) and pd.notna(rev) and pd.notna(gp):
        add.append(dict(ticker=tk, metric="CostOfGoods", end=end, val=rev - gp,
                        filed=max(F.loc[(tk, end), "Revenue"], F.loc[(tk, end), "GrossProfit"]), src="derived (rule)",
                        basis=basis_gp.get((tk, end), "")))
a = pd.DataFrame(add)
q2 = pd.concat([q, a], ignore_index=True).sort_values(["ticker", "metric", "end"]).reset_index(drop=True)
q2.to_csv(BASE / "clean_06_quarters.csv", index=False)
print("saved clean_06_quarters.csv:", len(q2), "rows (added", len(a), ")\n")
print("ADDED BY THE RULE:"); print(a.groupby(["ticker", "metric"]).size().to_string(), "\n")

P = q2.pivot(index=["ticker", "end"], columns="metric", values="val")
P["margin"] = P["GrossProfit"] / P["Revenue"] * 100
mt = P["margin"].dropna().reset_index()
print("CHECK 1: gross margin % by company (quarters, min, median, max)")
s = mt.groupby("ticker")["margin"].agg(quarters="size", min="min", median="median", max="max").round(1)
print(s.reindex(companies["ticker"]).to_string(), "\n")

low = mt[mt["margin"] < 10].copy(); low["margin"] = low["margin"].round(1)
print("CHECK 2: quarters with gross margin below 10% (expect the 2020 COVID closures):")
print(low.to_string(index=False), "\n")

gp_rep = q2[(q2.metric == "GrossProfit") & (q2.src != "derived (rule)")].set_index(["ticker", "end"])["val"]
cg_rep = q2[(q2.metric == "CostOfGoods") & (q2.src != "derived (rule)")].set_index(["ticker", "end"])["val"]
chk = pd.concat([gp_rep.rename("gp_reported"), (P["Revenue"] - cg_rep).rename("rev_minus_cogs")], axis=1).dropna()
chk["diff_pct"] = (chk["gp_reported"] - chk["rev_minus_cogs"]).abs() / chk["gp_reported"].abs().replace(0, np.nan) * 100
print("CHECK 3: reported gross profit vs revenue minus cost of goods, where both exist (the rule's own test)")
print(chk.groupby("ticker")["diff_pct"].agg(quarters="size", median="median", biggest="max").round(2).to_string(), "\n")

cnt = q2[q2.metric.isin(["Revenue", "CostOfGoods", "GrossProfit"])].groupby(["ticker", "metric"]).size().unstack().reindex(companies["ticker"]).fillna(0).astype(int)
print("CHECK 4: quarters per company after derivation")
print(cnt.to_string())
