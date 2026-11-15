# data/

Data files are not stored in this repository (they are large and come from SEC EDGAR).

Put these here, or keep them in your own folder and point the scripts at it:

- `clean_quarterly.csv`, `features_heldout.csv`, `coverage_added_companies.csv` (pipeline outputs)
- `primary.csv`, `secondary.csv`, `cuts.csv`, `per_company.csv`, `run_log.txt` (frozen test outputs)
- `per_observation.csv`, `control_comparisons.csv`, `false_positives.csv`, `decision_cutoffs.csv`, `decision_topshare.csv`, `live_scores.csv`, `forward_test_ledger.csv` (report extras from `test/step45_export.py`)

Small result files (the five test outputs) may be committed if readers want to check the numbers.
