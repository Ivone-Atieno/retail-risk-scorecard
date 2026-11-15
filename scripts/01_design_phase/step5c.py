# ===== STEP 5c: quarterly values with filing dates, a conflict rule and the DBI basis fix =====
st = pd.read_csv(BASE / "clean_04b_stitched.csv", parse_dates=["start", "end", "filed"])
flows = st[st.metric.isin(FLOW) & st.ptype.isin(["Q", "YTD", "A"])]
DBI_BAD = pd.Timestamp("2023-01-28")     # DBI Q4 FY2022 gross profit: restated annual minus unrestated 9-month = not a real number
DBI_BREAK = pd.Timestamp("2023-04-29")   # first DBI quarter on the restated basis

res, unplaced, recon, dropped = [], [], [], []
for tk in companies["ticker"]:
    grid = sorted(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique())
    if len(grid) < 2:
        continue
    g = pd.DatetimeIndex(grid)

    def gidx(d):
        diff = np.abs((g - d).days); pos = int(diff.argmin())
        return pos if diff[pos] <= 5 else None

    for m in FLOW:
        x = flows[(flows.ticker == tk) & (flows.metric == m)]
        V, VA = {}, {}
        for _, r in x.iterrows():
            i = gidx(r["start"] - pd.Timedelta(days=1)); j = gidx(r["end"])
            if i is None or j is None or j <= i:
                unplaced.append((tk, m, r["ptype"], str(r["start"].date()), str(r["end"].date()))); continue
            V.setdefault((i, j), (r["val"], r["filed"]))
            if r["ptype"] == "A":
                VA.setdefault((i, j), r["val"])
        q = {}

        def cum(a, k):
            if (a, k) in V: return V[(a, k)]
            ks = range(a + 1, k + 1)
            if all(t in q for t in ks):
                return (sum(q[t]["val"] for t in ks), max(q[t]["filed"] for t in ks))
            return None

        for k in range(1, len(g)):
            der = None
            for a in range(k - 2, -1, -1):
                if (a, k) in V:
                    c = cum(a, k - 1)
                    if c is not None:
                        der = (V[(a, k)][0] - c[0], max(V[(a, k)][1], c[1])); break
            rep = V.get((k - 1, k))
            if rep is None and der is None:
                continue
            conflict, other = False, None
            if der is None:
                pick, src = rep, "reported"
            elif rep is None:
                pick, src = der, "derived"
            else:
                pick, src, other = rep, "reported", der
                diff = abs(der[0] - rep[0])
                conflict = (diff > 2e6) and (diff > 0.005 * abs(rep[0]))
                if conflict and not (tk == "DBI" and m == "GrossProfit") and der[1] < rep[1]:
                    pick, src, other = der, "derived (earlier filing wins)", rep
            q[k] = dict(val=pick[0], filed=pick[1], src=src, alt_val=other[0] if other else np.nan,
                        alt_filed=other[1] if other else pd.NaT, conflict=conflict)
        if tk == "DBI" and m == "GrossProfit":
            for k in [k for k in q if g[k] == DBI_BAD]:
                dropped.append((tk, m, str(g[k].date()), round(q[k]["val"] / 1e6, 1))); del q[k]
        for k, v in q.items():
            basis = ("old" if g[k] < DBI_BREAK else "new") if (tk == "DBI" and m == "GrossProfit") else ""
            res.append(dict(ticker=tk, metric=m, end=g[k], val=v["val"], filed=v["filed"], src=v["src"],
                            alt_val=v["alt_val"], alt_filed=v["alt_filed"], conflict=v["conflict"], basis=basis))
        for (a, j), av in VA.items():
            ks = range(a + 1, j + 1)
            if all(t in q for t in ks):
                recon.append(dict(ticker=tk, metric=m, year_end=g[j], annual=av, sum_q=sum(q[t]["val"] for t in ks)))

qdf = pd.DataFrame(res).sort_values(["ticker", "metric", "end"]).reset_index(drop=True)
qdf.to_csv(BASE / "clean_05c_quarters.csv", index=False)
print("saved clean_05c_quarters.csv:", len(qdf), "quarterly values (previous version: 2578)")
print("dropped on purpose:", dropped, "| rows with no filing date:", int(qdf["filed"].isna().sum()), "\n")

print("CHECK 1: source of each quarterly value")
print(pd.crosstab(qdf["metric"], qdf["src"]).reindex(FLOW).fillna(0).astype(int).to_string(), "\n")

cf = qdf[qdf["conflict"]].copy()
print("CHECK 2: reported vs rebuilt disagree by more than 0.5% and $2m:", len(cf))
if len(cf):
    cf["val_m"] = (cf["val"] / 1e6).round(1); cf["other_m"] = (cf["alt_val"] / 1e6).round(1)
    print(cf[["ticker", "metric", "end", "src", "val_m", "other_m", "filed", "alt_filed"]].to_string(index=False))
print()

rc = pd.DataFrame(recon)
if len(rc):
    rc["diff_pct"] = (rc.sum_q - rc.annual).abs() / rc.annual.abs().replace(0, np.nan) * 100
    print("CHECK 3: four quarters vs annual:", len(rc), "years tested; over 0.5%:", int((rc.diff_pct > 0.5).sum()))
    bad = rc[rc.diff_pct > 0.5].sort_values("diff_pct", ascending=False)
    if len(bad):
        print(bad.assign(annual_m=(bad.annual / 1e6).round(1), sum_m=(bad.sum_q / 1e6).round(1), diff_pct=bad.diff_pct.round(2))
              [["ticker", "metric", "year_end", "annual_m", "sum_m", "diff_pct"]].to_string(index=False))
else:
    print("CHECK 3: no complete years to test")
print()

co = pd.read_csv(BASE / "companies.csv", parse_dates=["distress_date"])
rows = []
for _, r in co[co["group"] == "failed"].iterrows():
    z = qdf[qdf.ticker == r.ticker]
    late = z[z.filed > r.distress_date]
    rows.append(dict(ticker=r.ticker, distress=r.distress_date.date(), quarter_values=len(z),
                     filed_after_distress=len(late), quarter_ends_affected=late["end"].nunique(),
                     last_usable_end=z[z.filed <= r.distress_date]["end"].max().date()))
print("CHECK 4: what the as-of filter will remove for the failed companies")
print(pd.DataFrame(rows).to_string(index=False))
print("\nrows that could not be placed on the quarter grid:", len(unplaced), "(reasons were shown in Step 5b)")
