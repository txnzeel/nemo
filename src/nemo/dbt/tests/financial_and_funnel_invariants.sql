select order_id as invalid_id from {{ ref('fct_orders') }} where amount_paise <= 0
union all
select session_id from {{ ref('fct_sessions') }}
where first_paid_date < business_date
union all
select campaign_id from {{ ref('fct_ad_performance') }}
where impressions < 0 or clicks < 0 or spend_paise < 0
