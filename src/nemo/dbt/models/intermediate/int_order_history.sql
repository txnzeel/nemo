-- Full history ranking: a late earlier order may change an existing buyer's first purchase.
select o.*, row_number() over (
    partition by customer_id order by paid_at, order_id
) as purchase_rank
from {{ ref('stg_orders') }} o
