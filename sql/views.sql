-- Views for the retail risk project (MySQL 8). Run after the tables are loaded. Each view is built only from columns the loader creates.

DROP VIEW IF EXISTS v_verdict;
CREATE VIEW v_verdict AS
SELECT lev,
       companies AS scored_companies,
       obs AS observations,
       auc AS company_mean_auc,
       pooled AS pooled_auc,
       size_only_auc,
       ci95 AS interval_95,
       CAST(SUBSTRING_INDEX(ci95, ' to ', 1) AS DECIMAL(5,2)) AS interval_low,
       CAST(SUBSTRING_INDEX(ci95, ' to ', -1) AS DECIMAL(5,2)) AS interval_high,
       ci95_year AS interval_95_event_year,
       above_half,
       CAST(SUBSTRING_INDEX(above_half, '/', 1) AS UNSIGNED) AS companies_above_half,
       CAST(SUBSTRING_INDEX(above_half, '/', -1) AS UNSIGNED) AS companies_scored,
       CASE WHEN companies < 12 THEN 'INCONCLUSIVE (below floor of 12)'
            WHEN CAST(SUBSTRING_INDEX(ci95, ' to ', 1) AS DECIMAL(5,2)) > 0.5
                 AND CAST(SUBSTRING_INDEX(above_half, '/', 1) AS UNSIGNED) / CAST(SUBSTRING_INDEX(above_half, '/', -1) AS UNSIGNED) >= 2.0/3 THEN 'MET'
            ELSE 'NOT MET' END AS rule_result
FROM primary_result;

DROP VIEW IF EXISTS v_overall_verdict;
CREATE VIEW v_overall_verdict AS
SELECT CASE WHEN SUM(rule_result LIKE 'INCONCLUSIVE%') > 0 THEN 'INCONCLUSIVE for at least one version'
            WHEN SUM(rule_result = 'MET') = COUNT(*) THEN 'MET (both versions)'
            ELSE 'NOT MET (success needs both lev2 and lev3)' END AS overall
FROM v_verdict;

DROP VIEW IF EXISTS v_robustness;
CREATE VIEW v_robustness AS
SELECT view_name, lev, companies, obs, auc, pooled, above_half, ci95, ci95_year
FROM secondary_result;

DROP VIEW IF EXISTS v_event_cuts;
CREATE VIEW v_event_cuts AS
SELECT lev, event_cut, companies, obs, auc, pooled, above_half
FROM cut_result
ORDER BY lev, FIELD(event_cut, 'pre-2019', '2019', '2020 to Jan 2021', 'later');

DROP VIEW IF EXISTS v_company_results;
CREATE VIEW v_company_results AS
SELECT lev, company, event, event_cut, obs, auc, auc_min, auc_max, controls_median,
       CASE WHEN auc > 0.5 THEN 'above 0.5' WHEN auc = 0.5 THEN 'at 0.5' ELSE 'below 0.5' END AS side_of_chance
FROM company_result;

DROP VIEW IF EXISTS v_coverage;
CREATE VIEW v_coverage AS
SELECT q.ticker, c.grp,
       COUNT(*) AS quarters,
       SUM(q.Revenue IS NOT NULL) AS revenue_quarters,
       SUM(q.GrossProfit IS NOT NULL) AS gross_profit_quarters,
       SUM(q.Inventory IS NOT NULL) AS inventory_quarters,
       SUM(q.Debt IS NOT NULL) AS debt_quarters,
       ROUND(SUM(q.Revenue IS NOT NULL) / COUNT(*), 2) AS revenue_share,
       MIN(q.quarter_end) AS first_quarter,
       MAX(q.quarter_end) AS last_quarter
FROM clean_quarterly q
LEFT JOIN companies c ON c.ticker = q.ticker
GROUP BY q.ticker, c.grp;

DROP VIEW IF EXISTS v_public_lag;
CREATE VIEW v_public_lag AS
SELECT ticker, grp,
       COUNT(*) AS quarters,
       ROUND(AVG(DATEDIFF(as_of_date, quarter_end)), 1) AS mean_days_to_public,
       ROUND(AVG(DATEDIFF(as_of_date, quarter_end) > 135), 2) AS share_over_135_days
FROM features_heldout
WHERE as_of_date IS NOT NULL
GROUP BY ticker, grp;

DROP VIEW IF EXISTS v_failed_window_signals;
CREATE VIEW v_failed_window_signals AS
SELECT ticker, quarter_end, as_of_date, distress_date,
       ROUND(months_avail, 1) AS months_before_event,
       gm_chg_yoy, inv_gap, lev2_chg_yoy, lev3_chg_yoy, ttm_rev
FROM features_heldout
WHERE grp = 'ho_failed' AND months_avail >= 3 AND months_avail < 12;

DROP VIEW IF EXISTS v_events;
CREATE VIEW v_events AS
SELECT ticker, MIN(distress_date) AS event_date,
       CASE WHEN MIN(distress_date) < '2019-01-01' THEN 'pre-2019'
            WHEN MIN(distress_date) < '2020-01-01' THEN '2019'
            WHEN MIN(distress_date) < '2021-02-01' THEN '2020 to Jan 2021'
            ELSE 'later' END AS event_cut
FROM features_heldout
WHERE grp = 'ho_failed'
GROUP BY ticker;
