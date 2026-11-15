# Run order

What to run, in what order, what each step needs and what it writes. The step scripts were developed in Google Colab and share variables inside one session, so they are a record of the work. To reproduce the final results you need only parts B to F.

**Where things run**

| Where | What |
|---|---|
| Google Colab (data on Google Drive) | Extraction, cleaning, pipeline, protocol, frozen test, export |
| Your own computer | MySQL, the loader, Power BI Desktop |

Folder used throughout (change it once at the top of each script): `BASE = /content/drive/MyDrive/retail_risk_project`, with sub-folders `heldout/`, `heldout/controls/`, `heldout/test_results/`, `heldout_pipeline/`.

**Before you start.** The SEC asks automated clients to identify themselves. Set a descriptive `User-Agent` string with a contact email in `HEADERS` in your start-of-session cell. Do not commit that email to a public repository.

---

## A. Background: how the project was built (read, do not re-run)

| Stage | Scripts | Output |
|---|---|---|
| Design phase: data extraction and cleaning | `scripts/01_design_phase/step1.py` to `step9.py` (with `step4b`, `step5c`, `step6`, `step7`, `step8`) | `clean_01_long.csv` → … → `clean_quarterly.csv`, `features_quarterly.csv` |
| Design phase: hypotheses, score, stress tests | `step10.py` to `step18.py` | Findings in `docs/findings/`; no files the final pipeline needs |
| Held-out selection: candidates, extraction QA, debt formulas | `scripts/02_heldout_selection/step19.py` to `step40.py` | Tag maps, debt tables, final control list |
| Protocol drafts | `step41.py`, `step42.py` | Protocol v1.2 and checks |

The held-out selection scripts compute **no scores**. Outcomes were never used to choose anything.

## B. Inputs the pipeline needs

As far as I read the script headers, these come from the held-out selection stage. Confirm against your own Drive folder.

| File | Folder | Produced by |
|---|---|---|
| Raw SEC JSON, one file per company (`<10-digit CIK>.json`) | `raw/` folders | `step1.py`, `step19.py`, `step31.py` |
| `companies.csv` | `BASE/` | design phase |
| `tag_map_heldout_v4.csv` | `heldout/` | `step24.py` onward |
| `debt_quarterly_heldout.csv` | `heldout/` | `step30.py` |
| `manual_debt_overrides.csv` | `heldout/` | `step29.py` |
| `controls_final.csv`, `debt_quarterly_controls_final.csv` | `heldout/controls/` | `step38.py` |
| `design_debt_2014.pkl` | `heldout/` | `step21.py` |

## C. Pipeline

```
python pipeline/heldout_pipeline.py        # in Colab
```
- Builds clean quarterly tables for all 82 companies from 2014, with the as-of dates, the gross-profit date rule and the three-input rule.
- Runs the regression check: **must print PASS (428 of 428 unchanged)**. If not, stop.
- Writes to `heldout_pipeline/`: `clean_quarterly.csv`, `features_heldout.csv`, `coverage_added_companies.csv`, `regression_differences.csv`, `debt_quarterly_final.csv`.
- `pipeline/audit_asof.py` is a diagnostic for the as-of lag; it is also built into the pipeline.

## D. Protocol (done once; do not repeat)

```
python protocol/make_protocol_v1_3.py      # frozen = False for a draft, True to freeze
```
- Writes `heldout/heldout_protocol_v1_3.md` and `.sha256`.
- Frozen 2026-11-02. SHA-256 `781fe9b663d973a9b157eb26eaef453f26268c3c2f712efb11bc819d96c49292`.
- Copy both files to `protocol/` in this repository. Do not edit them.

## E. The frozen test (run once)

```
python test/step44_test.py                 # in Colab
```
- Refuses to run unless the protocol file matches its saved hash.
- Writes `heldout/test_results/`: `primary.csv`, `secondary.csv`, `cuts.csv`, `per_company.csv`, `run_log.txt`.
- A second run is logged as a rerun. It ran twice on 2026-11-02 with identical output.

## F. Report extras (optional, read-only; known open issue)

> Status: on the author's data this step stops at its own reconciliation check (184 vs 187 failed observations). It exports nothing in that case. The frozen results do not depend on it.

```
python test/step45_export.py               # in Colab, after step 44
```
- Checks the protocol hash, **reproduces the frozen primary result** (company-mean AUC and company counts must match `primary.csv`, otherwise it stops), then exports.
- Writes `heldout/extras/`: `per_observation.csv`, `control_comparisons.csv`, `false_positives.csv`, `decision_cutoffs.csv`, `decision_topshare.csv`, `live_scores.csv`.
- Writes `heldout/forward_test/`: `forward_test_ledger.csv` (append-only) and `forward_test_hashes.txt`.
- Everything it produces is descriptive. It changes no frozen output.
- It also prints, and saves as `extras/readme_tables.md`, ready-made markdown tables (decision view and live scores) to paste into the README.
- **Rerun `live_scores` whenever new quarters are filed**, then commit the ledger. The ledger is the record for the forward test (compare the scores with actual failures about 12 months later).

## G. Database and report (on your computer)

1. Install MySQL and `pip install pandas sqlalchemy pymysql cryptography`.
2. Copy these CSV files into one folder: `features_heldout.csv`, `clean_quarterly.csv`, `companies.csv`, `coverage_added_companies.csv`, and the four result files from step E (`primary.csv`, `secondary.csv`, `cuts.csv`, `per_company.csv`).
3. Edit `DATA`, and your MySQL user and password, at the top of `sql/load_to_mysql.py`. Never commit your password.
4. Run `python sql/load_to_mysql.py`. It loads the tables, creates the views from `views.sql`, and prints the verdict. Expected: lev2 **MET**, lev3 **NOT MET**, overall **NOT MET**.
5. Run the view scripts that are not in `views.sql` (`v_robustness_update.sql`, `v_company_events.sql`, `v_input_coverage.sql`) in MySQL Workbench.
6. Open `powerbi/retail_risk.pbix`, point it at your server and **Refresh**. The report has five pages: Verdict, Evidence, Event cuts, Companies, Data quality.

The step F files are not loaded into the report. They feed the README and the summary (see F).

## H. Checks before publishing

- [ ] Pipeline printed PASS (428 of 428)
- [ ] Protocol hash matches
- [ ] Step 45 printed `RECONCILE … OK` for both versions
- [ ] Step 45 printed `OK` beside the false-positive rates (26% and 34%)
- [ ] Verdict page shows 0.658, 0.606 and NOT MET
- [ ] No password, email or personal path in any committed file
