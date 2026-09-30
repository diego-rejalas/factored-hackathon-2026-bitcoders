-- Regression guard: transactions.customer_id always owns transactions.product_id
-- (100% today). The tool layer relies on this to authorize "my own movements".
select t.transaction_id, t.customer_id, t.product_id, p.customer_id as product_owner
from {{ ref('stg_transactions') }} t
join {{ ref('stg_products') }} p on p.product_id = t.product_id
where p.customer_id <> t.customer_id
