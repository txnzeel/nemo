select o.order_id, o.session_id, o.customer_id, o.paid_at, o.business_date,
       o.amount_paise, o.purchase_rank, s.channel, s.campaign_id, s.device, s.is_paid
from {{ ref('int_order_history') }} o
join {{ ref('fct_sessions') }} s on o.session_id = s.session_id
