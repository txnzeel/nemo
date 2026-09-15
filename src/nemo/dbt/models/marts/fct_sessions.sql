select s.*, o.first_paid_date
from {{ ref('stg_sessions') }} s
left join (
    select session_id, min(business_date) as first_paid_date
    from {{ ref('stg_orders') }}
    group by session_id
) o on s.session_id = o.session_id
