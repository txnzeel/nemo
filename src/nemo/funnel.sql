-- Session-cohort payment evidence; one attempt and one terminal outcome contract only.
WITH event_stages AS (
    SELECT session_id,
           count(*) FILTER (WHERE name = 'payment_attempted') AS attempts,
           count(*) FILTER (WHERE name = 'payment_succeeded') AS successes,
           count(*) FILTER (WHERE name = 'payment_failed') AS failures,
           min(cast(occurred_at AS timestamptz)) FILTER
               (WHERE name = 'payment_attempted') AS attempted_at,
           max(cast(occurred_at AS timestamptz)) FILTER
               (WHERE name IN ('payment_succeeded', 'payment_failed')) AS terminal_at
    FROM read_json($events, columns = {
        event_id: 'VARCHAR', name: 'VARCHAR', session_id: 'VARCHAR',
        order_id: 'VARCHAR', occurred_at: 'VARCHAR'})
    GROUP BY session_id
), paid AS (
    SELECT session_id, count(*) AS orders
    FROM analytics.fct_orders
    GROUP BY session_id
), session_stages AS (
    SELECT s.device,
           CASE WHEN s.business_date < cast($current_start AS date)
                THEN 'baseline' ELSE 'current' END AS period,
           coalesce(e.attempts, 0) AS attempts,
           coalesce(e.successes, 0) AS successes,
           coalesce(e.failures, 0) AS failures,
           coalesce(p.orders, 0) AS orders,
           e.attempted_at, e.terminal_at, s.started_at
    FROM analytics.fct_sessions s
    LEFT JOIN event_stages e USING (session_id)
    LEFT JOIN paid p USING (session_id)
    WHERE s.business_date >= cast($baseline_start AS date)
      AND s.business_date < cast($end AS date)
)
SELECT device, period, count(*) AS sessions,
       count(*) FILTER (WHERE attempts > 0) AS attempting_sessions,
       count(*) FILTER (WHERE successes > 0) AS successful_sessions,
       count(*) FILTER (WHERE
           attempts > 1 OR successes + failures > 1
           OR ((attempts + successes + failures > 0) AND
               (attempts <> 1 OR successes + failures <> 1))
           OR successes <> CASE WHEN orders > 0 THEN 1 ELSE 0 END
           OR orders > 1
           OR terminal_at < attempted_at
           OR attempted_at < cast(started_at AS timestamptz)
       ) AS invalid_sessions
FROM session_stages
GROUP BY device, period
ORDER BY device, period
