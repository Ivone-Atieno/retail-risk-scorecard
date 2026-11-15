# ===== STEP 3: one value per period (earliest-filed; DBI gross profit = latest-filed) =====
df = pd.read_csv(BASE / "clean_02_dates.csv", parse_dates=["start", "end", "filed", "end_raw"])
key = ["ticker", "metric", "tag", "end", "ptype"]
n_before = len(df)

df = df.sort_values(key + ["filed"], kind="stable")
first = df.drop_duplicates(key, keep="first").rename(columns={"val": "val_first", "filed": "filed_first"})
last = (df.drop_duplicates(key, keep="last")[key + ["val", "filed"]]
        .rename(columns={"val": "val_last", "filed": "filed_last"}))
nver = df.groupby(key).size().rename("n_versions").reset_index()
out = first.merge(last, on=key).merge(nver, on=key)

use_last = (out["ticker"] == "DBI") & (out["metric"] == "GrossProfit")   # reclassification restatement
out["val"] = out["val_first"].where(~use_last, out["val_last"])
out["filed"] = out["filed_first"].where(~use_last, out["filed_last"])
out["chg_pct"] = np.where(out["val_first"] != 0, (out["val_last"] / out["val_first"] - 1) * 100, np.nan)

cols = ["ticker", "metric", "tag", "start", "end", "days", "ptype", "val", "filed",
        "val_first", "filed_first", "val_last", "filed_last", "n_versions", "chg_pct", "form", "fy", "fp", "end_raw"]
out = out[[c for c in cols if c in out.columns]].sort_values(["ticker", "metric", "tag", "end", "ptype"]).reset_index(drop=True)
out.to_csv(BASE / "clean_03_asof.csv", index=False)

print("saved clean_03_asof.csv: rows", n_before, "->", len(out))
print("duplicate keys left:", int(out.duplicated(key).sum()), "\n")
print("versions per period:"); print(out["n_versions"].value_counts().sort_index().to_string(), "\n")

prim = set(zip(tm["ticker"], tm["metric"], tm["primary_tag"]))
op = out[[(t, m, g) in prim for t, m, g in zip(out["ticker"], out["metric"], out["tag"])]]
chg = op[op["chg_pct"].abs() > 1]
print("PRIMARY-TAG periods that changed more than 1% between first and last filing (count, largest %):")
print(chg.groupby(["ticker", "metric"])["chg_pct"].agg(periods="size", biggest=lambda s: s.loc[s.abs().idxmax()]).round(2).to_string(), "\n")
print("WMT Revenue periods that changed at all:", int((op[(op.ticker == "WMT") & (op.metric == "Revenue")]["chg_pct"].abs() > 0).sum()))
d = out[use_last & (out["n_versions"] > 1)]
print("DBI GrossProfit exception applied: rows", len(d), "| all use latest value:", bool((d["val"] == d["val_last"]).all()))
