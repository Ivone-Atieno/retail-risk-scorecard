# ===== STEP 4: one tag per company/metric (stitch by priority) =====
df = pd.read_csv(BASE / "clean_03_asof.csv", parse_dates=["start", "end", "filed", "filed_first", "filed_last", "end_raw"])

STITCH = {
    ("PLCE", "Revenue"):   ["RevenueFromContractWithCustomerExcludingAssessedTax",
                            "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues", "SalesRevenueNet"],
    ("PRTY", "Revenue"):   ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                            "RevenueFromContractWithCustomerIncludingAssessedTax"],
    ("PLCE", "NetIncome"): ["NetIncomeLoss", "ProfitLoss"],
    ("PLCE", "Capex"):     ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    ("WOOF", "Equity"):    ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
}
DERIVE_ALL = {("COST", "GrossProfit"), ("DBI", "CostOfGoods")}   # always derived (Step 8), reported tag not used

parts, gaps = [], []
for tk in companies["ticker"]:
    for m in FLOW + BAL:
        if (tk, m) in DERIVE_ALL:
            continue
        prio = STITCH.get((tk, m)) or [primary(tk, m)]
        prio = [p for p in prio if p]
        if not prio:
            continue
        sub = df[(df.ticker == tk) & (df.metric == m)]
        use = sub[sub.tag.isin(prio)].copy()
        use["rank"] = use["tag"].map({p: i for i, p in enumerate(prio)})
        use = use.sort_values(["end", "ptype", "rank"]).drop_duplicates(["end", "ptype"], keep="first")
        use["tag_used"] = use["tag"]
        use["stitched"] = use["rank"] > 0
        parts.append(use.drop(columns=["rank"]))
        # periods that exist under some OTHER tag but are empty in the chosen series
        have = set(zip(use["end"], use["ptype"]))
        oth = sub[~sub.tag.isin(prio)]
        miss = oth[[(e, p) not in have for e, p in zip(oth["end"], oth["ptype"])]]
        if len(miss):
            gaps.append(dict(ticker=tk, metric=m, periods=miss[["end", "ptype"]].drop_duplicates().shape[0],
                             other_tags=", ".join(sorted(miss["tag"].unique()))[:80]))

st = pd.concat(parts, ignore_index=True).sort_values(["ticker", "metric", "end", "ptype"]).reset_index(drop=True)
st.to_csv(BASE / "clean_04_stitched.csv", index=False)
print("saved clean_04_stitched.csv:", len(st), "rows (from", len(df), ")")
print("duplicate (company, metric, end, type) keys:", int(st.duplicated(["ticker", "metric", "end", "ptype"]).sum()), "\n")

print("STITCHED SERIES: rows taken from each tag")
for (tk, m) in STITCH:
    print(f"  {tk} {m}:", st[(st.ticker == tk) & (st.metric == m)]["tag_used"].value_counts().to_dict())
print()
print("PERIODS PRESENT UNDER ANOTHER TAG BUT EMPTY IN THE CHOSEN SERIES (possible fills, to review):")
print(pd.DataFrame(gaps).to_string(index=False) if gaps else "  none")
