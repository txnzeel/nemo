select campaign_id, name, channel, is_paid, _batch_id, _loaded_at
from {{ source('canonical', 'campaigns') }}
