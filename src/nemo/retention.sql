-- Completed-calendar-month purchase activity, distinct buyers/original cohort size.
WITH first_orders AS (
    SELECT customer_id, cast(date_trunc('month', business_date) AS date) AS cohort_month
    FROM analytics.fct_orders WHERE purchase_rank = 1
), cohorts AS (
    SELECT cohort_month, count(*) AS buyers FROM first_orders GROUP BY cohort_month
), activity AS (
    SELECT f.cohort_month, cast(date_trunc('month', o.business_date) AS date) AS activity_month,
           count(DISTINCT o.customer_id) AS active_buyers
    FROM analytics.fct_orders o JOIN first_orders f USING(customer_id)
    GROUP BY f.cohort_month, activity_month
), grid AS (
    SELECT c.*, age.range AS age_months,
           cast(c.cohort_month + age.range * interval '1 month' AS date) AS activity_month
    FROM cohorts c CROSS JOIN range($max_age + 1) age
)
SELECT g.*, coalesce(a.active_buyers, 0) AS observed_active_buyers,
       CASE WHEN g.activity_month >= cast($cutoff AS date) THEN 'not_yet_observed'
            WHEN g.activity_month + interval '1 month' > cast($cutoff AS date)
                 THEN 'partial_month' ELSE 'complete' END AS observation_status
FROM grid g LEFT JOIN activity a USING(cohort_month, activity_month)
ORDER BY cohort_month, age_months
