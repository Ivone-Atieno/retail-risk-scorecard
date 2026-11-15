# ===== STEP 41 (revised for v1.3): writes protocol v1.3 from the final data files (lists are generated, not typed) and records its SHA-256 hash. NO SCORES. Run in the SAME Colab session after Step 40 (seconds). =====
# FROZEN = False writes a DRAFT. Review the file; when you accept every item, set FROZEN = True, run again, and keep the printed hash (email the file and the hash to yourself or upload it to a public registry such as OSF).
FROZEN = False
for nm in ["CT", "pd"]:
    if nm not in globals(): raise NameError(f"{nm} is not defined: run Steps 31-40 in this session first")
import hashlib, json, re
HO = CT.parent
FR = pd.read_csv(CT / "controls_final.csv"); EXC = pd.read_csv(CT / "controls_exclusions_final.csv")
EV = pd.read_csv(HO / "failed_events_checked.csv"); CAND = pd.read_csv(HO / "failed_candidates.csv"); DT = pd.read_csv(HO / "debt_quarterly_heldout.csv")
def d10(x):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(x)); return pd.Timestamp(m.group(0)) if m else pd.NaT
def cut(ev): return "pre-2019" if ev < pd.Timestamp("2019-01-01") else ("2019" if ev < pd.Timestamp("2020-01-01") else ("2020 to Jan 2021" if ev < pd.Timestamp("2021-02-01") else "later"))
CAND["cik_i"] = pd.to_numeric(CAND["cik"], errors="coerce"); EV["cik_i"] = pd.to_numeric(EV["cik"], errors="coerce"); CAND["pet"] = CAND["petition_date"].map(d10)
H = CAND[CAND.ticker.isin(DT.ticker.unique())].merge(EV[["cik_i", "event_8k_date", "event_accession"]], on="cik_i", how="left")
H["ev"] = pd.to_datetime(H["event_8k_date"]); H["cut"] = H["ev"].map(cut)
PET = {"QVCG": "2026-04-16", "CIK1575360": "2019-06-03", "CIK1051251": "2019-06-03"}; PET["CIK1051251"] = "2020-05-04"
NF = FR[FR.status == "NEW FAILED"].copy(); NF["ev"] = pd.to_datetime(NF["event"], errors="coerce"); NF["cut"] = NF["ev"].map(cut)
def petshow(r):
    if pd.notna(r.pet): return str(r.pet)[:10]
    m = re.search(r"\d{4}-\d{2}", str(r.petition_date)); return (m.group(0) + " (day unverified)") if m else "unverified"
fail_rows = [f"| {r.ticker} | {r.name[:44]} | {petshow(r)} | {str(r.ev)[:10]} | {r.event_accession} | {r.cut} |" for r in H.sort_values("ev").itertuples()]
fail_rows += [f"| {r.ticker} | {r.name[:34]} | {PET.get(r.ticker, '')} | {str(r.ev)[:10]} | (scan of the submissions file) | {r.cut} |" for r in NF.sort_values("ev").itertuples()]
cuts = pd.concat([H[["ticker", "cut"]], NF[["ticker", "cut"]]]); cut_line = "; ".join(f"{k}: {n}" for k, n in cuts.cut.value_counts().reindex(["pre-2019", "2019", "2020 to Jan 2021", "later"]).fillna(0).astype(int).items())
C = FR[FR.status == "CONTROL"].sort_values("ticker")
def cell(x, n): return str(x).replace("|", "/").replace("\n", " ")[:n]
ctl_rows = [f"| {r.ticker} | {cell(r.name, 40)} | {cell(r.formula, 110)} | {r.ties} | {cell(r.gap_check, 130)} |" for r in C.itertuples()]
def grp(x):
    x = str(x)
    if x.startswith("business-model exclusion"): return "business-model exclusion"
    if x.startswith("EXCLUDED: formula"): return "Step 38: formula disagrees with the filing"
    if x.startswith("EXCLUDED: year-end"): return "Step 38: double count"
    if x.startswith("EXCLUDED: series below"): return "Step 38: series below a reported debt tag"
    if x.startswith("EXCLUDED: non-recourse"): return "Step 38: non-recourse debt tagged inconsistently"
    if x.startswith("best component"): return "best component set does not tie"
    if x.startswith("debt lines in gap") or x.startswith("gap quarters"): return "gap quarters hold debt the formula lacks"
    if x.startswith("core data"): return "core data incomplete"
    if x.startswith("only"): return "filing could not be read"
    return x[:50]
EXC["group"] = EXC["reason"].map(grp)
exc_group = EXC.group.value_counts(); exc_rows = [f"| {r.cik} | {cell(r.name, 40)} | {cell(r.reason, 170)} |" for r in EXC.sort_values("name").itertuples()]
dev = []
for r in FR.itertuples():
    p = CT / "cache" / f"c37_{int(r.cik)}.json"
    if p.exists():
        for ln in json.load(open(p)).get("fails", []): dev.append(f"- {r.ticker}: {ln.strip()[:230]}")
status = "FROZEN on " + str(pd.Timestamp.now().date()) if FROZEN else "DRAFT: not frozen. Accept every item below, then set FROZEN = True in step41.py and run it again"
HP = HO.parent / "heldout_pipeline"
FH = pd.read_csv(HP / "features_heldout.csv", usecols=lambda c: c in ("ticker", "excluded_control"))
DROPPED = sorted(set(FH[FH["excluded_control"].astype(str).str.lower().isin(["true", "1", "1.0"])]["ticker"])) if "excluded_control" in FH.columns else []
print("controls dropped by the three-input rule (read from features_heldout.csv):", DROPPED, "(expected: AAP and CIK1701114)")
if sorted(DROPPED) != ["AAP", "CIK1701114"]: raise ValueError("the dropped controls differ from the Step 43 output; check heldout_pipeline/features_heldout.csv")
C = C[~C.ticker.isin(DROPPED)]
ctl_rows = [f"| {r.ticker} | {cell(r.name, 40)} | {cell(r.formula, 110)} | {r.ties} | {cell(r.gap_check, 130)} |" for r in C.itertuples()]
n_ctl, n_nf = len(C), len(NF)
md = f"""# Held-out validation protocol, version 1.3

Project: US retail financial-risk early-warning scorecard (Portfolio Project 2)
Status: {status}. The owner confirmed the three v1.1 defaults (control universe rule, primary endpoint, success rule) on 2026-10-27. No held-out company has been scored.

Changes from v1.2 (all made before any held-out score; the pipeline run of 2026-11-02 is described in section 10): the reference composition text is corrected (section 2); the data pipeline rules for tag stitching, the extended reference, the public date of gross profit and the three-input rule are written down (section 10); the control count is reduced by the three-input rule (section 5); a minimum number of controls per scored observation is added (section 8); further limitations are stated (section 9).

Changes from v1.1, carried over from v1.2, all made before any scoring (so no deviation entry): the control universe is the SIC and SEC data-set rule below, replacing the December 2019 XRT or S&P holdings default; rule R2 (no debt anywhere means zero) is added; the debt extraction and tie-out rules (section 6) are written down; the 3 retailers found by the Item 1.03 scan (FTD, J.Crew, QVC) join the failed set; the secondary event cuts are four, not one; a subgroup of companies with debt on both dates is added; the limitations are stated in section 9. Any change after the first held-out score is computed goes in the deviations log (section 13) with the date and the reason.

## 1. The question

Does the existing, unchanged score distinguish retailers approaching a documented bankruptcy filing from comparable retailers that have not filed, using only information that was public on each score date?

What the design sample already showed (so the held-out test is built to answer the harder question): against the six large healthy retailers the score separated well (AUC about 0.87 to 0.91 at 3-12 months), but company size alone separated better (0.98); against controls matched within 10x of size the AUC was 0.56 to 0.59 with intervals including 0.5; against the under-pressure group it was about 0.5 to 0.6. The primary comparison below is therefore against size-matched controls.

## 2. Frozen score (no changes allowed)

- Signals: gross margin change vs the same quarter a year earlier (lower is riskier); inventory growth minus sales growth, year on year (higher is riskier); leverage change in two versions that are BOTH reported: lev2 = year-on-year change in debt / trailing four-quarter sales, lev3 = year-on-year percentage growth in debt (blank if last year's debt was zero).
- Score: for each signal, the percentile of the company's value among the reference companies on the same date, direction-adjusted; core score = unweighted mean of the three percentiles; all three must be present; at least 5 reference companies with a value.
- Reference group on a score date: the design-sample controls (WMT, COST, TGT, HD, TJX, ROST, KSS, M, WOOF, DBI, BGFV, PLCE), each represented by its latest quarter whose inputs were all public on or before that date and not older than 135 days (the as-of engine, MAXSTALE = 135).
- Reference composition (corrected in v1.3; v1.2 said about 8 companies before 2020, which was wrong): the reference uses 2014 history. The signals gross margin change, inventory growth gap and lev3 can be computed from 2015; lev2 (which needs eight quarters of revenue) from 2016Q1. Companies with all three inputs for lev2, counted by calendar quarter: 4 in 2016Q1, 5 to 7 from 2016Q2 to 2018Q4, 10 to 11 in 2019. With the as-of rule (latest quarter public on the score date, at most 135 days old) some members are missing on pre-2019 score dates, because M, TGT, TJX and DBI have 2016-2018 quarters that were first public in later restated filings (median lag 316 to 573 days). Percentiles before 2019 are therefore coarse and based on mostly large, healthy retailers. Failed and control observations are scored against the same reference, so their comparison is unaffected, but absolute scores are not comparable with the design period.
- COVID treatment: all signals are blanked for observations whose calendar quarter (quarter end + 30 days) falls in 2020Q2 to 2021Q4. No quarter is restored or removed after seeing outcomes.
- Data rules (details in section 10): earliest-filed value wins for each fact; quarter grid and Q4 derivation as in the design pipeline; no filling of holes with guesses.
- Weights, thresholds, signal definitions and missing-data rules are not changed on the basis of held-out results.

## 3. Distress event

- Event date = filing date of the first 8-K with Item 1.03 filed from 10 days before to 30 days after the petition date. Every included company has one (0 to 4 days after the petition for the 19 candidates). The accession number is recorded. Pier 1's petition day is unverified (its event 8-K is dated 2020-02-18).
- A company with no such 8-K is excluded and listed. No substitute rule is used.
- Additional failures are found by an objective scan: every company in the control universe was checked for any Item 1.03 8-K since 2014 across its full filing history (older submission files included). Hits are failed companies, not controls. QVC Group and Qurate are one economic entity and count once, with QVC Inc as the unit.

## 4. Failed companies (positives): {len(H) + n_nf}

US retailers (consumer goods, store-based or online), SEC registrants with XBRL data, event 8-K as above, excluding the eight design failures (BBBY, RAD, BIG, PRTY, JOAN, EXPR, TUEM, CONN). Excluded: The Container Store (XBRL data from 2022 only, no cost-of-goods tag, no debt series) and Christopher & Banks (one usable quarter after the COVID blank).

| Ticker | Name | Petition | Event 8-K | Accession | Cut |
| --- | --- | --- | --- | --- | --- |
""" + "\n".join(fail_rows) + f"""

Events by cut: {cut_line}.

## 5. Control companies (negatives)

- Universe: US 10-K filers with retail SIC codes (5200-5499, 5531, 5600-5799, 5900-5999) in the SEC Financial Statement Data Sets for 2019 Q1 and Q2; annual revenue between 250m and 20bn; design-sample and held-out failed companies removed. {n_ctl} controls remain after the extraction rules in section 6 and the three-input rule (AAP and the Blue Apron company, CIK1701114, were dropped by it: AAP has no four consecutive quarters with all inputs, Blue Apron has no cost-of-goods or gross-profit tag). Accounting for the universe in the size range: {n_ctl} controls + {len(DROPPED)} dropped by the three-input rule + {n_nf} new failed + {len(EXC)} excluded = {n_ctl + len(DROPPED) + n_nf + len(EXC)}.
- Business-model exclusions, decided on what the company does before any score: B2B IT resellers (CDW, Insight, PC Connection, PCM), building and industrial distribution (Builders FirstSource, BMC, Fastenal), machinery dealer (Titan Machinery), specialty pharmacy (Diplomat), apparel manufacturer (Hanesbrands), pawn lender (FirstCash), non-retail (IAC/Match, Liberty Expedia, Crestwood).
- Time-varying labels: every company-quarter is a candidate control for any score date more than 27 months before that company's own event (or if it never has one). A company-quarter within 27 months before its own event is a positive and never a control.
- No separate "stressed" label is assigned in advance.
- Size matching: for each failed observation, controls on the same score date whose annual revenue is within a factor of 3 (primary) or 10 (secondary) of the failed company's. Checked before scoring (Step 43, using the as-of dates and trailing four-quarter sales as the size measure; an approximation of the annual-revenue rule): for every failed company and leverage version the worst scored observation has at least 3 controls within 3x, except PSUN (lev3: 1 control) and francesca's (lev2: one observation with no control that has the required inputs).

| Ticker | Name | Debt formula | Filing ties | Gap handling |
| --- | --- | --- | --- | --- |
""" + "\n".join(ctl_rows) + """

## 6. Debt extraction and series rules (applied identically to failed companies and controls; filings only, never scores)

- Each debt formula is chosen from XBRL tags by agreement with the balance-sheet debt lines of up to 6 sampled filings spread across the whole period; accepted if at least 5 of 6 readable quarters tie within 2% (and at least 5 are readable). A total tag is used if present, otherwise noncurrent plus current; a total tag is never added to its own components.
- Current portions are always included where they exist (a going-concern reclassification moves debt to current, as for QVC in December 2025).
- Leases: operating leases are never debt. Finance (capital) lease obligations are included only where the company's own debt tag includes them (for example Sears, GNC and several design companies, as documented in the design debt definitions); lease-like lines that have no such tag are excluded (for example JCP's line of 204-219m, about 5% of its debt). Because the score uses year-on-year changes, a constant definitional difference largely cancels, but the mix is a stated limitation (section 9).
- Rule R2: a company with no debt tag with any value and no positive debt line in the sampled filings has zero debt in every quarter.
- Gaps: up to 3 isolated gap quarters stay MISSING. Larger gaps are zero-filled only if no material (above 2m) debt tag of any kind has a value in the gap quarters and the sampled gap filings show no debt line. Verified zero quarters and hand-entered quarters are recorded with their source filing (24 manual rows for the failed companies: Pier 1 revolver 4, RTW 8, francesca's 4, hhgregg 4, LL Flooring 4).
- Series screen (written after seeing the Step 37 control output and before any score): a control is excluded if its series is more than 10% below a debt tag it reports in 2 or more quarters, or has a one-quarter spike of 1.8x-2.2x on both sides in a multi-term formula (double count); a single flagged quarter is blanked. An excluded company is restored only if every flagged quarter matches the filing balance sheet within 2% (rule fixed before reading; applied in Step 40: Abercrombie & Fitch restored, Haverty's stays excluded).
- Quarter-level blanks: a control quarter where the filing contradicts the series by more than 2% and the contradiction is unresolved is set to MISSING, never corrected by guess. Applied before any score to DLTH 2017-01-29 and Hibbett 2019-02-02 (section 11); the debt table is blanked for these two quarters when the held-out inputs are built.
- Spikes that match the filing balance sheet are kept (Genesco and Duluth seasonal revolver draws were verified in the filings).
- The three-input rule: a company is dropped if extraction QA finds no usable debt series for at least 8 quarter ends before its event, or fewer than 4 consecutive quarters with all three signal inputs. Applied in the Step 43 pipeline run: no failed company is dropped; two controls are dropped (AAP, CIK1701114). CTRN passes with exactly 4 consecutive quarters and gross profit in 8% of its quarters, so it is rarely used as a control; it is kept because the rule was written before it was checked.

## 7. Horizons

Horizon is measured from the date the score could first be computed (all inputs public) to the event date.
- Primary endpoint: 3 to 12 months, pooled.
- Secondary, reported separately and never re-selected: 3-6, 6-12, 12-18, 18-27 months.

## 8. Metrics, uncertainty, success criteria

- Metric: company-mean AUC (each failed observation against controls on the same date, averaged within company, then across companies). Pooled AUC is shown beside it, and the size-only AUC on the same sets is shown beside every headline number.
- Uncertainty: two-way cluster bootstrap (failed companies and control companies resampled; repeated quarters stay with their company), 2,000 draws, additionally clustered by event year; leave-one-failed-company-out range; the number of distinct companies beside every headline number.
- Primary success criterion (default; owner confirms before freezing): for BOTH lev2 and lev3, the 95% interval of the size-matched (within 3x) 3-12 month company-mean AUC has a lower end above 0.5, AND at least two thirds of failed companies have an AUC above 0.5.
- Minimum controls (added in v1.3, before any scoring): an observation is scored in the size-matched (3x) comparison only if at least 3 controls within 3x have a scored value on that date; otherwise it is listed as unscored and the company's count uses its other observations.
- Floor (clarified in v1.2, before any scoring): the count is made separately for lev2 and lev3. If fewer than 12 held-out failed companies have a scored observation in the primary window for a leverage version, that version is reported as inconclusive regardless of its point estimate. With history starting in 2014, the earliest events (2016) may lack a lev2 value in the window; the count shows it. Forecast from the Step 43 pipeline run (input gating only, no scores): lev2 19 of 22 failed companies, lev3 20 of 22 (not available for lev2: PSUN and ARO, too few revenue quarters; CIK1575360, a reference of 4 companies on one date and a missing signal on the other; not available for lev3: HGG and RTW, zero debt a year earlier). No claim of generalisation beyond what the intervals support.
- Secondary cuts, descriptive only and never tested against the floor: events pre-2019 (survivorship: the controls are 2019 filers, so earlier events face healthier controls), 2019, 2020 to January 2021 (COVID shock), and later. The pooled 3-12 month endpoint is the only result tested against the floor.
- Subgroup, pre-registered: failed and control companies with debt on both dates of the year-on-year comparison (a leverage change is not meaningful for a debt-free company).
- Also reported: AUC against all held-out controls; AUC against the design controls (frozen reference); false-positive table (share of control observations above the median and the 75th percentile of the failed companies' scores) with the raw signals beside every rank; per-company table; leakage audit by filing date (not period end: for example QVC's March 2026 balance sheet was filed after the petition); signal ablation as a diagnostic only.

## 9. Limitations stated in advance

- Survivorship: controls are 2019 filers.
- Selection by extraction difficulty: companies with several debt instruments were harder to tie to filings and are over-represented among the exclusions, so the controls lean toward simpler capital structures.
- Leverage mix: about a quarter of the controls are mostly debt-free; the failed companies are mostly levered.
- Universe: retailers with March to November fiscal year-ends are under-represented.
- Event clustering: ten of the failed companies filed between February 2020 and January 2021, a shared shock.
- The design-sample score choices (window, lev3) were made after seeing results; only the equal weights were fixed in advance.
- Debt definition is not identical across companies: some tags include finance leases and others do not.
- Pre-2019 reference: thin and partly late-dated (section 2); the six pre-2019 events (PSUN, ARO, HGG, GMAN, BONT, SHLD) are the most affected and are reported only as a descriptive cut.
- Design reference debt for 2014 to 2018 is a formula series that was not tied to filings one by one (flag FORMULA 2014-18).
- Companies whose old tags were rejected by the 1% rule lose history before the 2018 revenue-tag change; this mainly affects events before 2019.
- The gross-profit date rule (section 10) was written after the SMRT case showed an empty window; it is applied to all added companies and is a timing correction, not a change of values.
- Percentile ranks carry no level information and can rank benign companies high when peers are deleveraging.

## 10. Data work and blinding

- Extraction QA is done before any score is computed and uses filings, not scores. Manual data fixes are allowed only for documented extraction errors with a source filing, made without looking at scores.
- The history start moves from 2019 to 2014. Go/no-go test (run 2026-11-02): with the earlier start the 20 design companies reproduce their existing 2020-onward values: 428 of 428 quarter rows in both runs, zero changed and zero lost. New values appear only where a year-on-year signal gains a value because earlier data now exists (gm and inventory gap 20 cells, lev2 70 cells), among them two lev2 values after mid-2021 (BGFV 2021-07-04 and PRTY 2021-09-30) explained by newly filled 2019 quarters.
- Step 2 (merge of period ends within a window of 2 days) was rebuilt from its description and checked against the owner's clean_02_dates.csv: identical for windows 2 to 4.
- Tag stitching for added companies and the extended design reference: an alternate tag is used only if it agrees within 1% with the first tag where both report the same period, or does not overlap it. 45 alternate tags were rejected for the added companies (list in the pipeline output); for the reference, WMT Revenues (1.18%), COST SalesRevenueNet (2.28%), TGT SalesRevenueNet (1.36%), KSS SalesRevenueNet (6.06%) and M SalesRevenueNet (1.49%) were rejected. After the rule, 88 overlapping tag pairs were audited and none differ by more than 1%. The candidate tag lists include SalesRevenueGoodsNet (revenue) and RetailRelatedInventory (inventory), added after a tag scan of SPWH, GMAN, PIR, SSI and FRAN and before any score.
- Where several accepted tags report the same period, the earliest-filed value wins and the tag priority only breaks ties (applies to the added companies and the extended reference; the design cells' own stitching lists are unchanged).
- Public date of a quarter: the latest filing date among its inputs. For the added companies, a reported gross profit that equals revenue minus cost of goods within 1% takes the later of the revenue and cost filing dates when that is earlier than its own filing date (the value is not changed). It moved 43 quarters (BJ 9, BURL 9, CIK1096376 14, GCO 3, QVCG 1, SMRT 6, SPWH 1) by a median of about 200 days. The rule was added after the first pipeline runs showed SMRT with no observation in the 3-12 month window; before it, those quarters were dated at the next annual report.
- Quarters with a reported gross profit that does not match revenue minus cost of goods keep their own filing date.
- Pipeline run reference: heldout_pipeline.py v6, run 2026-11-02; outputs in heldout_pipeline/ (clean_quarterly.csv, features_heldout.csv, coverage_added_companies.csv, regression_differences.csv, logs).
- Scores on held-out companies are computed once after the dataset and protocol are locked. Any rerun is logged.

## 11. Known deviations in the control series (printed by the Step 37 tie-out)

Lines are shown as the tie-out printed them (filing figures usually in thousands). DDS ties exactly (365.7m + 200.0m); the extra 12.3m line appears to be an interest line the reader counted. AAP is missing a 95m current portion in one quarter (about 5%).

""" + ("\n".join(dev) if dev else "(none recorded in the Step 37 caches)") + """

Reading of each (by the analyst, from the numbers printed above; none uses a score):
- AAP: formula 1,785.1m against filing long-term debt 1,785.1m plus a current portion of 95.0m, about 5% under for one quarter. Kept as is.
- DDS: formula 565.7m equals long-term debt 365.7m plus subordinated debentures 200.0m. The extra 12.3m is an interest line the reader counted as debt (analyst reading). Treated as a tie.
- DLTH, 2017-01-29: formula 0.8m against filing lines of about 5.0m (current maturities 0.7m plus long-term debt 4.3m), an undercount of about 4.3m. Blanked (MISSING) under the rule in section 6.
- CIK1017480 (Hibbett), 2019-02-02: formula 35.0m against no positive debt line in the filing. Cannot be confirmed either way. Blanked (MISSING) under the rule in section 6.
""" + f"""

Two small items are to be handled as manual overrides, each recorded with its source filing, in the pipeline-inputs step and before any score: Duluth 2017-01-29 (the series reads 0.8m; the filing lines show 4.3m long-term plus 0.7m current) and Hibbett 2019-02-02 (the series reads 35.0m; the filing shows no positive debt line, so the quarter is blanked). Both are documented extraction errors, not choices made from scores.

## 12. Exclusions from the control universe, with reasons

Grouped counts:

""" + "\n".join(f"- {k}: {v}" for k, v in exc_group.items()) + """

| CIK | Name | Reason |
| --- | --- | --- |
""" + "\n".join(exc_rows) + """

## 13. Deviations log

(empty)
"""
p = HO / ("heldout_protocol_v1_3.md"); p.write_text(md, encoding="utf-8")
h = hashlib.sha256(p.read_bytes()).hexdigest(); (HO / "heldout_protocol_v1_3.sha256").write_text(f"{h}  heldout_protocol_v1_3.md\n")
print(f"written: {p} ({len(md.splitlines())} lines)\nstatus: {status}\nfailed companies listed: {len(H) + n_nf} | controls listed: {n_ctl} | exclusions listed: {len(EXC)} | known deviations listed: {len(dev)}\nSHA-256: {h}")
print("Open the file and read it before freezing. Any later edit changes the hash.")
