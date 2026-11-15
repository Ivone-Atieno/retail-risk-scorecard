# ===== STEP 18: as-of-date scoring. A real-time test of the SAME fixed score, and the live scores. Run after the Step 17 setup cell (and 17A, for failed_only_ci). =====
from scipy.stats import spearmanr
MAXSTALE = 135       # days. A company's latest public quarter may be at most this old on the scoring date, otherwise it is not used
LIVE_DATE = None     # for the live scores: None = latest public date in the data, or a date such as "2026-10-19"
CT = D[D.group.isin(CTRL)]
SIG = {"gm_chg_yoy": -1, "inv_gap": +1}

def latest_rows(t, pool):
    """for each company: its most recent quarter (by quarter end) whose inputs were ALL public on or before date t, if that quarter is not older than MAXSTALE days"""
    x = pool[pool.as_of_date <= t].sort_values(["ticker", "end"]).groupby("ticker").tail(1)
    return x[(t - x.end).dt.days <= MAXSTALE]

def score_set(t, lc, focal=None):
    """scores on date t. Reference = every control's latest public quarter. Same score as before: mean of direction-adjusted percentiles of gm, inventory gap and one leverage signal.
    returns (score of focal or nan, Series of control scores by ticker, DataFrame of control percentiles by signal)"""
    L = latest_rows(t, CT).set_index("ticker"); sigs = {**SIG, lc: +1}; ctl = {}
    for c, sg in sigs.items():
        res = {}
        for tk in L.index:
            if pd.isna(L.at[tk, c]): continue
            o = L[c].drop(tk).dropna()
            if len(o) >= 5:
                x = pct(o.values, L.at[tk, c]); res[tk] = x if sg > 0 else 1 - x
        ctl[c] = pd.Series(res, dtype=float)
    ctl = pd.DataFrame(ctl, index=L.index)
    cs = ctl.mean(axis=1, skipna=False).dropna()
    fs = np.nan
    if focal is not None:
        ps = []
        for c, sg in sigs.items():
            v = L[c].drop(focal["ticker"], errors="ignore").dropna().values
            if pd.isna(focal[c]) or len(v) < 5: ps = None; break
            x = pct(v, focal[c]); ps.append(x if sg > 0 else 1 - x)
        if ps: fs = float(np.mean(ps))
    return fs, cs, ctl

idx = {t: k for k, t in enumerate(tick_all)}
PR = {lv: [] for lv in LEVS}; rows = []
for i, r in fo_all.sort_values(["ticker", "end"]).iterrows():
    d = dict(ticker=r.ticker, quarter_end=r.end.date(), public_on=r.as_of_date.date(), m_from_public=round(r.months_avail, 1))
    for lv, lc in LEVS.items():
        fs, cs, _ = score_set(r.as_of_date, lc, r)
        d[f"asof_score_{lv}"] = round(fs, 3) if fs == fs else np.nan; d[f"samequarter_score_{lv}"] = round(r["s_" + lv], 3) if pd.notna(r["s_" + lv]) else np.nan
        d[f"n_ctrl_{lv}"] = len(cs)
        if fs == fs and len(cs) >= 5:
            PR[lv].append(dict(comp=r.ticker, s=fs, rs=cs.values, ri=np.array([idx[t] for t in cs.index]), tk=np.array(cs.index), mp=r.months_avail, key=i))
    rows.append(d)
AS = pd.DataFrame(rows); AS.to_csv(BASE / "asof_audit.csv", index=False)

print("PART 1: does the as-of engine reproduce the earlier score? (failed observations 3-27 months before distress)")
for lv in LEVS:
    x = AS.dropna(subset=[f"asof_score_{lv}", f"samequarter_score_{lv}"])
    print(f"  {lv}: scored as-of {int(AS[f'asof_score_{lv}'].notna().sum())} | scored same-quarter {int(AS[f'samequarter_score_{lv}'].notna().sum())} | both {len(x)} | "
          f"rank correlation {spearmanr(x[f'asof_score_{lv}'], x[f'samequarter_score_{lv}'])[0]:.2f} | mean absolute difference {np.abs(x[f'asof_score_{lv}'] - x[f'samequarter_score_{lv}']).mean():.3f}")
print("  controls available per observation (lev2): median", int(AS.n_ctrl_lev2.median()), "min", int(AS.n_ctrl_lev2.min()), "max", int(AS.n_ctrl_lev2.max()))
avail = {t: 0 for t in tick_all}
for o in PR["lev2"]:
    for t in o["tk"]: avail[t] += 1
print("  share of scored observations in which each control was available (lev2):", {t: f"{v / max(len(PR['lev2']), 1):.0%}" for t, v in avail.items()})

def subset(pr, tickers):
    out = []
    for o in pr:
        m = np.isin(o["tk"], list(tickers))
        out.append(dict(o, rs=o["rs"][m], ri=o["ri"][m], tk=o["tk"][m]))
    return out
BQ = [("<3", -99, 3), ("3-6", 3, 6), ("6-12", 6, 12), ("12-18", 12, 18), ("18-27+", 18, 99)]
print("\nPART 2: AUC by horizon, measured from the date the score could first be computed. every control = its latest public quarter on that date; no same-calendar-quarter alignment")
print("ci95 = two-way bootstrap (failed AND control companies resampled)\n")
rows = []
for lv in LEVS:
    for bn, lo, hi in BQ:
        ent = [o for o in PR[lv] if lo <= o["mp"] < hi]
        if not ent: continue
        s = summarize(ent, n_all)
        rows.append(dict(leverage=lv, months=bn, obs=s.get("obs", 0), companies=s.get("companies", 0), auc=s.get("company_mean_auc"), ci95=s.get("ci95"), above_half=s.get("above_half"),
                         median_controls=int(np.median([len(o["rs"]) for o in ent]))))
print(pd.DataFrame(rows).to_string(index=False))

print("\nPART 3: ledger, same scores, different comparison groups. 3-12 months and 12-18 months from the public date. groups need at least 4 available controls on the date")
def led(label, hz, lv, ent, min_w):
    s = summarize(ent, n_all, min_w)
    if not s.get("companies"): return dict(comparison=label, horizon=hz, leverage=lv, obs=0)
    v = np.array(list(s["_cm"].values())); loo = [np.delete(v, k).mean() for k in range(len(v))] if len(v) > 2 else [np.nan]
    lo_ = float(s["ci95"].split(" to ")[0]) if s["ci95"] != "n/a" else np.nan
    return dict(comparison=label, horizon=hz, leverage=lv, obs=s["obs"], companies=s["companies"], auc=s["company_mean_auc"], ci95=s["ci95"], above_half=s["above_half"],
                loo=f"{min(loo):.2f} to {max(loo):.2f}", excludes_half="yes" if lo_ > 0.5 else "no")
hl, ul = set(H.ticker), set(U.ticker)
def up_entries(lv, lc, lo, hi):
    """under-pressure companies scored the same way at their own public dates (their own value excluded from the reference), compared with healthy controls only. Calendar quarters taken from the failed observations in the same horizon window"""
    qs_hz = set(fo_all[(fo_all.months_avail >= lo) & (fo_all.months_avail < hi)].cal_q); out = []
    for i, r in U[U.cal_q.isin(qs_hz)].iterrows():
        fs, cs, _ = score_set(r.as_of_date, lc, r)
        if fs == fs and len(cs) >= 5: out.append(dict(comp=r.ticker, s=fs, rs=cs.values, ri=np.array([idx[t] for t in cs.index]), tk=np.array(cs.index), mp=0, key=i))
    return subset(out, hl)
rows = []
for hz, lo, hi in [("3-12", 3, 12), ("12-18", 12, 18)]:
    for lv, lc in LEVS.items():
        ent = [o for o in PR[lv] if lo <= o["mp"] < hi]
        rows.append(led("failed vs all controls", hz, lv, ent, 5))
        rows.append(led("failed vs healthy only", hz, lv, subset(ent, hl), 4))
        rows.append(led("failed vs under-pressure only", hz, lv, subset(ent, ul), 4))
        rows.append(led("under-pressure vs healthy (as-of)", hz, lv, up_entries(lv, lc, lo, hi), 4))
print(pd.DataFrame(rows).to_string(index=False))
print("\nPART 4: each failed company, as-of method (all scored observations 3-18 months from the public date; auc = average of its observation AUCs against all available controls)")
rows = []
for lv in LEVS:
    ent = [o for o in PR[lv] if 3 <= o["mp"] < 18]
    cm, rr = comp_auc(ent, np.ones(n_all))
    for c in sorted(cm): rows.append(dict(leverage=lv, company=c, obs=len(rr[c]), auc=round(cm[c], 2), min=round(min(rr[c]), 2), max=round(max(rr[c]), 2)))
print(pd.DataFrame(rows).to_string(index=False))

print("\nPART 5: LIVE SCORES. Not a validated forecast. These are relative stress rankings against the other 11 controls' latest public quarters.")
t_live = pd.Timestamp(LIVE_DATE) if LIVE_DATE else D.as_of_date.max()
print("scoring date:", t_live.date(), "| each company's latest public quarter must be no older than", MAXSTALE, "days")
Lr = latest_rows(t_live, CT).set_index("ticker")
_, cs2, c2 = score_set(t_live, "lev2_chg_yoy"); _, cs3, c3 = score_set(t_live, "lev3_chg_yoy")
live = pd.DataFrame({"group": Lr.group, "quarter_end": Lr.end.dt.date, "public_on": Lr.as_of_date.dt.date, "age_days": (t_live - Lr.end).dt.days,
                     "raw_gm": Lr.gm_chg_yoy.round(1), "raw_inv": Lr.inv_gap.round(1), "raw_lev2": Lr.lev2_chg_yoy.round(3), "raw_lev3": Lr.lev3_chg_yoy.round(1),
                     "p_gm": c2["gm_chg_yoy"], "p_inv": c2["inv_gap"], "p_lev2": c2["lev2_chg_yoy"], "p_lev3": c3["lev3_chg_yoy"], "s_lev2": cs2, "s_lev3": cs3}).round(2)
live["rank_lev2"] = live.s_lev2.rank(ascending=False, method="min"); live["rank_lev3"] = live.s_lev3.rank(ascending=False, method="min")
print(live.sort_values("s_lev2", ascending=False).to_string())
missing = [t for t in tick_all if t not in Lr.index]
print("not scored (no public quarter within the age limit):", missing if missing else "none")
for lv in LEVS:
    z = [o["s"] for o in PR[lv] if 3 <= o["mp"] < 12]
    if z: print(f"context, {lv}: failed companies' own scores 3-12 months before distress (as-of): 25th / median / 75th percentile = {np.percentile(z, 25):.2f} / {np.median(z):.2f} / {np.percentile(z, 75):.2f}  (n={len(z)})")
print("caveats: relative ranking among 12 retailers, not a probability. Quarters ending in 2026 may contain tariff-refund effects (verified for TGT and ROST only). BGFV lev3 is blank when last year's debt was zero.")
live.to_csv(BASE / "live_scores.csv")
