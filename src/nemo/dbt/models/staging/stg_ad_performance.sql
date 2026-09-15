select cast(business_date as date) as business_date, campaign_id, device,
       impressions, clicks, spend_paise, _batch_id, _loaded_at
from {{ source('canonical', 'ad_performance') }}
