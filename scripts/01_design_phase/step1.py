# ===== STEP 1: flat "long" table of every fact (all tags, all filings) =====
rows = []
want = cov[cov["metric"].isin(FLOW + BAL)]
for tk in companies["ticker"]:
    facts = load_facts(tk)
    for _, r in want[want["ticker"] == tk].iterrows():
        d = recs_df(facts, r["tag"])
        if d.empty:
            continue
        d = d.copy()
        d["ticker"] = tk; d["metric"] = r["metric"]; d["tag"] = r["tag"]
        d["ptype"] = d["days"].map(ptype)
        rows.append(d)

long_df = pd.concat(rows, ignore_index=True)
keep = ["ticker", "metric", "tag", "start", "end", "days", "ptype", "val", "filed", "form", "fy", "fp"]
long_df = (long_df[[c for c in keep if c in long_df.columns]]
           .sort_values(["ticker", "metric", "tag", "end", "start", "filed"])
           .reset_index(drop=True))
long_df.to_csv(BASE / "clean_01_long.csv", index=False)
print("saved clean_01_long.csv:", len(long_df), "rows\n")

# ---- CHECK 1: rows per company ----
c1 = long_df.groupby("ticker").agg(rows=("val", "size"), tags=("tag", "nunique"),
                                   first_end=("end", "min"), last_end=("end", "max"),
                                   last_filed=("filed", "max"))
print("CHECK 1: rows per company"); print(c1.reindex(companies["ticker"]).to_string(), "\n")

# ---- CHECK 2: metric x period type ----
print("CHECK 2: metric x period type (balance metrics should be all I, flow metrics Q/YTD/A)")
print(pd.crosstab(long_df["metric"], long_df["ptype"]).reindex(FLOW + BAL).fillna(0).astype(int).to_string(), "\n")

# ---- CHECK 3: anything that breaks the pattern ----
bad = long_df[(long_df["metric"].isin(BAL) & (long_df["ptype"] != "I")) |
              (long_df["metric"].isin(FLOW) & (long_df["ptype"].isin(["I", "other"])))]
print("CHECK 3: rows that break the pattern:", len(bad))
if len(bad):
    print(bad.groupby(["ticker", "metric", "ptype", "days"]).size().head(30).to_string())
print()

# ---- CHECK 4: tags in tag_coverage that gave no rows from 2019 on ----
got = set(zip(long_df["ticker"], long_df["tag"]))
miss = [(r["ticker"], r["metric"], r["tag"]) for _, r in want.iterrows()
        if (r["ticker"], r["tag"]) not in got and pd.to_datetime(r["last_end"], errors="coerce") >= pd.Timestamp("2019-01-01")]
print("CHECK 4: tags with data after 2019 that gave no rows:", len(miss))
for m in miss[:20]:
    print("  ", m)
