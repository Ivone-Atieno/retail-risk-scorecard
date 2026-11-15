# Methodology

How the data was built, how the score works, how it was tested, and what was decided after seeing results. Written so a reviewer can check every rule against the code in `pipeline/` and `test/`, and against the frozen protocol in `protocol/`.

---

## 1. Principles

1. **Use only what was public.** Every value carries the date it was first filed. A quarter becomes usable on the latest filing date among its inputs, never on its period end.
2. **Earliest-filed value wins.** Companies restate. The first-reported number is what an observer had at the time.
3. **Key everything on CIK.** Tickers change owner (the old Bed Bath & Beyond CIK now belongs to a shell with a different name).
4. **Never fill a gap with a guess.** Missing stays missing. Any hand-entered value records its source filing.
5. **Write the test before seeing the answer.** The held-out protocol was frozen and hashed before any held-out score existed.
6. **Report what happened.** The pre-registered verdict is reported as it came out, including the part that failed.

## 2. Data source and scope

- **Source:** SEC EDGAR XBRL `companyfacts` (one JSON file per company), saved untouched. Filing text was read only to check specific values.
- **Design sample (20 retailers):** 6 healthy, 6 under pressure, 8 failed. Used to explore hypotheses and fix the score.
- **Held-out sample:** 22 failed retailers and 38 controls (40 candidates; 2 dropped by the three-input rule), plus 36 documented exclusions.
- **History:** quarterly from 2014. The design pipeline was re-run from 2014 and still reproduced all 428 design-company quarters unchanged (428 of 428).
- **Failure event:** the filing date of the first 8-K with Item 1.03 (bankruptcy), filed from 10 days before to 30 days after the petition date. A company with no such 8-K is excluded and listed.

## 3. The data pipeline

| Stage | What it does | Main rules |
|---|---|---|
| 1. Extract | Flatten every fact (all tags, all filings) into one long table | One row per fact per filing; nothing dropped |
| 2. Dates | Merge period ends that differ by a few days (52/53-week years) | Window of 2 days; rebuilt from its description and checked against the original file |
| 3. As-of | One value per period | Earliest-filed value; duplicates broken by tag priority |
| 4. Stitch | One tag per company and metric | Fallback tags fill gaps; an alternate tag is used only if it agrees within **1%** with the first tag where both report the same period (45 alternate tags rejected for added companies; 88 overlapping pairs audited afterwards, 0 above 1%) |
| 5. Quarters | Reported quarters, or differenced from year-to-date or annual | Q4 = annual minus the first three quarters |
| 6. Derive | Gross profit and cost of goods where missing | Gross profit = revenue − cost of goods; cost of goods = revenue − gross profit; every derived value is labelled |
| 7. Debt | A formula per company, reconciled against cross-check tags and filings | See section 4 |
| 8. Final tables | Wide quarterly table with filing dates and flags | Quarters filed after the event are removed from failed companies; COVID and tariff flags added |
| 9. Signals | Year-on-year signals | Prior-year quarter matched by date (364 days, 15-day tolerance) |

**Public date of a quarter** = the latest filing date among its inputs. For added companies, a reported gross profit that equals revenue minus cost of goods (within 1%) takes the later of the revenue and cost filing dates when that is earlier than its own filing date. This moved 43 quarters in 7 companies by a median of about 200 days. It is a timing correction, not a change of values, and it was added after the SMRT case showed an empty scoring window.

**Regression test.** After every pipeline change the 20 design companies must reproduce their earlier values: 428 of 428 unchanged, none lost.

## 4. Debt: the hardest input

Debt has no single standard tag, so it is built company by company.

- **Definition:** borrowings at carrying value, including current maturities and drawn credit lines. Operating leases are excluded. Finance leases are included only where the company's own debt tag includes them.
- **Formula selection:** each held-out formula is chosen by agreement with the balance-sheet debt lines of up to 6 sampled filings spread across the period. Accepted if at least 5 of 6 readable quarters tie within 2%.
- **Problems the checks caught:**
  - *Double counting:* three formulas counted one balance twice (Express, Big Lots, Children's Place), inflating debt by up to 100%.
  - *Omitted components:* a Walmart combined tag excluded short-term borrowings worth up to 24% of its debt. Of 18 automatically proposed formulas for held-out failed companies, 11 tied to the filings, **6 were wrong** (omitting a revolver, a current portion or a related-party loan) and 1 could not be verified. They were corrected, not left as "conservative" errors.
  - *Tag meaning changes:* Designer Brands' `LongTermDebt` excluded current maturities in 2020-21; Children's Place moved its revolver between tags.
  - *Calendar artifacts:* Sears, Fred's and Destination Maternity looked like missing data but had a 53-week fiscal year.
- **Hand-entered values:** 24 quarters for failed companies were read from filings (Pier 1 revolver 4, RTW 8, francesca's 4, hhgregg 4, LL Flooring 4), each with its source. Two control quarters were blanked because the filing contradicted the series and it could not be resolved (DLTH 2017-01-29, Hibbett 2019-02-02).
- **Controls screen:** a control is excluded if its series is more than 10% below a debt tag it reports in 2 or more quarters, or has a one-quarter spike of 1.8x to 2.2x on both sides in a multi-term formula.
- **Known limit:** reference debt for 2014 to 2018 is a formula series not tied to filings one by one.

## 5. The score (frozen)

Three signals, each as a percentile against a fixed reference group, averaged with equal weights.

| Signal | Definition | Riskier when |
|---|---|---|
| `gm_chg_yoy` | Gross margin minus the same quarter a year earlier (percentage points) | lower |
| `inv_gap` | Inventory growth minus revenue growth, year on year | higher |
| `lev2` or `lev3` | lev2: change in debt / trailing four-quarter sales. lev3: year-on-year % growth in debt (blank if prior debt was zero) | higher |

- **Reference group:** the 12 design companies WMT, COST, TGT, HD, TJX, ROST, KSS, M, WOOF, DBI, BGFV, PLCE. On a score date each is represented by its latest quarter public on or before that date and at most **135 days old**. A company's own value is left out of its own ranking. At least **5** reference values are needed.
- **Score** = mean of the three direction-adjusted percentiles; all three must be present.
- **COVID:** all signals are blanked for observations whose calendar quarter falls in 2020Q2 to 2021Q4.
- **Weights, thresholds and signal definitions are not changed on the basis of held-out results.** Equal weights were fixed in advance; the score is deliberately not tuned toward leverage even though leverage carries most of the signal.

## 6. What the design phase showed

Run in-sample on 8 failed companies chosen with hindsight, so exploratory and descriptive.

| Hypothesis | Outcome |
|---|---|
| H1: margins fall and leverage rises before failure | Suggestive for leverage; weak for gross margin and the joint result |
| H2: inventory outgrows sales | Not supported as stated (5 of 8; split between inventory building and shrinking) |
| H3: a composite ranks failing companies as riskier | Modest ranking power in the last year (mean AUC 0.68 to 0.72); fades earlier |
| H4: late filing is an early warning | Not supported |

Findings that shaped the held-out design:

- **Leverage carried the score**; gross margin, inventory gap and filing delay were near coin flips.
- **Company size alone separated failed from healthy companies better than the score did** when the comparison was against six large healthy retailers (size-only AUC about 0.98 against the score's 0.87 to 0.91 in the as-of re-test). Against controls matched to within 10x of size the score's AUC fell to about 0.56 to 0.59 with intervals including 0.5. For this reason the held-out primary comparison uses **size-matched controls (within 3x)**, and the size-only AUC is printed beside every headline number.
- **The comparison group matters.** Failure is easier to tell apart from health than from stress that did not become failure.
- **Filing delay carried no signal**, and the current ratio was dropped from the score because for Conn's it measured the receivables book, not liquidity.

## 7. The held-out test

| Item | Rule |
|---|---|
| Primary endpoint | 3 to 12 months from public date to event, pooled |
| Metric | Company-mean AUC (each failed observation against controls on the same date; averaged within company, then across companies) |
| Controls | Same score date, trailing four-quarter sales within 3x of the failed company; at least 3 per scored observation |
| Control universe | US retail 10-K filers (SIC 5200-5499, 5531, 5600-5799, 5900-5999) in the SEC data sets for 2019 Q1 and Q2, revenue 250m to 20bn, minus failed and design companies |
| Time-varying labels | A control company-quarter more than 27 months before its own event may serve as a control; within 27 months it is a positive |
| Uncertainty | Two-way bootstrap (failed and control companies resampled), 2,000 draws, seed 20261102; also clustered by event year |
| Floor | At least 12 scored failed companies per leverage version, otherwise inconclusive |
| Success | For **both** versions: interval lower end above 0.5 **and** at least two thirds of companies above 0.5 |
| Reading rules (fixed before the run) | The verdict uses the two-way company interval; event-year interval shown beside it; early quarters of the three companies found by the control-universe scan serve as extra negatives, with a controls-only check; event cuts are descriptive only |

**Run log.** The test ran twice on 2026-11-02 (07:38 and 08:06 UTC) with identical output. The second run is logged as a repeat with no deviation.

**Leakage audit.** 0 of 62 scored observations were dated on or after the event 8-K.

## 8. Results in one table

| | lev2 | lev3 |
|---|---|---|
| Scored failed companies | 19 | 20 |
| Company-mean AUC | 0.658 | 0.606 |
| Two-way interval | 0.52 to 0.78 | 0.47 to 0.74 |
| Event-year clustered interval | 0.53 to 0.86 | 0.45 to 0.84 |
| Companies above 0.5 | 15 of 19 | 14 of 20 |
| Size-only AUC | 0.540 | 0.534 |
| Rule | **MET (narrowly)** | **NOT MET** |

**Overall: NOT MET.** lev3 fails on the interval (lower end 0.47), not on the share of companies (70% is above the two thirds needed).

## 9. Descriptive and diagnostic views (nothing here changes the verdict)

- **Horizons** (lev2 / lev3): 3-6 months 0.599 / 0.561; 6-12: 0.713 / 0.639; 12-18: 0.562 / 0.655; 18-27: 0.426 / 0.502.
- **Event cuts** (lev2 / lev3): pre-2019 0.822 / 0.683; 2019 0.755 / 0.871; 2020 to Jan 2021 0.554 / 0.442; later 0.719 / 0.703.
- **Ablation** (lev2 / lev3): leverage only 0.694 / 0.602; gross margin only 0.582 / 0.548; inventory gap only 0.556 / 0.562.
- **Robustness** (lev2 / lev3): within 10x 0.669 / 0.606; all held-out controls 0.674 / 0.609; controls only 0.657 / 0.615; design controls 0.645 / 0.562; debt on both dates 0.673 / 0.601.
- **False positives:** 26% (lev2) and 34% (lev3) of control company-quarters score above the failed companies' median.
- **Companies below 0.5:** lev2: GNC 0.07, JCP 0.29, SMRT 0.33 (ASNA at 0.50); lev3: GNC, JCP, FRAN, SMRT, ASNA, ARO.

## 10. What changed after seeing results, stated plainly

- Design phase: the leverage measure and the window were refined after seeing earlier results; only the equal weights were fixed in advance. This is why a held-out test was needed.
- Held-out phase: the pipeline rules in section 3 (the 1% stitching rule, the gross-profit date rule, the three-input rule) were written after pipeline runs but before any held-out score. They are listed in protocol section 10. The held-out sample is now used: **any change to the score needs new data and a new protocol (v2).**

## 11. Limitations

- Small sample: 19 to 20 scored failures per version; the lev2 interval lower end is 0.52, a narrow pass.
- Ten of the failures cluster in one shock period (Feb 2020 to Jan 2021), where the score is weakest.
- The pre-2019 reference group is thin (4 to 7 companies in 2016 to 2018) and partly late-dated.
- Controls are 2019 filers (survivorship); retailers with March to November year-ends are under-represented; extraction difficulty slightly favours simpler capital structures.
- Debt definitions are not identical across companies (finance leases).
- The score ignores the *level* of debt. That this explains lev3's weaker result is a hypothesis, untested.
- Live scores are a relative ranking among a small set of retailers, not probabilities.
