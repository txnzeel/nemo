-- Parameterized semantic query over dbt-owned facts. No duplicate history or attribution joins.
SELECT business_date, channel, campaign_id, device,
       impressions, clicks, spend_paise, 1 AS ad_rows,
       0 AS sessions, 0 AS purchasing_sessions, 0 AS orders, 0 AS revenue_paise,
       0 AS new_customers, 0 AS paid_orders, 0 AS paid_new_customers, 0 AS paid_revenue_paise
FROM analytics.fct_ad_performance
WHERE business_date >= cast($start as date) AND business_date < cast($end as date)
UNION ALL
SELECT business_date, channel, campaign_id, device,
       0, 0, 0, 0, 1,
       CASE WHEN first_paid_date < cast($end as date) THEN 1 ELSE 0 END,
       0, 0, 0, 0, 0, 0
FROM analytics.fct_sessions
WHERE business_date >= cast($start as date) AND business_date < cast($end as date)
UNION ALL
SELECT business_date, channel, campaign_id, device,
       0, 0, 0, 0, 0, 0, 1, amount_paise,
       CASE WHEN purchase_rank = 1 THEN 1 ELSE 0 END,
       CASE WHEN is_paid = 1 THEN 1 ELSE 0 END,
       CASE WHEN is_paid = 1 AND purchase_rank = 1 THEN 1 ELSE 0 END,
       CASE WHEN is_paid = 1 THEN amount_paise ELSE 0 END
FROM analytics.fct_orders
WHERE business_date >= cast($start as date) AND business_date < cast($end as date)
