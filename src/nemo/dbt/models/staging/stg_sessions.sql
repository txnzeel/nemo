select session_id, customer_id, started_at, cast(business_date as date) as business_date,
       channel, campaign_id, device, is_paid, _batch_id, _loaded_at
from {{ source('canonical', 'sessions') }}
