USE retail_risk;
CREATE OR REPLACE VIEW v_input_coverage AS
SELECT q.ticker, c.grp, 'Revenue' AS input_name, 1 AS input_order, ROUND(AVG(q.Revenue IS NOT NULL), 2) AS share, ROUND(LEAST(AVG(q.Revenue IS NOT NULL), AVG(q.GrossProfit IS NOT NULL), AVG(q.Inventory IS NOT NULL), AVG(q.Debt IS NOT NULL)), 2) AS min_share, COUNT(*) AS quarters FROM clean_quarterly q LEFT JOIN companies c ON c.ticker = q.ticker GROUP BY q.ticker, c.grp
UNION ALL
SELECT q.ticker, c.grp, 'GrossProfit' AS input_name, 2 AS input_order, ROUND(AVG(q.GrossProfit IS NOT NULL), 2) AS share, ROUND(LEAST(AVG(q.Revenue IS NOT NULL), AVG(q.GrossProfit IS NOT NULL), AVG(q.Inventory IS NOT NULL), AVG(q.Debt IS NOT NULL)), 2) AS min_share, COUNT(*) AS quarters FROM clean_quarterly q LEFT JOIN companies c ON c.ticker = q.ticker GROUP BY q.ticker, c.grp
UNION ALL
SELECT q.ticker, c.grp, 'Inventory' AS input_name, 3 AS input_order, ROUND(AVG(q.Inventory IS NOT NULL), 2) AS share, ROUND(LEAST(AVG(q.Revenue IS NOT NULL), AVG(q.GrossProfit IS NOT NULL), AVG(q.Inventory IS NOT NULL), AVG(q.Debt IS NOT NULL)), 2) AS min_share, COUNT(*) AS quarters FROM clean_quarterly q LEFT JOIN companies c ON c.ticker = q.ticker GROUP BY q.ticker, c.grp
UNION ALL
SELECT q.ticker, c.grp, 'Debt' AS input_name, 4 AS input_order, ROUND(AVG(q.Debt IS NOT NULL), 2) AS share, ROUND(LEAST(AVG(q.Revenue IS NOT NULL), AVG(q.GrossProfit IS NOT NULL), AVG(q.Inventory IS NOT NULL), AVG(q.Debt IS NOT NULL)), 2) AS min_share, COUNT(*) AS quarters FROM clean_quarterly q LEFT JOIN companies c ON c.ticker = q.ticker GROUP BY q.ticker, c.grp;
