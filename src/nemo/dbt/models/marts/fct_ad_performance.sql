{{
    config(
        materialized='incremental',
        unique_key=['business_date', 'campaign_id', 'device'],
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}
select a.business_date, a.campaign_id, c.channel, a.device,
       a.impressions, a.clicks, a.spend_paise,
       greatest(a._batch_id, c._batch_id) as _batch_id,
       greatest(a._loaded_at, c._loaded_at) as _loaded_at
from {{ ref('stg_ad_performance') }} a
join {{ ref('dim_campaign') }} c on c.campaign_id = a.campaign_id
{% if is_incremental() %}
where greatest(a._batch_id, c._batch_id) >
      (select coalesce(max(_batch_id), 0) from {{ this }})
{% endif %}
