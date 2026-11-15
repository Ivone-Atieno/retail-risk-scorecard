# ===== STEP 45: EXTRAS FOR THE REPORT (read-only). Per-observation export, false positives, decision view, live scores + forward-test ledger. =====
# This script does NOT re-run or change the frozen test. It reuses the frozen test's own data preparation and comparison-set logic (copied unchanged),
# checks the protocol hash, reconciles its company-mean AUC with the saved primary.csv, and writes ONLY to heldout/extras/ and heldout/forward_test/.
# Everything it produces is DESCRIPTIVE. Nothing here is a new test, nothing is tuned, and the cutoffs below were fixed before the run.
import hashlib, datetime
import numpy as np, pandas as pd
from pathlib import Path
pd.set_option("display.width", 230); pd.set_option("display.max_columns", 40)
BASE = Path(globals().get("BASE", "/content/drive/MyDrive/retail_risk_project"))
CT = Path(globals().get("CT", BASE / "heldout" / "controls"))
HO = Path(CT).parent; HP = BASE / "heldout_pipeline"; TR = HO / "test_results"
OUT = HO / "extras"; OUT.mkdir(exist_ok=True); FWD = HO / "forward_test"; FWD.mkdir(exist_ok=True)
SEED, NBOOT, MAXSTALE, MINCTL, MINREF, FLOOR = 20261102, 2000, 135, 3, 5, 12
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
CUTOFFS = [0.5, 0.6, 0.7, 0.8]          # fixed in advance for the decision view
TOPSHARES = [0.10, 0.20, 0.30]          # fixed in advance: flag the top 10 / 20 / 30 percent of a comparison set

# ---- 0. the protocol on disk must still be the frozen one (read-only check)
pmd = HO / "heldout_protocol_v1_3.md"; psh = HO / "heldout_protocol_v1_3.sha256"
hnow = hashlib.sha256(pmd.read_bytes()).hexdigest(); hsaved = psh.read_text().split()[0]
print("PROTOCOL CHECK: match:", hnow == hsaved, "| hash", hnow[:16] + "...")
if hnow != hsaved: raise RuntimeError("the protocol file is not the frozen v1.3: stop")

# ---- 1. data
F = pd.read_csv(HP / "features_heldout.csv", parse_dates=["end", "as_of_date", "distress_date"])
Q = pd.read_csv(HP / "clean_quarterly.csv", parse_dates=["end"])[["ticker", "end", "Debt"]]
Qp = Q.rename(columns={"end": "end_py", "Debt": "Debt_py"}).sort_values("end_py"); F["end_prev"] = F["end"] - pd.Timedelta(days=364)
F = pd.merge_asof(F.sort_values("end_prev"), Qp, left_on="end_prev", right_on="end_py", by="ticker", tolerance=pd.Timedelta(days=15), direction="nearest")
F = F.merge(Q, on=["ticker", "end"], how="left").sort_values(["ticker", "end"]).reset_index(drop=True)
F["debt_both"] = (F["Debt"] > 0) & (F["Debt_py"] > 0)
SIG = {"gm_chg_yoy": -1, "inv_gap": +1, "lev2_chg_yoy": +1, "lev3_chg_yoy": +1}
F.loc[F.cal_q.isin(WIN_B), list(SIG)] = np.nan          # frozen COVID treatment
F["size_risk"] = -np.log(F["ttm_rev"].where(F["ttm_rev"] > 0))
FR = pd.read_csv(CT / "controls_final.csv"); NEWF = set(FR[FR.status == "NEW FAILED"].ticker)
REF = F[F.group.isin(["healthy", "under_pressure"])]; REF_T = sorted(REF.ticker.unique())
print("reference (design controls):", REF_T, "| held-out controls kept:", F[(F.group == "ho_control") & ~F.excluded_control].ticker.nunique(), "| held-out failed:", F[F.group == "ho_failed"].ticker.nunique(), "| of which found by the control-universe scan (their early quarters may serve as controls):", sorted(NEWF))
def cut(d): return "pre-2019" if d < pd.Timestamp("2019-01-01") else ("2019" if d < pd.Timestamp("2020-01-01") else ("2020 to Jan 2021" if d < pd.Timestamp("2021-02-01") else "later"))
def pct(v, x): return ((v < x).sum() + 0.5 * (v == x).sum()) / len(v)

def latest(pool, t):
    x = pool[pool.as_of_date <= t].sort_values(["ticker", "end"]).groupby("ticker").tail(1)
    return x[(t - x.end).dt.days <= MAXSTALE]
_ref_cache = {}
def ref_at(t):
    if t not in _ref_cache: _ref_cache[t] = latest(REF, t).set_index("ticker")
    return _ref_cache[t]
def pcts(t, rows):
    """direction-adjusted percentiles of each row against the reference on date t (a reference company's own value is left out); NaN if fewer than 5 reference values"""
    R = ref_at(t); out = {}
    for c, sg in SIG.items():
        res = []
        for _, r in rows.iterrows():
            v = R[c].drop(r.ticker, errors="ignore").dropna().values
            if pd.isna(r[c]) or len(v) < MINREF: res.append(np.nan); continue
            x = pct(v, r[c]); res.append(x if sg > 0 else 1 - x)
        out["p_" + c] = res
    P = pd.DataFrame(out, index=rows.index)
    for lv in ("lev2", "lev3"):
        P["s_" + lv] = np.where(P[["p_gm_chg_yoy", "p_inv_gap", f"p_{lv}_chg_yoy"]].notna().all(axis=1), P[["p_gm_chg_yoy", "p_inv_gap", f"p_{lv}_chg_yoy"]].mean(axis=1), np.nan)
    return P

# ---- 2. every failed observation 3-27 months before the event (public date to event) and its comparison sets
CTL = F[(F.group == "ho_control") & ~F.excluded_control].assign(kind="control")
EARLY = F[F.ticker.isin(NEWF)].assign(kind="early")           # time-varying labels (protocol section 5)
POOL = pd.concat([CTL, EARLY]); FO = F[(F.group == "ho_failed") & F.as_of_date.notna() & (F.months_avail >= 3) & (F.months_avail < 27.01)].copy()
FO["cut"] = FO.distress_date.map(cut); FO["year"] = FO.distress_date.dt.year
FOCAL = {}
for i, r in FO.iterrows():
    t = r.as_of_date; P = pcts(t, FO.loc[[i]])
    L = latest(POOL, t); L = L[L.ticker != r.ticker]
    L = L[~((L.kind == "early") & ~(L.months_avail > 27.01))]
    PN = pcts(t, L); N = pd.concat([L[["ticker", "end", "kind", "ttm_rev", "size_risk", "debt_both", "gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"]], PN], axis=1)
    D = latest(REF, t); D = D[D.ticker != r.ticker]; PD = pcts(t, D)
    ND = pd.concat([D[["ticker", "end", "ttm_rev", "size_risk", "debt_both"]], PD], axis=1)
    FOCAL[i] = dict(row=r, p=P.iloc[0], neg=N, des=ND)
print(f"failed observations 3-27 months before the event: {len(FO)} in {FO.ticker.nunique()} companies\n")


# ---- 3. same comparison sets as the frozen test
def build(lv, lo=3, hi=12, size=3, pool="all", sub=False, comps=None, against="held-out"):
    """one entry per failed observation: the failed company, its event year, the control-company ids and per-control indicators (score below the failed company's: 1, tie: 0.5)"""
    obs = []; ids = {}
    for i, d in FOCAL.items():
        r = d["row"]
        if not (lo <= r.months_avail < hi): continue
        if comps is not None and r.ticker not in comps: continue
        s0 = d["p"]["s_" + lv]
        if pd.isna(s0): continue
        if sub and not r.debt_both: continue
        N = (d["des"] if against == "design" else d["neg"]).copy()
        if against != "design" and pool == "controls_only": N = N[N.kind == "control"]
        N = N[N["s_" + lv].notna()]
        if sub: N = N[N.debt_both]
        if size and pd.notna(r.ttm_rev):
            ratio = N.ttm_rev / r.ttm_rev; N = N[(ratio >= 1 / size) & (ratio <= size)]
        elif size: continue
        need = MINREF if against == "design" else MINCTL
        if len(N) < need: continue
        ci = np.array([ids.setdefault(t_, len(ids)) for t_ in N.ticker])
        ind = lambda a, b: ((a < b).astype(float) + 0.5 * (a == b)).values
        lc = f"p_{lv}_chg_yoy"
        obs.append(dict(comp=r.ticker, year=int(r.year), cut=r.cut, key=i, s0=s0, ci=ci, ind=ind(N["s_" + lv], s0), ind_size=ind(N.size_risk, r.size_risk) if pd.notna(r.size_risk) else np.full(len(N), np.nan),
                        ind_gm=ind(N.p_gm_chg_yoy, d["p"]["p_gm_chg_yoy"]), ind_inv=ind(N.p_inv_gap, d["p"]["p_inv_gap"]), ind_lev=ind(N[lc], d["p"][lc]), ctl_scores=N["s_" + lv].values, ctl_t=N.ticker.values, ctl_end=N.end.values))
    return obs, len(ids)

def cmeans(obs, W, key="ind", minw=MINCTL):
    rows = {}
    for o in obs:
        w = W[o["ci"]]; sw = w.sum()
        if sw >= minw and not np.isnan(o[key]).any(): rows.setdefault(o["comp"], []).append((w * o[key]).sum() / sw)
    return {c: float(np.mean(v)) for c, v in rows.items()}, rows


# ---- 4. integrity: this script must reproduce the frozen primary result before anything is exported
PRIM = {lv: build(lv) for lv in ("lev2", "lev3")}
chk = {}
for lv in ("lev2", "lev3"):
    cm, rr = cmeans(PRIM[lv][0], np.ones(PRIM[lv][1])); chk[lv] = (float(np.mean(list(cm.values()))), len(cm))
if (TR / "primary.csv").exists():
    P0 = pd.read_csv(TR / "primary.csv").set_index("leverage")
    for lv in ("lev2", "lev3"):
        ok = abs(chk[lv][0] - float(P0.loc[lv, "auc"])) < 0.0006 and chk[lv][1] == int(P0.loc[lv, "companies"])
        print(f"RECONCILE {lv}: this script {chk[lv][0]:.3f} on {chk[lv][1]} companies | frozen primary.csv {float(P0.loc[lv, 'auc']):.3f} on {int(P0.loc[lv, 'companies'])} | {'OK' if ok else 'MISMATCH'}")
        if not ok: raise RuntimeError("does not reproduce the frozen primary result: stop and tell the analyst")
else: print("primary.csv not found: reconciliation skipped")

# ---- 5. EXPORT A: one row per failed observation (3-27 months before the event)
ALL = {lv: {o["key"]: o for o in build(lv, lo=3, hi=27.01)[0]} for lv in ("lev2", "lev3")}
rows = []
for i, d in FOCAL.items():
    r, p = d["row"], d["p"]; rec = dict(ticker=r.ticker, event_date=r.distress_date.date(), event_year=int(r.year), event_cut=r.cut, quarter_end=r.end.date(), public_on=r.as_of_date.date(),
                                         months_before_event=round(r.months_avail, 1), in_primary_window=bool(3 <= r.months_avail < 12),
                                         raw_gm_chg=round(r.gm_chg_yoy, 3) if pd.notna(r.gm_chg_yoy) else np.nan, raw_inv_gap=round(r.inv_gap, 3) if pd.notna(r.inv_gap) else np.nan,
                                         raw_lev2=round(r.lev2_chg_yoy, 4) if pd.notna(r.lev2_chg_yoy) else np.nan, raw_lev3=round(r.lev3_chg_yoy, 2) if pd.notna(r.lev3_chg_yoy) else np.nan,
                                         p_gm=p["p_gm_chg_yoy"], p_inv=p["p_inv_gap"], p_lev2=p["p_lev2_chg_yoy"], p_lev3=p["p_lev3_chg_yoy"])
    for lv in ("lev2", "lev3"):
        o = ALL[lv].get(i); rec["score_" + lv] = round(p["s_" + lv], 3) if pd.notna(p["s_" + lv]) else np.nan
        rec["n_controls_" + lv] = len(o["ci"]) if o else 0
        rec["obs_auc_" + lv] = round(float(np.mean(o["ind"])), 3) if o and len(o["ci"]) >= MINCTL else np.nan
    rows.append(rec)
PO = pd.DataFrame(rows).sort_values(["event_date", "ticker", "quarter_end"]); PO = PO.round({c: 3 for c in PO.select_dtypes("number").columns}); PO.to_csv(OUT / "per_observation.csv", index=False)
print(f"\nEXPORT A per_observation.csv: {len(PO)} rows, {PO.ticker.nunique()} companies, {int(PO.in_primary_window.sum())} in the primary window")

# ---- 6. EXPORT B and C: control comparisons and false positives (primary window, within-3x comparison sets)
cmp_rows, fp_rows, dec_rows, top_rows = [], [], [], []
for lv in ("lev2", "lev3"):
    obs = PRIM[lv][0]; lc = f"{lv}_chg_yoy"
    if not obs: continue
    for o in obs:
        for t_, e_, s_, ind_ in zip(o["ctl_t"], o["ctl_end"], o["ctl_scores"], o["ind"]):
            cmp_rows.append(dict(lev=lv, failed=o["comp"], failed_key=o["key"], failed_score=round(o["s0"], 3), control=t_, control_quarter=pd.Timestamp(e_).date(), control_score=round(s_, 3), control_above_failed=float(1 - ind_)))
    fs = np.array([o["s0"] for o in obs]); med, q75 = np.median(fs), np.percentile(fs, 75)
    cs = pd.concat([pd.DataFrame(dict(ticker=o["ctl_t"], end=o["ctl_end"], score=o["ctl_scores"], above=1 - o["ind"])) for o in obs])
    agg = cs.groupby(["ticker", "end"]).agg(score=("score", "first"), times_compared=("above", "size"), times_above=("above", "sum")).reset_index()
    agg = agg.merge(F[["ticker", "end", "group", "gm_chg_yoy", "inv_gap", lc]].rename(columns={lc: "raw_leverage"}), on=["ticker", "end"], how="left")
    agg["lev"] = lv; agg["above_failed_median"] = agg.score > med; agg["above_failed_q75"] = agg.score > q75; agg["failed_median"] = round(med, 3); agg["failed_q75"] = round(q75, 3)
    fp_rows.append(agg)
    # fixed-cutoff decision view (observation and company level)
    cm_comp = pd.DataFrame(dict(comp=[o["comp"] for o in obs], s=fs)).groupby("comp").s.max()
    for c in CUTOFFS:
        fl = int((fs >= c).sum()); cf = int((cm_comp >= c).sum()); ca = int((agg.score >= c).sum())
        dec_rows.append(dict(lev=lv, cutoff=c, failed_obs=len(fs), failed_obs_flagged=fl, capture_rate_obs=round(fl / len(fs), 3), failed_companies=len(cm_comp), failed_companies_flagged=cf,
                             capture_rate_companies=round(cf / len(cm_comp), 3), control_quarters=len(agg), control_quarters_flagged=ca, false_alarm_rate=round(ca / len(agg), 3),
                             lift=round((fl / len(fs)) / (ca / len(agg)), 2) if ca else np.nan))
    # rank-based view: flag a failed observation if it ranks in the top share of its own comparison set (controls + itself)
    share_above = np.array([float((1 - o["ind"]).mean()) for o in obs if len(o["ind"])])   # share of its controls scoring above it
    comp_best = pd.DataFrame(dict(comp=[o["comp"] for o in obs if len(o["ind"])], x=share_above)).groupby("comp").x.min()
    for q in TOPSHARES:
        top_rows.append(dict(lev=lv, top_share=q, failed_obs=len(share_above), failed_obs_in_top=int((share_above <= q).sum()), capture_rate_obs=round(float((share_above <= q).mean()), 3),
                             failed_companies=len(comp_best), failed_companies_in_top=int((comp_best <= q).sum()), capture_rate_companies=round(float((comp_best <= q).mean()), 3)))
CMP = pd.DataFrame(cmp_rows); CMP.to_csv(OUT / "control_comparisons.csv", index=False)
FP = pd.concat(fp_rows).sort_values(["lev", "score"], ascending=[True, False]); FP = FP.round({c: 3 for c in FP.select_dtypes("number").columns}); FP.to_csv(OUT / "false_positives.csv", index=False)
DEC = pd.DataFrame(dec_rows); TOP = pd.DataFrame(top_rows); DEC.to_csv(OUT / "decision_cutoffs.csv", index=False); TOP.to_csv(OUT / "decision_topshare.csv", index=False)
print(f"EXPORT B control_comparisons.csv: {len(CMP)} rows | EXPORT C false_positives.csv: {len(FP)} control company-quarters")
for lv in ("lev2", "lev3"):
    x = FP[FP.lev == lv]
    exp = {"lev2": 0.26, "lev3": 0.34}[lv]
    print(f"  {lv}: controls above the failed median {x.above_failed_median.mean():.0%} (the frozen run reported {exp:.0%}: {'OK' if abs(x.above_failed_median.mean() - exp) < 0.015 else 'CHECK, does not match the frozen log'}) | above the failed 75th percentile {x.above_failed_q75.mean():.0%}")
print("\nEXPORT D decision_cutoffs.csv (fixed cutoffs, DESCRIPTIVE, not tuned):"); print(DEC.to_string(index=False))
print("\nEXPORT D decision_topshare.csv (flag the top share of each comparison set):"); print(TOP.to_string(index=False))

# ---- 7. EXPORT E: live scores. Same score, same reference, latest public quarter of each company. A relative stress ranking, not a forecast.
LIVEPOOL = F[(F.group.isin(["healthy", "under_pressure"])) | ((F.group == "ho_control") & ~F.excluded_control)]
t_live = F.as_of_date.max(); LV = latest(LIVEPOOL, t_live).copy()
PL = pcts(t_live, LV)
LS = pd.concat([LV[["ticker", "group", "end", "as_of_date", "gm_chg_yoy", "inv_gap", "lev2_chg_yoy", "lev3_chg_yoy"] + (["tariff_refund_quarter"] if "tariff_refund_quarter" in LV.columns else [])], PL], axis=1)
LS = LS.rename(columns={"end": "quarter_end", "as_of_date": "public_on", "gm_chg_yoy": "raw_gm_chg", "inv_gap": "raw_inv_gap", "lev2_chg_yoy": "raw_lev2", "lev3_chg_yoy": "raw_lev3", "p_gm_chg_yoy": "p_gm", "p_inv_gap": "p_inv", "p_lev2_chg_yoy": "p_lev2", "p_lev3_chg_yoy": "p_lev3"})
LS["age_days"] = (t_live - LS.quarter_end).dt.days; LS["scored_on"] = t_live.date()
LS["rank_lev2"] = LS.s_lev2.rank(ascending=False, method="min"); LS["rank_lev3"] = LS.s_lev3.rank(ascending=False, method="min")
LS = LS.sort_values("s_lev2", ascending=False); LS = LS.round({c: 3 for c in LS.select_dtypes("number").columns}); LS.to_csv(OUT / "live_scores.csv", index=False)
print(f"\nEXPORT E live_scores.csv: scoring date {t_live.date()} | {len(LS)} companies with a quarter public within {MAXSTALE} days (reference: the 12 design controls, own value left out)")
print(LS[["ticker", "group", "quarter_end", "age_days", "s_lev2", "s_lev3", "rank_lev2", "rank_lev3"]].to_string(index=False))
print("  caveat: relative ranking among a small set of retailers, not a probability; quarters ending in 2026 may include one-off tariff-refund effects (verified for TGT and ROST only); lev3 is blank when last year's debt was zero.")
# forward-test ledger: append-only record of what the score said today, with a hash so it cannot be quietly changed later
led = LS[["scored_on", "ticker", "group", "quarter_end", "public_on", "s_lev2", "s_lev3", "rank_lev2", "rank_lev3"]].copy()
lf = FWD / "forward_test_ledger.csv"
if lf.exists():
    old = pd.read_csv(lf)
    if str(t_live.date()) in set(old.scored_on.astype(str)): print("  ledger already holds this scoring date: not appended")
    else: pd.concat([old, led]).to_csv(lf, index=False); print("  appended to forward_test_ledger.csv")
else: led.to_csv(lf, index=False); print("  created forward_test_ledger.csv")
with open(FWD / "forward_test_hashes.txt", "a") as h: h.write(f"{datetime.date.today()} scored_on {t_live.date()} sha256 {hashlib.sha256((OUT / 'live_scores.csv').read_bytes()).hexdigest()}\n")
print("  Check these scores against actual failures about 12 months after the scoring date (protocol v2 should say how, before anyone looks).")
# ---- 8. ready-made markdown tables for the README (copy, or paste the output to the analyst)
md = [f"### What would a flag have caught? (descriptive, held-out sample, 3 to 12 months before the event)\n",
      "Cutoffs were fixed in advance and are not tuned. Each failed company-quarter is compared with size-matched control company-quarters on the same date.\n"]
for lv in ("lev2", "lev3"):
    d = DEC[DEC.lev == lv]
    md += [f"**{lv}**\n", "| Flag when score is at or above | Failed quarters caught | Companies with at least one catch | Control quarters flagged (false alarms) | Lift |", "|---|---|---|---|---|"]
    md += [f"| {r.cutoff:.1f} | {r.capture_rate_obs:.0%} ({r.failed_obs_flagged} of {r.failed_obs}) | {r.failed_companies_flagged} of {r.failed_companies} | {r.false_alarm_rate:.0%} ({r.control_quarters_flagged} of {r.control_quarters}) | {r.lift if pd.notna(r.lift) else 'n/a'}x |" for r in d.itertuples()] + [""]
md += ["**Flag the top share of each comparison set**\n", "| Version | Top share | Failed quarters in it | Companies with at least one |", "|---|---|---|---|"]
md += [f"| {r.lev} | {r.top_share:.0%} | {r.capture_rate_obs:.0%} ({r.failed_obs_in_top} of {r.failed_obs}) | {r.failed_companies_in_top} of {r.failed_companies} |" for r in TOP.itertuples()] + [""]
md += [f"### Live scores on {t_live.date()} (relative stress ranking, not a forecast)\n", "| Rank (lev2) | Company | Quarter | Age (days) | lev2 score | lev3 score |", "|---|---|---|---|---|---|"]
md += [f"| {int(r.rank_lev2) if pd.notna(r.rank_lev2) else ''} | {r.ticker} | {pd.Timestamp(r.quarter_end).date()} | {int(r.age_days)} | {r.s_lev2:.2f} | {'' if pd.isna(r.s_lev3) else format(r.s_lev3, '.2f')} |" for r in LS.itertuples()]
(OUT / "readme_tables.md").write_text("\n".join(md), encoding="utf-8")
print("\nREADME TABLES (saved as extras/readme_tables.md):\n" + "\n".join(md))
print("\nStep 45 done. Files in heldout/extras/ and heldout/forward_test/.")
