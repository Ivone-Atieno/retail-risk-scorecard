USE retail_risk;
CREATE OR REPLACE VIEW v_company_events AS
SELECT lev, company,
       STR_TO_DATE(event, '%Y-%m-%d') AS event_date,
       ROUND(YEAR(STR_TO_DATE(event, '%Y-%m-%d')) + (DAYOFYEAR(STR_TO_DATE(event, '%Y-%m-%d')) - 1) / 365.25, 2) AS event_year,
       event_cut,
       FIELD(event_cut, 'pre-2019', '2019', '2020 to Jan 2021', 'later') AS cut_order,
       obs, auc, auc_min, auc_max, controls_median,
       CASE WHEN auc > 0.5 THEN 'above 0.5' WHEN auc = 0.5 THEN 'at 0.5' ELSE 'below 0.5' END AS side_of_chance
FROM company_result;
