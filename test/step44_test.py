# ===== STEP 44: THE FROZEN HELD-OUT TEST (protocol v1.3). Run ONCE, in the Colab notebook where BASE, CT and pd exist, after the protocol is frozen. Nothing here is tuned on results. =====
# Reads only files already written: heldout_pipeline/features_heldout.csv, heldout_pipeline/clean_quarterly.csv, heldout/controls/controls_final.csv, heldout/heldout_protocol_v1_3.md.
# Writes only to heldout/test_results/. Every run is logged: if you run it a second time, tell me, it goes in the deviations log.
import hashlib, re, json, datetime
import numpy as np, pandas as pd
from pathlib import Path
pd.set_option("display.width", 230); pd.set_option("display.max_columns", 40)
HO = Path(CT).parent; HP = Path(BASE) / "heldout_pipeline"; OUT = HO / "test_results"; OUT.mkdir(exist_ok=True)
SEED, NBOOT, MAXSTALE, MINCTL, MINREF, FLOOR = 20261102, 2000, 135, 3, 5, 12
WIN_B = set(pd.period_range("2020Q2", "2021Q4", freq="Q").astype(str))
rng = np.random.default_rng(SEED)

# ---- 0. the protocol on disk must be the frozen one
pmd = HO / "heldout_protocol_v1_3.md"; psh = HO / "heldout_protocol_v1_3.sha256"
hnow = hashlib.sha256(pmd.read_bytes()).hexdigest(); hsaved = psh.read_text().split()[0]
txt = pmd.read_text(encoding="utf-8")
print("PROTOCOL CHECK: file hash", hnow[:16] + "...", "| saved hash", hsaved[:16] + "...", "| match:", hnow == hsaved, "| says FROZEN:", "Status: FROZEN" in txt)
if hnow != hsaved or "Status: FROZEN" not in txt: raise RuntimeError("the protocol file is not the frozen v1.3: stop and tell the analyst")
_lg = OUT / "run_log.txt"; _prev = _lg.read_text() if _lg.exists() else ""
print("run started", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "| seed", SEED, "| bootstrap draws", NBOOT, "| THIS IS A RERUN: it goes in the deviations log" if _prev else "| first run", "\n")
_lg.write_text(_prev + f"run {datetime.datetime.now():%Y-%m-%d %H:%M} protocol {hnow}\n")

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

# ---- 3. building the observation lists for any variant, and the estimators
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

def summarize(obs, nC, key="ind", boot=True):
    if not obs: return dict(obs=0, companies=0)
    cm, rows = cmeans(obs, np.ones(nC), key)
    if not cm: return dict(obs=0, companies=0)
    comps = sorted(cm); vals = np.array([cm[c] for c in comps]); allrows = np.concatenate([np.array(v) for v in rows.values()])
    yr = {o["comp"]: o["year"] for o in obs}; years = sorted(set(yr[c] for c in comps)); byyr = {y: [c for c in comps if yr[c] == y] for y in years}
    res = dict(obs=len(allrows), companies=len(comps), company_mean_auc=float(vals.mean()), pooled_auc=float(allrows.mean()), above_half=f"{int((vals > .5).sum())}/{len(comps)}", share_above=float((vals > .5).mean()), _cm=cm)
    loo = [np.delete(vals, k).mean() for k in range(len(vals))] if len(vals) > 2 else [np.nan]; res["loo"] = f"{min(loo):.2f} to {max(loo):.2f}"
    if boot:
        present = np.unique(np.concatenate([o["ci"] for o in obs])); b1, b2 = [], []
        for _ in range(NBOOT):
            W = np.bincount(rng.choice(present, len(present)), minlength=nC).astype(float); cmb, _ = cmeans(obs, W, key)
            if not cmb: continue
            av = [c for c in comps if c in cmb]
            if not av: continue
            b1.append(np.mean([cmb[c] for c in rng.choice(av, len(av))]))
            ys = rng.choice(years, len(years)); pick = []
            for y in ys:
                cc = [c for c in byyr[y] if c in cmb]
                if cc: pick += list(rng.choice(cc, len(cc)))
            if pick: b2.append(np.mean([cmb[c] for c in pick]))
        res["ci_lo"], res["ci_hi"] = (float(np.percentile(b1, 2.5)), float(np.percentile(b1, 97.5))) if b1 else (np.nan, np.nan)
        res["ci_year_lo"], res["ci_year_hi"] = (float(np.percentile(b2, 2.5)), float(np.percentile(b2, 97.5))) if b2 else (np.nan, np.nan)
    return res
def fmt(s):
    if not s.get("companies"): return dict(obs=0, companies=0)
    d = dict(obs=s["obs"], companies=s["companies"], auc=round(s["company_mean_auc"], 3), pooled=round(s["pooled_auc"], 3), above_half=s["above_half"], loo=s["loo"])
    if "ci_lo" in s: d["ci95"] = f"{s['ci_lo']:.2f} to {s['ci_hi']:.2f}"; d["ci95_year"] = f"{s['ci_year_lo']:.2f} to {s['ci_year_hi']:.2f}"
    return d

# ---- 4. PRIMARY RESULT
print("PART 1: PRIMARY ENDPOINT. 3-12 months from the public date to the event, pooled; controls within 3x of the failed company's trailing sales; company-mean AUC")
prim = {}; rows = []
for lv in ("lev2", "lev3"):
    obs, nC = build(lv); s = summarize(obs, nC); ss = summarize(obs, nC, "ind_size", boot=False); prim[lv] = (obs, nC, s)
    d = dict(leverage=lv, **fmt(s)); d["size_only_auc"] = round(ss["company_mean_auc"], 3) if ss.get("companies") else np.nan; d["median_controls"] = int(np.median([len(o["ci"]) for o in obs])) if obs else 0; rows.append(d)
PR = pd.DataFrame(rows); print(PR.to_string(index=False)); PR.to_csv(OUT / "primary.csv", index=False)
print("\nFLOOR AND SUCCESS RULE (protocol section 8):")
verd = {}
for lv in ("lev2", "lev3"):
    s = prim[lv][2]; n = s.get("companies", 0)
    if n < FLOOR: verd[lv] = f"INCONCLUSIVE ({n} scored failed companies, floor {FLOOR})"
    else:
        ok_ci = s["ci_lo"] > 0.5; ok_sh = s["share_above"] >= 2 / 3; ok_yr = s["ci_year_lo"] > 0.5
        verd[lv] = f"{'MET' if ok_ci and ok_sh else 'NOT MET'}: interval lower end {s['ci_lo']:.2f} ({'above' if ok_ci else 'not above'} 0.5), {s['above_half']} companies above 0.5 ({'at least' if ok_sh else 'under'} two thirds); with event-year clustering the lower end is {s['ci_year_lo']:.2f}"
    print(f"  {lv}: {verd[lv]}")
both = all(v.startswith("MET") for v in verd.values()); incon = any(v.startswith("INCONCLUSIVE") for v in verd.values())
print("  OVERALL (success needs BOTH lev2 and lev3):", "INCONCLUSIVE for at least one version" if incon else ("MET" if both else "NOT MET"))
print("  Reading rule fixed before running: the verdict uses the two-way company interval; the event-year interval is shown beside it and any disagreement is stated in the write-up.\n")

# ---- 5. SECONDARY
print("PART 2: SECONDARY VIEWS (all 3-12 months unless stated; same score, same controls rules)")
rows = []
def add(label, lv, **kw):
    o, nC = build(lv, **kw); s = summarize(o, nC); d = dict(view=label, leverage=lv, **fmt(s)); rows.append(d)
for lv in ("lev2", "lev3"):
    add("controls within 3x (primary)", lv); add("controls within 10x", lv, size=10); add("all held-out controls (no size match)", lv, size=None)
    add("within 3x, control companies only (no early quarters of later-failed)", lv, pool="controls_only")
    add("vs design controls (frozen reference, no size match)", lv, size=None, against="design")
    add("subgroup: debt on both dates, within 3x", lv, sub=True)
    for hz, lo, hi in [("3-6", 3, 6), ("6-12", 6, 12), ("12-18", 12, 18), ("18-27", 18, 27.01)]: add(f"horizon {hz} months, within 3x", lv, lo=lo, hi=hi)
SEC = pd.DataFrame(rows); print(SEC.to_string(index=False)); SEC.to_csv(OUT / "secondary.csv", index=False)

print("\nPART 3: DESCRIPTIVE EVENT CUTS (3-12 months, within 3x; never tested against the floor; no intervals)")
rows = []
for lv in ("lev2", "lev3"):
    for c in ["pre-2019", "2019", "2020 to Jan 2021", "later"]:
        ids = set(FO[FO.cut == c].ticker); o, nC = build(lv, comps=ids); s = summarize(o, nC, boot=False); rows.append(dict(leverage=lv, cut=c, **fmt(s)))
CUT = pd.DataFrame(rows); print(CUT.to_string(index=False)); CUT.to_csv(OUT / "cuts.csv", index=False)

# ---- 6. per company, false positives, ablation, leakage
print("\nPART 4: EACH FAILED COMPANY (3-12 months, within 3x)")
rows = []
for lv in ("lev2", "lev3"):
    obs = prim[lv][0]; cm, rr = cmeans(obs, np.ones(prim[lv][1]))
    for c in sorted(cm):
        e = FO[FO.ticker == c].iloc[0]; rows.append(dict(leverage=lv, company=c, event=str(e.distress_date.date()), cut=e.cut, obs=len(rr[c]), auc=round(cm[c], 2), min=round(min(rr[c]), 2), max=round(max(rr[c]), 2),
                                                      controls_median=int(np.median([len(o["ci"]) for o in obs if o["comp"] == c]))))
    miss = sorted(set(FO.ticker) - set(cm)); print(f"  not scored for {lv}: {miss}")
PC = pd.DataFrame(rows); print(PC.to_string(index=False)); PC.to_csv(OUT / "per_company.csv", index=False)

print("\nPART 5: FALSE POSITIVES. Share of distinct control company-quarters (those in the within-3x comparison sets) that score above the median / 75th percentile of the failed companies' own scores (3-12 months). Raw signals shown for the 8 highest")
for lv in ("lev2", "lev3"):
    obs = prim[lv][0]
    if not obs: continue
    fs = np.array([o["s0"] for o in obs]); med, q75 = np.median(fs), np.percentile(fs, 75)
    cs = pd.concat([pd.DataFrame(dict(ticker=o["ctl_t"], end=o["ctl_end"], score=o["ctl_scores"])) for o in obs]).drop_duplicates(["ticker", "end"])
    print(f"  {lv}: failed scores median {med:.2f}, 75th percentile {q75:.2f} (n={len(fs)} observations) | controls above median {(cs.score > med).mean():.0%}, above 75th {(cs.score > q75).mean():.0%} (n={len(cs)} control quarters)")
    top = cs.sort_values("score", ascending=False).head(8).merge(F[["ticker", "end", "gm_chg_yoy", "inv_gap", f"{lv}_chg_yoy"]], on=["ticker", "end"], how="left"); print(top.round({"score": 3, "gm_chg_yoy": 3, "inv_gap": 3, f"{lv}_chg_yoy": 3}).to_string(index=False))

print("\nPART 6: ABLATION (diagnostic only, nothing is chosen from it): company-mean AUC of each part alone, same comparison sets as the primary")
rows = []
for lv in ("lev2", "lev3"):
    obs, nC = prim[lv][0], prim[lv][1]
    for k, lab in [("ind", "full score"), ("ind_gm", "gross margin only"), ("ind_inv", "inventory gap only"), ("ind_lev", "leverage only"), ("ind_size", "size only (smaller = riskier)")]:
        s = summarize(obs, nC, k, boot=False); rows.append(dict(leverage=lv, part=lab, companies=s.get("companies", 0), auc=round(s["company_mean_auc"], 3) if s.get("companies") else np.nan))
print(pd.DataFrame(rows).to_string(index=False))

print("\nPART 7: LEAKAGE AUDIT by filing date")
u = FO.loc[sorted({o["key"] for lv in prim for o in prim[lv][0]})]
bad = u[~(u.as_of_date < u.distress_date)]
print(f"  failed observations used in the primary result: {len(u)} | public date on or after the event 8-K: {len(bad)} | latest public date used: {u.as_of_date.max().date()} | all control rows have public date on or before the failed company's public date by construction (as-of engine)")
print("\nPART 8: INPUT LOG")
print("  protocol hash", hnow, "| seed", SEED, "| features_heldout rows", len(F), "| failed observations", len(FO))
print("\nStep 44 done. Paste everything above. Do not rerun with changed settings; a rerun goes in the deviations log.")
