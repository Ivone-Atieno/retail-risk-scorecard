# ===== STEP 5: quarterly values (reported quarters, or differenced from year-to-date / annual) =====
st = pd.read_csv(BASE / "clean_04b_stitched.csv", parse_dates=["start", "end", "filed"])
flows = st[st.metric.isin(FLOW) & st.ptype.isin(["Q", "YTD", "A"])]

res, unassigned, recon = [], [], []
for tk in companies["ticker"]:
    grid = sorted(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique())
    if len(grid) < 2:
        continue
    g = pd.DatetimeIndex(grid)

    def gidx(d):
        """position of the balance-sheet date nearest to d (within 5 days), else None"""
        diff = np.abs((g - d).days)
        pos = int(diff.argmin())
        return pos if diff[pos] <= 5 else None

    for m in FLOW:
        x = flows[(flows.ticker == tk) & (flows.metric == m)]
        V, VA = {}, {}
        for _, r in x.iterrows():
            i = gidx(r["start"] - pd.Timedelta(days=1)); j = gidx(r["end"])
            if i is None or j is None or j <= i:
                unassigned.append((tk, m, r["ptype"], str(r["start"].date()), str(r["end"].date()))); continue
            V.setdefault((i, j), r["val"])
            if r["ptype"] == "A":
                VA.setdefault((i, j), r["val"])
        q, src, alt = {}, {}, {}

        def cum(a, k):
            if (a, k) in V: return V[(a, k)]
            ks = range(a + 1, k + 1)
            return sum(q[t] for t in ks) if all(t in q for t in ks) else None

        for k in range(1, len(g)):
            derived = None
            for a in range(k - 2, -1, -1):
                if (a, k) in V:
                    c = cum(a, k - 1)
                    if c is not None:
                        derived = V[(a, k)] - c; break
            if (k - 1, k) in V:
                q[k] = V[(k - 1, k)]; src[k] = "reported"; alt[k] = derived
            elif derived is not None:
                q[k] = derived; src[k] = "derived"
        for k in q:
            res.append(dict(ticker=tk, metric=m, end=g[k], val=q[k], src=src[k], val_alt=alt.get(k)))
        for (a, j), av in VA.items():
            ks = range(a + 1, j + 1)
            if all(t in q for t in ks):
                recon.append(dict(ticker=tk, metric=m, year_end=g[j], annual=av, sum_q=sum(q[t] for t in ks)))

qdf = pd.DataFrame(res).sort_values(["ticker", "metric", "end"]).reset_index(drop=True)
qdf.to_csv(BASE / "clean_05_quarters.csv", index=False)
print("saved clean_05_quarters.csv:", len(qdf), "quarterly values\n")

print("CHECK 1: where the quarterly values came from")
print(pd.crosstab(qdf["metric"], qdf["src"]).reindex(FLOW).fillna(0).astype(int).to_string(), "\n")

cmp_ = qdf[(qdf.src == "reported") & qdf.val_alt.notna()].copy()
cmp_["diff_pct"] = (cmp_["val_alt"] - cmp_["val"]).abs() / cmp_["val"].abs().replace(0, np.nan) * 100
print("CHECK 2: reported quarter vs the same quarter rebuilt by differencing (should agree)")
s2 = cmp_.groupby("metric")["diff_pct"].agg(compared="size", median="median", over_0_5pct=lambda s: int((s > 0.5).sum()), biggest="max").round(2)
print(s2.reindex(FLOW).to_string())
big = cmp_[cmp_.diff_pct > 0.5].sort_values("diff_pct", ascending=False).head(12)
if len(big):
    big = big.assign(val_m=(big.val / 1e6).round(1), rebuilt_m=(big.val_alt / 1e6).round(1), diff_pct=big.diff_pct.round(2))
    print(big[["ticker", "metric", "end", "val_m", "rebuilt_m", "diff_pct"]].to_string(index=False))
print()

rc = pd.DataFrame(recon)
if len(rc):
    rc["diff_pct"] = (rc.sum_q - rc.annual).abs() / rc.annual.abs().replace(0, np.nan) * 100
    print("CHECK 3: four quarters added up vs the reported annual figure:", len(rc), "years tested;",
          "over 0.5%:", int((rc.diff_pct > 0.5).sum()))
    bad = rc[rc.diff_pct > 0.5].sort_values("diff_pct", ascending=False).head(12)
    if len(bad):
        print(bad.assign(annual_m=(bad.annual / 1e6).round(1), sum_m=(bad.sum_q / 1e6).round(1), diff_pct=bad.diff_pct.round(2))
              [["ticker", "metric", "year_end", "annual_m", "sum_m", "diff_pct"]].to_string(index=False))
print()

ngrid = {tk: max(len(st[(st.ticker == tk) & (st.metric == "CurrAssets")]["end"].unique()) - 1, 0) for tk in companies["ticker"]}
holes = pd.DataFrame({m: {tk: ngrid[tk] - int(((qdf.ticker == tk) & (qdf.metric == m)).sum()) for tk in companies["ticker"]} for m in FLOW})
print("CHECK 4: quarters with NO value, per company and metric (grid = balance-sheet dates after the first)")
print(holes.to_string(), "\n")
print("CHECK 5: flow rows that could not be placed on the quarter grid:", len(unassigned))
for u in unassigned[:15]:
    print("  ", u)
