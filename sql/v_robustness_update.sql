USE retail_risk;
CREATE OR REPLACE VIEW v_robustness AS
SELECT view_name,
       CASE view_name
         WHEN 'controls within 3x (primary)' THEN '3x size match (primary)'
         WHEN 'controls within 10x' THEN '10x size match'
         WHEN 'all held-out controls (no size match)' THEN 'All controls, no size match'
         WHEN 'within 3x, control companies only (no early quarters of later-failed)' THEN '3x, control companies only'
         WHEN 'vs design controls (frozen reference, no size match)' THEN 'Design controls'
         WHEN 'subgroup: debt on both dates, within 3x' THEN 'Debt on both dates'
         WHEN 'horizon 3-6 months, within 3x' THEN '3-6 months'
         WHEN 'horizon 6-12 months, within 3x' THEN '6-12 months'
         WHEN 'horizon 12-18 months, within 3x' THEN '12-18 months'
         WHEN 'horizon 18-27 months, within 3x' THEN '18-27 months'
         ELSE view_name END AS short_label,
       FIELD(view_name, 'controls within 3x (primary)', 'controls within 10x', 'all held-out controls (no size match)',
             'within 3x, control companies only (no early quarters of later-failed)', 'vs design controls (frozen reference, no size match)',
             'subgroup: debt on both dates, within 3x', 'horizon 3-6 months, within 3x', 'horizon 6-12 months, within 3x',
             'horizon 12-18 months, within 3x', 'horizon 18-27 months, within 3x') AS view_order,
       lev, companies, obs, auc, pooled, above_half, ci95, ci95_year
FROM secondary_result;
