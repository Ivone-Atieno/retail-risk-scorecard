# Data dictionary

Every table, field and view used in the project, with a plain definition. Field names are as they appear in the CSV files; where the MySQL loader renames a field (because it is a reserved word) the table notes it.

Contents: [1. Core metrics](#1-the-11-core-metrics) · [2. Pipeline tables](#2-pipeline-tables) · [3. Test result tables](#3-test-result-tables) · [4. Analysis extras (Step 45)](#4-report-extras-step-45) · [5. SQL views](#5-sql-views) · [6. Codes and flags](#6-codes-and-flags) · [7. Glossary](#7-glossary)

---

## 1. The 11 core metrics

Chosen because every US retailer reports them, so a cross-company score can use the same inputs for everyone. Company-specific items (for example Conn's customer-credit receivables or Costco's membership fees) are deliberately left out of the score.

| Metric | Field | Type | Meaning | Standard tag (examples) |
|---|---|---|---|---|
| Revenue | `Revenue` | flow | Net sales | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet`, `SalesRevenueGoodsNet` |
| Cost of goods | `CostOfGoods` | flow | Direct cost of products sold | `CostOfGoodsAndServicesSold`, `CostOfRevenue`, `CostOfGoodsSold` |
| Gross profit | `GrossProfit` | flow | Revenue minus cost of goods; derived where the company does not report it | `GrossProfit` |
| Inventory | `Inventory` | balance | Unsold stock | `InventoryNet` |
| Current assets | `CurrAssets` | balance | Assets due within a year | `AssetsCurrent` |
| Current liabilities | `CurrLiab` | balance | Obligations due within a year | `LiabilitiesCurrent` |
| Equity | `Equity` | balance | Shareholders' equity | `StockholdersEquity` |
| Net income | `NetIncome` | flow | Profit after tax | `NetIncomeLoss` |
| Operating cash flow | `OpCashFlow` | flow | Cash from operations | `NetCashProvidedByUsedInOperatingActivities` |
| Capex | `Capex` | flow | Spending on property and equipment | `PaymentsToAcquirePropertyPlantAndEquipment` |
| Total debt | `Debt` | balance | Borrowings at carrying value; includes current maturities and drawn credit lines; excludes operating leases | one formula per company (see below) |

**Flow items have no Q4 in the SEC data.** Q4 is derived as the annual figure minus the first three quarters. Year-to-date values are differenced into quarters.

**Total debt.** Each company has its own formula built from XBRL tags (`+` adds terms, `?` marks an optional term, `|` means "use the first tag that has a value"). A total tag is used when it exists, otherwise noncurrent plus current; a total is never added to its own components. Finance leases are included only where the company's own debt tag includes them (TGT, HD, M, RAD, PRTY, WOOF, CONN among the design companies). Debt after a bankruptcy filing (for example debtor-in-possession financing) is excluded because it is dated after the event. Missing values are never filled with zeros or estimates.

---

## 2. Pipeline tables

### `clean_quarterly.csv` → table `clean_quarterly`
One row per company-quarter, after cleaning. Loader renames `end` → `quarter_end`.

| Field | Meaning |
|---|---|
| `ticker` | Company identifier used in the project. Some are `CIK…` codes where no stable ticker exists. Everything is keyed on the SEC CIK number, never on the ticker. |
| `end` / `quarter_end` | Fiscal quarter end date (matched to a quarter grid; a 52/53-week year can shift it by a few days). |
| `Revenue`, `CostOfGoods`, `GrossProfit`, `NetIncome`, `OpCashFlow`, `Capex` | Quarterly flow values in US dollars. |
| `Inventory`, `CurrAssets`, `CurrLiab`, `Equity` | Balance-sheet values at quarter end, in US dollars. |
| `Debt` | Total debt at quarter end, in US dollars (see the definition above). |
| `f_<metric>` (for example `f_Revenue`, `f_Debt`) | The date the first-filed value of that metric was filed with the SEC. |
| `as_of_date` | **Public date of the quarter** = the latest of the `f_…` filing dates among its inputs. A quarter may be used in a score only from this date. |
| `debt_flag` | Result of the debt reconciliation for that quarter (see [6. Codes and flags](#6-codes-and-flags)). |
| `tariff_refund_quarter` | `True` for quarters ending on or after 2026-07-31, which may contain one-off tariff-refund effects (verified for TGT and ROST only). |
| `gp_basis` | For DBI only: `old` or `new` gross-profit definition (the company changed it in 2023). Year-on-year gross-margin change across the break is blanked. |
| `group` / `grp` | Company group (see codes). |
| `distress_date` | Event date for failed companies (filing date of the first 8-K with Item 1.03), blank otherwise. |
| `q_rel` | Quarter position relative to the last quarter filed before the event (failed companies). |

Other helper columns written by the pipeline may also be present. The authoritative list is whatever `pipeline/heldout_pipeline.py` writes.

### `features_heldout.csv` → table `features_heldout`
One row per company-quarter with the signals. Loader renames `group` → `grp`, `end` → `quarter_end`.

| Field | Meaning |
|---|---|
| `ticker`, `group`, `end`, `distress_date`, `as_of_date`, `tariff_refund_quarter`, `gp_basis` | As above. |
| `qtd` | Quarters to distress: 1 = last quarter filed before the event (failed companies). |
| `gross_margin` | Gross profit / revenue, as a fraction. |
| `gm_chg_yoy` | **Signal 1.** Gross margin minus the same quarter a year earlier, in percentage points. Lower is riskier. |
| `rev_yoy`, `inv_yoy` | Year-on-year growth of revenue and inventory, in percent. |
| `inv_gap` | **Signal 2.** `inv_yoy` minus `rev_yoy`, in percentage points. Higher is riskier. |
| `ttm_rev` | Trailing four-quarter revenue, in US dollars. Used for size matching and the size-only benchmark. Blank unless the four quarters span 240 to 300 days. |
| `debt_to_sales` | `Debt / ttm_rev`. |
| `lev2_chg_yoy` | **Signal 3, version lev2.** `debt_to_sales` minus its value a year earlier. Higher is riskier. |
| `lev3_chg_yoy` | **Signal 3, version lev3.** Year-on-year % growth in `Debt`. Blank if debt a year earlier was zero. Higher is riskier. |
| `debt_to_ca`, `lev_chg_yoy`, `debt_to_equity`, `current_ratio`, `ocf_margin`, `net_margin`, `delay_days`, `delay_chg_yoy`, `equity_negative`, `inv_to_rev`, `basis_break_yoy` | Design-phase signals and flags. Not part of the frozen score; kept for the exploratory H1 to H4 work. |
| `cal_q` | Calendar quarter of the observation = quarter end + 30 days, as `YYYYQn`. Used for the COVID rule and for matching comparison dates. |
| `months_avail` | Months from the quarter's public date to the event date (failed companies). |
| `excluded_control` | `True` for the two controls dropped by the three-input rule (AAP, CIK1701114). |

The "year earlier" quarter is matched by date (364 days earlier, 15-day tolerance), never by row position. This is what makes 52/53-week years work.

### `companies.csv` → table `companies`
One row per company: `ticker`, `cik`, `name`, `group` (loader: `grp`), `distress_date`, and fiscal-year information.

### `coverage_added_companies.csv` → table `coverage_added`
For the 62 added companies (22 failed, 40 control candidates): `quarters`, the share of quarters that have `Revenue`, `GrossProfit`, `Inventory` and `Debt`, `longest_run` (longest run of consecutive quarters with all four inputs), and `min_share`. The three-input rule drops a company with a `longest_run` under 4.

---

## 3. Test result tables

All written by `test/step44_test.py` into `heldout/test_results/`. Loader renames `leverage` → `lev`.

| Table | File | Content |
|---|---|---|
| `primary_result` | `primary.csv` | The pre-registered endpoint (3 to 12 months, controls within 3x). One row per leverage version: `obs`, `companies`, `auc` (company-mean AUC), `pooled`, `above_half` (for example `15/19`), `loo` (leave-one-company-out range), `ci95` (two-way bootstrap interval), `ci95_year` (event-year clustered interval), `size_only_auc`, `median_controls`. |
| `secondary_result` | `secondary.csv` | Robustness views (`view` → `view_name`): control sets (within 10x, all held-out controls, controls only, design controls), debt-on-both-dates subgroup, and four horizons. |
| `cut_result` | `cuts.csv` | Four descriptive event cuts (`cut` → `event_cut`). Never tested against the floor. |
| `company_result` | `per_company.csv` | One row per failed company and version: `event` date, `event_cut`, `obs`, `auc`, `min`/`max` (→ `auc_min`/`auc_max`), `controls_median`. |
| `run_log` | (created by the loader) | One row per frozen-test run. |

**Company-mean AUC.** For each failed observation, the probability that it scores riskier than a control on the same date (ties count half); averaged within each company, then across companies. 0.5 means no better than chance.

---

## 4. Analysis extras (Step 45)

Written by `test/step45_export.py` into `heldout/extras/` and `heldout/forward_test/`. These files are not loaded into the Power BI report; they feed the README and the one-page summary. The script is read-only: it checks the protocol hash, reproduces the frozen primary result and stops if it does not, and uses the same data preparation and comparison sets as the frozen test. Everything here is **descriptive**.

| File → table | One row per | Key fields |
|---|---|---|
| `per_observation.csv` | failed company-quarter 3 to 27 months before the event | `ticker`, `event_date`, `event_year`, `event_cut`, `quarter_end`, `public_on`, `months_before_event`, `in_primary_window`, raw signals (`raw_gm_chg`, `raw_inv_gap`, `raw_lev2`, `raw_lev3`), percentiles (`p_gm`, `p_inv`, `p_lev2`, `p_lev3`), `score_lev2`/`score_lev3`, `n_controls_*`, `obs_auc_*` |
| `control_comparisons.csv` | failed observation × control company-quarter in its size-matched comparison set (primary window) | `lev`, `failed`, `failed_score`, `control`, `control_quarter`, `control_score`, `control_above_failed` (1 above, 0.5 tie, 0 below) |
| `false_positives.csv` | distinct control company-quarter in those comparison sets | `lev`, `ticker`, `quarter_end`, `group`, `score`, raw signals, `times_compared`, `times_above`, `above_failed_median`, `above_failed_q75`, `failed_median`, `failed_q75` |
| `decision_cutoffs.csv` | version × fixed cutoff (0.5, 0.6, 0.7, 0.8) | `failed_obs`, `failed_obs_flagged`, `capture_rate_obs`, `failed_companies_flagged`, `capture_rate_companies`, `control_quarters`, `control_quarters_flagged`, `false_alarm_rate`, `lift` |
| `decision_topshare.csv` | version × top share (10%, 20%, 30%) | `capture_rate_obs`, `capture_rate_companies` for failed observations that rank in the top share of their own comparison set |
| `live_scores.csv` | company with a quarter public within 135 days of the scoring date | `scored_on`, `ticker`, `group`, `quarter_end`, `public_on`, `age_days`, raw signals, percentiles, `s_lev2`, `s_lev3`, `rank_lev2`, `rank_lev3`, `tariff_refund_quarter` |
| `forward_test_ledger.csv` | company × scoring date, appended each run | the scores as recorded on that date. A SHA-256 of each `live_scores.csv` is appended to `forward_test_hashes.txt` so the record cannot be quietly changed. |

**Decision-view definitions.**
- *Capture rate* = share of failed observations (or companies, counting a company if any observation qualifies) with a score at or above the cutoff.
- *False-alarm rate* = share of distinct control company-quarters with a score at or above the cutoff.
- *Lift* = capture rate divided by false-alarm rate.
- The cutoffs and top shares were fixed in advance and are not optimised. With 19 to 20 failed companies these are rough descriptions, not estimates with tight error bars.

**Live scores** are a relative stress ranking among a small set of retailers. They are not probabilities and not forecasts.

---

## 5. SQL views

| View | Built from | Purpose |
|---|---|---|
| `v_verdict` | `primary_result` | Numeric interval bounds, companies above 0.5, and the pre-registered `rule_result` (MET / NOT MET / INCONCLUSIVE) per version |
| `v_overall_verdict` | `v_verdict` | Overall verdict: success needs both versions |
| `v_robustness` | `secondary_result` | Robustness views with `short_label` and `view_order` |
| `v_event_cuts` | `cut_result` | Four event cuts with `cut_order` |
| `v_company_results` | `company_result` | Per-company AUC with `side_of_chance` |
| `v_company_events` | `company_result` | Per-company AUC with event date and year, for the scatter chart |
| `v_coverage`, `v_input_coverage` | `clean_quarterly`, `companies` | Share of quarters with each input, per company |
| `v_public_lag` | `clean_quarterly` | Share of quarters public more than 135 days after quarter end |
| `v_failed_window_signals`, `v_events` | `features_heldout`, `companies` | Signals in the window before each event; event list |

---

## 6. Codes and flags

**`group` / `grp`**

| Value | Meaning |
|---|---|
| `healthy` | Design sample: large, healthy retailers (WMT, COST, TGT, HD, TJX, ROST) |
| `under_pressure` | Design sample: stressed but not failed (KSS, M, WOOF, DBI, BGFV, PLCE) |
| `failed` | Design sample: failed (BBBY, BIG, CONN, EXPR, JOAN, PRTY, RAD, TUEM) |
| `ho_failed` | Held-out failed retailers (22) |
| `ho_control` | Held-out control retailers (38 kept) |

The 12 `healthy` and `under_pressure` companies form the fixed **reference group** that every score is ranked against.

**`debt_flag`** (reconciliation of the debt series against cross-check tags and filings)

| Flag | Meaning |
|---|---|
| `ok` | Within 5% of an independent cross-check tag |
| `no_check` | No independent tag to compare against |
| `DIFF` | More than 5% from a cross-check; needs reading, not obeying (cross-check tags often cover only part of the debt) |
| `JUMP` | Moved more than 40% in a quarter; many are real events (2020 borrowing, revolver seasonality) |
| `MISSING` | A required component is absent |
| `MANUAL (filing)` | Value read by hand from a filing, with the source recorded |
| `FORMULA 2014-18` | Design-reference debt for 2014 to 2018 from the formula, not tied to filings one by one |

**`event_cut`**: `pre-2019`, `2019`, `2020 to Jan 2021`, `later`, by event date. Descriptive only.

---

## 7. Glossary

| Term | Definition |
|---|---|
| **XBRL / companyfacts** | The SEC's machine-readable financial data, one JSON file per company |
| **CIK** | The SEC's permanent company number. Tickers change owner; CIKs do not |
| **Public date / as-of date** | The latest filing date among a quarter's inputs. Scores use only quarters public on the score date |
| **MAXSTALE** | A company's latest public quarter may be at most 135 days old on the score date |
| **Look-ahead bias** | Using data that was not yet public at the time, which makes a score look better than it would have been in real time |
| **Percentile score** | Where a company's value falls among the 12 reference companies on the same date, direction-adjusted so higher is riskier; the score is the mean of three percentiles |
| **lev2 / lev3** | The two pre-registered leverage signals (change in debt / sales; % growth in debt) |
| **AUC** | Probability that a failed observation scores riskier than a control; 0.5 is chance |
| **Two-way bootstrap** | Interval estimate that resamples both failed and control companies |
| **Size-only AUC** | AUC of "smaller company is riskier" on the same comparison sets; the benchmark the score must beat |
| **Pre-registration** | Writing the test and success rule down, and hashing the file, before any held-out score exists |
| **Held-out sample** | Companies never used to design the score |
