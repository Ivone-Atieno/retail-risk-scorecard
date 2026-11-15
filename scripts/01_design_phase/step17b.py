# ===== STEP 17B: real-time audit of every failed observation, then an uncertainty ledger =====
def rt_obs(r, lc):
    """strict real-time version for one failed observation: only controls whose inputs were public on or before this observation's own public date"""
    pool = D[(D.cal_q == r.cal_q) & D.group.isin(CTRL)]
    A = pool[pool.as_of_date <= r.as_of_date]
    if len(A) < 6: return np.nan, len(A), "fewer than 6 controls public"
    pf, pcs = [], []
    for c, sg in {"gm_chg_yoy": -1, "inv_gap": +1, lc: +1}.items():
        if pd.isna(r[c]): return np.nan, len(A), f"its own {c} is missing"
        vals = A[c].values; valid = ~np.isnan(vals)
        if valid.sum() < 6: return np.nan, len(A), f"fewer than 6 public controls with {c}"
        x = pct(vals[valid], r[c]); pf.append(x if sg > 0 else 1 - x)
        pc = np.full(len(A), np.nan)
        for j in np.where(valid)[0]:
            o = vals[valid & (np.arange(len(A)) != j)]
            if len(o) >= 5:
                y = pct(o, vals[j]); pc[j] = y if sg > 0 else 1 - y
        pcs.append(pc)
    M = np.vstack(pcs); cs = M.mean(axis=0); cs = cs[~np.isnan(M).any(axis=0)]
    if len(cs) < 5: return np.nan, len(A), "fewer than 5 public controls with a full score"
    s0 = np.mean(pf)
    return ((cs < s0).sum() + 0.5 * (cs == s0).sum()) / len(cs), len(A), "ok"

rows = []
for i, r in fo_all.sort_values(["ticker", "end"]).iterrows():
    d = dict(ticker=r.ticker, quarter_end=r.end.date(), public_on=r.as_of_date.date(), distress=r.distress_date.date(),
             m_from_qend=round(r.months_q, 1), m_from_public=round(r.months_avail, 1), _mq=r.months_q, _mp=r.months_avail)
    for lv, lc in LEVS.items():
        nmain = int(ctr_all[(ctr_all.cal_q == r.cal_q) & ctr_all["s_" + lv].notna()].shape[0])
        scored = pd.notna(r["s_" + lv])
        d[f"main_{lv}"] = "yes" if (scored and nmain >= 5) else ("no: own score missing" if not scored else "no: <5 controls")
        d[f"n_ctrl_{lv}"] = nmain
        a, npub, why = rt_obs(r, lc)
        d[f"n_public_{lv}"] = npub; d[f"rt_auc_{lv}"] = round(a, 2) if a == a else np.nan; d[f"rt_{lv}"] = why
    rows.append(d)
AUD = pd.DataFrame(rows)
AUD.drop(columns=["_mq", "_mp"]).to_csv(BASE / "validation_audit.csv", index=False)
print(f"PART 1: audit of all {len(AUD)} failed observations used (3-27 months before distress). saved to validation_audit.csv with both leverage versions")
print("quarter_end = fiscal quarter end; public_on = date the last needed input was first filed (the prediction date); m_from_qend / m_from_public = months from each to the distress date")
print("main_lev2 = counted in the Step 16 AUC (needs its own score and at least 5 same-quarter controls); n_ctrl = same-quarter controls with a score; n_public = of ALL same-quarter controls, how many were public by public_on")
print("rt_auc = strict real-time AUC of that observation; rt_lev2 = why it was or was not computed\n")
show = AUD[["ticker", "quarter_end", "public_on", "distress", "m_from_qend", "m_from_public", "main_lev2", "n_ctrl_lev2", "n_public_lev2", "rt_auc_lev2", "rt_lev2"]]
print(show.to_string(index=False))

print("\nPART 2: samples by horizon. Same fixed score; 'horizon' measured two ways. realtime = strict version (controls restricted to those already public)")
BQ = [("<3", -99, 3), ("3-6", 3, 6), ("6-12", 6, 12), ("12-18", 12, 18), ("18-27+", 18, 99)]
rows = []
for basis, col in [("from quarter end", "_mq"), ("from public date", "_mp")]:
    for bn, lo, hi in BQ:
        x = AUD[(AUD[col] >= lo) & (AUD[col] < hi)]
        if not len(x): continue
        for lv in LEVS:
            ok = x[x[f"main_{lv}"] == "yes"]; rt = x[x[f"rt_{lv}"] == "ok"]
            rows.append(dict(horizon=basis, bin=bn, leverage=lv, failed_obs=len(x), in_main=len(ok), companies_main=ok.ticker.nunique(), in_realtime=len(rt),
                             companies_realtime=rt.ticker.nunique(), median_public_controls=float(x[f"n_public_{lv}"].median())))
print(pd.DataFrame(rows).to_string(index=False))

print("\nPART 3: AUC by horizon measured from the PUBLIC date (the date a user could really have computed the score). main = Step 16 method; realtime = strict. ci_main = two-way bootstrap; ci_realtime resamples failed companies only (too narrow)")
rows = []
for lv in LEVS:
    for bn, lo, hi in BQ:
        x = AUD[(AUD._mp >= lo) & (AUD._mp < hi)]
        if not len(x): continue
        fo = fo_all[(fo_all.months_avail >= lo) & (fo_all.months_avail < hi)]
        m = summarize(prep(fo, ctr_all, "s_" + lv, tick_all), n_all)
        rt = x[x[f"rt_{lv}"] == "ok"].groupby("ticker")[f"rt_auc_{lv}"].mean()
        rows.append(dict(leverage=lv, months_from_public=bn, obs=m.get("obs", 0), companies=m.get("companies", 0), main_auc=m.get("company_mean_auc"), ci_main=m.get("ci95"),
                         rt_obs=int((x[f"rt_{lv}"] == "ok").sum()), rt_companies=len(rt), rt_auc=round(rt.mean(), 3) if len(rt) else np.nan,
                         ci_rt=failed_only_ci(rt.values) if len(rt) > 1 else "n/a"))
print(pd.DataFrame(rows).to_string(index=False))

print("\nPART 4: which controls were eligible? Share of failed observations (3-18 months) for which each control had a score in the same calendar quarter, and was already public by the failed company's public date (lev2)")
rows = []
for t_ in tick_all:
    ct = D[(D.ticker == t_) & D.s_lev2.notna()]; has = pub = 0
    for i, r in fo_s.iterrows():
        z = ct[ct.cal_q == r.cal_q]
        if len(z): has += 1; pub += int((z.as_of_date <= r.as_of_date).any())
    rows.append(dict(control=t_, group=D[D.ticker == t_].group.iloc[0], scored_in_quarter=f"{has / len(fo_s):.0%}", public_in_time=f"{pub / len(fo_s):.0%}"))
print(pd.DataFrame(rows).sort_values(["group", "control"]).to_string(index=False))

print("\nPART 5: evidence ledger. Every comparison uses the SAME fixed score. horizon 3-12 months from quarter end is the main one (the 3-6 and 6-12 cells have only 1 and 2 quarters per company, so they are pooled).")
print("ci95 = two-way bootstrap (resamples failed AND control companies) except size-matched rows, which resample failed companies only. loo = range of the average when each failed company is left out in turn. excludes_0.5 = lower end of the interval is above 0.5\n")
def ledger(label, hz, lv, fo, ref, focal=None, min_w=5):
    focal = fo if focal is None else focal
    s = summarize(prep(focal, ref, "s_" + lv, tick_all), n_all, min_w)
    if not s.get("companies"): return dict(comparison=label, horizon=hz, leverage=lv, obs=0)
    cm = s["_cm"]; v = np.array(list(cm.values()))
    loo = [np.delete(v, k).mean() for k in range(len(v))] if len(v) > 2 else [np.nan]
    lo_ = float(s["ci95"].split(" to ")[0]) if s["ci95"] != "n/a" else np.nan
    return dict(comparison=label, horizon=hz, leverage=lv, obs=s["obs"], companies=s["companies"], auc=s["company_mean_auc"], ci95=s["ci95"],
                above_half=s["above_half"], loo=f"{min(loo):.2f} to {max(loo):.2f}", excludes_half="yes" if lo_ > 0.5 else "no")
def ledger_matched(label, hz, lv, fo, K):
    res = matched(fo, "s_" + lv, K)
    if not res: return dict(comparison=label, horizon=hz, leverage=lv, obs=0)
    df = pd.DataFrame(res); cm = df.groupby("comp").auc.mean(); v = cm.values
    b = [rng.choice(v, len(v)).mean() for _ in range(NBOOT)]; lo_, hi_ = np.percentile(b, [2.5, 97.5])
    loo = [np.delete(v, k).mean() for k in range(len(v))] if len(v) > 2 else [np.nan]
    return dict(comparison=label, horizon=hz, leverage=lv, obs=len(df), companies=len(cm), auc=round(v.mean(), 3), ci95=f"{lo_:.2f} to {hi_:.2f}",
                above_half=f"{int((v > .5).sum())}/{len(v)}", loo=f"{min(loo):.2f} to {max(loo):.2f}", excludes_half="yes" if lo_ > 0.5 else "no")
rows = []
for hz, lo, hi in [("3-12", 3, 12), ("12-18", 12, 18)]:
    fo = D[(D.group == "failed") & (D.months_q >= lo) & (D.months_q < hi)]
    for lv in LEVS:
        rows.append(ledger("failed vs all controls", hz, lv, fo, ctr_all))
        rows.append(ledger("failed vs healthy only", hz, lv, fo, H))
        rows.append(ledger("failed vs under-pressure only", hz, lv, fo, U))
        rows.append(ledger("failed vs UP without BGFV+PLCE (4 cos.)", hz, lv, fo, U[~U.ticker.isin(["BGFV", "PLCE"])], min_w=3))
        rows.append(ledger_matched("failed vs size-matched (within 10x)", hz, lv, fo, 10))
        rows.append(ledger_matched("failed vs size-matched (within 3x)", hz, lv, fo, 3))
        rows.append(ledger("under-pressure vs healthy (same quarters)", hz, lv, fo, H, focal=U[U.cal_q.isin(set(fo.cal_q))]))
L = pd.DataFrame(rows)
print(L.sort_values(["horizon", "leverage"], ascending=[True, True], kind="stable").to_string(index=False))
