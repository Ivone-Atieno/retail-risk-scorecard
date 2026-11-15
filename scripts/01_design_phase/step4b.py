# ===== STEP 4b: fallback tags for the gaps found in Step 4 =====
df = pd.read_csv(BASE / "clean_03_asof.csv", parse_dates=["start", "end", "filed", "filed_first", "filed_last", "end_raw"])
st = pd.read_csv(BASE / "clean_04_stitched.csv", parse_dates=["start", "end", "filed", "filed_first", "filed_last", "end_raw"])
st["fallback"] = False

PLCE_EQ = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
FALLBACK = {("PLCE", "CostOfGoods"): "CostOfGoodsSold",
            ("PLCE", "Equity"): PLCE_EQ,
            ("DBI", "NetIncome"): "ProfitLoss",
            ("RAD", "Capex"): "PaymentsToAcquireProductiveAssets",
            ("PRTY", "Equity"): PLCE_EQ,
            ("EXPR", "CostOfGoods"): "CostOfGoodsAndServicesSold"}

report, adds = [], []
for (tk, m), alt in FALLBACK.items():
    cur = st[(st.ticker == tk) & (st.metric == m)]
    a = df[(df.ticker == tk) & (df.metric == m) & (df.tag == alt)]
    both = cur.merge(a, on=["end", "ptype"], suffixes=("", "_alt"))
    nover = len(both)
    mx = (((both["val_alt"] / both["val"]) - 1).abs() * 100).max() if nover else np.nan
    have = set(zip(cur["end"], cur["ptype"]))
    cand = a[[(e, p) not in have for e, p in zip(a["end"], a["ptype"])]].copy()
    ok = (nover == 0) or (mx <= 1.0)
    note = ("verified (agrees within 1%)" if nover and mx <= 1.0 else
            "unverified (no overlap to test)" if nover == 0 else "REJECTED (differs by more than 1%)")
    report.append(dict(ticker=tk, metric=m, alt_tag=alt[:45], overlap=nover,
                       max_diff_pct=round(mx, 2) if nover else "", candidates=len(cand), decision=note))
    if ok and len(cand):
        cand["tag_used"] = alt; cand["stitched"] = True; cand["fallback"] = True
        adds.append(cand)

print("FALLBACK DECISIONS:"); print(pd.DataFrame(report).to_string(index=False), "\n")
st2 = pd.concat([st] + adds, ignore_index=True).sort_values(["ticker", "metric", "end", "ptype"]).reset_index(drop=True)
st2.to_csv(BASE / "clean_04b_stitched.csv", index=False)
print("saved clean_04b_stitched.csv:", len(st2), "rows (added", int(st2["fallback"].sum()), "fallback rows)")
print("duplicate keys:", int(st2.duplicated(["ticker", "metric", "end", "ptype"]).sum()))
print("\nFilled periods:")
print(st2[st2["fallback"]][["ticker", "metric", "end", "ptype", "val"]].to_string(index=False))
