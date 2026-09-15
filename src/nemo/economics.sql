-- One row per observed buyer. Aggregate refunds before joining to paid orders.
WITH refunds AS (
    SELECT order_id, sum(cast(amount_paise AS hugeint)) AS refund_paise
    FROM read_json($refunds, columns = {order_id: 'VARCHAR', amount_paise: 'HUGEINT'})
    GROUP BY order_id
), costs AS (
    SELECT order_id, variable_cost_paise
    FROM read_json($costs, columns = {order_id: 'VARCHAR', variable_cost_paise: 'HUGEINT'})
), paid AS (
    SELECT o.*,
           CASE WHEN $refunds_complete THEN coalesce(r.refund_paise, 0) END AS refund_paise,
           c.variable_cost_paise
    FROM analytics.fct_orders o
    LEFT JOIN refunds r USING (order_id)
    LEFT JOIN costs c USING (order_id)
), totals AS (
    SELECT customer_id, count(*) AS paid_orders,
           sum(cast(amount_paise AS hugeint)) AS gross_merchandise_paise,
           CASE WHEN $refunds_complete THEN sum(refund_paise) END AS refunds_paise,
           count(variable_cost_paise) AS cost_covered_orders,
           CASE WHEN count(variable_cost_paise) = count(*)
                THEN sum(variable_cost_paise) END AS variable_cost_paise
    FROM paid GROUP BY customer_id
)
SELECT t.*, first.business_date AS first_paid_date,
       cast(date_trunc('month', first.business_date) AS date) AS cohort_month,
       first.channel AS acquisition_channel, first.campaign_id AS acquisition_campaign_id,
       first.device AS acquisition_device, first.is_paid,
       gross_merchandise_paise - refunds_paise AS net_merchandise_paise,
       gross_merchandise_paise - refunds_paise - variable_cost_paise AS contribution_paise
FROM totals t
JOIN analytics.fct_orders first ON first.customer_id = t.customer_id AND first.purchase_rank = 1
