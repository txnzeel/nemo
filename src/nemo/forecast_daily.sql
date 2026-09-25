with days as (
    select cast(day as date) as business_date
    from generate_series(cast(? as date), cast(? as date) - interval '1 day', interval '1 day') t(day)
), sessions as (
    select cast(business_date as date) as business_date, count(*) as sessions
    from analytics.fct_sessions group by 1
), orders as (
    select cast(business_date as date) as business_date, count(*) as orders,
           sum(amount_paise) as revenue_paise
    from analytics.fct_orders group by 1
)
select d.business_date, coalesce(s.sessions, 0), coalesce(o.orders, 0),
       coalesce(o.revenue_paise, 0)
from days d
left join sessions s using(business_date)
left join orders o using(business_date)
order by d.business_date
