select business_date, campaign_id, device
from {{ ref('fct_ad_performance') }}
group by business_date, campaign_id, device
having count(*) <> 1
