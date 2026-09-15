select 1 as mismatch
where
  (select count(*) from {{ ref('stg_orders') }}) <>
  (select count(*) from {{ ref('fct_orders') }})
or
  (select coalesce(sum(amount_paise),0) from {{ ref('stg_orders') }}) <>
  (select coalesce(sum(amount_paise),0) from {{ ref('fct_orders') }})
