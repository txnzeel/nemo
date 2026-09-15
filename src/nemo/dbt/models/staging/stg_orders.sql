select order_id, session_id, customer_id, paid_at, cast(business_date as date) as business_date,
       amount_paise, _batch_id, _loaded_at
from {{ source('canonical', 'orders') }}
