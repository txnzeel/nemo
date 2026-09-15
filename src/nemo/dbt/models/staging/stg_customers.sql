select customer_id, first_seen_at, _batch_id, _loaded_at
from {{ source('canonical', 'customers') }}
