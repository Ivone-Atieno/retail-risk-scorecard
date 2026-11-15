import pandas as pd, numpy as np
H = BASE / "heldout_pipeline"
cq = pd.read_csv(H / "clean_quarterly.csv", parse_dates=["end"])
fc = [c for c in cq.columns if c.startswith("f_")]
print("filing-date columns:", fc)
d0 = pd.Timestamp("1970-01-01")
days = cq[fc].apply(lambda s: (pd.to_datetime(s, errors="coerce") - d0).dt.days)
ok = days.notna().any(axis=1)
cq = cq[ok].copy(); days = days[ok]
cq["asof"] = d0 + pd.to_timedelta(days.max(axis=1), unit="D")
cq["lag"] = (cq["asof"] - cq["end"]).dt.days
cq["driver"] = days.idxmax(axis=1)
FAILED = ["PSUN","ARO","HGG","GMAN","BONT","SHLD","CIK1575360","FRED","DEST","PIR","CIK1051251",
          "SSI","JCP","GNC","RTW","ASNA","TLRD","SMRT","FRAN","IMBI","LL","QVCG"]
f = cq[cq.ticker.isin(FAILED)]
def drv(g):
    late = g[g.lag > 135]["driver"]
    return late.value_counts().index[0] if len(late) else ""
t = f.groupby("ticker").apply(lambda g: pd.Series({"quarters": len(g), "median_lag": g.lag.median(),
        "share_over_135": round((g.lag > 135).mean(), 2), "usual_driver_when_late": drv(g)}))
print("\nAS-OF LAG, failed companies, all quarters:"); print(t.to_string())
print("\nSMRT: quarter end and every filing date:")
print(cq[cq.ticker == "SMRT"].sort_values("end").tail(10)[["end"] + fc + ["lag"]].to_string(index=False))
