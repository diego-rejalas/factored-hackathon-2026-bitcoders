{{ config(severity='warn') }}
-- KNOWN DATA QUIRK: ~7.5k credit products carry a balance above their limit.
select product_id, customer_id, product_type, current_balance, credit_limit
from {{ ref('stg_products') }}
where credit_limit is not null and current_balance > credit_limit
